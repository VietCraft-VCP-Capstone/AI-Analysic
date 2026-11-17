"""Seasonal Intelligence — lõi phân tích có căn cứ cho module Mùa vụ.

Nguyên tắc: MỌI con số trả ra đều đến từ dữ liệu quan sát (đơn hàng, listing sàn, chuỗi tìm kiếm)
hoặc từ mô hình đã kiểm chứng (STL, QuantileForecaster). Không đủ dữ liệu thì trả `status =
"insufficient"` kèm lý do, KHÔNG bịa số.

Các hàm đều thuần (nhận list/dict, trả dict) để kiểm thử được mà không cần MongoDB.
Chuẩn tham chiếu: Amazon Brand Analytics (so sánh với cohort), Etsy Search Analytics
(độ tập trung người bán), Shopee Business Insights (percentile trong ngành).
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

COMPLETED = {"DELIVERED", "COMPLETED", "PAID"}
MIN_WINDOW_ORDERS = 15      # tối thiểu đơn trong các cửa sổ dịp để coi là "đo được"
MIN_SHOPS_FOR_RANK = 5      # tối thiểu shop ngành để xếp hạng percentile


# ----------------------------------------------------------------------------- STL thật
def real_stl(points: List[Tuple[str, float]], period: int = 52) -> Dict[str, Any]:
    """Phân rã STL (Loess, robust) bằng statsmodels trên TOÀN BỘ chuỗi tuần.

    Trả 52 tuần gần nhất của trend/seasonal/residual + độ mạnh mùa vụ Fs và độ mạnh xu hướng Ft
    theo Wang–Smith–Hyndman: Fs = max(0, 1 − Var(R)/Var(S+R)).
    """
    vals = [float(v) for _, v in points]
    if len(vals) < period * 2:
        return {"method": "insufficient", "n": len(vals), "seasonal_strength": None, "trend_strength": None}
    from statsmodels.tsa.seasonal import STL
    res = STL(np.asarray(vals), period=period, robust=True).fit()
    s, r, t = res.seasonal, res.resid, res.trend
    fs = max(0.0, 1.0 - float(np.var(r)) / max(1e-9, float(np.var(s + r))))
    ft = max(0.0, 1.0 - float(np.var(r)) / max(1e-9, float(np.var(t + r))))
    return {
        "method": "statsmodels.STL(robust)",
        "n": len(vals),
        "trend": [round(float(x), 2) for x in t[-period:]],
        "seasonal": [round(float(x), 2) for x in s[-period:]],
        "residual": [round(float(x), 2) for x in r[-period:]],
        "seasonal_strength": round(fs, 3),
        "trend_strength": round(ft, 3),
        "window": f"{period} tuần gần nhất (STL trên {len(vals)} tuần)",
    }


def seasonal_peak_years(points: List[Tuple[str, float]], event_month: int) -> Dict[str, Any]:
    """Đếm số năm đỉnh năm rơi vào ±1 tháng quanh dịp (bằng chứng lặp lại theo năm)."""
    by_year: Dict[int, List[Tuple[int, float]]] = defaultdict(list)
    for ds, v in points:
        try:
            d = datetime.strptime(ds[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        by_year[d.year].append((d.month, float(v)))
    analysed = peaked = 0
    for yr, mv in by_year.items():
        if len(mv) < 40:
            continue
        analysed += 1
        peak_month = max(mv, key=lambda x: x[1])[0]
        diff = min((peak_month - event_month) % 12, (event_month - peak_month) % 12)
        if diff <= 1:
            peaked += 1
    return {"years_analyzed": analysed, "years_peaked": peaked}


# ----------------------------------------------------------------------------- Orders helpers
def _dt(x: Any) -> Optional[datetime]:
    if isinstance(x, datetime):
        return x.replace(tzinfo=None)
    if isinstance(x, date):
        return datetime(x.year, x.month, x.day)
    if isinstance(x, str):
        try:
            return datetime.fromisoformat(x[:19]).replace(tzinfo=None)
        except Exception:
            return None
    return None


def _to_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v.to_decimal()) if hasattr(v, "to_decimal") else float(str(v))
    except Exception:
        return 0.0


def order_amount(o: Dict[str, Any]) -> float:
    fb = o.get("financial_breakdown") or {}
    val = fb.get("subtotal") or fb.get("seller_payout_amount") or o.get("total_amount") or 0
    return _to_float(val)


def _completed(orders: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for o in orders:
        if (o.get("order_status") or "").upper() in COMPLETED and _dt(o.get("created_at")):
            out.append(o)
    return out


def _window_stats(win: List[Dict[str, Any]], base: List[Dict[str, Any]], event: date,
                  win_days: int, base_days: int) -> Optional[Dict[str, float]]:
    if len(win) == 0 or len(base) == 0:
        return None
    rate_w = len(win) / win_days
    rate_b = len(base) / base_days
    amt_w = [order_amount(o) for o in win if order_amount(o) > 0]
    amt_b = [order_amount(o) for o in base if order_amount(o) > 0]
    per_day: Dict[date, int] = defaultdict(int)
    for o in win:
        per_day[_dt(o["created_at"]).date()] += 1
    top3 = sum(sorted(per_day.values(), reverse=True)[:3]) / len(win)
    lead = [(event - _dt(o["created_at"]).date()).days for o in win]
    return {
        "orders_growth": (rate_w / rate_b - 1.0) * 100.0 if rate_b > 0 else float("nan"),
        "aov_growth": (np.mean(amt_w) / np.mean(amt_b) - 1.0) * 100.0 if amt_w and amt_b else float("nan"),
        "lead_days": float(median(lead)),
        "peak_clump": top3 * 100.0,
        "combo_pct": 100.0 * sum(1 for o in win if len(o.get("items") or []) >= 2) / len(win),
        "voucher_pct": 100.0 * sum(1 for o in win if o.get("coupon_code")) / len(win),
        "n": float(len(win)),
        "aov_w": float(np.mean(amt_w)) if amt_w else float("nan"),
        "aov_b": float(np.mean(amt_b)) if amt_b else float("nan"),
        "rate_w": rate_w, "rate_b": rate_b,
    }


TRAIT_KEYS = ("orders_growth", "aov_growth", "lead_days", "peak_clump", "combo_pct", "voucher_pct")


def occasion_metrics(orders: List[Dict[str, Any]], past_events: Dict[int, date], win_days: int,
                     today: date, base_weeks: int = 8) -> Dict[str, Any]:
    """6 chỉ số hành vi của một tập đơn trong các cửa sổ dịp ĐÃ DIỄN RA (trung vị qua các năm)."""
    done = _completed(orders)
    per_year: List[Dict[str, float]] = []
    base_days = base_weeks * 7
    for _, ev in sorted(past_events.items()):
        if ev >= today:
            continue
        ws = datetime.combine(ev - timedelta(days=win_days), datetime.min.time())
        we = datetime.combine(ev, datetime.max.time())
        bs = ws - timedelta(days=base_days)
        win = [o for o in done if ws <= _dt(o["created_at"]) <= we]
        base = [o for o in done if bs <= _dt(o["created_at"]) < ws]
        st = _window_stats(win, base, ev, win_days, base_days)
        if st:
            per_year.append(st)
    n = int(sum(s["n"] for s in per_year))
    agg: Dict[str, Optional[float]] = {}
    for k in TRAIT_KEYS + ("aov_w", "aov_b", "rate_w", "rate_b"):
        vals = [s[k] for s in per_year if not math.isnan(s[k])]
        agg[k] = float(median(vals)) if vals else None
    return {"n_orders": n, "n_cycles": len(per_year), "values": agg}


def summarize_industry_orders(
    industry_orders: List[Dict[str, Any]],
    past_events: Dict[int, date],
    win_days: int,
    today: date,
) -> Dict[str, Any]:
    """Tổng hợp dữ liệu toàn ngành thành JSON gọn nhẹ để cache Redis (không mất mẫu lịch sử)."""
    ind = occasion_metrics(industry_orders, past_events, win_days, today)
    by_shop: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for o in industry_orders:
        sid = str(o.get("shop_id") or "")
        if sid:
            by_shop[sid].append(o)
    shop_vals: Dict[str, List[float]] = {k: [] for k in TRAIT_KEYS}
    for sid, od in by_shop.items():
        m = occasion_metrics(od, past_events, win_days, today)
        if m["n_orders"] >= MIN_WINDOW_ORDERS:
            for k in TRAIT_KEYS:
                v = m["values"].get(k)
                if v is not None:
                    shop_vals[k].append(round(float(v), 3))
    return {"ind": ind, "shop_vals": shop_vals}


def compare_shop_vs_industry_summary(
    shop_orders: List[Dict[str, Any]],
    industry_summary: Dict[str, Any],
    past_events: Dict[int, date],
    win_days: int,
    today: date,
    model_uplift_pct: Optional[float] = None,
    model_label: str = "",
) -> Dict[str, Any]:
    """So sánh shop với bản tổng hợp toàn ngành (đọc từ Redis cache hoặc tính trực tiếp)."""
    shop = occasion_metrics(shop_orders, past_events, win_days, today)
    ind = industry_summary["ind"]
    shop_vals = industry_summary["shop_vals"]

    out: Dict[str, Any] = {}
    shop_ok = shop["n_orders"] >= MIN_WINDOW_ORDERS
    ind_ok = ind["n_orders"] >= MIN_WINDOW_ORDERS
    for k in TRAIT_KEYS:
        sv = shop["values"].get(k) if shop_ok else None
        iv = ind["values"].get(k) if ind_ok else None
        pct = None
        peers = shop_vals[k]
        if sv is not None and len(peers) >= MIN_SHOPS_FOR_RANK:
            pct = round(100.0 * sum(1 for p in peers if p <= sv) / len(peers))
        if sv is not None:
            basis = "measured_shop"
        elif iv is not None:
            basis = "industry_only"
        elif k == "orders_growth" and model_uplift_pct is not None:
            basis = "model_forecast"
        else:
            basis = "insufficient"
        out[k] = {
            "basis": basis,
            "shop": {"value": None if sv is None else round(sv, 1), "n": shop["n_orders"], "cycles": shop["n_cycles"],
                     "status": "measured" if sv is not None else "insufficient"},
            "industry": {"value": None if iv is None else round(iv, 1), "n_orders": ind["n_orders"],
                         "n_shops": len(peers), "status": "measured" if iv is not None else "insufficient"},
            "model_value": round(model_uplift_pct, 1) if (k == "orders_growth" and model_uplift_pct is not None) else None,
            "model_label": model_label if k == "orders_growth" else "",
            "shop_percentile": pct,
            "gap": None if (sv is None or iv is None) else round(sv - iv, 1),
        }
    out["_meta"] = {"shop_orders": shop["n_orders"], "industry_orders": ind["n_orders"],
                    "past_cycles_shop": shop["n_cycles"], "past_cycles_industry": ind["n_cycles"],
                    "min_window_orders": MIN_WINDOW_ORDERS}
    return out


def compare_shop_vs_industry(shop_orders: List[Dict[str, Any]], industry_orders: List[Dict[str, Any]],
                             past_events: Dict[int, date], win_days: int, today: date,
                             model_uplift_pct: Optional[float] = None,
                             model_label: str = "") -> Dict[str, Any]:
    """Đặt shop cạnh toàn ngành trên 6 chỉ số hành vi mua; xếp hạng percentile giữa các shop."""
    summary = summarize_industry_orders(industry_orders, past_events, win_days, today)
    return compare_shop_vs_industry_summary(
        shop_orders, summary, past_events, win_days, today,
        model_uplift_pct=model_uplift_pct, model_label=model_label,
    )


# ----------------------------------------------------------------------------- Competition (Etsy-style)
def seller_competition(listings: List[Dict[str, Any]], my_price: float) -> Dict[str, Any]:
    """Độ tập trung người bán (HHI theo thị phần sold_count), top-3 share, vị trí giá."""
    rows = [l for l in listings if l.get("price_vnd")]
    if len(rows) < 3:
        return {"status": "insufficient", "n_listings": len(rows), "n_sellers": len({l.get('seller_id') or l.get('seller_name') for l in rows})}
    sold: Dict[str, float] = defaultdict(float)
    for l in rows:
        sid = str(l.get("seller_id") or l.get("seller_name") or l.get("shop_name") or id(l))
        sold[sid] += float(l.get("sold_count") or 0) or 1.0
    tot = sum(sold.values())
    shares = sorted((v / tot for v in sold.values()), reverse=True)
    hhi = sum((s * 100) ** 2 for s in shares)
    top3 = sum(shares[:3])
    prices = np.array([float(l["price_vnd"]) for l in rows])
    q25, q50, q75 = (float(np.percentile(prices, q)) for q in (25, 50, 75))
    my_pct = round(100.0 * float(np.mean(prices <= my_price))) if my_price else None
    return {"status": "measured", "n_listings": len(rows), "n_sellers": len(sold), "hhi": round(hhi),
            "top3_share_pct": round(top3 * 100, 1), "price_q25": q25, "price_median": q50, "price_q75": q75,
            "my_price_percentile": my_pct}


# ----------------------------------------------------------------------------- Product coverage (hot keyword actions)
def keyword_shop_coverage(keyword: str, shop_products: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Shop đã có bao nhiêu sản phẩm chứa từ khóa trong tên/tag → hành động có giá trị thật."""
    kw_low = keyword.lower().strip()
    toks = [t for t in kw_low.split() if len(t) > 1]
    if not toks:
        return {"matching": 0, "total": len(shop_products), "gap": True, "product_ids": [], "products": [], "already_tagged": False}
    hits = []
    matched_products = []
    tagged_hits = 0
    for p in shop_products:
        p_tags = [str(t).lower().strip() for t in (p.get("tags") or [])]
        title = str(p.get("title") or p.get("name") or "")
        text = " ".join([title] + p_tags).lower()
        score = sum(1 for t in toks if t in text) / len(toks)
        if kw_low in text or score >= 0.75:
            pid = str(p.get("_id") or p.get("id") or "")
            hits.append(pid)
            matched_products.append({"id": pid, "title": title})
            if any(kw_low == pt or kw_low in pt for pt in p_tags):
                tagged_hits += 1
    return {
        "matching": len(hits),
        "total": len(shop_products),
        "gap": len(hits) == 0,
        "product_ids": hits[:5],
        "products": matched_products[:5],
        "already_tagged": len(hits) > 0 and tagged_hits == len(hits),
    }


