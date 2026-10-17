import re
import time
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

NGUONG_GIONG = 0.15         # dưới mức này coi là không giống (đo ở scripts/danh_gia_doi_thu_ai.py)
NGUONG_KHONG_LY_DO = 0.35   # không có từ hiếm nào chung thì phải giống tới mức này mới tính
SO_DOI_THU = 5
K_GIA = 8
TOI_THIEU_GIA = 3
TRON_GIA = 10                # càng nhiều đối thủ trực tiếp thì càng tin giá của họ hơn mặt bằng cùng loại
TRONG_SO_KY_TU = 0.6        # cụm ký tự giúp bắt "tshirt"/"t-shirt" nhưng không được lấn từ
TRONG_SO_MO_TA = 0.5        # mô tả hay là văn mẫu của shop nên nhẹ hơn tên
TAN_SUAT_LY_DO = 0.5        # từ có ở từ nửa số sản phẩm CÙNG LOẠI trở lên là từ chung của loại, không làm lý do
CACHE_GIAY = 300

# Từ quảng cáo và hư từ: có mặt ở mọi sản phẩm nên chỉ làm nhiễu độ giống.
TU_BO = set("""
cấp giá rẻ freeship chính hãng hot trend sale giảm new đẹp chất lượng siêu ship tốt nhất sản phẩm shop mua bán hàng
và với của các những cho là có không một trong được để từ này khi sẽ đã rất nhiều hơn thì mà nên
""".split())


def bo_dau(s: Any) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _tach(s: Any) -> List[str]:
    """Giữ dấu: "đeo" và "đèo", "cung" và "cũng" là các từ khác nhau."""
    s = unicodedata.normalize("NFC", str(s or "").lower())
    return [t for t in re.findall(r"\w+", s) if len(t) >= 2 and t not in TU_BO]


TACH_TRUONG = " | "


def _gram(doc: str) -> List[str]:
    """Từ và cặp từ, KHÔNG ghép xuyên qua ranh giới giữa các trường (tên | từ khoá | loại hàng)."""
    ra: List[str] = []
    for truong in doc.split(TACH_TRUONG):
        t = _tach(truong)
        ra += t + [f"{x} {y}" for x, y in zip(t, t[1:])]
    return ra


def truong(row: Dict[str, Any], ten_tag: Dict[str, str]) -> List[str]:
    """Tên nhân đôi (quan trọng nhất), từng từ khoá (tên có dấu), loại hàng."""
    tag = [ten_tag.get(t) or str(t).replace("-", " ") for t in row.get("tags") or []]
    return [row.get("title") or ""] * 2 + tag + [row.get("product_type_name") or ""]


def _tfidf(docs: List[str], **kw):
    """TF-IDF; None khi không có từ nào (vd mọi sản phẩm đều chưa có mô tả)."""
    try:
        return TfidfVectorizer(sublinear_tf=True, **kw).fit(docs)
    except ValueError:
        return None


