"""
Cào giá thị trường thật cho F42 (gợi ý giá) — chạy 2 lần/ngày (6:00 và 18:00 giờ VN).

Nguồn: API tìm kiếm công khai của Tiki (`/api/v2/products`, robots.txt không cấm, không cần
đăng nhập). Không cào Shopee/Lazada vì phải vượt cơ chế chống bot.
Google Trends KHÔNG có giá — dùng ở trend_signal.py để biết nhu cầu đang lên hay xuống.

Dữ liệu "hợp lệ" để làm căn cứ giá:
  - giá trong khoảng PRICE_MIN..PRICE_MAX, tên sản phẩm có nghĩa, đang còn bán;
  - đã có người mua hoặc đánh giá (sold >= 1 hoặc review >= 1): giá đó đã được thị trường
    chấp nhận, không phải giá treo cho có. Tin chưa ai mua vẫn lưu nhưng is_valid=False.

Từ khóa cào: danh sách seed + tiêu đề seller đã nhập ở F42 (f42_query_log), để lấp những
ngành hàng thủ công mà dữ liệu Tiki cũ thiếu (nến, gốm, tranh thêu...).
"""

import argparse
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

from app.services.f42.vi_text import clean_tokens, normalize_nfc, strip_accents

logger = logging.getLogger(__name__)

TIKI_SEARCH_URL = "https://tiki.vn/api/v2/products"
LISTING_COLLECTION = "market_price_listing"
QUERY_LOG_COLLECTION = "f42_query_log"
RUN_COLLECTION = "collector_run"
SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "seed_keywords.do-not-remove.json"

PRICE_MIN, PRICE_MAX = 1_000, 200_000_000
PER_KEYWORD = 40            # số tin lấy mỗi từ khóa (1 trang)
MAX_REQUESTS = 120          # trần số request mỗi lượt, tránh gây tải cho Tiki
REQUEST_DELAY_S = 1.5       # nghỉ giữa 2 request
TIMEOUT_S = 10
QUERY_LOG_DAYS = 14         # chỉ lấy tiêu đề seller nhập trong 14 ngày gần nhất
QUERY_LOG_TOP = 60
QUERY_HEAD_WORDS = 5        # cắt tiêu đề dài: tìm kiếm Tiki khớp tốt nhất với vài từ đầu
HISTORY_KEEP = 60           # giữ 60 lần giá gần nhất (~1 tháng với 2 lần/ngày)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VietCraftPriceBot/1.0)", "Accept": "application/json"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _int(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def query_key(text: str) -> str:
    """Khóa so trùng từ khóa: bỏ dấu, thường hoá, tối đa QUERY_HEAD_WORDS từ đầu."""
    return " ".join(strip_accents(t) for t in clean_tokens(text)[:QUERY_HEAD_WORDS])


def parse_tiki_item(raw: Dict[str, Any], keyword: str, fetched_at: datetime) -> Optional[Dict[str, Any]]:
    """Chuẩn hoá 1 tin Tiki. Trả None nếu dữ liệu không dùng được (giá/tên sai, ngừng bán)."""
    if not isinstance(raw, dict):
        return None
    pid = _int(raw.get("id"))
    name = normalize_nfc(str(raw.get("name") or "")).strip()
    price = _int(raw.get("price"))
    if not pid or len(name) < 3 or not (PRICE_MIN <= price <= PRICE_MAX):
        return None
    if str(raw.get("inventory_status") or "available") not in ("available", ""):
        return None

    sold = _int((raw.get("quantity_sold") or {}).get("value") if isinstance(raw.get("quantity_sold"), dict) else 0)
    reviews = _int(raw.get("review_count"))
    list_price = _int(raw.get("original_price")) or _int(raw.get("list_price")) or price
    return {
        "_id": f"tiki_{pid}",
        "source": "tiki",
        "external_id": pid,
        "title": name,
        "price": price,
        "list_price": max(list_price, price),
        "sold": sold,
        "review_count": reviews,
        "rating": float(raw.get("rating_average") or 0),
        "url": f"https://tiki.vn/{raw.get('url_path')}" if raw.get("url_path") else None,
        "keyword": keyword,
        "is_valid": sold >= 1 or reviews >= 1,
        "fetched_at": fetched_at,
    }


