"""
tag_suggest_service.py — Gợi ý tag và danh mục từ tiêu đề sản phẩm.

Bài toán: seller gõ "ao thun anime tang ban than" thì hệ thống gợi ý ngay tag
và danh mục chuẩn, thay vì bắt họ tự chọn trong danh sách 77 tag.

VÌ SAO KHÔNG TRAIN MÔ HÌNH NGÔN NGỮ (PhoBERT) Ở BƯỚC NÀY
---------------------------------------------------------
Tài liệu ai-bi-v2.md đề xuất fine-tune PhoBERT trên 5.000 listings.csv. Đã kiểm
tra: KHÔNG LÀM ĐƯỢC, vì nhãn trong dữ liệu mồi không liên quan tới văn bản.

  tiêu đề "Đồ Gỗ - Dòng Sản Phẩm 15 Họa Tiết GenZ Vibe"  ->  nhãn backpack
  tiêu đề "Lụa Tơ Tằm - Dòng Sản Phẩm 4 Họa Tiết Tài Lộc" ->  nhãn blanket_sherpa

Tiêu đề sinh từ CHỦ ĐỀ THỦ CÔNG còn nhãn là LOẠI PHÔI — hai thứ sinh độc lập.
Chỉ 1,1% tiêu đề chứa tên loại sản phẩm. Cột `tags` thì gán ngẫu nhiên (áo bomber
gắn tag `bao-li-xi`). Train mô hình trên dữ liệu đó sẽ ra một model học nhiễu,
và tệ hơn là KHÔNG ĐO ĐƯỢC nó đúng hay sai.

Nên bước 1 là bộ khớp từ vựng chạy trên dữ liệu CÓ THẬT: 77 tag do Nhi soạn tay,
mỗi tag kèm 6-7 biến thể cách viết (463 biến thể, đã bỏ dấu sẵn). Đó là tri thức
ngôn ngữ thật, và có thể đo được bằng cách GIỮ LẠI một phần biến thể làm tập
kiểm tra.

Khi nào thì nâng lên PhoBERT: khi có tập (tiêu đề thật, tag thật) do seller đặt
— tức sau khi sàn chạy thật một thời gian. Lúc đó bộ khớp từ vựng này thành mốc
so sánh để chứng minh mô hình học sâu có hơn hay không.

CÁCH CHẤM ĐIỂM
--------------
Với mỗi tag, mỗi biến thể S được chấm so với truy vấn Q:

    điểm(S, Q) = (S nằm trọn trong Q ? 1.0 : 0) + độ_phủ_idf(S, Q)

    độ_phủ_idf = tổng idf các token của S xuất hiện trong Q
                 ─────────────────────────────────────────
                        tổng idf toàn bộ token của S

Dùng IDF vì các token như "ao", "qua", "do" xuất hiện ở rất nhiều tag nên gần
như không mang thông tin; "anime", "valentine", "canvas" thì ngược lại. Không
cân IDF thì mọi truy vấn có chữ "ao" đều khớp hàng chục tag như nhau.

Điểm của tag = điểm cao nhất trong các biến thể của nó. Khớp đúng nguyên một
biến thể cho 2.0 (1.0 cụm + 1.0 phủ).
"""

import csv
import io
import math
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
DATA_DIR = os.path.join(APP_DIR, "data")

