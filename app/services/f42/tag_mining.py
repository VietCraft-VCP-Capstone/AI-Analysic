import math
from collections import Counter
from typing import Any, Dict, List, Optional, Set
from bson import ObjectId

from app.services.f42 import config
from app.services.f42.schemas import TagItem, TagResult
from app.services.f42.vi_text import normalize_nfc, strip_accents


def compute_tag_scores(
    category_tags: List[str],
    global_tags: List[str],
    banned_keywords: Set[str],
    top_n: int = config.TAG_TOP_N,
    min_freq: int = config.TAG_MIN_FREQ,
    stoplist: List[str] = config.TAG_GENERIC_STOPLIST
) -> TagResult:
    if not category_tags:
        return TagResult(items=[], basis="popular_tags_internal", sample_size=0)

    stop_set = {strip_accents(s) for s in stoplist}
    banned_set = {strip_accents(b) for b in banned_keywords}

    clean_cat_tags: List[str] = []
    for t in category_tags:
        norm = normalize_nfc(t).strip()
        stripped = strip_accents(norm)
        if not norm or len(norm) < 2:
            continue
        if stripped in stop_set or any(b in stripped for b in banned_set):
            continue
        clean_cat_tags.append(norm)

    cat_counts = Counter(clean_cat_tags)
    if not cat_counts:
        return TagResult(items=[], basis="popular_tags_internal", sample_size=0)

    global_counts = Counter([normalize_nfc(t).strip() for t in global_tags if t])
    total_docs = max(len(global_tags), len(category_tags), 1)

    scored_items: List[TagItem] = []
    for tag, freq in cat_counts.items():
        if freq < min_freq and len(cat_counts) > top_n:
            continue

        g_freq = global_counts.get(tag, freq)
        idf = math.log((total_docs + 1.0) / (g_freq + 1.0)) + 1.0
        score = round(freq * idf, 2)
        scored_items.append(TagItem(tag=tag, score=score, freq=freq))

    scored_items.sort(key=lambda x: (x.score, x.freq), reverse=True)

    return TagResult(
        items=scored_items[:top_n],
        basis="popular_tags_internal",
        sample_size=len(category_tags)
    )


def fetch_tags_from_db(
    category_id: Optional[str],
    db_live: Any,
    banned_keywords: Set[str]
) -> TagResult:
    if db_live is None:
        return TagResult(items=[], basis="popular_tags_internal", sample_size=0)

    try:
        cat_filter: Dict[str, Any] = {"is_hidden": {"$ne": True}}
        if category_id:
            if ObjectId.is_valid(category_id):
                oid = ObjectId(category_id)
                cat_filter["$or"] = [{"category_ids": oid}, {"category_id": oid}, {"categories": category_id}]
            else:
                cat_filter["$or"] = [{"categories": category_id}, {"category_id": category_id}]

        cat_prods = list(db_live["products"].find(cat_filter, {"tags": 1}).limit(100))
        cat_tags: List[str] = []
        for p in cat_prods:
            tags = p.get("tags") or []
            if isinstance(tags, list):
                for t in tags:
                    if isinstance(t, str):
                        cat_tags.append(t)

        global_prods = list(db_live["products"].find({"is_hidden": {"$ne": True}}, {"tags": 1}).limit(300))
        global_tags: List[str] = []
        for p in global_prods:
            tags = p.get("tags") or []
            if isinstance(tags, list):
                for t in tags:
                    if isinstance(t, str):
                        global_tags.append(t)

        if len(cat_tags) < 5:
            all_db_tags = list(db_live["tags"].find({"status": {"$ne": "INACTIVE"}}, {"name": 1}).limit(20))
            for t in all_db_tags:
                nm = t.get("name")
                if nm:
                    cat_tags.append(nm)
                    global_tags.append(nm)

        return compute_tag_scores(
            category_tags=cat_tags,
            global_tags=global_tags,
            banned_keywords=banned_keywords,
            top_n=config.TAG_TOP_N,
            min_freq=1 if len(cat_tags) < 15 else config.TAG_MIN_FREQ
        )

    except Exception:
        return TagResult(items=[], basis="popular_tags_internal", sample_size=0)
