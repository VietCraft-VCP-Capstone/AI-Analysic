import json
import os
import re
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.api.v1._doi_thu_toan_canh import vung_ban_chay

TOI_DA_VIEC = 10      # trang chia 5 việc mỗi trang, trang đầu vẫn là 5 việc gấp nhất
MOI_LOAI = 2          # mỗi loại việc tối đa 2 dòng để kế hoạch không toàn một việc
CACHE_GIAY = 1800
THU_TU_MUC = {"gap": 0, "quan_trong": 1, "nen_lam": 2, "duy_tri": 3}
VUOT_VUNG_GIA = 1.05  # giá thấp nhất của bạn vượt quá 5% trên vùng bán chạy mới nhắc
MO_HINH_CLAUDE = os.getenv("COMPETITOR_BRIEF_MODEL", "claude-sonnet-5-5")


def _so(text: str) -> List[int]:
    """Các con số trong câu, bỏ dấu phân cách nghìn: '159.000đ' -> 159000."""
    return [int(re.sub(r"[.,\s]", "", m)) for m in re.findall(r"\d[\d.,]*\d|\d", text)]


def _tien(v: Optional[float]) -> str:
    return f"{int(round(v)):,}".replace(",", ".") + "đ" if v is not None else "?"


def gom_su_that(f32: Dict, f33: Dict, f34: Dict, f35_theo_sp: List[Dict], f36: Dict) -> List[Dict[str, Any]]:
    """Sự thật đã tính ở các tab (dữ liệu `data` của F32–F36), mỗi điều kèm các con số được phép nhắc lại."""
    su: List[Dict[str, Any]] = []
    theo_doi = {t["shop_id"] for t in (f36 or {}).get("tracked") or []}
    da_bao = {a.get("listing_id") for a in (f36 or {}).get("alerts") or []}
    for a in (f36 or {}).get("alerts") or []:
        t = a.get("threat") or {}
        if t.get("level") in ("high", "medium") and t.get("matched_title"):
            su.append({"kind": "de_doa", "level": t["level"], "shop_id": a["shop_id"], "shop": a.get("shop_name"),
                       "title": a.get("title"), "mine": t["matched_title"], "similarity_pct": round(t["similarity"] * 100),
                       "near_identical": bool(t.get("near_identical")),
                       "cheaper_pct": t.get("price_gap_pct") if (t.get("price_gap_pct") or 0) > 0 else None})
    # Mẫu gần như trùng hàng của tôi đăng trong 8 tuần mà cảnh báo 7 ngày đã bỏ qua: gom theo shop.
    for tr in (f36 or {}).get("tracked") or []:
        sao = [x for x in tr.get("launches") or [] if x["listing_id"] not in da_bao
               and (x.get("threat") or {}).get("near_identical") and x["threat"].get("level") == "high"]
        if sao:
            su.append({"kind": "ban_sao", "shop_id": tr["shop_id"], "shop": tr.get("shop_name"), "n": len(sao),
                       "items": [{"title": x["title"], "mine": x["threat"]["matched_title"],
                                  "similarity_pct": round(x["threat"]["similarity"] * 100),
                                  "cheaper_pct": x["threat"]["price_gap_pct"] if (x["threat"].get("price_gap_pct") or 0) > 0 else None}
                                 for x in sorted(sao, key=lambda x: -x["threat"]["score"])[:2]]})
    for s in (f36 or {}).get("surging") or []:
        su.append({"kind": "tang_toc", "shop_id": s["shop_id"], "shop": s.get("shop_name"),
                   "last_week": s["last_week"], "baseline": round(s["baseline"])})
    for p in f35_theo_sp:
        g, gia = p.get("ai_price"), p.get("my_price")
        # Chỉ báo khi lệch cả khoảng đề xuất lẫn khoảng giá đối thủ thật: shop cao cấp vẫn trong khoảng đối thủ thì để yên.
        if g and gia and ((gia > g["high_vnd"] * 1.05 and gia > g["rival_price_max_vnd"])
                          or (gia < g["low_vnd"] * 0.95 and gia < g["rival_price_min_vnd"])):
            su.append({"kind": "gia", "product_id": p["product_id"], "title": p["title"], "my_price": int(gia),
                       "vs_suggested_pct": round((gia / g["suggested_vnd"] - 1) * 100),
                       "low": g["low_vnd"], "high": g["high_vnd"], "n_rivals": g["n_neighbors"],
                       "rival_min": g["rival_price_min_vnd"], "rival_max": g["rival_price_max_vnd"]})
    # Cả một loại hàng đắt hơn vùng bán chạy cùng chất liệu; loại đã có việc "điều chỉnh giá" thì không nhắc lại.
    gia_sp = {f["product_id"] for f in su if f["kind"] == "gia"}
    diem = (f32 or {}).get("price_points") or []
    for loai in sorted({d["product_type_name"] for d in diem if d["is_mine"]}):
        toi = [d for d in diem if d["is_mine"] and d["product_type_name"] == loai]
        if any(d["listing_id"] in gia_sp for d in toi):
            continue
        cl = {c for d in toi for c in d["materials"]}
        # Biến thể có giá riêng theo chất liệu thì lấy giá của chất liệu đang so, như biểu đồ giá ở FE.
        doi = [{**d, "price_vnd": min(d.get("price_by_material", {}).get(m, d["price_vnd"]) for m in cl & set(d["materials"]))}
               if cl else d
               for d in diem if not d["is_mine"] and d["product_type_name"] == loai and (not cl or cl & set(d["materials"]))]
        vung = vung_ban_chay(doi)
        lo, hi = min(d["price_vnd"] for d in toi), max(d["price_vnd"] for d in toi)
        if vung and lo > vung["p75"] * VUOT_VUNG_GIA:
            su.append({"kind": "vung_gia", "type": loai, "n_mine": len(toi), "my_min": lo, "my_max": hi,
                       "low": vung["p25"], "high": vung["p75"], "materials": sorted(cl),
                       "rival_max": max(d["price_vnd"] for d in doi)})
    ten_tag = (f34 or {}).get("tag_names") or {}
    for p in ((f34 or {}).get("per_product") or [])[:3]:
        x = next((x for x in p["suggestions"] if x["used_by"] >= 2), None)
        if x:
            su.append({"kind": "tu_khoa", "product_id": p["product_id"], "title": p["title"],
                       "tag": ten_tag.get(x["tag_id"], x["tag_id"]), "used_by": x["used_by"], "better_sellers": x["better_sellers"]})
    # Shop cùng phân khúc giá mà bán gấp nhiều lần: đáng tham khảo (thay nhóm chiến lược k-means, vài shop thì không vững).
    shops = (f32 or {}).get("shops") or []
    toi_shop = next((s for s in shops if s["is_me"]), None)
    for s in shops:
        if s.get("is_peer") and toi_shop:
            su.append({"kind": "tham_khao", "shop_id": s["shop_id"], "shop": s.get("shop_name"),
                       "their_median": s["price_vnd"]["median"], "my_median": toi_shop["price_vnd"]["median"],
                       "times": round(s["units_90d"] / max(toi_shop["units_90d"], 1))})
    # Lấy trên mọi danh mục, không chỉ danh mục chính, để không bỏ sót đối thủ ở danh mục phụ.
    ten_dm = (f32 or {}).get("category_names") or {}
    for s in ((f32 or {}).get("rival_shops_by_category") or {}).get("all") or (f32 or {}).get("direct_rival_shops") or []:
        if s["shop_id"] not in theo_doi:
            su.append({"kind": "theo_doi", "shop_id": s["shop_id"], "shop": s.get("shop_name"), "overlap": s["overlap"],
                       "categories": [ten_dm.get(c) or c for c in s.get("categories") or []]})
            break
    # Đánh giá dồn vào nhóm bán chạy mà shop mình gần như chưa có: nên xin đánh giá.
    top = (f32 or {}).get("competitors") or []
    tong_dg = sum(c.get("n_reviews") or 0 for c in top)
    dg_top5 = sum(c.get("n_reviews") or 0 for c in top[:5])
    dg_toi = sum(x.get("n_reviews") or 0 for x in (f32 or {}).get("my_listings") or [])
    if tong_dg >= 5 and dg_top5 / tong_dg >= 0.5 and dg_toi <= 3:
        su.append({"kind": "danh_gia", "top5": dg_top5, "total": tong_dg, "mine": dg_toi})
    # Điểm mạnh nên giữ: trả lời khách nhanh nhất danh mục.
    khac = [s["response_minutes"] for s in shops if not s["is_me"] and s.get("response_minutes") is not None]
    if toi_shop and toi_shop.get("response_minutes") is not None and khac and toi_shop["response_minutes"] < min(khac):
        su.append({"kind": "duy_tri", "mine": toi_shop["response_minutes"], "others_min": min(khac), "others_max": max(khac)})
    return su


