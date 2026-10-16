import csv
import io
import json
import os
import sys
from collections import Counter
from datetime import date, datetime
from typing import Any, Dict, List

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from app.core.backtest import rolling_origin                      # noqa: E402
from app.core.calendar_vn import TET_DATES, days_to_tet           # noqa: E402
from app.core.metrics import mase                                 # noqa: E402
from app.models.seasonal_forecast import (                        # noqa: E402
    BUCKET_DAYS, estimate_tet_effect, seasonal_naive,
    stl_no_tet_forecast, tet_aware_forecast,
)

WORKSPACE = os.path.dirname(ROOT)
TRENDS = os.path.join(ROOT, "app/collectors/data/trends_weekly.json")
DATA_DIR = os.path.join(ROOT, "app/data")
LISTINGS = os.path.join(WORKSPACE, "SE16-AI/data/Le_Hat_Task_AI/listings.csv")
OUT_DOCS = os.path.join(ROOT, "docs/RESULTS.json")
OUT_MVP = os.path.join(WORKSPACE, "pricing-mvp/data")

PERIOD = 52
HORIZON = 12
N_ORIGINS = 8
STEP = 6
RECENT_WEEKS = 12


def read_csv(path: str) -> List[Dict[str, str]]:
    with io.open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def pct_rank(values: List[float]) -> List[float]:
    """Xếp hạng phân vị 0-100. Dùng thay tỉ số Demand/Supply vì tỉ số nổ tung khi cung -> 0."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    for position, idx in enumerate(order):
        ranks[idx] = 100.0 * position / max(len(values) - 1, 1)
    return ranks


# --------------------------------------------------------------------------- #
# 1. Backtest — bằng chứng khoa học
# --------------------------------------------------------------------------- #

def run_backtests(series: Dict[str, Any]) -> Dict[str, Any]:
    models = {
        "seasonal_naive": lambda td, tv, fd: seasonal_naive(tv, len(fd), PERIOD),
        "stl_no_tet": lambda td, tv, fd: stl_no_tet_forecast(td, tv, fd, PERIOD)["predictions"],
        "tet_aware_stl": lambda td, tv, fd: tet_aware_forecast(td, tv, fd, PERIOD)["predictions"],
    }
    per_keyword: Dict[str, Any] = {}
    total = len(series)

    for n, (kw, entry) in enumerate(sorted(series.items()), start=1):
        if entry.get("is_anchor"):
            continue
        points = entry["points"]
        dates = [p["date"] for p in points]
        values = [float(p["scaled"]) for p in points]

        # Chuỗi gần như phẳng thì mọi mô hình đều vô nghĩa; loại và nói rõ lý do.
        if float(np.max(values)) < 5.0:
            per_keyword[kw] = {"status": "excluded_flat_series",
                               "reason": f"Đỉnh chỉ {max(values):.1f}; tín hiệu quá yếu để dự báo.",
                               "max_value": round(float(np.max(values)), 2)}
            print(f"  [{n}/{total}] {kw}: loại (chuỗi phẳng)")
            continue

        scores = {}
        for name, fn in models.items():
            scores[name] = rolling_origin(dates, values, fn, horizon=HORIZON,
                                          n_origins=N_ORIGINS, step=STEP, period=PERIOD)

        valid = {k: v["mase"]["mean"] for k, v in scores.items()
                 if v.get("status") == "ok" and v.get("mase")}
        best = min(valid, key=valid.get) if valid else None
        per_keyword[kw] = {
            "status": "ok" if best else "no_valid_origin",
            "product_type": entry.get("product_type"),
            "topic": entry.get("topic"),
            "best_model": best,
            "models": {k: {"mase": v.get("mase"), "rmsse": v.get("rmsse"),
                           "n_origins": v.get("n_origins"), "status": v.get("status")}
                       for k, v in scores.items()},
        }
        if best:
            print(f"  [{n}/{total}] {kw}: tốt nhất {best} MASE {valid[best]:.3f} "
                  f"(naive {valid.get('seasonal_naive', float('nan')):.3f})")
    return per_keyword


def summarise(per_keyword: Dict[str, Any]) -> Dict[str, Any]:
    ok = {k: v for k, v in per_keyword.items() if v.get("status") == "ok"}
    out: Dict[str, Any] = {"keywords_evaluated": len(ok),
                           "keywords_excluded": len(per_keyword) - len(ok)}
    for model in ("seasonal_naive", "stl_no_tet", "tet_aware_stl"):
        vals = [v["models"][model]["mase"]["mean"] for v in ok.values()
                if v["models"].get(model, {}).get("mase")]
        if vals:
            out[model] = {
                "mase_mean": round(float(np.mean(vals)), 4),
                "mase_median": round(float(np.median(vals)), 4),
                "beat_naive_count": None,
                "n": len(vals),
            }
    naive = {k: v["models"]["seasonal_naive"]["mase"]["mean"] for k, v in ok.items()
             if v["models"]["seasonal_naive"].get("mase")}
    for model in ("stl_no_tet", "tet_aware_stl"):
        wins = sum(1 for k, base in naive.items()
                   if ok[k]["models"][model].get("mase")
                   and ok[k]["models"][model]["mase"]["mean"] < base)
        if model in out:
            out[model]["beat_naive_count"] = wins
            out[model]["beat_naive_pct"] = round(100.0 * wins / max(len(naive), 1), 1)
    out["best_model_counts"] = dict(Counter(v["best_model"] for v in ok.values()))
    return out


# --------------------------------------------------------------------------- #
# 2. Dự báo + đếm ngược đỉnh mùa
# --------------------------------------------------------------------------- #

def next_peak(kw_dates: List[str], values: List[float], today: date) -> Dict[str, Any]:
    """Xác định đỉnh mùa kế tiếp, phân biệt đỉnh do Tết (âm lịch) và đỉnh dương lịch."""
    effect = estimate_tet_effect(kw_dates, values, PERIOD)
    tet_amp = 0.0
    peak_bucket = None
    if effect:
        eff = {b: e["effect"] for b, e in effect.items()}
        peak_bucket = max(eff, key=eff.get)
        tet_amp = float(max(eff.values()) - min(eff.values()))

    # Biên độ mùa vụ dương lịch: trung vị giá trị theo tuần-trong-năm.
    by_week: Dict[int, List[float]] = {}
    for d, v in zip(kw_dates, values):
        by_week.setdefault(pd.Timestamp(d).isocalendar().week, []).append(v)
    week_median = {w: float(np.median(vs)) for w, vs in by_week.items() if len(vs) >= 2}
    solar_amp = float(max(week_median.values()) - min(week_median.values())) if week_median else 0.0

    if tet_amp >= solar_amp and peak_bucket is not None:
        offset = peak_bucket * BUCKET_DAYS + BUCKET_DAYS // 2
        for year in sorted(TET_DATES):
            peak = pd.Timestamp(TET_DATES[year]) + pd.Timedelta(days=offset)
            if peak.date() > today:
                return {"driver": "tet_lunar", "peak_date": str(peak.date()),
                        "days_from_today": (peak.date() - today).days,
                        "offset_days_from_tet": offset,
                        "tet_date": TET_DATES[year],
                        "amplitude": round(tet_amp, 1),
                        "seasons_observed": effect[peak_bucket]["n"]}
    if week_median:
        peak_week = max(week_median, key=week_median.get)
        for year in (today.year, today.year + 1):
            try:
                peak = date.fromisocalendar(year, int(peak_week), 7)
            except ValueError:
                continue
            if peak > today:
                return {"driver": "solar_calendar", "peak_date": str(peak),
                        "days_from_today": (peak - today).days,
                        "iso_week": int(peak_week),
                        "amplitude": round(solar_amp, 1),
                        "seasons_observed": len(by_week.get(peak_week, []))}
    return {"driver": "unknown", "peak_date": None, "days_from_today": None}


def build_forecasts(series: Dict[str, Any], backtest: Dict[str, Any],
                    today: date) -> Dict[str, Any]:
    items = []
    for kw, entry in sorted(series.items()):
        bt = backtest.get(kw)
        if entry.get("is_anchor") or not bt or bt.get("status") != "ok":
            continue
        points = entry["points"]
        dates = [p["date"] for p in points]
        values = [float(p["scaled"]) for p in points]

        last = pd.Timestamp(dates[-1])
        future = [(last + pd.Timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(1, HORIZON + 1)]
        fc = tet_aware_forecast(dates, values, future, PERIOD)

        naive_mase = bt["models"]["seasonal_naive"]["mase"]["mean"]
        tet_mase = bt["models"]["tet_aware_stl"]["mase"]["mean"]
        improvement = round((1 - tet_mase / naive_mase) * 100, 1) if naive_mase else None

        recent = float(np.mean(values[-RECENT_WEEKS:]))
        prior = float(np.mean(values[-2 * RECENT_WEEKS:-RECENT_WEEKS]))

        items.append({
            "keyword": kw,
            "product_type": entry.get("product_type"),
            "topic": entry.get("topic"),
            "history": [{"date": d, "value": round(v, 1)} for d, v in zip(dates[-104:], values[-104:])],
            "forecast": fc.get("components", []),
            "peak": next_peak(dates, values, today),
            "recent_mean": round(recent, 1),
            "prior_mean": round(prior, 1),
            "change_pct": round((recent / prior - 1) * 100, 1) if prior > 0 else None,
            "validation": {
                "metric": "MASE",
                "model": "tet_aware_stl",
                "value": tet_mase,
                "baseline_model": "seasonal_naive",
                "baseline_value": naive_mase,
                "improvement_pct": improvement,
                "beats_baseline": tet_mase < naive_mase,
                "n_origins": bt["models"]["tet_aware_stl"]["n_origins"],
                "horizon_weeks": HORIZON,
                "std": bt["models"]["tet_aware_stl"]["mase"]["std"],
            },
            "tet_bucket_sample_sizes": fc.get("tet_bucket_sample_sizes", {}),
        })
    items.sort(key=lambda x: (x["peak"]["days_from_today"] is None,
                              x["peak"].get("days_from_today", 9999)))
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {"database": "data-collection", "collection": "trend_interest",
                   "field": "scaled", "mode": "precomputed_from_collector_export",
                   "note": "Chỉ số tìm kiếm Google Trends đã quy chuẩn qua từ khoá mốc."},
        "horizon_weeks": HORIZON,
        "items": items,
        "limitation": ("Dự báo NHU CẦU TÌM KIẾM, không phải số đơn hay doanh thu. "
                       "Chỉ quan sát được 5 mùa Tết nên hiệu ứng Tết ước lượng còn thô."),
    }


# --------------------------------------------------------------------------- #
# 3. Ma trận cung cầu
# --------------------------------------------------------------------------- #

def build_market_gap(series: Dict[str, Any]) -> Dict[str, Any]:
    keyword_to_tags: Dict[str, List[str]] = {}
    for row in read_csv(os.path.join(DATA_DIR, "tag_keyword_map.csv")):
        keyword_to_tags.setdefault(row["keyword"], []).append(row["tag_id"])

    tag_counts: Counter = Counter()
    listings_total = 0
    if os.path.exists(LISTINGS):
        for row in read_csv(LISTINGS):
            listings_total += 1
            for tag in str(row.get("tags", "")).split(";"):
                tag = tag.strip()
                if tag:
                    tag_counts[tag] += 1

    rows, unmapped = [], []
    for kw, entry in sorted(series.items()):
        if entry.get("is_anchor"):
            continue
        values = [float(p["scaled"]) for p in entry["points"]]
        demand = float(np.mean(values[-RECENT_WEEKS:]))
        tags = keyword_to_tags.get(kw)
        if not tags:
            unmapped.append(kw)
            continue
        supply = sum(tag_counts.get(t, 0) for t in tags)
        rows.append({"keyword": kw, "product_type": entry.get("product_type"),
                     "topic": entry.get("topic"), "tags": tags,
                     "demand_raw": round(demand, 1), "supply_listings": supply})

    if rows:
        dp = pct_rank([r["demand_raw"] for r in rows])
        sp = pct_rank([float(r["supply_listings"]) for r in rows])
        for r, d, s in zip(rows, dp, sp):
            r["demand_pct"] = round(d, 1)
            r["supply_pct"] = round(s, 1)
            r["quadrant"] = ("opportunity" if d >= 70 and s <= 30 else
                             "crowded" if d >= 70 else
                             "oversupplied" if s >= 70 else "niche")
        rows.sort(key=lambda r: (-(r["demand_pct"] - r["supply_pct"])))

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": "percentile_rank_quadrant",
        "method_note": ("Xếp hạng phân vị hai trục thay cho tỉ số Demand/Supply, "
                        "vì tỉ số nổ tung khi cung tiến về 0 và rất nhạy với epsilon tuỳ chọn."),
        "coverage": {"keywords_total": len([k for k, v in series.items() if not v.get("is_anchor")]),
                     "keywords_mapped": len(rows), "keywords_unmapped": unmapped,
                     "listings_scanned": listings_total},
        "items": rows,
        "source": {"demand": "data-collection.trend_interest (scaled, 12 tuần gần nhất)",
                   "supply": "SE16-AI/data/Le_Hat_Task_AI/listings.csv",
                   "mode": "seed_demo", "attributed_to_live_shop": False},
        "limitation": ("TRỤC CUNG DÙNG DỮ LIỆU MỒI. Tag trong listings.csv được gán ngẫu nhiên "
                       "khi sinh dữ liệu, nên số listing theo tag KHÔNG phản ánh nguồn cung thật "
                       "của sàn. Đây là minh hoạ phương pháp, không phải tín hiệu thị trường. "
                       "Chỉ dùng được thật khi nối với catalog live."),
    }


# --------------------------------------------------------------------------- #
# 4. Bảng chờ dữ liệu
# --------------------------------------------------------------------------- #

def build_readiness(series: Dict[str, Any], backtest: Dict[str, Any],
                    gap: Dict[str, Any]) -> Dict[str, Any]:
    variants = len(read_csv(os.path.join(DATA_DIR, "vc_catalog_variant.csv")))
    types = len(read_csv(os.path.join(DATA_DIR, "vc_product_type.csv")))
    ok = sum(1 for v in backtest.values() if v.get("status") == "ok")
    points = sum(len(v["points"]) for k, v in series.items() if not v.get("is_anchor"))

    capabilities = [
        {"feature": "Định giá khi tạo listing", "status": "ready",
         "evidence": f"{variants:,} variant giá vốn Printify, {types} loại sản phẩm",
         "blocked_by": None, "unlocks_when": None},
        {"feature": "Dự báo mùa vụ Tết", "status": "ready",
         "evidence": f"{points:,} điểm Trends, {ok} keyword có backtest hợp lệ",
         "blocked_by": None, "unlocks_when": None},
        {"feature": "Ma trận cơ hội cung–cầu", "status": "limited",
         "evidence": f"{gap['coverage']['keywords_mapped']}/{gap['coverage']['keywords_total']} keyword ghép được tag",
         "blocked_by": "Trục cung dùng tag gán ngẫu nhiên của dữ liệu mồi",
         "unlocks_when": "Nối với catalog live và tag do seller đặt thật"},
        {"feature": "Tỉ lệ chuyển đổi", "status": "insufficient_data",
         "evidence": "product_events = 0", "blocked_by": "Chưa có sự kiện hành vi live",
         "unlocks_when": "Gắn tracking và tích luỹ ít nhất 7 ngày"},
        {"feature": "Dò bất thường doanh thu", "status": "insufficient_data",
         "evidence": "product_daily_metrics = 0",
         "blocked_by": "Chưa chạy rollup ngày",
         "unlocks_when": "Rollup chạy và tích luỹ ~30 ngày (period=7 cần nhiều chu kỳ)"},
        {"feature": "Khoảng trống từ khoá tìm kiếm", "status": "insufficient_data",
         "evidence": "search_logs = 0", "blocked_by": "Chưa ghi log tìm kiếm nội sàn",
         "unlocks_when": "Ghi query + click + kết quả rỗng"},
        {"feature": "Dự báo doanh thu", "status": "insufficient_data",
         "evidence": "21 đơn live", "blocked_by": "Lịch sử doanh thu quá ngắn",
         "unlocks_when": "~180 ngày giao dịch liên tục"},
        {"feature": "Theo dõi đối thủ", "status": "insufficient_data",
         "evidence": "Không có ảnh chụp định kỳ", "blocked_by": "Chưa có kho snapshot",
         "unlocks_when": "Cron snapshot chạy + tích luỹ 4 tuần"},
    ]
    counts = Counter(c["status"] for c in capabilities)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "capabilities": capabilities,
        "summary": {"ready": counts.get("ready", 0), "limited": counts.get("limited", 0),
                    "insufficient_data": counts.get("insufficient_data", 0),
                    "total": len(capabilities)},
        "principle": "Thiếu dữ liệu thì báo thiếu. Không bao giờ trả 0 thay cho giá trị chưa có.",
    }


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# 5. Chỉ mục gợi ý tag + bộ đối chiếu cho bản JS
# --------------------------------------------------------------------------- #

def build_tag_index() -> Dict[str, Any]:
    """
    Xuất taxonomy thô cho MVP. Gợi ý tag chạy NGAY LÚC seller gõ nên không tính
    sẵn được — bản Node phải tự chấm điểm. Ở đây chỉ xuất nguyên liệu, còn thuật
    toán được cài lại bằng JS.
    """
    tags = read_csv(os.path.join(DATA_DIR, "tags.csv"))
    cats = read_csv(os.path.join(DATA_DIR, "categories.csv"))
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tags": [{"tag_id": t["tag_id"], "name_vi": t.get("name_vi", ""),
                  "category_id": t.get("category_id", ""),
                  "source_keywords": t.get("source_keywords", ""),
                  "aliases": t.get("aliases", "")} for t in tags],
        "categories": [{"category_id": c["category_id"], "name_vi": c.get("name_vi", "")}
                       for c in cats],
        "source": {"dataset": "AI-Analysic/app/data",
                   "files": ["tags.csv", "categories.csv"],
                   "mode": "reference_master_data"},
    }


PARITY_QUERIES = [
    "ao thun", "ao thun anime", "ao hoodie nam mua dong",
    "Cốc sứ in hình tặng sinh nhật", "tui tote canvas di hoc",
    "Bao lì xì Tết in chữ thư pháp", "qua tang me ngay 8/3",
    "ao doi cho cap doi yeu nhau", "Tranh canvas trang trí phòng khách",
    "ao lop ky niem cap 3", "Móc khoá acrylic in hình chibi",
    "qua tang nguoi yeu valentine", "ao local brand oversize",
    "do tap gym nam", "", "!!! ???",
]


def build_parity_fixture() -> Dict[str, Any]:
    """
    Bộ đối chiếu Python <-> JS.

    Cùng một thuật toán cài ở hai ngôn ngữ thì sớm muộn cũng lệch nhau. File này
    ghim kết quả của bản Python; test bên Node chạy lại y hệt truy vấn và bắt
    buộc phải ra cùng kết quả. Lệch là test đỏ.
    """
    from app.services.tag_suggest_service import load_from_csv  # noqa: E402
    svc = load_from_csv(DATA_DIR)
    cases = []
    for q in PARITY_QUERIES:
        got = svc.suggest(q, top_k=5)
        cases.append({
            "query": q,
            "expected": [{"tag_id": g["tag_id"], "score": g["score"]} for g in got],
            "expected_categories": [{"category_id": c["category_id"], "score": c["score"]}
                                    for c in svc.suggest_category(q, 3)],
        })
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_of_truth": "AI-Analysic/app/services/tag_suggest_service.py",
        "note": ("Bản Node phải ra kết quả trùng khít. Sửa thuật toán một bên thì "
                 "phải chạy lại build_mvp_export.py và cập nhật file này."),
        "top_k": 5,
        "cases": cases,
    }


# --------------------------------------------------------------------------- #
# 6. F30 Dò bất thường + F28 Phễu chuyển đổi, trên dữ liệu hành vi seed
# --------------------------------------------------------------------------- #

ANOMALY_PERIOD = 7        # chuỗi NGÀY, chu kỳ tuần
MIN_DAYS_PER_SHOP = 120   # cần đủ nhiều chu kỳ tuần thì STL mới bóc được mùa vụ
TOP_SHOPS = 12


def build_anomaly_export() -> Dict[str, Any]:
    """
    Gộp doanh thu ngày lên CẤP SHOP rồi dò bất thường.

    Vì sao không làm ở cấp listing: đo được trên chính dữ liệu này — trung vị
    mỗi listing chỉ có 41 ngày và 3 ngày có bán (7,3% khác 0). Đó là nhu cầu
    rời rạc kiểu Lumpy, đúng trường hợp mà benchmark M5 của nhóm kết luận là
    ARIMA/dò bất thường thua cả cách ngây thơ. Gộp lên cấp shop thì chuỗi liên
    tục và mô hình mới có nghĩa.

    Vì sao phải nối qua listings.csv: cột shop_id trong listing_daily là chuỗi
    RỖNG — lỗi thiếu identity đã ghi trong báo cáo audit. listing_id là khoá duy
    nhất dùng được.
    """
    from pymongo import MongoClient  # noqa: E402
    from app.config import settings  # noqa: E402
    from app.services.zscore_service import ZScoreService  # noqa: E402

    shop_of, shop_name = {}, {}
    for r in read_csv(LISTINGS):
        shop_of[r["listing_id"]] = r["shop_id"]
    for r in read_csv(os.path.join(WORKSPACE, "SE16-AI/data/Le_Hat_Task_AI/shops.csv")):
        shop_name[r["shop_id"]] = r.get("name", r["shop_id"])

    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=20000,
                         appName="vc-mvp-export")
    coll = client[settings.MONGO_DB_SEED]["listing_daily"]
    cursor = coll.find({}, {"_id": 0, "listing_id": 1, "date": 1, "revenue_vnd": 1,
                            "views": 1, "add_to_carts": 1, "orders": 1})
    df = pd.DataFrame(list(cursor))
    client.close()

    df["shop_id"] = df["listing_id"].map(shop_of)
    unmapped = int(df["shop_id"].isna().sum())
    df = df.dropna(subset=["shop_id"])

    grouped = (df.groupby(["shop_id", "date"], as_index=False)
                 .agg(revenue=("revenue_vnd", "sum"), views=("views", "sum"),
                      carts=("add_to_carts", "sum"), orders=("orders", "sum")))

    all_dates = sorted(grouped["date"].unique())
    items, skipped = [], []

    for shop_id, g in grouped.groupby("shop_id"):
        # Chỉ reindex các cột SỐ. Để nguyên cả khung thì pandas cố điền 0 vào
        # cột shop_id kiểu chuỗi và ném TypeError.
        # Ngày không có bản ghi nghĩa là doanh thu 0 thật, không phải thiếu dữ
        # liệu — chuỗi phải liên tục thì STL mới bóc được chu kỳ tuần.
        g = (g.set_index("date")[["revenue", "views", "carts", "orders"]]
               .reindex(all_dates, fill_value=0)
               .reset_index(names="date"))
        if len(g) < MIN_DAYS_PER_SHOP:
            skipped.append({"shop_id": shop_id, "days": len(g)})
            continue

        revenue = [float(x) for x in g["revenue"]]
        res = ZScoreService.analyze(revenue, dates=list(g["date"]),
                                    period=ANOMALY_PERIOD, top_n=8)

        views, carts, orders = int(g["views"].sum()), int(g["carts"].sum()), int(g["orders"].sum())
        items.append({
            "shop_id": shop_id,
            "shop_name": shop_name.get(shop_id, shop_id),
            "series": [{"date": d, "revenue": round(r, 0)}
                       for d, r in zip(g["date"], revenue)],
            "total_revenue": round(float(sum(revenue)), 0),
            "days": len(g),
            "funnel": {
                "views": views, "carts": carts, "orders": orders,
                # Thiếu ≠ 0: mẫu số bằng 0 thì trả None chứ không trả 0%.
                "view_to_cart_pct": round(carts / views * 100, 2) if views else None,
                "cart_to_order_pct": round(orders / carts * 100, 2) if carts else None,
                "view_to_order_pct": round(orders / views * 100, 2) if views else None,
            },
            "anomaly": {
                "status": res["status"],
                "method": res["method"],
                "period": res["period"],
                "threshold": res["threshold"],
                "cycles_observed": res["cycles_observed"],
                "count": res["anomaly_count"],
                "rate": res["anomaly_rate"],
                "calendar_sensitive_count": res["calendar_sensitive_count"],
                "note": res["reliability_note"],
                "top": [{"date": p["date"], "value": round(p["value"], 0),
                         "trend": p["trend"], "seasonal": p["seasonal"],
                         "residual": p["residual"], "score": p["score"],
                         "direction": p["direction"],
                         "calendar_sensitive": p["calendar_sensitive"]}
                        for p in res["top_anomalies"]],
            },
        })

    items.sort(key=lambda x: -x["total_revenue"])
    items = items[:TOP_SHOPS]

    total_views = int(grouped["views"].sum())
    total_carts = int(grouped["carts"].sum())
    total_orders = int(grouped["orders"].sum())

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "level": "shop",
        "level_reason": ("Gộp lên cấp shop vì cấp listing quá thưa: trung vị 41 ngày dữ liệu "
                         "và chỉ 3 ngày có bán. Đây đúng kết luận của benchmark M5 trong dự án."),
        "date_range": {"from": all_dates[0], "to": all_dates[-1], "days": len(all_dates)},
        "marketplace_funnel": {
            "views": total_views, "carts": total_carts, "orders": total_orders,
            "view_to_cart_pct": round(total_carts / total_views * 100, 2) if total_views else None,
            "cart_to_order_pct": round(total_orders / total_carts * 100, 2) if total_carts else None,
            "view_to_order_pct": round(total_orders / total_views * 100, 2) if total_views else None,
        },
        "coverage": {"shops_exported": len(items), "shops_skipped_short_series": len(skipped),
                     "listing_daily_rows_unmapped": unmapped},
        "items": items,
        "source": {"database": settings.MONGO_DB_SEED, "collection": "listing_daily",
                   "joined_with": "SE16-AI/data/Le_Hat_Task_AI/listings.csv (shop_id)",
                   "mode": "seed_demo", "attributed_to_live_shop": False},
        "limitation": ("DỮ LIỆU MỒI, KHÔNG PHẢI SHOP THẬT. listing_daily là chuỗi tự sinh; "
                       "hệ số mùa vụ của nó trích từ chính Google Trends nên tương quan với "
                       "Trends là vòng lặp tự thân. Dùng để minh hoạ phương pháp và kiểm chứng "
                       "mô hình, KHÔNG dùng để kết luận về shop live. Cột shop_id trong "
                       "listing_daily rỗng nên phải nối qua listings.csv."),
    }


def build_price_benchmark() -> Dict[str, Any]:
    """
    F35 — định vị giá cạnh tranh.

    Câu hỏi seller thật sự hỏi lúc đặt giá không phải "giá vốn bao nhiêu" mà là
    "so với những người đang bán cùng loại phôi thì giá này đã hợp lý chưa".
    Hàm dựng phân phối giá của từng loại phôi từ 5.000 listing đang bán.

    CỐ Ý KHÔNG ĐỤNG GIÁ VỐN. Bảng giá vốn catalog và cột base_cost_vnd của
    listing không khớp nhau: áo thun catalog ghi 221.000đ, listing ghi 86.000đ,
    và 58,3% listing có giá thấp hơn giá vốn catalog cùng phôi. Trộn hai nguồn
    lên một màn hình là để máy tự mâu thuẫn. View cạnh tranh chỉ dùng GIÁ nên
    vênh đó không lan vào đây; phần giá vốn nằm riêng ở khối unit economics.
    """
    listings = read_csv(LISTINGS)
    names = {r["product_type_id"]: r["name_vi"]
             for r in read_csv(os.path.join(DATA_DIR, "vc_product_type.csv"))}

    groups: Dict[str, List[int]] = {}
    tiers: Dict[str, Dict[str, List[int]]] = {}
    for r in listings:
        if r.get("status") != "active":
            continue
        try:
            price = int(r["base_price_vnd"])
        except (ValueError, KeyError, TypeError):
            continue
        pt = r["product_type_id"]
        groups.setdefault(pt, []).append(price)
        tiers.setdefault(pt, {}).setdefault(r.get("tier", "?"), []).append(price)

    def q(sorted_vals: List[int], p: float) -> int:
        if not sorted_vals:
            return 0
        idx = min(len(sorted_vals) - 1, int(round((len(sorted_vals) - 1) * p)))
        return int(sorted_vals[idx])

    # Bằng chứng cho nhãn trung thực: tier có dự báo được giá không?
    # Nếu hot > medium > tail đơn điệu ở phần lớn phôi thì mới nói được
    # "nhóm bán chạy đặt giá cao hơn". Đo thật rồi ghi số ra màn hình.
    monotonic = 0
    comparable = 0
    for pt, byt in tiers.items():
        med = {t: q(sorted(v), 0.5) for t, v in byt.items() if len(v) >= 3}
        if {"hot", "medium", "tail"} <= set(med):
            comparable += 1
            if med["hot"] > med["medium"] > med["tail"]:
                monotonic += 1

    items = []
    for pt, vals in sorted(groups.items()):
        v = sorted(vals)
        med = q(v, 0.5)
        items.append({
            "product_type_id": pt,
            "name_vi": names.get(pt, pt),
            "n_listings": len(v),
            "p10": q(v, 0.10), "p25": q(v, 0.25), "p50": med,
            "p75": q(v, 0.75), "p90": q(v, 0.90),
            "min": v[0], "max": v[-1],
            # Độ rộng tương đối: thị trường phân tán thì một mức giá lệch
            # trung vị chưa chắc là bất thường.
            "iqr_over_median": round((q(v, 0.75) - q(v, 0.25)) / med, 3) if med else None,
            # Dưới 30 mẫu thì phân vị đuôi rất lung lay, nói thẳng ra.
            "confidence": "ok" if len(v) >= 30 else "low_sample",
        })

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": "percentile_of_comparable_listings",
        "method_note": (
            "Phân vị giá tính trên các listing đang bán CÙNG loại phôi. "
            "Chỉ dùng giá niêm yết, không dùng giá vốn."
        ),
        "coverage": {
            "listings_used": sum(len(v) for v in groups.values()),
            "product_types": len(items),
            "product_types_ok_sample": sum(1 for i in items if i["confidence"] == "ok"),
            "min_sample": min((i["n_listings"] for i in items), default=0),
            "median_sample": q(sorted(i["n_listings"] for i in items), 0.5),
        },
        "tier_price_independence": {
            "product_types_compared": comparable,
            "monotonic_hot_gt_medium_gt_tail": monotonic,
            "note": (
                f"Chỉ {monotonic}/{comparable} loại phôi có thứ tự giá hot > medium > tail. "
                "Trong dữ liệu mồi, tier được gán độc lập với giá, nên KHÔNG kết luận "
                "được mức giá nào bán chạy hơn. Chỉ nói được vị trí tương đối."
            ),
        },
        "items": items,
        "source": {"dataset": "SE16-AI/data/Le_Hat_Task_AI/listings.csv", "mode": "seed_demo"},
        "limitation": (
            "DỮ LIỆU MỒI. 5.000 listing tự sinh, không phải hàng đang bán thật trên sàn. "
            "Giá và mức độ bán chạy trong bộ này độc lập với nhau, nên màn hình chỉ trả lời "
            "'giá này đứng ở đâu so với mặt bằng', KHÔNG trả lời 'giá nào bán tốt hơn'. "
            "Muốn trả lời vế sau cần dữ liệu giao dịch live."
        ),
    }


def main() -> None:
    today = date.today()
    print(f"=== BUILD MVP EXPORT ({today}) ===\n")
    with io.open(TRENDS, encoding="utf-8") as f:
        series = json.load(f)["series"]
    print(f"Nạp {len(series)} keyword từ trends_weekly.json\n")

    print("1/5 Backtest trượt điểm cắt (45 keyword × 3 mô hình)...")
    backtest = run_backtests(series)
    summary = summarise(backtest)
    print(f"\n  Tổng kết: {summary}\n")

    print("2/5 Dự báo 12 tuần + đếm ngược đỉnh mùa...")
    forecasts = build_forecasts(series, backtest, today)
    print(f"  {len(forecasts['items'])} keyword có dự báo\n")

    print("3/5 Ma trận cung cầu...")
    gap = build_market_gap(series)
    print(f"  {gap['coverage']['keywords_mapped']} keyword ghép được tag, "
          f"{gap['coverage']['listings_scanned']:,} listing quét\n")

    print("4/5 Bảng chờ dữ liệu...")
    readiness = build_readiness(series, backtest, gap)
    print(f"  {readiness['summary']}\n")

    print("5/6 Chỉ mục gợi ý tag + bộ đối chiếu Python/JS...")
    tag_index = build_tag_index()
    parity = build_parity_fixture()
    print(f"  {len(tag_index['tags'])} tag, {len(parity['cases'])} truy vấn đối chiếu\n")

    print("6/6 F30 dò bất thường + F28 phễu, trên dữ liệu hành vi seed...")
    anomaly = build_anomaly_export()
    mf = anomaly["marketplace_funnel"]
    print(f"  {anomaly['coverage']['shops_exported']} shop, {anomaly['date_range']['days']} ngày")
    print(f"  phễu toàn sàn: {mf['views']:,} view -> {mf['carts']:,} cart -> {mf['orders']:,} đơn")
    flagged = sum(i["anomaly"]["count"] for i in anomaly["items"])
    ok = sum(1 for i in anomaly["items"] if i["anomaly"]["status"] == "ok")
    print(f"  {flagged} điểm bất thường, {ok}/{len(anomaly['items'])} shop có status ok\n")

    print("7/7 F35 định vị giá cạnh tranh, trên 5.000 listing seed...")
    price_bm = build_price_benchmark()
    cov = price_bm["coverage"]
    ti = price_bm["tier_price_independence"]
    print(f"  {cov['listings_used']:,} listing, {cov['product_types']} loại phôi, "
          f"{cov['product_types_ok_sample']} loại đủ mẫu (>=30)")
    print(f"  tier vs giá: {ti['monotonic_hot_gt_medium_gt_tail']}/{ti['product_types_compared']} "
          f"đơn điệu -> không kết luận được về chuyển đổi\n")

    os.makedirs(os.path.dirname(OUT_DOCS), exist_ok=True)
    os.makedirs(os.path.join(OUT_MVP, "..", "tests", "fixtures"), exist_ok=True)
    os.makedirs(OUT_MVP, exist_ok=True)

    results = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "protocol": {"method": "rolling_origin", "window": "expanding",
                     "horizon_weeks": HORIZON, "n_origins": N_ORIGINS,
                     "step_weeks": STEP, "seasonal_period": PERIOD,
                     "primary_metric": "MASE",
                     "metric_note": ("MASE < 1 nghĩa là tốt hơn dự báo ngây thơ mùa vụ. "
                                     "MAPE bị loại vì chia cho 0 và không so sánh được giữa các chuỗi.")},
        "summary": summary,
        "per_keyword": backtest,
    }
    with io.open(OUT_DOCS, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    with io.open(os.path.join(WORKSPACE, "pricing-mvp", "tests", "fixtures",
                              "tagSuggest.parity.json"), "w", encoding="utf-8") as f:
        json.dump(parity, f, ensure_ascii=False, indent=2)
    for name, payload in (("trend_forecast.json", forecasts),
                          ("market_gap.json", gap),
                          ("readiness.json", readiness),
                          ("tag_index.json", tag_index),
                          ("anomaly.json", anomaly),
                          ("price_benchmark.json", price_bm)):
        with io.open(os.path.join(OUT_MVP, name), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"✅ Đã ghi:\n   {OUT_DOCS}")
    for name in ("trend_forecast.json", "market_gap.json", "readiness.json",
                 "tag_index.json", "anomaly.json", "price_benchmark.json"):
        print(f"   {os.path.join(OUT_MVP, name)}")


if __name__ == "__main__":
    main()
