"""
Định giá theo sản phẩm tương đồng (comparable listings / k-nearest-neighbours).

Ý tưởng: thay vì nhân hệ số theo từ khoá (dễ nhận nhầm "màu bạc" thành kim loại bạc,
"đồng hồ" thành chất liệu đồng...), ta tìm các tin đăng THẬT giống nhất với sản phẩm
seller định bán rồi lấy phân vị giá có trọng số của chúng. Loại sản phẩm, thương hiệu,
chất liệu, dung tích/kích thước... đều nằm sẵn trong tiêu đề, nên các tin tương đồng
tự phản ánh những yếu tố đó mà không cần luật viết tay.

Nguồn dữ liệu:
  - Tập TMĐT bên ngoài (Tiki, ~45k tin) do ExternalMarketProvider nạp.
  - Sản phẩm đang bán trên chính sàn (MongoDB), làm mới mỗi LIVE_REFRESH_S giây.
"""

import math
import re
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, vstack
from sklearn.feature_extraction.text import TfidfVectorizer

from app.services.f42.vi_text import clean_tokens, normalize_nfc, strip_accents

# ---------------------------------------------------------------------------
# Tham số (đã hiệu chỉnh bằng backtest trên tập test Tiki, xem scripts/backtest)
# ---------------------------------------------------------------------------
TOP_K = 40                 # số ứng viên lấy ra trước khi lọc
MIN_SIM = 0.18             # độ tương đồng cosine tối thiểu để được coi là "tương đồng"
REL_SIM = 0.55             # chỉ giữ tin có sim >= REL_SIM * sim của tin giống nhất
MIN_COMPARABLES = 3        # dưới mức này coi như không đủ dữ liệu
PRICE_MIN, PRICE_MAX = 1_000, 200_000_000
LIVE_REFRESH_S = 300
MARKET_FRESH_DAYS = 14     # chỉ dùng giá cào trong 14 ngày gần nhất

# Từ đứng đầu tiêu đề nhưng không phải tên sản phẩm
_LEADING_NOISE = {
    "new", "hot", "sale", "combo", "set", "cai", "chiec", "doi", "hang", "freeship",
    "sieu", "giam", "gia", "chinh", "hang", "mau", "moi", "loai", "1", "2", "3",
}
# Từ không nên trở thành "thương hiệu"
_GENERIC_LATIN = {
    "size", "free", "new", "hot", "sale", "mini", "pro", "max", "plus", "cotton", "inox",
    "kaki", "jean", "jeans", "unisex", "nam", "nu", "tre", "len", "da", "pu", "led", "usb",
    "set", "combo", "cao", "cap", "basic", "style", "form", "oversize", "hang", "chinh",
    "ml", "cm", "mm", "kg", "gr", "lit", "the", "and", "for", "with", "big", "full",
    "ban", "loai", "mau", "kem", "tui", "vi", "ao", "quan", "giay", "dep", "mu", "non",
}
# Hư từ không được đứng đầu/cuối một thẻ
_EDGE_STOP = {"cho", "danh", "va", "voi", "cua", "la", "cac", "nhung", "tu", "den", "the", "kem", "co", "khong"}
# Cam kết rủi ro (khớp content_validator): không gợi ý làm thẻ
_RISKY_TAG = ("chinh hang", "hang hieu", "authentic", "bao hanh", "tot nhat", "re nhat")

# Cụm từ không mang giá trị gợi ý thẻ
_TAG_STOP = {
    "chinh hang", "hang chinh", "gia re", "cao cap", "chat luong", "hang moi", "mau moi",
    "sieu re", "free ship", "freeship", "hang nhap", "nhap khau", "giao mau", "ngau nhien",
    "nhieu mau", "san", "tot", "dep", "re", "hot", "new", "sale", "loai", "mau", "size",
}


@dataclass
class Comparable:
    title: str
    price: float
    similarity: float
    source: str           # "tiki" | "vietcraft"
    sold: int = 0
    group: str = ""
    category_ids: List[str] = field(default_factory=list)


@dataclass
class ComparableEstimate:
    comparables: List[Comparable]
    p25: int = 0
    p50: int = 0
    p75: int = 0
    p90: int = 0
    n_used: int = 0
    n_effective: float = 0.0
    mean_similarity: float = 0.0
    spread: float = 0.0             # p75 / p25
    confidence: str = "none"        # high | medium | low | none
    detected_product: Optional[str] = None
    detected_brand: Optional[str] = None
    brand_median: Optional[int] = None
    dominant_group: Optional[str] = None
    category_votes: Dict[str, float] = field(default_factory=dict)
    match_note: Optional[str] = None   # vd chưa có dữ liệu đúng mẫu máy, đang tham khảo cùng hãng

    @property
    def usable(self) -> bool:
        return self.confidence != "none"


# Cách viết liền/viết tắt hay gặp → dạng chuẩn ("iphone 18 promax" = "iPhone 18 Pro Max")
_JOINED = {"promax": "pro max", "prm": "pro max", "proplus": "pro plus"}


