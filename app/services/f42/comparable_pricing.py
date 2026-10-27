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

    @property
    def usable(self) -> bool:
        return self.confidence != "none"


def _prep(text: str) -> str:
    """Chuẩn hoá tiêu đề cho truy hồi: bỏ dấu, thường hoá, bỏ ký tự đặc biệt."""
    t = strip_accents(normalize_nfc(text or ""))
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _contains(text_prepped: str, phrase_prepped: str) -> bool:
    return f" {phrase_prepped} " in f" {text_prepped} "


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
    return int(round(val / step) * step)


_ACCESSORY_MARKERS = [
    "tui dung", "tui deo", "tui chong soc", "bao da", "bao dung", "op lung", "op",
    "kinh cuong luc", "cuong luc", "mieng dan", "dan man hinh", "day deo", "day sac",
    "cap sac", "cu sac", "dock sac", "khay nhom", "khay nuong", "khay lot", "khay giay",
    "giay nen", "giay bac", "vi nuong", "khoa buom", "khoa kim", "day dong ho",
    "chot dong ho", "hop dung", "gia do", "chan de", "mieng lot", "de lot", "lot ly",
    "lot chuot", "vo boc", "nap day", "dau chuyen", "jack chuyen", "filter", "nap ong kinh",
    "mang loc", "loi loc", "khung vien", "nap lung", "pin thay the", "pin du phong",
    "adapter", "remote", "remot", "dieu khien", "de giu", "mieng dan camera", "kinh bao ve"
]


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
        self._live_ts = 0.0
        self._live_matrix: Optional[csr_matrix] = None
        self._live_rows: List[Dict[str, Any]] = []

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
        """Nạp sản phẩm đang bán trên sàn (giá thật của chính VietCraft)."""
        if db_live is None or time.time() - self._live_ts < LIVE_REFRESH_S:
            return
        from app.services.f42.pricing_engine import to_float_price

        rows: List[Dict[str, Any]] = []
        try:
            cursor = db_live["products"].find(
                {"is_hidden": {"$ne": True}, "status": {"$ne": "UNPUBLISHED"}},
                {"title": 1, "min_price": 1, "max_price": 1, "category_ids": 1},
            ).limit(20000)
            for p in cursor:
                lo = to_float_price(p.get("min_price"))
                hi = to_float_price(p.get("max_price"))
                price = lo if lo else hi
                if not price or not (PRICE_MIN <= price <= PRICE_MAX):
                    continue
                title = normalize_nfc(p.get("title") or "")
                prep = _prep(title)
                if len(prep) < 3:
                    continue
                rows.append({
                    "title": title, "prep": prep, "price": price,
                    "category_ids": [str(c) for c in (p.get("category_ids") or [])],
                })
        except Exception:
            self._live_ts = time.time()
            return

        self._live_rows = rows
        self._live_matrix = self.vectorizer.transform([r["prep"] for r in rows]) if rows else None
        self._live_ts = time.time()

    # ------------------------------------------------------------------ query
    def search(self, query: str, top_k: int = TOP_K, exclude_idx: Optional[int] = None) -> List[Comparable]:
        prep = _prep(query)
        if not prep:
            return []
        q = self.vectorizer.transform([prep])
        if q.nnz == 0:
            return []

        q_is_acc = any(_contains(prep, m) for m in _ACCESSORY_MARKERS)

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
            c_is_acc = any(_contains(c_prep, m) for m in _ACCESSORY_MARKERS)
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

        if self._live_matrix is not None and self._live_rows:
            lsims = (self._live_matrix @ q.T).toarray().ravel()
            lk = min(top_k * 2, len(lsims))
            lidx = np.argpartition(-lsims, lk - 1)[:lk]
            sorted_lidx = lidx[np.argsort(-lsims[lidx])]
            for i in sorted_lidx:
                if lsims[i] <= 0:
                    continue
                r = self._live_rows[i]
                c_is_acc = any(_contains(r["prep"], m) for m in _ACCESSORY_MARKERS)
                if not q_is_acc and c_is_acc:
                    continue
                if q_is_acc and not c_is_acc:
                    continue

                out.append(Comparable(
                    title=r["title"], price=r["price"], similarity=float(lsims[i]),
                    source="vietcraft", category_ids=r["category_ids"],
                ))
                if len(out) >= top_k:
                    break

        out.sort(key=lambda c: c.similarity, reverse=True)
        return out[:top_k]

    # --------------------------------------------------------------- estimate
    def estimate(self, query: str, exclude_idx: Optional[int] = None) -> ComparableEstimate:
        cands = self.search(query, exclude_idx=exclude_idx)
        if not cands:
            return ComparableEstimate(comparables=[])

        top_sim = cands[0].similarity
        floor = max(MIN_SIM, REL_SIM * top_sim)
        comps = [c for c in cands if c.similarity >= floor]
        if len(comps) < MIN_COMPARABLES:
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

        est = ComparableEstimate(
            comparables=comps,
            p25=round_price_nice(p25), p50=round_price_nice(p50),
            p75=round_price_nice(p75), p90=round_price_nice(p90),
            n_used=len(comps), n_effective=round(n_eff, 1),
            mean_similarity=round(mean_sim, 3), spread=round(spread, 2),
            confidence=confidence,
        )
        est.p25 = min(est.p25, est.p50)
        est.p75 = max(est.p75, est.p50)
        est.p90 = max(est.p90, est.p75)

        est.detected_product = self._detect_product(query, comps)
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