# Token quá ngắn không mang nghĩa phân biệt, nhưng vẫn giữ "ao", "ly" vì chúng
# là tên loại sản phẩm thật trong tiếng Việt.
MIN_TOKEN_LEN = 2
KEEP_SHORT = {"ao", "ly", "ba", "tu", "bo"}


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt. Seller rất hay gõ không dấu nên đây là bước bắt buộc."""
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def normalize(text: str) -> str:
    """Chuẩn hoá về chữ thường, không dấu, chỉ còn chữ-số và một khoảng trắng."""
    t = strip_accents(str(text)).lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def tokens(text: str) -> List[str]:
    return [w for w in normalize(text).split()
            if len(w) >= MIN_TOKEN_LEN or w in KEEP_SHORT]


class TagSuggestService:
    """Bộ gợi ý tag dựa trên khớp từ vựng có cân IDF."""

    def __init__(self, tags: Sequence[Dict[str, str]],
                 categories: Optional[Sequence[Dict[str, str]]] = None,
                 exclude_aliases: Optional[Set[Tuple[str, str]]] = None):
        """
        `exclude_aliases` là tập (tag_id, alias_đã_chuẩn_hoá) bị loại khỏi chỉ mục.
        Dùng để giữ lại một phần biến thể làm tập kiểm tra — không có nó thì mọi
        phép đo đều là hỏi lại chính câu đã dạy.
        """
        exclude = exclude_aliases or set()
        self.category_name = {c["category_id"]: c["name_vi"] for c in (categories or [])}

        self.surfaces: Dict[str, List[List[str]]] = {}
        self.meta: Dict[str, Dict[str, str]] = {}

        for t in tags:
            tag_id = t["tag_id"]
            self.meta[tag_id] = {"tag_id": tag_id, "name_vi": t.get("name_vi", ""),
                                 "category_id": t.get("category_id", "")}
            forms: List[List[str]] = []
            raw_forms = [t.get("name_vi", ""), t.get("source_keywords", ""), tag_id.replace("-", " ")]
            raw_forms += [a for a in str(t.get("aliases", "")).split("|") if a.strip()]
            seen = set()
            for f in raw_forms:
                n = normalize(f)
                if not n or n in seen or (tag_id, n) in exclude:
                    continue
                seen.add(n)
                tk = tokens(f)
                if tk:
                    forms.append(tk)
            if forms:
                self.surfaces[tag_id] = forms

        # IDF tính trên số TAG chứa token, không phải số biến thể — một tag có
        # nhiều biến thể cùng chứa "ao" thì vẫn chỉ tính là một.
        df: Dict[str, int] = {}
        for tag_id, forms in self.surfaces.items():
            for tok in {w for f in forms for w in f}:
                df[tok] = df.get(tok, 0) + 1
        n_tags = max(len(self.surfaces), 1)
        self.idf = {w: math.log(1 + n_tags / c) for w, c in df.items()}
        self._default_idf = math.log(1 + n_tags)

    def _idf(self, token: str) -> float:
        return self.idf.get(token, self._default_idf)

    def score_tag(self, tag_id: str, query_norm: str,
                  query_tokens: Set[str]) -> Tuple[float, str, float]:
        """Trả (điểm, biến thể khớp, khối lượng IDF đã khớp).

        Khối lượng IDF dùng làm tiêu chí PHÁ HOÀ. Hai tag cùng phủ 100% biến thể
        thì cùng điểm, nhưng "qua valentine" (valentine hiếm) mang nhiều thông
        tin hơn "qua tang" (cả hai từ đều phổ thông) nên phải xếp trên. Không có
        tiêu chí này thì hoà điểm bị phá bằng thứ tự chữ cái — tức ngẫu nhiên.
        """
        best, best_form, best_mass = 0.0, "", 0.0
        for form in self.surfaces.get(tag_id, []):
            total = sum(self._idf(w) for w in form)
            if total <= 0:
                continue
            covered = sum(self._idf(w) for w in form if w in query_tokens)
            score = covered / total
            phrase = " ".join(form)
            if phrase and re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", query_norm):
                score += 1.0
            if (score, covered) > (best, best_mass):
                best, best_form, best_mass = score, phrase, covered
        return best, best_form, best_mass

    def suggest(self, title: str, top_k: int = 5,
                min_score: float = 0.34) -> List[Dict[str, Any]]:
        """
        Gợi ý tag cho một tiêu đề.

        `min_score` 0.34 nghĩa là phải phủ được khoảng một phần ba trọng số IDF
        của biến thể mới được đề xuất — dưới mức đó thì khớp quá mỏng, thà không
        gợi ý còn hơn gợi ý bừa.
        """
        q_norm = normalize(title)
        q_tokens = set(tokens(title))
        if not q_tokens:
            return []

        scored = []
        for tag_id in self.surfaces:
            s, form, mass = self.score_tag(tag_id, q_norm, q_tokens)
            if s >= min_score:
                m = self.meta[tag_id]
                # Phá hoà: taxonomy có những tag dùng chung biến thể (cả `ao-thun`
                # lẫn `ao-t-shirt` đều nhận "ao thun"). Khi điểm bằng nhau, ưu tiên
                # tag mà truy vấn trùng đúng TÊN của nó.
                if normalize(tag_id.replace("-", " ")) == q_norm:
                    s += 0.01
                scored.append({
                    "tag_id": tag_id,
                    "name_vi": m["name_vi"],
                    "category_id": m["category_id"],
                    "category_name": self.category_name.get(m["category_id"], ""),
                    "score": round(s, 4),
                    "matched_form": form,
                    "matched_idf_mass": round(mass, 4),
                    "exact": s >= 1.0,
                })
        scored.sort(key=lambda x: (-x["score"], -x["matched_idf_mass"], x["tag_id"]))
        return scored[:top_k]

    CATEGORY_POOL = 8

    def suggest_category(self, title: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Gộp điểm tag theo danh mục.

        Cộng BÌNH PHƯƠNG điểm và chỉ lấy 8 tag mạnh nhất. Cộng thẳng trên top-20
        thì một danh mục có nhiều tag khớp yếu sẽ đè danh mục có một tag khớp
        mạnh — đo được: "coc su in hinh tang sinh nhat" từng ra danh mục áo thun
        vì các tag ngành may khớp lẹt đẹt nhưng đông.
        """
        agg: Dict[str, float] = {}
        for s in self.suggest(title, top_k=self.CATEGORY_POOL, min_score=0.34):
            agg[s["category_id"]] = agg.get(s["category_id"], 0.0) + s["score"] ** 2
        rows = [{"category_id": c, "category_name": self.category_name.get(c, ""),
                 "score": round(v, 4)} for c, v in agg.items()]
        rows.sort(key=lambda x: (-x["score"], x["category_id"]))
        return rows[:top_k]