def _muc(f: Dict[str, Any]) -> str:
    """Mức ưu tiên hiện trên trang: hàng gần như trùng, hàng mới cạnh tranh cao là khẩn cấp; giá lệch, tăng đột biến là quan trọng."""
    if f["kind"] == "ban_sao" or (f["kind"] == "de_doa" and f.get("level") == "high"):
        return "gap"
    if f["kind"] in ("de_doa", "gia", "vung_gia", "tang_toc"):
        return "quan_trong"
    return "duy_tri" if f["kind"] == "duy_tri" else "nen_lam"


def ke_hoach_luat(su: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Kế hoạch sinh theo luật từ sự thật: xếp theo mức ưu tiên, trong một mức thì theo loại việc."""
    thu_tu = {"de_doa": 0, "ban_sao": 1, "gia": 2, "vung_gia": 3, "tang_toc": 4, "tham_khao": 5, "tu_khoa": 6,
              "theo_doi": 7, "danh_gia": 8, "duy_tri": 9}
    viec, da_co = [], {}
    for f in sorted(su, key=lambda f: (THU_TU_MUC[_muc(f)], thu_tu[f["kind"]], f.get("level") != "high",
                                       -abs(f.get("vs_suggested_pct") or 0))):
        k = f["kind"]
        da_co[k] = da_co.get(k, 0) + 1
        if da_co[k] > MOI_LOAI:
            continue
        if k == "de_doa":
            re_hon = f", giá thấp hơn {f['cheaper_pct']}%" if f.get("cheaper_pct") else ""
            viec.append({"action": f"{'Xem ngay' if f['level'] == 'high' else 'Lưu ý'} sản phẩm mới \"{f['title']}\" của {f['shop']}",
                         "why": (f"Gần như trùng với \"{f['mine']}\" của bạn (tương đồng {f['similarity_pct']}%){re_hon}."
                                 if f.get("near_identical") else f"Tương đồng {f['similarity_pct']}% với \"{f['mine']}\" của bạn{re_hon}."),
                         "link": f"/seller/competitors/{f['shop_id']}"})
        elif k == "ban_sao":
            ly_do = "; ".join(f"\"{x['title']}\" tương đồng {x['similarity_pct']}% với \"{x['mine']}\""
                              + (f", giá thấp hơn {x['cheaper_pct']}%" if x.get("cheaper_pct") else "") for x in f["items"])
            viec.append({"action": f"Đối chiếu {f['n']} mẫu của {f['shop']} gần như trùng sản phẩm của bạn",
                         "why": f"{ly_do}.", "link": "/seller/insights/competitors#theo-doi"})
        elif k == "gia":
            huong = "cao hơn" if f["my_price"] > f["high"] else "thấp hơn"
            viec.append({"action": f"Điều chỉnh giá \"{f['title']}\": hiện {_tien(f['my_price'])}, {huong} khoảng đề xuất "
                                   f"{_tien(f['low'])} – {_tien(f['high'])}",
                         "why": f"{f['n_rivals']} sản phẩm tương đồng nhất của đối thủ đang bán {_tien(f['rival_min'])} – {_tien(f['rival_max'])}.",
                         "link": f"/seller/insights/pricing?productId={f['product_id']}"})
        elif k == "vung_gia":
            gia_toi = _tien(f["my_min"]) if f["my_min"] == f["my_max"] else f"{_tien(f['my_min'])} – {_tien(f['my_max'])}"
            cl = f" {', '.join(f['materials'])}" if f["materials"] else ""
            viec.append({"action": f"Rà soát giá {f['n_mine']} mẫu {f['type'].lower()} ({gia_toi}), cao hơn vùng giá bán chạy "
                                   f"{_tien(f['low'])} – {_tien(f['high'])}",
                         "why": f"50% lượng {f['type'].lower()}{cl} bán ra nằm trong vùng giá này; mẫu đắt nhất của đối thủ là {_tien(f['rival_max'])}.",
                         "link": "/seller/insights/competitors#gia"})
        elif k == "tang_toc":
            viec.append({"action": f"Theo sát {f['shop']}: lượng bán đang tăng đột biến",
                         "why": f"Tuần vừa rồi bán {f['last_week']} sản phẩm, mức nền khoảng {f['baseline']} sản phẩm/tuần.",
                         "link": f"/seller/competitors/{f['shop_id']}"})
        elif k == "tham_khao":
            viec.append({"action": f"Tham khảo chiến lược bán hàng của {f['shop']}",
                         "why": f"Cùng phân khúc giá với bạn ({_tien(f['their_median'])} so với {_tien(f['my_median'])}) "
                                f"nhưng lượng bán 90 ngày gấp {f['times']} lần.",
                         "link": f"/seller/competitors/{f['shop_id']}"})
        elif k == "tu_khoa":
            them = f", {f['better_sellers']} trong đó bán chạy hơn" if f["better_sellers"] else ""
            viec.append({"action": f"Bổ sung từ khoá \"{f['tag']}\" cho \"{f['title']}\"",
                         "why": f"{f['used_by']} sản phẩm tương đồng đang dùng từ khoá này{them}.",
                         "link": f"/seller/products?edit={f['product_id']}"})
        elif k == "theo_doi":
            viec.append({"action": f"Theo dõi {f['shop']}",
                         "why": f"Shop có sản phẩm tương đồng với {f['overlap']} sản phẩm của bạn, nhiều nhất trong các shop bạn chưa theo dõi"
                                + (f" (ở {', '.join(f['categories'])})." if f.get("categories") else "."),
                         "link": f"/seller/competitors/{f['shop_id']}"})
        elif k == "danh_gia":
            viec.append({"action": "Đề nghị khách đã nhận hàng để lại đánh giá",
                         "why": f"5 sản phẩm dẫn đầu danh mục chiếm {f['top5']}/{f['total']} lượt đánh giá của top 20; "
                                f"shop bạn mới có {f['mine']} lượt.",
                         "link": "/seller/orders"})
        elif k == "duy_tri":
            viec.append({"action": "Duy trì thời gian phản hồi khách hàng hiện tại",
                         "why": f"Bạn phản hồi trong {f['mine']} phút, nhanh nhất danh mục (các shop khác {f['others_min']}–{f['others_max']} phút).",
                         "link": "/seller/chat"})
        viec[-1]["priority"] = _muc(f)      # thứ tự xếp ở trên đã đi từ khẩn cấp tới duy trì
        if len(viec) == TOI_DA_VIEC:
            break
    return viec


def _loi_nhac(su: List[Dict[str, Any]]) -> str:
    return ("Bạn là trợ lý cho người bán mới trên sàn thương mại điện tử VietCraft. Dưới đây là các SỰ THẬT đã được hệ "
            f"thống tính sẵn về đối thủ của shop (JSON). Hãy viết tối đa {TOI_DA_VIEC} việc nên làm trong tuần này, xếp "
            "việc quan trọng nhất lên đầu, bằng tiếng Việt dễ hiểu, không dùng thuật ngữ. CHỈ dùng con số có trong dữ liệu, "
            "không suy ra số mới, không bịa. Mỗi việc ghi `fact` là số thứ tự của sự thật làm căn cứ. Trả về DUY NHẤT "
            'một JSON dạng {"actions":[{"fact":0,"action":"việc cần làm","why":"vì sao, có số liệu"}]}.\n\nSỰ THẬT:\n'
            + json.dumps([{"fact": i, **f} for i, f in enumerate(su)], ensure_ascii=False))


def _goi(url: str, body: Dict, headers: Dict[str, str], lay: Callable[[Dict], str]) -> Optional[str]:
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json", **headers}, method="POST")
        # 12s để cả lượt (tính sự thật ~4s + LLM) vẫn dưới timeout 20s của BE gateway.
        with urllib.request.urlopen(req, timeout=12) as r:
            return lay(json.loads(r.read().decode("utf-8")))
    except Exception:
        return None


def goi_llm(loi_nhac: str) -> Tuple[Optional[str], Optional[str]]:
    """(văn bản, nhà cung cấp) từ khoá đầu tiên có trong môi trường; không có khoá hoặc lỗi thì (None, None)."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return _goi("https://api.anthropic.com/v1/messages",
                    {"model": MO_HINH_CLAUDE, "max_tokens": 1200, "messages": [{"role": "user", "content": loi_nhac}]},
                    {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                    lambda b: b["content"][0]["text"]), f"anthropic/{MO_HINH_CLAUDE}"
    khoa = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if khoa:
        m = "gemini-3.5-flash"                         # cùng họ mô hình service mùa vụ của nhóm đang dùng
        return _goi(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={khoa}",
                    {"contents": [{"parts": [{"text": loi_nhac}]}], "generationConfig": {"temperature": 0.3}},
                    {}, lambda b: b["candidates"][0]["content"]["parts"][0]["text"]), f"gemini/{m}"
    if os.getenv("OPENAI_API_KEY"):
        return _goi("https://api.openai.com/v1/chat/completions",
                    {"model": "gpt-4o-mini", "temperature": 0.3, "messages": [{"role": "user", "content": loi_nhac}]},
                    {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                    lambda b: b["choices"][0]["message"]["content"]), "openai/gpt-4o-mini"
    return None, None


def loc_viec_llm(van_ban: str, su: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Đọc JSON của LLM; bỏ việc nào có con số không nằm trong sự thật (chống bịa số)."""
    m = re.search(r"\{.*\}", van_ban or "", re.S)
    try:
        viec = json.loads(m.group(0))["actions"] if m else []
    except (ValueError, KeyError, TypeError):
        return []
    # Mã shop/sản phẩm có chữ số, bỏ ra để không vô tình cho phép số lạ; 0–10 cho "5 việc", "7 ngày".
    so_lieu = [{k: v for k, v in f.items() if not k.endswith("_id")} for f in su]
    cho_phep = set(_so(json.dumps(so_lieu, ensure_ascii=False))) | set(range(11))
    ra = []
    for v in viec[:TOI_DA_VIEC]:
        if not isinstance(v, dict) or not v.get("action"):
            continue
        i = v.get("fact")
        # Không chỉ ra được sự thật làm căn cứ thì không biết mức ưu tiên, và cũng không chắc là có căn cứ: bỏ.
        if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(su):
            continue
        cau = f"{v.get('action', '')} {v.get('why', '')}"
        if all(n in cho_phep for n in _so(cau)):
            ra.append({"action": str(v["action"]), "why": str(v.get("why") or ""), "link": None, "priority": _muc(su[i])})
    return sorted(ra, key=lambda x: THU_TU_MUC[x["priority"]])


_CACHE: Dict[str, Tuple[float, str, Dict[str, Any]]] = {}


def lap_ke_hoach(shop_id: str, su: List[Dict[str, Any]]) -> Dict[str, Any]:
    """LLM nếu có khoá và trả lời qua được bộ lọc số; không thì kế hoạch theo luật. Lưu đệm theo shop 30 phút."""
    khoa = json.dumps(su, ensure_ascii=False, sort_keys=True)
    co = _CACHE.get(shop_id)
    if co and co[1] == khoa and time.time() - co[0] < CACHE_GIAY:
        return co[2]
    van_ban, nguon = goi_llm(_loi_nhac(su)) if su else (None, None)
    viec = loc_viec_llm(van_ban, su) if van_ban else []
    kq = {"source": "llm", "provider": nguon, "actions": viec} if viec else \
         {"source": "rules", "provider": None, "actions": ke_hoach_luat(su)}
    _CACHE[shop_id] = (time.time(), khoa, kq)
    return kq