def _prep(text: str) -> str:
    """Chuẩn hoá tiêu đề cho truy hồi: bỏ dấu, thường hoá, bỏ ký tự đặc biệt, tách chữ viết liền."""
    t = strip_accents(normalize_nfc(text or "")).replace("+", " plus ")
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = " ".join(_JOINED.get(w, w) for w in t.split())
    # Dòng máy viết liền số đời: "reno15" = "reno 15", "iphone15" = "iphone 15" (mã ngắn như s25, a17 giữ nguyên)
    t = re.sub(r"\b([a-z]{4,})(\d{1,4})\b", r"\1 \2", t)
    return t.strip()


# ---------------------------------------------------------------- nhận diện đúng mẫu (hãng + đời)
_MODEL_QUALIFIERS = {"pro", "max", "plus", "mini", "ultra", "lite", "se", "fe", "air", "note", "neo"}
_UNIT_RE = re.compile(r"^\d+(gb|tb|mb|ml|l|cm|mm|m|kg|g|gr|w|mah|inch|hz|k)$")
_CODE_RE = re.compile(r"^(?=.{2,})[a-z]{0,3}\d{1,4}[a-z]{0,2}$")   # 18, s25, a17, c85, 14t — không lấy "2" (áo 2 dây)
EXACT_MIN_SOLD = 20      # 1 tin ĐÚNG mẫu đã bán >= 20 cái là đủ căn cứ (Tiki gộp mọi người bán vào 1 tin)


def _contains(text_prepped: str, phrase_prepped: str) -> bool:
    return f" {phrase_prepped} " in f" {text_prepped} "


# Từ đầu quá chung, không đủ để coi là cùng loại ("Bộ ấm chén" ≠ "Bộ quần áo")
_GENERIC_HEAD = {"bo", "do", "phu", "san", "hop"}


def _head_tokens(prep: str) -> List[str]:
    """2 từ có nghĩa đầu tiêu đề — tiếng Việt đặt danh từ chính ở đầu ("dong ho", "nen thom")."""
    return [t for t in prep.split() if t not in _LEADING_NOISE and not any(ch.isdigit() for ch in t)][:2]


def _same_product_type(q_head: List[str], c_prep: str) -> bool:
    """
    Tin c cùng loại với truy vấn khi MỞ ĐẦU bằng cùng danh từ chính ("giày nam chelsea" ~
    "giày boots"); từ đầu quá chung ("bộ", "đồ") thì phải trùng cả 2 từ đầu.
    Chỉ so ở ĐẦU tiêu đề: "Balo laptop" không dùng để định giá "Laptop Dell", "bờm đồng hồ la mã"
    hay "hình xăm đồng hồ" không dùng cho "đồng hồ nam".
    """
    if not q_head:
        return True
    c_head = _head_tokens(c_prep)
    if not c_head:
        return False
    if q_head[0] in _GENERIC_HEAD:
        return c_head == q_head
    return c_head[0] == q_head[0]


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cw = np.cumsum(w) - 0.5 * w
    cw /= w.sum()
    return float(np.interp(q, cw, v))


def round_price_nice(val: float) -> int:
    """Làm tròn giá theo thói quen niêm yết: <100k → nghìn, <1tr → 5 nghìn, còn lại → 10 nghìn."""
    if val <= 0:
        return 0
    step = 1_000 if val < 100_000 else (5_000 if val < 1_000_000 else 10_000)
    return int(math.floor(val / step + 0.5) * step)  # nửa lên, không làm tròn về số chẵn


_ACCESSORY_MARKERS = [
    # Phụ kiện công nghệ / điện tử / gia dụng
    "tui dung", "tui deo", "tui chong soc", "bao da", "bao dung", "op lung", "op dien thoai", "op iphone", "op ipad", "op airpods", "op samsung", "op xiaomi", "op oppo",
    "kinh cuong luc", "cuong luc", "mieng dan", "dan man hinh", "day deo", "day sac",
    "cap sac", "cu sac", "dock sac", "khay nhom", "khay nuong", "khay lot", "khay giay",
    "giay nen", "giay bac", "vi nuong", "khoa buom", "khoa kim", "day dong ho",
    "chot dong ho", "khoa dong ho", "dung phu kien", "hop dung", "gia do", "chan de", "mieng lot", "de lot", "lot ly",
    "lot chuot", "vo boc", "nap day", "dau chuyen", "jack chuyen", "filter", "nap ong kinh",
    "mang loc", "loi loc", "khung vien", "nap lung", "pin thay the", "pin du phong",
    "adapter", "remote", "remot", "dieu khien", "de giu", "mieng dan camera", "kinh bao ve",
    # Phụ kiện thời trang / may mặc (không dùng đai nịt, cà vạt để định giá váy đầm)
    "dai nit", "that lung", "ca vat", "caravat", "no deo co", "cai ao", "tram cai ao",
    "khuyen tai", "bong tai", "vong tay", "day chuyen", "day nit", "tat chan", "tat vo", "vo chan", "gang tay",
    "khan quang", "mieng dan nguc", "day ao", "moc ao", "kep toc", "bang do", "nit dam"
]


