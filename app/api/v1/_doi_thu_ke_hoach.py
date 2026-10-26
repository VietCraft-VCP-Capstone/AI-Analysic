import json
import os
import re
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

TOI_DA_VIEC = 10      # trang chia 5 việc mỗi trang, trang đầu vẫn là 5 việc gấp nhất
MOI_LOAI = 2          # mỗi loại việc tối đa 2 dòng để kế hoạch không toàn một việc
CACHE_GIAY = 1800
THU_TU_MUC = {"gap": 0, "quan_trong": 1, "nen_lam": 2}
MO_HINH_CLAUDE = os.getenv("COMPETITOR_BRIEF_MODEL", "claude-sonnet-5-5")


def _so(text: str) -> List[int]:
    """Các con số trong câu, bỏ dấu phân cách nghìn: '159.000đ' -> 159000."""
    return [int(re.sub(r"[.,\s]", "", m)) for m in re.findall(r"\d[\d.,]*\d|\d", text)]


def _tien(v: Optional[float]) -> str:
    return f"{int(round(v)):,}".replace(",", ".") + "đ" if v is not None else "?"


# Cùng đơn vị với thẻ nhóm chiến lược ở FE (BenchmarkPage DON_VI).
DON_VI = {
    "gia": _tien,
    "sao": lambda v: f"{v:.1f}".replace(".", ",") + "/5",
    "phan_hoi": lambda v: f"{round(v)} phút",
    "so_sp": lambda v: f"{round(v)} sản phẩm",
    "doanh_so": _tien,
}


def gom_su_that(f32: Dict, f33: Dict, f34: Dict, f35_theo_sp: List[Dict], f36: Dict) -> List[Dict[str, Any]]:
    """Sự thật đã tính ở các tab (dữ liệu `data` của F32–F36), mỗi điều kèm các con số được phép nhắc lại."""
    su: List[Dict[str, Any]] = []
    theo_doi = {t["shop_id"] for t in (f36 or {}).get("tracked") or []}
    for a in (f36 or {}).get("alerts") or []:
        t = a.get("threat") or {}
        if t.get("level") in ("high", "medium") and t.get("matched_title"):
            su.append({"kind": "de_doa", "level": t["level"], "shop_id": a["shop_id"], "shop": a.get("shop_name"),
                       "title": a.get("title"), "mine": t["matched_title"], "similarity_pct": round(t["similarity"] * 100),
                       "near_identical": bool(t.get("near_identical")),
                       "cheaper_pct": t.get("price_gap_pct") if (t.get("price_gap_pct") or 0) > 0 else None})
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
    ten_tag = (f34 or {}).get("tag_names") or {}
    for p in ((f34 or {}).get("per_product") or [])[:3]:
        x = next((x for x in p["suggestions"] if x["used_by"] >= 2), None)
        if x:
            su.append({"kind": "tu_khoa", "product_id": p["product_id"], "title": p["title"],
                       "tag": ten_tag.get(x["tag_id"], x["tag_id"]), "used_by": x["used_by"], "better_sellers": x["better_sellers"]})
    nhom = (f33 or {}).get("strategic_groups")
    if nhom and nhom.get("best_group") is not None and nhom["best_group"] != nhom["my_group"]:
        ten = {g["id"]: g["label"] for g in nhom["groups"]}
        gaps = [{"name": x["name"].split(" (")[0].lower(), "mine": DON_VI[x["feature"]](x["mine"]),
                 "theirs": DON_VI[x["feature"]](x["theirs"])} for x in nhom.get("gaps") or []]
        gaps = [g for g in gaps if g["mine"] != g["theirs"]]          # làm tròn ra bằng nhau thì không đáng nêu
        if gaps:
            su.append({"kind": "nhom", "mine": ten[nhom["my_group"]], "best": ten[nhom["best_group"]], "gaps": gaps})
    for s in (f32 or {}).get("direct_rival_shops") or []:
        if s["shop_id"] not in theo_doi:
            su.append({"kind": "theo_doi", "shop_id": s["shop_id"], "shop": s.get("shop_name"), "overlap": s["overlap"]})
            break
    return su