# ----------------------------------------------------------------------------- Counterfactual impact (Thành quả)
def impact_report(shop_orders: List[Dict[str, Any]], event: date, win_days: int, today: date,
                  adopted_keywords: List[str], market_uplift: Optional[Dict[str, Any]],
                  prev_event: Optional[date]) -> Dict[str, Any]:
    """Thành quả = thực tế − phản thực (không áp dụng).

    Phản thực = nhịp đơn nền 8 tuần × uplift thị trường (QuantileForecaster P10/P50/P90).
    Nhóm "áp dụng" = đơn có sản phẩm khớp từ khóa gợi ý đã chọn. So thêm với mùa trước (YoY).
    """
    done = _completed(shop_orders)
    ws = datetime.combine(event - timedelta(days=win_days), datetime.min.time())
    we = datetime.combine(event, datetime.max.time())
    if today < event - timedelta(days=win_days):
        phase = "upcoming"
    elif today <= event:
        phase = "running"
    else:
        phase = "ended"

    toks = [k.lower() for k in adopted_keywords if k]

    def _hits(o: Dict[str, Any]) -> bool:
        txt = " ".join(str(it.get("title") or it.get("name") or "") for it in (o.get("items") or [])).lower()
        return any(all(t in txt for t in k.split() if len(t) > 1) for k in toks) if toks else False

    base_days = 56
    bs = ws - timedelta(days=base_days)
    base = [o for o in done if bs <= _dt(o["created_at"]) < ws]
    win = [o for o in done if ws <= _dt(o["created_at"]) <= min(we, datetime.combine(today, datetime.max.time()))]
    elapsed = max(1, min(win_days, (min(today, event) - (event - timedelta(days=win_days))).days + 1)) if phase != "upcoming" else 0
    base_rate = len(base) / base_days if base else None
    base_amt = float(np.mean([order_amount(o) for o in base if order_amount(o) > 0])) if any(order_amount(o) > 0 for o in base) else None

    res: Dict[str, Any] = {"phase": phase, "window": [ws.date().isoformat(), event.isoformat()],
                           "elapsed_days": elapsed, "adopted_keywords": adopted_keywords,
                           "baseline_orders_per_day": None if base_rate is None else round(base_rate, 3),
                           "baseline_n": len(base)}
    if phase == "upcoming" or base_rate is None or not market_uplift:
        res["status"] = "insufficient" if base_rate is None else "projected"
        if base_rate is not None and market_uplift:
            days = win_days
            for q in ("p10", "p50", "p90"):
                res[f"expected_orders_{q}"] = round(base_rate * days * float(market_uplift.get(f"uplift_{q}", 1.0)), 1)
            if base_amt:
                res["expected_gmv_p50"] = round(res["expected_orders_p50"] * base_amt)
        return res

    cf = {q: base_rate * elapsed * float(market_uplift.get(f"uplift_{q}", 1.0)) for q in ("p10", "p50", "p90")}
    actual = len(win)
    adopted = [o for o in win if _hits(o)]
    res.update({
        "status": "measured",
        "actual_orders": actual,
        "counterfactual_orders": {q: round(v, 1) for q, v in cf.items()},
        "lift_vs_counterfactual_pct": None if cf["p50"] <= 0 else round((actual / cf["p50"] - 1.0) * 100, 1),
        "beats_p90": actual > cf["p90"],
        "below_p10": actual < cf["p10"],
        "adopted_orders": len(adopted),
        "adopted_gmv": round(sum(order_amount(o) for o in adopted)),
        "adopted_share_pct": round(100.0 * len(adopted) / actual, 1) if actual else 0.0,
        "gmv": round(sum(order_amount(o) for o in win)),
        "aov_vs_baseline_pct": None if not base_amt or not win else round(
            (np.mean([order_amount(o) for o in win if order_amount(o) > 0]) / base_amt - 1.0) * 100, 1),
    })
    if prev_event:
        pws = datetime.combine(prev_event - timedelta(days=win_days), datetime.min.time())
        pwe = datetime.combine(prev_event, datetime.max.time())
        pw = [o for o in done if pws <= _dt(o["created_at"]) <= pwe]
        prev_cut = pws + timedelta(days=elapsed)
        pw_same = [o for o in pw if _dt(o["created_at"]) < prev_cut]
        res["previous_season"] = {"orders_same_period": len(pw_same), "orders_total": len(pw),
                                  "yoy_pct": None if not pw_same else round((actual / len(pw_same) - 1.0) * 100, 1)}
    return res


