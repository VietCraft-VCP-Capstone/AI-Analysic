"""
Cào giá tham khảo từ Etsy cho F42 (gợi ý giá) — chạy chung lịch với Tiki (6:00 và 18:00 giờ VN).

Nguồn: Etsy Open API v3, endpoint tìm kiếm công khai `/v3/application/listings/active`
(chỉ cần API key qua header `x-api-key`, không cần OAuth — theo tài liệu Etsy, endpoint
này dùng được mà không cần người dùng đăng nhập).

Giá Etsy là USD (hoặc tiền tệ khác tuỳ shop) — bài toán seller VietCraft cần là VND, nên
quy đổi sang VND trước khi lưu. Tỷ giá lấy từ API tỷ giá miễn phí (không cần key), cache
trong RAM vài giờ; nếu API tỷ giá lỗi thì dùng tỷ giá dự phòng cố định (không chính xác
bằng nhưng còn hơn không có giá).

Etsy là chợ tiếng Anh: từ khóa tiếng Việt được dịch sang cụm tìm tiếng Anh (LLM dùng chung, cache vào
Mongo) trước khi gọi Etsy. Tiêu đề gốc (tiếng Anh) để hiển thị, từ khóa tiếng Việt (`match_title`) để khớp
với câu seller gõ. Tin không phải hàng vật lý, hết hàng, ít lượt yêu thích, hoặc có dấu hiệu lệch loại
(file tải về, vintage, bán sỉ...) bị loại ngay lúc cào.

shortcut: chỉ quy đổi listing có currency_code="USD" (đa số); listing tiền tệ khác bị bỏ
qua vì cần bảng tỷ giá đầy đủ hơn — khi nào cần mở rộng thì thêm vào RATE cho đồng đó.
"""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import requests

from app.config import settings
from app.services import llm
from app.services.f42 import config
from app.services.f42.market_crawler import (
    build_keywords,
    query_key,
    save_listings,
    seed_keywords,
    seller_queries,
)
from app.services.f42.vi_text import normalize_nfc

logger = logging.getLogger(__name__)

ETSY_SEARCH_URL = "https://openapi.etsy.com/v3/application/listings/active"
RUN_COLLECTION = "collector_run"
TRANSLATION_COLLECTION = "f42_keyword_en"
TRANSLATE_BATCH = 40
# Tin lệch loại so với sản phẩm vật lý bán lẻ: file tải về, đồ cổ, bán sỉ/theo lô, nguyên liệu
_NOISE = re.compile(
    r"\b(digital|printable|download|svg|pdf|template|instant|vintage|antique|supplies|supply|wholesale|bulk|lot of|pattern only)\b",
    re.I,
)

PRICE_MIN_USD, PRICE_MAX_USD = 0.5, 10_000  # lọc giá USD vô lý trước khi quy đổi
PER_KEYWORD = 25
MAX_REQUESTS = 80
REQUEST_DELAY_S = 1.5
TIMEOUT_S = 10
FALLBACK_USD_VND = 25_400  # dùng khi không gọi được API tỷ giá
RATE_CACHE_TTL_S = 6 * 3600

_rate_cache: Dict[str, Any] = {"value": None, "at": 0.0}


def get_usd_to_vnd_rate(fetch=requests.get, now=time.time) -> float:
    """Tỷ giá USD->VND, cache vài giờ; lỗi mạng thì dùng tỷ giá dự phòng cố định."""
    cached, fetched_at = _rate_cache["value"], _rate_cache["at"]
    if cached and now() - fetched_at < RATE_CACHE_TTL_S:
        return cached
    try:
        res = fetch("https://open.er-api.com/v6/latest/USD", timeout=5)
        res.raise_for_status()
        rate = float(res.json()["rates"]["VND"])
        _rate_cache["value"], _rate_cache["at"] = rate, now()
        return rate
    except Exception as exc:  # noqa: BLE001 — API tỷ giá lỗi không được chặn cả lượt cào
        logger.warning("f42.etsy_crawler.rate_fetch_failed", extra={"error": str(exc)})
        return cached or FALLBACK_USD_VND