# --------------------------------------------------------------------------- #

def load_from_csv(data_dir: str = DATA_DIR,
                  exclude_aliases: Optional[Set[Tuple[str, str]]] = None) -> TagSuggestService:
    def read(name: str) -> List[Dict[str, str]]:
        with io.open(os.path.join(data_dir, name), encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    return TagSuggestService(read("tags.csv"), read("categories.csv"), exclude_aliases)


def evaluate_holdout(data_dir: str = DATA_DIR, n_holdout: int = 2) -> Dict[str, Any]:
    """
    Giữ lại `n_holdout` biến thể CUỐI của mỗi tag làm tập kiểm tra, dựng chỉ mục
    từ phần còn lại, rồi truy vấn bằng chính các biến thể đã giấu.

    Đây là phép đo thật: mô hình chưa từng thấy câu truy vấn đó.
    """
    def read(name: str) -> List[Dict[str, str]]:
        with io.open(os.path.join(data_dir, name), encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    tags = read("tags.csv")
    held: List[Tuple[str, str]] = []
    exclude: Set[Tuple[str, str]] = set()
    for t in tags:
        aliases = [a.strip() for a in str(t.get("aliases", "")).split("|") if a.strip()]
        for a in aliases[-n_holdout:]:
            n = normalize(a)
            if n:
                held.append((t["tag_id"], a))
                exclude.add((t["tag_id"], n))

    svc = TagSuggestService(tags, read("categories.csv"), exclude_aliases=exclude)

    cat_of = {t["tag_id"]: t.get("category_id", "") for t in tags}
    top1 = top3 = top5 = cat_top1 = 0
    rr_total = 0.0
    misses: List[Tuple[str, str]] = []
    for tag_id, query in held:
        got = svc.suggest(query, top_k=5)
        ids = [g["tag_id"] for g in got]
        if ids[:1] == [tag_id]:
            top1 += 1
        # Taxonomy có nhiều tag đồng nghĩa (qua-giang-sinh / qua-noel,
        # moc-khoa / keychain). Đoán trúng tag anh em cùng danh mục thì trên
        # thực tế vẫn dùng được, nên đo thêm ở cấp danh mục cho công bằng.
        if ids and cat_of.get(ids[0]) == cat_of.get(tag_id):
            cat_top1 += 1
        if tag_id in ids[:3]:
            top3 += 1
        if tag_id in ids:
            top5 += 1
            rr_total += 1.0 / (ids.index(tag_id) + 1)
        else:
            misses.append((tag_id, query))

    n = max(len(held), 1)
    # Mốc so sánh: đoán bừa trong số tag có mặt.
    random_top1 = 1.0 / max(len(svc.surfaces), 1)
    return {
        "n_queries": len(held),
        "n_tags": len(svc.surfaces),
        "holdout_per_tag": n_holdout,
        "top1": round(top1 / n, 4),
        "top3": round(top3 / n, 4),
        "top5": round(top5 / n, 4),
        "category_top1": round(cat_top1 / n, 4),
        "mrr": round(rr_total / n, 4),
        "random_top1": round(random_top1, 4),
        "lift_vs_random": round((top1 / n) / random_top1, 1) if random_top1 else None,
        "misses": misses[:10],
    }


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA MODULE TAG_SUGGEST_SERVICE.PY ===")

    # 1. Chuẩn hoá và bỏ dấu.
    assert normalize("Áo Thun Nam — Size XL!") == "ao thun nam size xl"
    assert strip_accents("Quà Tết đỏ") == "Qua Tet do"
    assert normalize("   ") == ""
    print("✓ Chuẩn hoá: bỏ dấu, hạ chữ thường, gom khoảng trắng")

    svc = load_from_csv()
    print(f"✓ Nạp {len(svc.surfaces)} tag, {sum(len(v) for v in svc.surfaces.values())} biến thể, "
          f"{len(svc.idf)} token trong từ điển IDF")

    # 2. IDF phải hạ trọng số các token xuất hiện ở nhiều tag.
    assert svc._idf("ao") < svc._idf("anime"), "Token phổ biến phải có IDF thấp hơn"
    print(f"✓ IDF phân biệt được: 'ao'={svc._idf('ao'):.2f} < 'anime'={svc._idf('anime'):.2f}")

    # 3. Khớp đúng nguyên biến thể phải cho điểm tối đa và đứng đầu.
    got = svc.suggest("ao thun")
    assert got and got[0]["tag_id"] == "ao-thun", got[:2]
    assert got[0]["exact"] and got[0]["score"] >= 1.9
    print(f"✓ Khớp nguyên cụm: 'ao thun' -> {got[0]['tag_id']} (điểm {got[0]['score']})")

    # 4. Gõ KHÔNG DẤU vẫn phải ra đúng — seller rất hay gõ kiểu này.
    # Taxonomy có chỗ mơ hồ thật (qua-valentine và qua-tang-nguoi-yeu đều đúng
    # cho cùng một câu), nên kỳ vọng là TẬP đáp án chấp nhận được.
    for q, want in [("ao thun anime", {"ao-anime", "otaku"}),
                    ("qua tang nguoi yeu valentine", {"qua-valentine", "qua-tang-nguoi-yeu", "qua-le-tinh-nhan"}),
                    ("tranh canvas treo tuong", {"tranh-canvas", "tranh-treo-tuong"})]:
        ids = [g["tag_id"] for g in svc.suggest(q, top_k=5)]
        assert want & set(ids), f"'{q}' không ra {want}, chỉ có {ids}"
    print("✓ Truy vấn không dấu: 3/3 ví dụ ra đúng tag trong top-5")

    # 5. Truy vấn rỗng hoặc rác thì trả rỗng, không bịa.
    assert svc.suggest("") == []
    assert svc.suggest("!!!  ???") == []
    print("✓ Truy vấn rỗng/rác: trả danh sách rỗng, không gợi ý bừa")

    # 6. Gợi ý danh mục.
    cats = svc.suggest_category("ao thun nam local brand")
    assert cats and cats[0]["category_id"].startswith("apparel"), cats
    print(f"✓ Gợi ý danh mục: 'ao thun nam local brand' -> {cats[0]['category_id']} "
          f"({cats[0]['category_name']})")

    # 7. ĐÁNH GIÁ THẬT — giữ lại biến thể làm tập kiểm tra.
    ev = evaluate_holdout(n_holdout=2)
    print(f"\n  --- Đánh giá giữ lại {ev['holdout_per_tag']} biến thể/tag ---")
    print(f"  {ev['n_queries']} truy vấn chưa từng thấy, trên {ev['n_tags']} tag")
    print(f"  top-1  {ev['top1']:.1%}   top-3  {ev['top3']:.1%}   top-5  {ev['top5']:.1%}   MRR {ev['mrr']:.3f}")
    print(f"  đúng DANH MỤC ở vị trí 1: {ev['category_top1']:.1%}")
    print(f"  đoán bừa top-1 {ev['random_top1']:.1%}  ->  tốt hơn {ev['lift_vs_random']} lần")
    print("  (top-1 thấp là do taxonomy có nhiều tag đồng nghĩa: qua-giang-sinh/qua-noel,")
    print("   moc-khoa/keychain, do-handmade/qua-handmade. Với giao diện gợi ý 3-5 lựa")
    print("   chọn thì top-3 mới là con số đáng quan tâm.)")
    # Ngưỡng dưới đây là CHỐT CHỐNG TỤT, không phải mục tiêu chất lượng: chúng
    # đặt thấp hơn mức đo được để bắt lỗi khi ai đó sửa làm hỏng, chứ không
    # khẳng định mức này là đủ tốt.
    assert ev["top3"] > 0.60, f"top-3 tụt dưới mức đã đo: {ev['top3']}"
    assert ev["top1"] > 0.25, f"top-1 tụt dưới mức đã đo: {ev['top1']}"
    assert ev["top1"] > ev["random_top1"] * 10, "Phải hơn hẳn đoán bừa"
    if ev["misses"]:
        print(f"  trượt ví dụ: {ev['misses'][:3]}")

    # 8. Tập kiểm tra tự soạn — tiêu đề kiểu seller thật hay gõ.
    #    Soạn tay từ taxonomy, KHÔNG lấy từ listings.csv vì nhãn ở đó là ngẫu nhiên.
    REAL = [
        ("Áo thun unisex form rộng in hình anime", "ao-anime"),
        ("ao hoodie nam mua dong", "ao-hoodie"),
        ("Cốc sứ in hình tặng sinh nhật", "qua-tang-sinh-nhat"),
        ("tui tote canvas di hoc", "tui-tote"),
        ("Bao lì xì Tết in chữ thư pháp", "bao-li-xi"),
        ("qua tang me ngay 8/3", "qua-8-3"),
        ("ao doi cho cap doi yeu nhau", "ao-cap-doi"),
        ("Tranh canvas trang trí phòng khách", "tranh-canvas"),
        ("ao lop ky niem cap 3", "ao-lop"),
        ("Móc khoá acrylic in hình chibi", "moc-khoa"),
    ]
    hit1 = sum(1 for q, want in REAL if [g["tag_id"] for g in svc.suggest(q, top_k=1)] == [want])
    hit3 = sum(1 for q, want in REAL if want in [g["tag_id"] for g in svc.suggest(q, top_k=3)])
    print(f"\n  --- Tập tự soạn {len(REAL)} tiêu đề kiểu thật ---")
    print(f"  top-1 {hit1}/{len(REAL)}   top-3 {hit3}/{len(REAL)}")
    for q, want in REAL:
        got = svc.suggest(q, top_k=3)
        mark = "✓" if want in [g["tag_id"] for g in got] else "✗"
        print(f"   {mark} {q[:42]:<44} -> {[g['tag_id'] for g in got]}")
    assert hit3 >= len(REAL) * 0.6, f"top-3 quá thấp trên tập tự soạn: {hit3}/{len(REAL)}"

    print("\n✅ TẤT CẢ SELF-CHECKS CỦA TAG_SUGGEST_SERVICE.PY ĐÃ PASS!")