def _close(a: float, b: float, tol: float = 0.05) -> bool:
    return b > 0 and abs(a - b) / b <= tol


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load_market_rows(db_data: Any, days: int = MARKET_FRESH_DAYS) -> List[Dict[str, Any]]:
    """
    Giá thị trường còn mới để so: market_price_listing (cào 2 lần/ngày) + external_market_products
    (bộ dữ liệu Tiki đã nạp sẵn). Chỉ lấy tin HỢP LỆ: đã có người mua hoặc đánh giá, giá trong khoảng.
    """
    import datetime as _dt

    since = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    rows: Dict[str, Dict[str, Any]] = {}

    def _add(key: str, title: str, price: float, sold: float) -> None:
        if not (PRICE_MIN <= price <= PRICE_MAX):
            return
        prep = _prep(title)
        if len(prep) < 3:
            return
        rows[key] = {"title": normalize_nfc(title), "prep": prep, "price": price, "sold": int(sold)}

    for d in db_data["external_market_products"].find(
        {}, {"external_id": 1, "title": 1, "price_vnd": 1, "sold_count": 1, "review_count": 1}
    ):
        sold, reviews = _num(d.get("sold_count")), _num(d.get("review_count"))
        if sold >= 1 or reviews >= 1:
            _add(str(d.get("external_id") or d["_id"]), str(d.get("title") or ""), _num(d.get("price_vnd")), sold)
    # Bản mới cào ghi đè cùng sản phẩm (cùng khoá tiki_<id>) vì giá mới hơn
    for d in db_data["market_price_listing"].find(
        {"is_valid": True, "last_seen_at": {"$gte": since}}, {"title": 1, "price": 1, "sold": 1}
    ):
        _add(str(d["_id"]), str(d.get("title") or ""), _num(d.get("price")), _num(d.get("sold")))
    return list(rows.values())


def _is_accessory(prep: str) -> bool:
    """
    Phụ kiện: có dấu hiệu trong danh sách, hoặc tiêu đề MỞ ĐẦU bằng "ốp" (ốp chống sốc/ốp dẻo/ốp da...).
    "Ốp chống sốc cho iPhone 17 Pro Max" 29k từng lọt vào nhóm "đúng mẫu" cùng máy 32,5 triệu.
    """
    return prep.startswith("op ") or any(_contains(prep, m) for m in _ACCESSORY_MARKERS)