def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_etsy_item(raw: Dict[str, Any], keyword: str, usd_vnd_rate: float, fetched_at: datetime,
                    match_title: str = "") -> Optional[Dict[str, Any]]:
    """Chuẩn hoá 1 tin Etsy, quy đổi giá sang VND. Trả None nếu không dùng được hoặc lệch loại."""
    if not isinstance(raw, dict):
        return None
    if raw.get("state") not in (None, "active") or raw.get("listing_type") not in (None, "physical"):
        return None
    if raw.get("quantity") is not None and int(raw.get("quantity") or 0) <= 0:
        return None
    lid = raw.get("listing_id")
    title = normalize_nfc(str(raw.get("title") or "")).strip()
    if _NOISE.search(title):
        return None
    price_obj = raw.get("price") or {}
    divisor = price_obj.get("divisor") or 100
    amount = price_obj.get("amount")
    currency = price_obj.get("currency_code")
    if not lid or len(title) < 3 or amount is None or currency != "USD":
        return None
    price_usd = float(amount) / float(divisor or 100)
    if not (PRICE_MIN_USD <= price_usd <= PRICE_MAX_USD):
        return None
    price_vnd = round(price_usd * usd_vnd_rate)

    # Etsy không công khai số lượt bán qua API tìm kiếm; lượt yêu thích (đủ ETSY_MIN_FAVORERS) là tín hiệu
    # "đã được thị trường chú ý" thay cho sold/review bên Tiki.
    favorers = int(raw.get("num_favorers") or 0)
    return {
        "_id": f"etsy_{lid}",
        "source": "etsy",
        "external_id": lid,
        "title": title,
        "price": price_vnd,
        "list_price": price_vnd,
        "price_usd": round(price_usd, 2),
        "usd_vnd_rate": usd_vnd_rate,
        "sold": 0,
        "review_count": favorers,
        "rating": 0.0,
        "url": raw.get("url"),
        "keyword": keyword,
        "match_title": match_title or keyword,
        "is_valid": favorers >= config.ETSY_MIN_FAVORERS,
        "fetched_at": fetched_at,
    }


def fetch_etsy(query_en: str, session: Optional[requests.Session] = None, match_title: str = "",
               limit: int = PER_KEYWORD) -> List[Dict[str, Any]]:
    """Một trang kết quả tìm kiếm Etsy cho cụm tìm tiếng Anh `query_en`; `match_title` là từ khóa tiếng Việt gốc.
    Lỗi mạng/HTTP thì ném ra cho lượt cào ghi nhận."""
    http = session or requests
    res = http.get(
        ETSY_SEARCH_URL,
        params={"keywords": keyword, "limit": limit},
        headers={"x-api-key": settings.etsy_x_api_key, "Accept": "application/json"},
        timeout=TIMEOUT_S,
    )
    res.raise_for_status()
    results = res.json().get("results") or []
    now, rate = _now(), get_usd_to_vnd_rate()
    return [it for it in (parse_etsy_item(r, query_en, rate, now, match_title) for r in results) if it]


def _translate_with_llm(keywords: List[str]) -> Dict[str, str]:
    """Dịch từ khóa sản phẩm tiếng Việt sang cụm tìm Etsy tiếng Anh (1 lượt LLM cho cả lô)."""
    prompt = (
        "Dịch các từ khóa sản phẩm thủ công/đời sống tiếng Việt sau sang cụm từ tìm kiếm tiếng Anh ngắn (2-5 từ) "
        "đúng như người mua gõ trên Etsy. Giữ đúng loại sản phẩm, không thêm thương hiệu hay tính từ quảng cáo. "
        'Trả JSON: {"items": [{"vi": "...", "en": "..."}]}\n'
        + "\n".join(f"- {k}" for k in keywords)
    )
    data = llm.generate_json([{"text": prompt}], timeout_s=25, temperature=0.1, max_output_tokens=2048,
                             accept=lambda d: isinstance(d.get("items"), list))
    out: Dict[str, str] = {}
    for it in (data or {}).get("items", []):
        vi, en = str((it or {}).get("vi") or "").strip(), str((it or {}).get("en") or "").strip().lower()
        if vi and re.fullmatch(r"[a-z0-9][a-z0-9 '\-]{1,58}", en):
            out[vi] = en
    return out