class MayGiong:
    """Độ giống nội dung: TF-IDF tên + từ khoá (mô tả nhẹ hơn, thêm cụm ký tự của tên), cosine, chỉ so cùng loại hàng."""

    def __init__(self, dong: Sequence[Dict[str, Any]], mo_ta: Optional[Dict[str, str]] = None,
                 ten_tag: Optional[Dict[str, str]] = None):
        mo_ta, ten_tag = mo_ta or {}, ten_tag or {}
        self.dong = list(dong)
        self.vi_tri = {r["listing_id"]: i for i, r in enumerate(self.dong)}
        ten = [TACH_TRUONG.join(truong(r, ten_tag)) for r in self.dong]
        mt = [(mo_ta.get(r["listing_id"]) or "")[:300] for r in self.dong]
        ky_tu = [bo_dau(r.get("title")) for r in self.dong]      # bỏ dấu riêng ở đây để bắt tên gõ không dấu
        self.vec_tu = _tfidf(ten, analyzer=_gram)
        if self.vec_tu is None:
            self.x = None
            return
        self.x_tu = self.vec_tu.transform(ten)
        phan = [self.x_tu]
        for vec, docs, trong_so in ((_tfidf(mt, analyzer=_gram), mt, TRONG_SO_MO_TA),
                                    (_tfidf(ky_tu, analyzer="char_wb", ngram_range=(3, 5)), ky_tu, TRONG_SO_KY_TU)):
            if vec is not None:
                phan.append(vec.transform(docs) * trong_so)
        self.x = normalize(hstack(phan).tocsr())
        self.ten_tu = self.vec_tu.get_feature_names_out()
        self.loai_tu = {t for r in self.dong for t in _tach(r.get("product_type_name"))}
        co = (self.x_tu > 0).astype(float)
        theo_loai: Dict[Any, List[int]] = {}
        for i, r in enumerate(self.dong):
            theo_loai.setdefault(r.get("product_type_id"), []).append(i)
        self.hiem = {l: np.asarray(co[idx].mean(axis=0)).ravel() < TAN_SUAT_LY_DO for l, idx in theo_loai.items()}

    def _ly_do(self, i: int, j: int, k: int = 3) -> List[str]:
        """Các từ hiếm hai sản phẩm cùng có; bỏ tên loại hàng vì cùng loại là điều kiện so, không phải lý do."""
        chung = self.x_tu[i].multiply(self.x_tu[j]).tocoo()
        hiem = self.hiem[self.dong[i].get("product_type_id")]
        xep = sorted(((v, c) for v, c in zip(chung.data, chung.col) if hiem[c]), reverse=True)
        ra: List[str] = []
        for _, c in xep:
            f = " ".join(t for t in self.ten_tu[c].split() if t not in self.loai_tu)
            ft = set(f.split())
            if not ft:
                continue
            if any(ft <= set(r.split()) for r in ra):     # đã có cặp từ chứa từ này
                continue
            ra = [r for r in ra if not set(r.split()) <= ft]
            ra.append(f)
            if len(ra) == k:
                break
        return ra

    def lang_gieng(self, listing_id: str, k: int, nguong: float = NGUONG_GIONG) -> List[Tuple[int, float]]:
        """k sản phẩm giống nhất CÙNG LOẠI HÀNG, khác shop, đạt ngưỡng."""
        i = self.vi_tri.get(listing_id)
        if i is None or self.x is None:
            return []
        loai = self.dong[i].get("product_type_id")
        sim = (self.x @ self.x[i].T).toarray().ravel()
        ung = sorted(((float(sim[j]), j) for j, r in enumerate(self.dong)
                      if j != i and r.get("product_type_id") == loai
                      and r["shop_id"] != self.dong[i]["shop_id"] and sim[j] >= nguong), reverse=True)
        # Đối thủ trực tiếp phải có điểm chung có nghĩa, không chỉ giống nhau ở văn mẫu mô tả.
        return [(j, s) for s, j in ung if s >= NGUONG_KHONG_LY_DO or self._ly_do(i, j, 1)][:k]

    def doi_thu_truc_tiep(self, listing_id: str, k: int = SO_DOI_THU) -> List[Dict[str, Any]]:
        i = self.vi_tri.get(listing_id)
        return [{
            "product_id": self.dong[j]["listing_id"],
            "shop_id": self.dong[j]["shop_id"],
            "shop_name": self.dong[j].get("shop_name"),
            "title": self.dong[j].get("title"),
            "price_vnd": self.dong[j].get("price_vnd"),
            "est_sales_90d": self.dong[j].get("est_sales_90d") or 0,
            "similarity": round(s, 3),
            "reasons": self._ly_do(i, j),
        } for j, s in self.lang_gieng(listing_id, k)]


def _phan_vi_trong_so(gia: np.ndarray, w: np.ndarray, q: float) -> float:
    thu_tu = np.argsort(gia)
    g, ww = gia[thu_tu], w[thu_tu]
    tich = np.cumsum(ww) - ww / 2
    return float(np.interp(q * ww.sum(), tich, g))