class ComparableIndex:
    """Chỉ mục TF-IDF (từ + cụm 2 từ) trên tiêu đề sản phẩm, singleton lười nạp."""

    _instance: Optional["ComparableIndex"] = None
    _lock = threading.Lock()

    def __init__(self, df: pd.DataFrame):
        df = df.copy()
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df = df[(df["price"] >= PRICE_MIN) & (df["price"] <= PRICE_MAX)]
        df["title"] = df["title"].astype(str).map(normalize_nfc)
        df["prep"] = df["title"].map(_prep)
        df = df[df["prep"].str.len() >= 3]
        df = df.drop_duplicates(subset=["prep", "price"])
        df["sold"] = pd.to_numeric(df.get("sold", 0), errors="coerce").fillna(0).astype(int)
        df = df.reset_index(drop=True)

        self.titles: List[str] = df["title"].tolist()
        self.preps: List[str] = df["prep"].tolist()
        self.prices = df["price"].to_numpy(dtype=float)
        self.sold = df["sold"].to_numpy(dtype=int)
        self.groups: List[str] = df["group"].astype(str).tolist() if "group" in df else [""] * len(df)

        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2), min_df=2, max_df=0.4, sublinear_tf=True, dtype=np.float32
        )
        self.matrix: csr_matrix = self.vectorizer.fit_transform(self.preps)
        self.doc_freq = np.asarray((self.matrix > 0).sum(axis=0)).ravel()
        self.vocab = self.vectorizer.vocabulary_
        self.n_docs = self.matrix.shape[0]

        # Phần dữ liệu sống của sàn
        # (rows, matrix) gán MỘT lần: endpoint chạy trong threadpool, gán 2 biến riêng lẻ từng để
        # luồng khác thấy matrix cũ + rows mới → IndexError bị nuốt, mất phần dữ liệu sàn.
        self._live_ts = 0.0
        self._live: Tuple[List[Dict[str, Any]], Optional[csr_matrix]] = ([], None)
        self._live_lock = threading.Lock()
        # Giá thị trường mới cào 2 lần/ngày (market_crawler.py), cùng cơ chế snapshot như trên
        self._market_ts = 0.0
        self._market: Tuple[List[Dict[str, Any]], Optional[csr_matrix]] = ([], None)
        self._market_lock = threading.Lock()

    # ------------------------------------------------------------------ build
    @classmethod
    def get(cls) -> Optional["ComparableIndex"]:
        if cls._instance is not None:
            return cls._instance
        with cls._lock:
            if cls._instance is None:
                df = cls._load_external_corpus()
                if df is not None and len(df) > 50:
                    cls._instance = ComparableIndex(df)
        return cls._instance

    @staticmethod
    def _load_external_corpus() -> Optional[pd.DataFrame]:
        from app.services.f42.external_market import TIKI23_PATH, TIKI26_PATH

        frames = []
        for path in (TIKI23_PATH, TIKI26_PATH):
            if path.exists():
                cols = ["group", "title", "price", "sold"]
                frames.append(pd.read_parquet(path, columns=cols))
        if not frames:
            return None
        return pd.concat(frames, ignore_index=True)

    def refresh_live(self, db_live: Any) -> None:
        """Nạp sản phẩm đang bán công khai trên sàn, giá thật lấy từ product_variants.retail_price."""
        if db_live is None or time.time() - self._live_ts < LIVE_REFRESH_S:
            return
        # Chỉ một luồng nạp lại; các luồng khác dùng tạm bản cũ thay vì cùng quét 20k sản phẩm
        if not self._live_lock.acquire(blocking=False):
            return
        try:
            self._refresh_live_locked(db_live)
        finally:
            self._live_lock.release()

    def _refresh_live_locked(self, db_live: Any) -> None:
        if time.time() - self._live_ts < LIVE_REFRESH_S:
            return
        from app.services.f42.pricing_engine import fetch_live_listings, fetch_sold_items

        sold = fetch_sold_items(db_live)
        rows: List[Dict[str, Any]] = []
        live_price: Dict[Any, float] = {}
        for r in fetch_live_listings(db_live):
            if not (PRICE_MIN <= r["price"] <= PRICE_MAX):
                continue
            prep = _prep(r["title"])
            if len(prep) < 3:
                continue
            s_info = sold.get(r["_id"])
            live_price[r["_id"]] = r["price"]
            rows.append({"title": r["title"], "prep": prep, "price": r["price"], "category_ids": r["category_ids"],
                         # đã bán được ở đúng giá đang niêm yết → nặng ký hơn khi so giá
                         "sold": s_info["qty"] if s_info and _close(s_info["price"], r["price"]) else 0})
        # Giá đã bán thật nhưng khác giá đang niêm yết (đổi giá) hoặc sản phẩm đã ngừng bán: thêm dòng riêng
        for pid, s_info in sold.items():
            cur = live_price.get(pid)
            if cur is not None and _close(s_info["price"], cur):
                continue
            prep = _prep(s_info["title"])
            if len(prep) < 3 or not (PRICE_MIN <= s_info["price"] <= PRICE_MAX):
                continue
            rows.append({"title": s_info["title"], "prep": prep, "price": s_info["price"], "category_ids": [],
                         "sold": s_info["qty"], "source": "vietcraft_sold"})

        matrix = self.vectorizer.transform([r["prep"] for r in rows]) if rows else None
        self._live = (rows, matrix)
        self._live_ts = time.time()

    def invalidate_market(self) -> None:
        """Buộc lần refresh_market kế tiếp nạp lại (vừa cào thêm theo yêu cầu)."""
        self._market_ts = 0.0

    def refresh_market(self, db_data: Any) -> None:
        """Nạp giá thị trường hợp lệ (đã có người mua/đánh giá) cào trong MARKET_FRESH_DAYS ngày."""
        if db_data is None or time.time() - self._market_ts < LIVE_REFRESH_S:
            return
        if not self._market_lock.acquire(blocking=False):
            return
        try:
            if time.time() - self._market_ts < LIVE_REFRESH_S:
                return
            rows = load_market_rows(db_data)
            matrix = self.vectorizer.transform([r["prep"] for r in rows]) if rows else None
            self._market = (rows, matrix)
            self._market_ts = time.time()
        except Exception as exc:  # noqa: BLE001 — DB lỗi thì dùng tạm snapshot cũ, thử lại lượt sau
            import logging
            logging.getLogger(__name__).warning("f42.refresh_market_failed: %s: %s", type(exc).__name__, exc)
            self._market_ts = time.time()
        finally:
            self._market_lock.release()

    # ------------------------------------------------------------------ query
    def _is_brandish(self, tok: str) -> bool:
        """Từ Latin hiếm trong toàn tập (hãng/dòng máy: iphone, galaxy, redmi...), không phải từ chung."""
        if not re.fullmatch(r"[a-z]{3,}", tok) or tok in _GENERIC_LATIN or tok in _MODEL_QUALIFIERS:
            return False
        col = self.vocab.get(tok)
        return col is None or self.doc_freq[col] <= 0.005 * self.n_docs

    def model_signature(self, query: str) -> List[str]:
        """
        Tên mẫu trong tiêu đề: hãng/dòng + số đời (+ pro/max/plus...), vd ["iphone","18","pro","max"].
        Rỗng nếu tiêu đề không nêu mẫu có số đời (khi đó so theo loại sản phẩm như cũ).
        Bỏ qua dung lượng/kích thước (256gb, 500ml): cùng mẫu khác dung lượng vẫn là căn cứ giá.
        """
        raw = [t for t in _prep(query).split()]
        # chỉ lấy từ không dấu ở bản gốc (hãng/mã máy viết Latin), tránh "ao thun" gõ không dấu
        orig = set(_prep(" ".join(t for t in clean_tokens(query) if t == strip_accents(t))).split()) | {"pro", "max", "plus"}
        best: List[str] = []
        i = 0
        while i < len(raw):
            if raw[i] in orig and self._is_brandish(raw[i]):
                phrase = [raw[i]]
                j = i + 1
                while j < len(raw) and (self._is_brandish(raw[j]) or raw[j] in _MODEL_QUALIFIERS
                                        or (_CODE_RE.match(raw[j]) and not _UNIT_RE.match(raw[j]))):
                    phrase.append(raw[j])
                    j += 1
                if any(any(ch.isdigit() for ch in t) for t in phrase) and len(phrase) > len(best):
                    best = phrase
                i = j
            else:
                i += 1
        return best

    @staticmethod
    def _type_matcher(prep: str):
        """Hàm kiểm tra 1 tin cùng loại sản phẩm (2 từ đầu tiêu đề)."""
        q_head = _head_tokens(prep)
        return lambda c_prep: _same_product_type(q_head, c_prep)

    def _snapshot_hits(self, snapshot, q, match, q_is_acc, source: str, limit: int) -> List[Comparable]:
        """Tin tương đồng trong một snapshot (sàn VietCraft / giá mới cào), có bộ đếm RIÊNG."""
        rows, matrix = snapshot  # đọc snapshot một lần
        if matrix is None or not rows:
            return []
        sims = (matrix @ q.T).toarray().ravel()
        k = min(limit * 2, len(sims))
        idx = np.argpartition(-sims, k - 1)[:k]
        out: List[Comparable] = []
        for i in idx[np.argsort(-sims[idx])]:
            if sims[i] <= 0:
                continue
            r = rows[i]
            if not match(r["prep"]):
                continue
            c_is_acc = _is_accessory(r["prep"])
            if q_is_acc != c_is_acc:  # không lấy phụ kiện định giá hàng chính và ngược lại
                continue
            out.append(Comparable(
                title=r["title"], price=r["price"], similarity=float(sims[i]), source=r.get("source", source),
                sold=int(r.get("sold") or 0), category_ids=r.get("category_ids") or [],
            ))
            if len(out) >= limit:
                break
        return out

    def search(self, query: str, top_k: int = TOP_K, exclude_idx: Optional[int] = None) -> List[Comparable]:
        return self.search_detail(query, top_k, exclude_idx)[0]

    def _quals_after_model(self, toks: List[str]) -> set:
        """Hậu tố phiên bản đứng sau số đời máy: "iphone 17 pro max" → {pro, max}; "iphone 17" → {}."""
        for i, t in enumerate(toks):
            if _CODE_RE.match(t) and not _UNIT_RE.match(t) and any(ch.isdigit() for ch in t):
                out = set()
                for u in toks[i + 1:]:
                    if u not in _MODEL_QUALIFIERS:
                        break
                    out.add(u)
                return out
        return set()

    def query_brand(self, query: str, sig: Optional[List[str]] = None) -> Optional[str]:
        """Thương hiệu Latin trong tiêu đề (Tefal, Anessa, Nike...) khi tiêu đề không nêu mẫu có số đời."""
        orig = {strip_accents(t) for t in clean_tokens(query) if t == strip_accents(t)}
        for t in _prep(query).split():
            if t in orig and t not in (sig or []) and self._is_brandish(t):
                return t
        return None

    def search_detail(self, query: str, top_k: int = TOP_K, exclude_idx: Optional[int] = None):
        """
        Tin để so giá + ghi chú khi phải nới điều kiện + cờ "đúng mẫu".
        Lọc theo bậc, bậc trên đủ dữ liệu thì dùng, không thì lùi và GHI RÕ thiếu gì:
          đúng mẫu (iPhone 17 ≠ 17 Pro) → đúng hãng + chất liệu → đúng hãng → đúng chất liệu → cùng loại.
        Kiểm thử 72 sản phẩm thật: chảo Tefal từng lấy giá chảo Elmich, bát melamine lấy giá bát gốm Bát
        Tràng, "Bàn gỗ óc chó" lấy giá "Bàn chải gỗ", iPhone 17 lấy giá iPhone 17 Pro Max.
        """
        prep = _prep(query)
        if not prep:
            return [], None, False
        q = self.vectorizer.transform([prep])
        if q.nnz == 0:
            return [], None, False
        q_is_acc = _is_accessory(prep)
        q_head = _head_tokens(prep)
        type_strict = (lambda c: _head_tokens(c) == q_head) if len(q_head) == 2 else (lambda c: _same_product_type(q_head, c))
        type_loose = lambda c: _same_product_type(q_head, c)  # noqa: E731
        collect = lambda m: self._collect(q, m, q_is_acc, top_k, exclude_idx)  # noqa: E731

        sig = self.model_signature(query)
        if sig:
            need, q_quals = set(sig), self._quals_after_model(prep.split())
            exact = collect(lambda c: need <= set(c.split()) and self._quals_after_model(c.split()) == q_quals)
            if exact:
                return exact, None, True
            brand = sig[0]
            if self._brand_known(brand, exclude_idx):
                return (collect(lambda c: brand in c.split() and type_loose(c)),
                        f"Chưa có dữ liệu giá đúng mẫu \"{' '.join(sig)}\" — đang tham khảo sản phẩm cùng hãng/cùng loại, "
                        "giá có thể chênh nhiều so với đúng mẫu.", False)

        from app.services.f42.pricing_engine import detect_material
        brand = None if sig else self.query_brand(query)
        material = detect_material(query)
        attrs = []
        if brand:
            attrs.append((f"thương hiệu {brand.capitalize()}", lambda c, b=brand: b in c.split()))
        if material:
            mp = _prep(material)
            attrs.append((f"chất liệu {material.lower()}", lambda c, m=mp: _contains(c, m)))
        # Thử từ đủ điều kiện nhất tới lỏng nhất; mỗi mức thử loại khớp 2 chữ đầu trước, 1 chữ đầu sau
        combos = [attrs] + ([[a] for a in attrs] if len(attrs) > 1 else []) + ([[]] if attrs else [])
        last: List[Comparable] = []
        for combo in combos or [[]]:
            for typ in (type_strict, type_loose):
                hits = collect(lambda c, cb=combo, t=typ: t(c) and all(f(c) for _, f in cb))
                if len(hits) >= MIN_COMPARABLES:
                    missing = [name for name, _ in attrs if all(name != n for n, _ in combo)]
                    note = (f"Chưa đủ dữ liệu đúng {', '.join(missing)} — đang tham khảo sản phẩm cùng loại khác "
                            f"{'thương hiệu' if any(m.startswith('thương hiệu') for m in missing) else 'chất liệu'}, "
                            "giá có thể chênh nhiều.") if missing else None
                    return hits, note, False
                if len(hits) > len(last):
                    last = hits
        return last, None, False

    def _brand_known(self, brand: str, exclude_idx: Optional[int] = None) -> bool:
        col = self.vocab.get(brand)
        df = int(self.doc_freq[col]) if col is not None else 0
        if exclude_idx is not None and brand in self.preps[exclude_idx].split():
            df -= 1
        if df >= 1:
            return True
        return any(brand in r["prep"].split() for snap in (self._market, self._live) for r in snap[0])

    @staticmethod
    def _diversify(comps: List[Comparable], per_family: int = 2) -> List[Comparable]:
        """
        Tối đa `per_family` tin mỗi dòng sản phẩm (7 chữ đầu tiêu đề): 4 biến thể Logitech G304 hay 4 mùi
        Yankee Candle 1,2 triệu từng chiếm hết kết quả "chuột không dây", "nến sáp đậu nành".
        """
        kept: Dict[str, List[float]] = defaultdict(list)
        out = []
        for c in comps:
            # cùng 7 chữ đầu VÀ giá lệch < 10% mới coi là biến thể lặp lại; khác giá nhiều là bằng chứng riêng
            key = " ".join(_prep(c.title).split()[:7])
            close = [p for p in kept[key] if abs(p - c.price) <= 0.10 * max(p, c.price)]
            if len(close) < per_family:
                kept[key].append(c.price)
                out.append(c)
        return out

    def _collect(self, q, match, q_is_acc: bool, top_k: int, exclude_idx: Optional[int]) -> List[Comparable]:
        out: List[Comparable] = []
        sims = (self.matrix @ q.T).toarray().ravel()
        if exclude_idx is not None:
            sims[exclude_idx] = 0.0
        k = min(top_k * 3, len(sims))
        idx = np.argpartition(-sims, k - 1)[:k]
        sorted_idx = idx[np.argsort(-sims[idx])]
        for i in sorted_idx:
            if sims[i] <= 0:
                continue
            c_prep = self.preps[i]
            if not match(c_prep):
                continue
            c_is_acc = _is_accessory(c_prep)
            # Không dùng phụ kiện để định giá thiết bị chính
            if not q_is_acc and c_is_acc:
                continue
            # Ngược lại, không dùng thiết bị chính để định giá phụ kiện
            if q_is_acc and not c_is_acc:
                continue

            out.append(Comparable(
                title=self.titles[i], price=float(self.prices[i]), similarity=float(sims[i]),
                source="tiki", sold=int(self.sold[i]), group=self.groups[i],
            ))
            if len(out) >= top_k:
                break

        # Mỗi nguồn một bộ đếm riêng: trước đây sàn VietCraft dùng chung bộ đếm với Tiki cũ (thường
        # đã đủ top_k) nên tin của sàn gần như không bao giờ được so.
        fresh = self._snapshot_hits(self._market, q, match, q_is_acc, "tiki_fresh", top_k)
        if fresh:
            # Cùng sản phẩm có trong dữ liệu Tiki cũ và bản mới cào: chỉ giữ giá mới
            fresh_preps = {_prep(c.title) for c in fresh}
            out = [c for c in out if c.source != "tiki" or _prep(c.title) not in fresh_preps]
        out += fresh
        out += self._snapshot_hits(self._live, q, match, q_is_acc, "vietcraft", top_k)

        out.sort(key=lambda c: c.similarity, reverse=True)
        return self._diversify(out)[:top_k]

    # --------------------------------------------------------------- estimate
    def estimate(self, query: str, exclude_idx: Optional[int] = None) -> ComparableEstimate:
        cands, note, exact_tier = self.search_detail(query, exclude_idx=exclude_idx)
        if not cands:
            return ComparableEstimate(comparables=[], match_note=note)

        top_sim = cands[0].similarity
        # Đã phải nới điều kiện (ghi chú) thì các tin đều chỉ "cùng loại": không lọc thêm theo tin giống nhất,
        # nếu không 1 tin rất giống (thớt teak) sẽ loại hết các tin còn lại (thớt gỗ khác) → không ra giá.
        floor = MIN_SIM if note else max(MIN_SIM, REL_SIM * top_sim)
        comps = [c for c in cands if c.similarity >= floor]
        sig = self.model_signature(query)
        is_exact = exact_tier
        exact = is_exact and sum(c.sold for c in comps) >= EXACT_MIN_SOLD
        if len(comps) < MIN_COMPARABLES and not exact:
            return ComparableEstimate(comparables=comps, n_used=len(comps),
                                      detected_product=self._detect_product(query, comps or cands[:5]))

        logp = np.log(np.array([c.price for c in comps]))
        sims = np.array([c.similarity for c in comps])
        sold = np.array([c.sold for c in comps])
        # Tin giống hơn và tin đã thực sự bán được (giá thị trường chấp nhận) nặng ký hơn
        w = sims ** 2 * (1.0 + 0.15 * np.log1p(sold))

        # Lọc ngoại lai bằng MAD trên log-giá
        med = weighted_quantile(logp, w, 0.5)
        mad = weighted_quantile(np.abs(logp - med), w, 0.5)
        if mad > 0:
            keep = np.abs(logp - med) <= 3.0 * 1.4826 * mad
            if keep.sum() >= MIN_COMPARABLES:
                comps = [c for c, k in zip(comps, keep) if k]
                logp, w, sims = logp[keep], w[keep], sims[keep]

        p25 = math.exp(weighted_quantile(logp, w, 0.25))
        p50 = math.exp(weighted_quantile(logp, w, 0.50))
        p75 = math.exp(weighted_quantile(logp, w, 0.75))
        p90 = math.exp(weighted_quantile(logp, w, 0.90))
        n_eff = float(w.sum() ** 2 / (w ** 2).sum())
        mean_sim = float(np.average(sims, weights=w))
        spread = p75 / p25 if p25 > 0 else 99.0

        if n_eff >= 6 and mean_sim >= 0.40 and spread <= 2.2:
            confidence = "high"
        elif n_eff >= 3.5 and mean_sim >= 0.28 and spread <= 3.5:
            confidence = "medium"
        else:
            confidence = "low"
        if exact and confidence == "low":
            # Đúng mẫu máy và đã bán thật nhiều: căn cứ mạnh dù số tin ít (Tiki gộp người bán vào 1 tin)
            confidence = "medium"
        match_note = note
        if match_note:  # phải nới điều kiện (khác mẫu / thương hiệu / chất liệu) → căn cứ yếu
            confidence = "low"

        est = ComparableEstimate(
            comparables=comps,
            p25=round_price_nice(p25), p50=round_price_nice(p50),
            p75=round_price_nice(p75), p90=round_price_nice(p90),
            n_used=len(comps), n_effective=round(n_eff, 1),
            mean_similarity=round(mean_sim, 3), spread=round(spread, 2),
            confidence=confidence,
            match_note=match_note,
        )
        est.p25 = min(est.p25, est.p50)
        est.p75 = max(est.p75, est.p50)
        est.p90 = max(est.p90, est.p75)

        est.detected_product = (self._display_model(sig, comps, query) if sig else None) or self._detect_product(query, comps)
        est.detected_brand, est.brand_median = self._detect_brand(query, comps, w)
        groups = Counter()
        cat_votes: Dict[str, float] = defaultdict(float)
        for c, wi in zip(comps, w):
            if c.group:
                groups[c.group] += wi
            for cid in c.category_ids:
                cat_votes[cid] += wi
        est.dominant_group = groups.most_common(1)[0][0] if groups else None
        est.category_votes = dict(cat_votes)
        return est

    @staticmethod
    def _display_model(sig: List[str], comps: Sequence[Comparable], query: str = "") -> Optional[str]:
        """
        Tên mẫu viết như trong tin bán chạy nhất ("iPhone 18 Pro Max"): cụm LIỀN NHAU đầu tiên khớp mẫu
        (tiêu đề ốp lưng hay lặp "iPhone 18 Pro Max 18 Pro..."). Phụ kiện thì thêm loại ở đầu ("Ốp lưng ...").
        """
        top = max(comps, key=lambda c: c.sold, default=None)
        if top is None:
            return None
        run: List[str] = []
        for w in top.title.split():
            if _prep(w) in sig and len(run) < len(sig):
                run.append(w)
            elif run:
                break
        model = " ".join(run)
        if not model:
            return None
        q_prep = _prep(query)
        if any(_contains(q_prep, m) for m in _ACCESSORY_MARKERS):
            head = " ".join(clean_tokens(query)[:2]).capitalize()
            return f"{head} {model}"
        return model

    # ------------------------------------------------------ product detection
    def _detect_product(self, query: str, comps: Sequence[Comparable]) -> Optional[str]:
        """
        Tên loại sản phẩm = cụm từ đầu tiêu đề (1–4 từ) được nhiều tin tương đồng dùng nhất.
        Ví dụ "Bình giữ nhiệt inox 304 Elmich 500ml" → "Bình giữ nhiệt".
        """
        orig_tokens = clean_tokens(query)
        prep_tokens = [strip_accents(t) for t in orig_tokens]
        if not prep_tokens:
            return None

        starts = [i for i, t in enumerate(prep_tokens[:4]) if t not in _LEADING_NOISE and not t.isdigit()]
        if not starts or not comps:
            return " ".join(orig_tokens[:2]).capitalize() if orig_tokens else None

        sims = np.array([c.similarity for c in comps])
        total = float(sims.sum()) or 1.0
        comp_preps = [_prep(c.title) for c in comps]

        best: Tuple[float, int, int, int] = (0.0, 0, 0, 0)  # (score, length, start, end)
        for s in starts[:2]:
            for length in range(1, 5):
                e = s + length
                if e > len(prep_tokens):
                    break
                phrase = " ".join(prep_tokens[s:e])
                if any(ch.isdigit() for ch in phrase):
                    break
                support = sum(sim for sim, cp in zip(sims, comp_preps) if _contains(cp, phrase)) / total
                if support < 0.30:
                    break
                # Ưu tiên cụm dài hơn khi vẫn được đa số tin tương đồng dùng
                score = support * (1.0 + 0.35 * (length - 1))
                if score > best[0]:
                    best = (score, length, s, e)

        if best[0] == 0.0:
            s = starts[0]
            return " ".join(orig_tokens[s:s + 2]).capitalize()
        _, _, s, e = best
        return " ".join(orig_tokens[s:e]).capitalize()

    def _detect_brand(self, query: str, comps: Sequence[Comparable], w: np.ndarray) -> Tuple[Optional[str], Optional[int]]:
        """
        Thương hiệu/dòng sản phẩm = từ Latin hiếm trong toàn tập (< 0.5% tin) xuất hiện
        trong tiêu đề seller và ở ít nhất 2 tin tương đồng. Trả kèm giá trung vị của
        nhóm tin cùng thương hiệu để seller thấy thương hiệu ảnh hưởng giá thế nào.
        """
        raw = normalize_nfc(query)
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9&\-]{2,}", raw)
        best_tok, best_df = None, None
        for tok in tokens:
            low = tok.lower()
            if low in _GENERIC_LATIN or low.isdigit():
                continue
            if _prep(tok) != low:  # có dấu tiếng Việt → không phải tên thương hiệu Latin
                continue
            col = self.vocab.get(low)
            df = int(self.doc_freq[col]) if col is not None else 0
            if df > 0.005 * self.n_docs:
                continue
            hits = [i for i, c in enumerate(comps) if _contains(_prep(c.title), low)]
            if len(hits) < 2:
                continue
            if best_df is None or df < best_df:
                best_tok, best_df = tok, df
        if not best_tok:
            return None, None

        low = best_tok.lower()
        idx = [i for i, c in enumerate(comps) if _contains(_prep(c.title), low)]
        logp = np.log(np.array([comps[i].price for i in idx]))
        med = math.exp(weighted_quantile(logp, w[idx], 0.5))
        return best_tok, round_price_nice(med)

    # ------------------------------------------------------------- keywords
    @staticmethod
    def mine_keywords(comps: Sequence[Comparable], query: str, top_n: int = 8) -> List[Tuple[str, float, int]]:
        """Cụm 2–3 từ mà các tin tương đồng hay dùng (gợi ý thẻ sát loại sản phẩm)."""
        if not comps:
            return []
        q_prep = _prep(query)
        q_head = _head_tokens(q_prep)
        support: Dict[str, float] = defaultdict(float)
        freq: Counter = Counter()
        display: Dict[str, str] = {}
        for c in comps:
            toks = clean_tokens(c.title)
            seen = set()
            for n in (2, 3):
                for i in range(len(toks) - n + 1):
                    gram = toks[i:i + n]
                    if any(any(ch.isdigit() for ch in g) for g in gram):
                        continue
                    key = " ".join(strip_accents(g) for g in gram)
                    if key in seen or key in _TAG_STOP or any(g in _TAG_STOP for g in key.split()[:1]):
                        continue
                    ks = key.split()
                    # Cụm cắt dở: bắt đầu/kết thúc bằng hư từ ("dành cho", "cho iphone"), hoặc cắt
                    # ngang tên loại sản phẩm ("lưng điện" trong "ốp lưng điện thoại")
                    if ks[0] in _EDGE_STOP or ks[-1] in _EDGE_STOP:
                        continue
                    if len(q_head) == 2 and ks[0] == q_head[1]:
                        continue
                    if any(_contains(key, r) for r in _RISKY_TAG):  # cam kết cần chứng nhận, không gợi ý làm thẻ
                        continue
                    seen.add(key)
                    support[key] += c.similarity
                    freq[key] += 1
                    display.setdefault(key, " ".join(gram))
        ranked = sorted(
            (k for k in support if freq[k] >= 3),
            key=lambda k: (support[k] * (1.2 if _contains(q_prep, k) else 1.0)), reverse=True,
        )
        # Bỏ cụm con nằm trong cụm dài hơn đã chọn
        chosen: List[str] = []
        for k in ranked:
            if any(k in ch or ch in k for ch in chosen):
                continue
            chosen.append(k)
            if len(chosen) >= top_n:
                break
        return [(display[k], round(support[k], 2), freq[k]) for k in chosen]