def _muc(f: Dict[str, Any]) -> str:
    """Mức ưu tiên hiện trên trang: hàng mới đe doạ cao là gấp; giá lệch, tăng tốc, đe doạ vừa là quan trọng."""
    if f["kind"] == "de_doa" and f.get("level") == "high":
        return "gap"
    return "quan_trong" if f["kind"] in ("de_doa", "gia", "tang_toc") else "nen_lam"


def ke_hoach_luat(su: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Kế hoạch sinh theo luật từ sự thật, ưu tiên: đe doạ cao > giá lệch > đối thủ tăng tốc > từ khoá > nhóm > theo dõi."""
    thu_tu = {"de_doa": 0, "gia": 1, "tang_toc": 2, "tu_khoa": 3, "nhom": 4, "theo_doi": 5}
    viec, da_co = [], {}
    for f in sorted(su, key=lambda f: (thu_tu[f["kind"]], f.get("level") != "high", -abs(f.get("vs_suggested_pct") or 0))):
        k = f["kind"]
        da_co[k] = da_co.get(k, 0) + 1
        if da_co[k] > MOI_LOAI:
            continue
        if k == "de_doa":
            re_hon = f", rẻ hơn {f['cheaper_pct']}%" if f.get("cheaper_pct") else ""
            viec.append({"action": f"{'Xem ngay' if f['level'] == 'high' else 'Để ý'} sản phẩm mới \"{f['title']}\" của {f['shop']}",
                         "why": (f"Gần như cùng sản phẩm với \"{f['mine']}\" của bạn (giống {f['similarity_pct']}%){re_hon}."
                                 if f.get("near_identical") else f"Giống {f['similarity_pct']}% \"{f['mine']}\" của bạn{re_hon}."),
                         "link": f"/seller/competitors/{f['shop_id']}"})
        elif k == "gia":
            huong = "cao hơn" if f["my_price"] > f["high"] else "thấp hơn"
            viec.append({"action": f"Xem lại giá \"{f['title']}\": đang {_tien(f['my_price'])}, {huong} khoảng nên cân nhắc "
                                   f"{_tien(f['low'])} – {_tien(f['high'])}",
                         "why": f"{f['n_rivals']} sản phẩm giống nhất của shop khác đang bán {_tien(f['rival_min'])} – {_tien(f['rival_max'])}.",
                         "link": f"/seller/insights/pricing?productId={f['product_id']}"})
        elif k == "tang_toc":
            viec.append({"action": f"Theo sát {f['shop']}: shop đang bán tăng đột biến",
                         "why": f"Tuần vừa rồi bán {f['last_week']} sản phẩm, thường chỉ khoảng {f['baseline']}/tuần.",
                         "link": f"/seller/competitors/{f['shop_id']}"})
        elif k == "tu_khoa":
            them = f", {f['better_sellers']} trong đó bán chạy hơn" if f["better_sellers"] else ""
            viec.append({"action": f"Thêm từ khoá \"{f['tag']}\" cho \"{f['title']}\"",
                         "why": f"{f['used_by']} sản phẩm giống đang dùng từ khoá này{them}.",
                         "link": f"/seller/products?edit={f['product_id']}"})
        elif k == "nhom":
            khac = ", ".join(f"{g['name']} {g['theirs']} (bạn {g['mine']})" for g in f["gaps"][:2])
            viec.append({"action": f"Học cách bán của nhóm \"{f['best']}\"",
                         "why": f"Bạn thuộc nhóm \"{f['mine']}\"; nhóm bán tốt hơn khác bạn ở {khac}.",
                         "link": "/seller/insights/competitors#manh-yeu"})
        elif k == "theo_doi":
            viec.append({"action": f"Theo dõi {f['shop']}",
                         "why": f"Shop này có hàng giống {f['overlap']} sản phẩm của bạn nhất.",
                         "link": f"/seller/competitors/{f['shop_id']}"})
        viec[-1]["priority"] = _muc(f)      # thứ tự xếp ở trên đã đi từ gấp tới nên làm
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