def gia_de_xuat(may: MayGiong, listing_id: str, k: int = K_GIA) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Giá của đối thủ trực tiếp (kNN theo độ giống), pha với mặt bằng cùng loại theo độ tin cậy.
    Trả (kết quả, lý do nếu không có)."""
    i = may.vi_tri.get(listing_id)
    lg = [(j, s) for j, s in may.lang_gieng(listing_id, k) if may.dong[j].get("price_vnd")]
    if i is None or len(lg) < TOI_THIEU_GIA:
        return None, (f"Mới tìm được {len(lg)} sản phẩm đủ giống cùng loại trên sàn, "
                      f"cần ít nhất {TOI_THIEU_GIA} để AI tính giá đối thủ trực tiếp")
    gia = np.array([float(may.dong[j]["price_vnd"]) for j, _ in lg])
    sim = np.array([s for _, s in lg])
    cung_loai = np.array([float(r["price_vnd"]) for r in may.dong
                          if r.get("product_type_id") == may.dong[i].get("product_type_id")
                          and r["shop_id"] != may.dong[i]["shop_id"] and r.get("price_vnd")])
    # Đo ở scripts/danh_gia_doi_thu_ai.py: kNN đơn lẻ dao động hơn trung vị cùng loại; pha theo độ tin cậy thì không kém.
    a = len(lg) / (len(lg) + TRON_GIA) * min(1.0, float(sim.mean()) / 0.5)
    tron = lambda q: int(round((a * _phan_vi_trong_so(gia, sim, q) + (1 - a) * float(np.quantile(cung_loai, q))) / 1000) * 1000)
    giua, thap, cao = tron(0.5), tron(0.25), tron(0.75)
    tin = "high" if len(lg) >= 6 and sim.mean() >= 0.35 else "medium" if sim.mean() >= 0.2 else "low"
    return {
        "suggested_vnd": giua,
        "low_vnd": min(thap, giua),
        "high_vnd": max(cao, giua),
        "confidence": tin,
        "rival_weight": round(a, 2),
        "n_neighbors": len(lg),
        "avg_similarity": round(float(sim.mean()), 3),
        "rival_price_min_vnd": int(gia.min()),
        "rival_price_max_vnd": int(gia.max()),
        "neighbors": [{
            "product_id": may.dong[j]["listing_id"],
            "shop_name": may.dong[j].get("shop_name"),
            "title": may.dong[j].get("title"),
            "price_vnd": may.dong[j]["price_vnd"],
            "est_sales_90d": may.dong[j].get("est_sales_90d") or 0,
            "similarity": round(s, 3),
        } for j, s in lg],
        "method": "knn-tfidf-blend",
    }, None


def shop_canh_tranh_nhat(may: MayGiong, cua_toi: Sequence[str], k: int = 3) -> List[Dict[str, Any]]:
    """Shop xuất hiện nhiều nhất trong đối thủ trực tiếp của các sản phẩm của tôi."""
    gom: Dict[str, Dict[str, Any]] = {}
    for pid in cua_toi:
        for j, s in may.lang_gieng(pid, SO_DOI_THU):
            r = may.dong[j]
            g = gom.setdefault(r["shop_id"], {"shop_id": r["shop_id"], "shop_name": r.get("shop_name"),
                                              "overlap": 0, "best_similarity": 0.0, "_sp": set()})
            g["_sp"].add(pid)
            g["best_similarity"] = max(g["best_similarity"], round(s, 3))
    for g in gom.values():
        g["overlap"] = len(g.pop("_sp"))
    return sorted(gom.values(), key=lambda g: (-g["overlap"], -g["best_similarity"]))[:k]


_CACHE: Dict[str, Any] = {"khoa": None, "luc": 0.0, "may": None}


def may_giong(dong: Sequence[Dict[str, Any]], doc_mo_ta, doc_ten_tag) -> MayGiong:
    """Dựng lại máy khi tập sản phẩm đổi hoặc quá CACHE_GIAY. doc_mo_ta(ids) -> {id: mô tả}, doc_ten_tag(slugs) -> {slug: tên}."""
    # shortcut: cache trong RAM của một tiến trình, nhiều worker thì mỗi worker tự dựng; sàn lớn thì chuyển sang Redis.
    khoa = hash(tuple(sorted((r["listing_id"], r.get("title"), r.get("price_vnd"), r.get("est_sales_90d")) for r in dong)))
    if _CACHE["khoa"] != khoa or time.time() - _CACHE["luc"] > CACHE_GIAY:
        _CACHE.update(khoa=khoa, luc=time.time(), may=MayGiong(
            dong, doc_mo_ta([r["listing_id"] for r in dong]), doc_ten_tag({t for r in dong for t in r.get("tags") or []})))
    return _CACHE["may"]