# ----------------------------------------------------------------------------- Playbook (Áp dụng)
def build_playbook(idea: Dict[str, Any], cut_off: date, event: date, today: date,
                   uplift: Optional[Dict[str, Any]], base_orders_per_day: Optional[float],
                   shop_lead_days: int) -> Dict[str, Any]:
    """Biến một ý tưởng thành kế hoạch hành động lùi từ hạn chốt đơn, kèm kỳ vọng định lượng có khoảng."""
    total_days = max(0, (cut_off - today).days)
    ship_days = 4
    produce_deadline = cut_off - timedelta(days=shop_lead_days + ship_days)
    steps = []

    def _add(label: str, d: date, kpi: str, why: str):
        steps.append({"date": d.isoformat(), "days_from_today": (d - today).days, "task": label,
                      "kpi": kpi, "why": why, "overdue": d < today})

    kw = idea.get("keyword") or idea.get("title") or ""
    _add(f"Đăng listing & gắn tag «{kw}»", min(cut_off, today + timedelta(days=min(3, max(0, total_days)))),
         "Listing hiển thị trên tìm kiếm", "Sàn cần vài ngày để index; đăng sớm giúp thu thập đánh giá trước đỉnh.")
    _add("Thử nhỏ 20 đơn đầu / ngân sách có dừng lỗ", today + timedelta(days=min(7, max(1, total_days // 3))),
         "≥ ngưỡng hòa vốn ở bước thử", "Xác nhận chuyển đổi thật trước khi gom hàng số lượng lớn.")
    _add("Quyết định nhân rộng hay dừng", today + timedelta(days=min(10, max(2, total_days // 2))),
         "Đạt tiêu chí → nhập thêm; không đạt → dừng", "Giảm rủi ro tồn kho sau dịp.")
    _add("Chốt sản xuất / nhập hàng", produce_deadline, "Đủ tồn trước hạn ship",
         f"Trừ {shop_lead_days} ngày làm hàng + {ship_days} ngày vận chuyển khỏi hạn chốt đơn.")
    _add("Hạn chốt nhận đơn an toàn", cut_off, "Đóng nhận đơn giao kịp lễ", "Sau mốc này giao trễ rủi ro cao.")

    exp = None
    if uplift and base_orders_per_day is not None:
        days = max(1, (event - max(today, event - timedelta(days=30))).days)
        exp = {q: round(base_orders_per_day * days * float(uplift.get(f"uplift_{q}", 1.0)), 1) for q in ("p10", "p50", "p90")}
    return {"idea": idea.get("title"), "steps": sorted(steps, key=lambda s: s["date"]),
            "expected_orders_next_30d": exp, "feasible": total_days >= shop_lead_days + ship_days,
            "days_left_to_cut_off": total_days}