def english_queries(db_data: Any, keywords: List[str],
                    translate: Callable[[List[str]], Dict[str, str]] = _translate_with_llm) -> Dict[str, str]:
    """{từ khóa VN: cụm tìm Etsy tiếng Anh}. Bản dịch cache trong Mongo; từ khóa không dịch được thì BỎ
    (không bao giờ gửi tiếng Việt cho Etsy: kết quả sẽ lạc loại)."""
    cache = db_data[TRANSLATION_COLLECTION]
    out: Dict[str, str] = {}
    missing: List[str] = []
    for kw in keywords:
        doc = cache.find_one({"_id": query_key(kw)}, {"en": 1})
        if doc and doc.get("en"):
            out[kw] = doc["en"]
        else:
            missing.append(kw)
    for i in range(0, len(missing), TRANSLATE_BATCH):
        batch = missing[i:i + TRANSLATE_BATCH]
        try:
            got = translate(batch)
        except Exception as exc:  # noqa: BLE001 — dịch lỗi thì thôi lượt này, từ khóa đó cào lượt sau
            logger.warning("f42.etsy_crawler.translate_failed: %s: %s", type(exc).__name__, exc)
            continue
        for kw in batch:
            en = got.get(kw)
            if en:
                out[kw] = en
                cache.update_one({"_id": query_key(kw)}, {"$set": {"vi": kw, "en": en, "at": _now()}}, upsert=True)
    return out


def run_crawl_etsy(
    db_data: Any,
    max_requests: int = MAX_REQUESTS,
    delay_s: float = REQUEST_DELAY_S,
    fetch=fetch_etsy,
    sleep=time.sleep,
) -> Dict[str, Any]:
    """Một lượt cào Etsy: lấy từ khóa (dùng chung với Tiki) → gọi Etsy từng từ → lưu. Trả tóm tắt lượt chạy."""
    started = _now()
    if not settings.ETSY_API_KEY:
        summary = {"job": "f42_etsy_crawl", "started_at": started, "finished_at": _now(),
                   "keywords": 0, "items": 0, "valid_items": 0, "saved": 0,
                   "errors": ["ETSY_API_KEY chưa cấu hình"], "status": "skipped"}
        return summary

    keywords = build_keywords(seed_keywords(), seller_queries(db_data))[:max_requests]
    queries = english_queries(db_data, keywords)
    session = requests.Session()
    n_items = n_valid = n_saved = 0
    errors: List[str] = []
    for i, kw in enumerate(k for k in keywords if k in queries):
        if i:
            sleep(delay_s)
        try:
            items = fetch(queries[kw], session, kw)
        except Exception as exc:  # noqa: BLE001 — một từ khóa lỗi không dừng cả lượt
            errors.append(f"{kw}: {type(exc).__name__}")
            continue
        n_items += len(items)
        n_valid += sum(1 for it in items if it["is_valid"])
        n_saved += save_listings(db_data, items)

    summary = {
        "job": "f42_etsy_crawl",
        "started_at": started,
        "finished_at": _now(),
        "keywords": len(queries),
        "untranslated": len(keywords) - len(queries),
        "items": n_items,
        "valid_items": n_valid,
        "saved": n_saved,
        "errors": errors[:20],
        "status": "ok" if not errors else ("partial" if len(errors) < max(1, len(queries)) else "failed"),
    }
    try:
        db_data[RUN_COLLECTION].insert_one(dict(summary))
    except Exception:  # noqa: BLE001
        pass
    return summary


def _main() -> None:
    import argparse

    from pymongo import MongoClient

    ap = argparse.ArgumentParser(description="Cào giá Etsy cho F42 (một lượt).")
    ap.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    args = ap.parse_args()
    db = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=20000)[settings.MONGO_DB_DATA]
    s = run_crawl_etsy(db, max_requests=args.max_requests)
    print(f"{s['status']}: {s['keywords']} từ khóa, {s['items']} tin ({s['valid_items']} hợp lệ), "
          f"lưu {s['saved']}, lỗi {len(s['errors'])}")


if __name__ == "__main__":
    _main()