def fetch_tiki(keyword: str, session: Optional[requests.Session] = None, limit: int = PER_KEYWORD) -> List[Dict[str, Any]]:
    """Một trang kết quả tìm kiếm Tiki cho `keyword`. Lỗi mạng/HTTP thì ném ra cho lượt cào ghi nhận."""
    http = session or requests
    res = http.get(TIKI_SEARCH_URL, params={"q": keyword, "limit": limit, "page": 1},
                   headers=HEADERS, timeout=TIMEOUT_S)
    res.raise_for_status()
    data = res.json().get("data") or []
    now = _now()
    return [it for it in (parse_tiki_item(r, keyword, now) for r in data) if it]


def seed_keywords() -> List[str]:
    try:
        rows = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        return [r["keyword"] for r in rows if r.get("keyword")]
    except Exception as exc:  # noqa: BLE001
        logger.warning("f42.crawler.seed_load_failed", extra={"error": str(exc)})
        return []


def seller_queries(db_data: Any, days: int = QUERY_LOG_DAYS, top: int = QUERY_LOG_TOP) -> List[str]:
    """Tiêu đề seller hay nhập gần đây (đã cắt gọn), nhiều lượt trước."""
    if db_data is None:
        return []
    since = _now() - timedelta(days=days)
    try:
        cur = db_data[QUERY_LOG_COLLECTION].find({"last_seen": {"$gte": since}}, {"query": 1}) \
            .sort("count", -1).limit(top)
        return [d["query"] for d in cur if d.get("query")]
    except Exception as exc:  # noqa: BLE001
        logger.warning("f42.crawler.query_log_failed", extra={"error": str(exc)})
        return []


def build_keywords(seeds: Iterable[str], queries: Iterable[str]) -> List[str]:
    """Seed trước, rồi tiêu đề seller; bỏ trùng theo khóa không dấu."""
    out: List[str] = []
    seen = set()
    for text in list(seeds) + list(queries):
        head = " ".join(clean_tokens(text)[:QUERY_HEAD_WORDS])
        key = query_key(head)
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        out.append(head)
    return out


def record_seller_query(db_data: Any, title: str) -> None:
    """F42 gọi mỗi lần seller xin gợi ý: chỉ lưu tiêu đề đã cắt gọn, không lưu shop/người dùng."""
    if db_data is None or not title or not title.strip():
        return
    head = " ".join(clean_tokens(title)[:QUERY_HEAD_WORDS])
    key = query_key(head)
    if len(key) < 2:
        return
    try:
        db_data[QUERY_LOG_COLLECTION].update_one(
            {"_id": key},
            {"$set": {"query": head, "last_seen": _now()}, "$inc": {"count": 1}},
            upsert=True,
        )
    except Exception as exc:  # noqa: BLE001 — ghi log thất bại không được làm hỏng gợi ý
        logger.warning("f42.crawler.record_query_failed", extra={"error": str(exc)})


ON_DEMAND_COOLDOWN_H = 12
ON_DEMAND_TIMEOUT_S = 6


def fetch_on_demand(db_data: Any, title: str, fetch=None) -> bool:
    """
    Seller xin gợi ý cho loại hàng CHƯA có dữ liệu (vd "ốp lưng điện thoại"): cào Tiki ngay 1 request
    thay vì bắt chờ lượt 6h/18h. Mỗi tiêu đề tối đa 1 lần / ON_DEMAND_COOLDOWN_H giờ.
    Trả True nếu vừa lưu được ít nhất 1 tin hợp lệ.
    """
    if db_data is None or not title or not title.strip():
        return False
    head = " ".join(clean_tokens(title)[:QUERY_HEAD_WORDS])
    key = query_key(head)
    if len(key) < 2:
        return False
    try:
        log = db_data[QUERY_LOG_COLLECTION]
        doc = log.find_one({"_id": key}, {"last_crawled": 1}) or {}
        last = doc.get("last_crawled")
        if last is not None:
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if _now() - last < timedelta(hours=ON_DEMAND_COOLDOWN_H):
                return False
        log.update_one({"_id": key}, {"$set": {"query": head, "last_crawled": _now()}}, upsert=True)
        items = (fetch or fetch_tiki_quick)(head)
        save_listings(db_data, items)
        return any(it["is_valid"] for it in items)
    except Exception as exc:  # noqa: BLE001 — Tiki chậm/lỗi thì vẫn trả gợi ý "chưa đủ dữ liệu"
        logger.warning("f42.crawler.on_demand_failed", extra={"error": str(exc)})
        return False


