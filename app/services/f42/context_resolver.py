import math
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple
from bson import ObjectId

from app.services.f42 import config
from app.services.f42.schemas import CategoryCandidate, CategoryResult
from app.services.f42.vi_text import clean_tokens, get_ngrams, normalize_nfc, strip_accents


def _cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
    """Tính cosine similarity giữa 2 vector TF-IDF."""
    common_keys = set(vec1.keys()) & set(vec2.keys())
    if not common_keys:
        return 0.0
    dot = sum(vec1[k] * vec2[k] for k in common_keys)
    norm1 = math.sqrt(sum(v * v for v in vec1.values()))
    norm2 = math.sqrt(sum(v * v for v in vec2.values()))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class ContextResolver:
    def __init__(self, categories: List[Dict[str, Any]]):
        self.categories = categories
        self.cat_map: Dict[str, Dict[str, Any]] = {}
        self.doc_vectors: Dict[str, Dict[str, float]] = {}
        self.idf: Dict[str, float] = {}
        self._build_index()

    def _build_index(self):
        docs: Dict[str, List[str]] = {}
        df: Counter = Counter()

        for cat in self.categories:
            cid = str(cat.get("_id") or cat.get("id") or "")
            name = str(cat.get("name") or "")
            if not cid or not name:
                continue
            self.cat_map[cid] = cat

            tokens_vi = clean_tokens(name)
            tokens_no_acc = clean_tokens(strip_accents(name))
            cat_tokens = get_ngrams(tokens_vi) + get_ngrams(tokens_no_acc)

            docs[cid] = cat_tokens
            for t in set(cat_tokens):
                df[t] += 1

        n_docs = max(len(docs), 1)
        self.idf = {w: math.log((n_docs + 1.0) / (cnt + 1.0)) + 1.0 for w, cnt in df.items()}

        for cid, t_list in docs.items():
            tf = Counter(t_list)
            total = len(t_list) or 1
            vec: Dict[str, float] = {}
            for w, count in tf.items():
                vec[w] = (count / total) * self.idf.get(w, 1.0)
            self.doc_vectors[cid] = vec

    def resolve(
        self,
        category_id: Optional[str] = None,
        category_name: Optional[str] = None,
        user_title: str = ""
    ) -> CategoryResult:
        if category_id and category_id in self.cat_map:
            cat = self.cat_map[category_id]
            name = cat.get("name") or category_name or ""
            return CategoryResult(
                resolved_id=category_id,
                resolved_name=name,
                source="seller_selected",
                candidates=[CategoryCandidate(id=category_id, name=name, score=1.0)],
                needs_confirmation=False
            )

        if category_id:
            for cid, cat in self.cat_map.items():
                if cid.lower() == category_id.lower():
                    return CategoryResult(
                        resolved_id=cid,
                        resolved_name=cat.get("name", ""),
                        source="seller_selected",
                        candidates=[CategoryCandidate(id=cid, name=cat.get("name", ""), score=1.0)],
                        needs_confirmation=False
                    )

        if category_name:
            for cid, cat in self.cat_map.items():
                if strip_accents(cat.get("name", "")) == strip_accents(category_name):
                    return CategoryResult(
                        resolved_id=cid,
                        resolved_name=cat.get("name", ""),
                        source="seller_selected",
                        candidates=[CategoryCandidate(id=cid, name=cat.get("name", ""), score=1.0)],
                        needs_confirmation=False
                    )

        clean_title = normalize_nfc(user_title).strip()
        if not clean_title or not self.doc_vectors:
            return CategoryResult(
                resolved_id=None,
                resolved_name=None,
                source="none",
                candidates=[],
                needs_confirmation=True
            )

        q_tokens = get_ngrams(clean_tokens(clean_title)) + get_ngrams(clean_tokens(strip_accents(clean_title)))
        if not q_tokens:
            return CategoryResult(
                resolved_id=None,
                resolved_name=None,
                source="none",
                candidates=[],
                needs_confirmation=True
            )

        q_tf = Counter(q_tokens)
        q_total = len(q_tokens)
        q_vec = {w: (cnt / q_total) * self.idf.get(w, 1.0) for w, cnt in q_tf.items()}

        scores: List[Tuple[str, float]] = []
        for cid, doc_vec in self.doc_vectors.items():
            sim = _cosine_similarity(q_vec, doc_vec)
            if sim > 0:
                scores.append((cid, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        top_k = scores[:config.CATEGORY_TOP_K]

        candidates = [
            CategoryCandidate(
                id=cid,
                name=self.cat_map[cid].get("name", ""),
                score=round(s, 3)
            )
            for cid, s in top_k
        ]

        if not candidates or candidates[0].score < config.CATEGORY_MIN_SCORE:
            return CategoryResult(
                resolved_id=None,
                resolved_name=None,
                source="none",
                candidates=candidates,
                needs_confirmation=True
            )

        top1 = candidates[0]
        needs_conf = top1.score < config.CATEGORY_AUTOCONFIRM_SCORE

        return CategoryResult(
            resolved_id=top1.id,
            resolved_name=top1.name,
            source="tfidf",
            candidates=candidates,
            needs_confirmation=needs_conf
        )