def fetch_tiki_quick(keyword: str) -> List[Dict[str, Any]]:
    """Như fetch_tiki nhưng timeout ngắn: đang có seller chờ phản hồi."""
    res = requests.get(TIKI_SEARCH_URL, params={"q": keyword, "limit": PER_KEYWORD, "page": 1},
                       headers=HEADERS, timeout=ON_DEMAND_TIMEOUT_S)
    res.raise_for_status()
    now = _now()
    return [it for it in (parse_tiki_item(r, keyword, now) for r in (res.json().get("data") or [])) if it]


def save_listings(db_data: Any, items: List[Dict[str, Any]]) -> int:
    """Upsert theo id Tiki; giữ lịch sử giá để thấy giá lên/xuống theo thời gian."""
    from pymongo import UpdateOne

    if not items:
        return 0
    ops = []
    for it in items:
        doc = {k: v for k, v in it.items() if k not in ("_id", "keyword")}
        ops.append(UpdateOne(
            {"_id": it["_id"]},
            {
                "$set": {**doc, "last_seen_at": it["fetched_at"]},
                "$setOnInsert": {"first_seen_at": it["fetched_at"]},
                "$addToSet": {"keywords": it["keyword"]},
                "$push": {"price_history": {"$each": [{"price": it["price"], "at": it["fetched_at"]}],
                                            "$slice": -HISTORY_KEEP}},
            },
            upsert=True,
        ))
    res = db_data[LISTING_COLLECTION].bulk_write(ops, ordered=False)
    return res.upserted_count + res.modified_count


def ensure_indexes(db_data: Any) -> None:
    db_data[LISTING_COLLECTION].create_index([("last_seen_at", -1)], name="by_last_seen")
    db_data[LISTING_COLLECTION].create_index([("is_valid", 1), ("last_seen_at", -1)], name="valid_recent")
    db_data[QUERY_LOG_COLLECTION].create_index([("last_seen", -1), ("count", -1)], name="recent_popular")


def run_crawl(
    db_data: Any,
    max_requests: int = MAX_REQUESTS,
    delay_s: float = REQUEST_DELAY_S,
    fetch=fetch_tiki,
    sleep=time.sleep,
) -> Dict[str, Any]:
    """Một lượt cào: lấy từ khóa → gọi Tiki từng từ (có nghỉ) → lưu. Trả tóm tắt lượt chạy."""
    started = _now()
    keywords = build_keywords(seed_keywords(), seller_queries(db_data))[:max_requests]
    ensure_indexes(db_data)
    session = requests.Session()
    n_items = n_valid = n_saved = 0
    errors: List[str] = []
    for i, kw in enumerate(keywords):
        if i:
            sleep(delay_s)
        try:
            items = fetch(kw, session)
        except Exception as exc:  # noqa: BLE001 — một từ khóa lỗi không dừng cả lượt
            errors.append(f"{kw}: {type(exc).__name__}")
            continue
        n_items += len(items)
        n_valid += sum(1 for it in items if it["is_valid"])
        n_saved += save_listings(db_data, items)

    summary = {
        "job": "f42_market_crawl",
        "started_at": started,
        "finished_at": _now(),
        "keywords": len(keywords),
        "items": n_items,
        "valid_items": n_valid,
        "saved": n_saved,
        "errors": errors[:20],
        "status": "ok" if not errors else ("partial" if len(errors) < len(keywords) else "failed"),
    }
    try:
        db_data[RUN_COLLECTION].insert_one(dict(summary))
    except Exception:  # noqa: BLE001
        pass
    return summary


def _main() -> None:
    from pymongo import MongoClient
    from app.config import settings

    ap = argparse.ArgumentParser(description="Cào giá Tiki cho F42 (một lượt).")
    ap.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    args = ap.parse_args()
    db = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=20000)[settings.MONGO_DB_DATA]
    s = run_crawl(db, max_requests=args.max_requests)
    print(f"{s['status']}: {s['keywords']} từ khóa, {s['items']} tin ({s['valid_items']} hợp lệ), "
          f"lưu {s['saved']}, lỗi {len(s['errors'])}")


if __name__ == "__main__":
    _main()
