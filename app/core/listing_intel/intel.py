import threading
import time
from dataclasses import replace

import numpy as np

from . import advice, axes, embedder, fusion, image_load, live_data, peers, store
from .features import TEXT_COLS, assemble, trend_demand, trend_matches
from .lexicon import attributes
from .output import listing_intel, score_doc
from .text_axis import MATERIAL_GROUPS
from .trend_axis import timeline
from .types import ListingInput

MAX_IMAGES = 8
WEEKS = 8
_TEXT_CACHE: dict = {}
_TEXT_CACHE_MAX = 4096
PEER_TTL = 900
PEER_MAX = 5000
_PEER_ROWS: dict = {}
_LOCK = threading.Lock()


def text_vecs(texts: list[str]) -> list:
    if not embedder.available():
        return [None] * len(texts)
    with _LOCK:
        found = {t: _TEXT_CACHE[t] for t in texts if t in _TEXT_CACHE}
    todo = list(dict.fromkeys(t for t in texts if t not in found))
    if todo:
        found.update(zip(todo, np.asarray(embedder.embed_texts(todo), dtype=np.float16).astype(np.float32)))
        with _LOCK:
            if len(_TEXT_CACHE) + len(todo) > _TEXT_CACHE_MAX:
                _TEXT_CACHE.clear()
            _TEXT_CACHE.update((t, found[t]) for t in todo)
    return [found[t] for t in texts]


def _peer_heads(inp: ListingInput) -> tuple[list, str | None]:
    heads = live_data.peer_heads(inp.group, inp.product_id) if inp.group else []
    return (heads, inp.group) if heads else (live_data.peer_heads(None, inp.product_id), None)


def _fresh_stats(keys, ctx, pending) -> dict:
    rows = live_data.load_many([k[0] for k in keys])
    keys, terms, out = [k for k in keys if k[0] in rows], peers.rising(ctx), {}
    for k, vec in zip(keys, text_vecs([rows[k[0]].title for k in keys])):
        p = rows[k[0]]
        out[k] = (peers.tag_raw(p, ctx, terms, pending), trend_demand(trend_matches(p, vec, ctx), ctx, p.group))
    return out


def peer_stats(heads, ctx, pending) -> list[tuple[float, float]]:
    now, keys = time.monotonic(), [(pid, updated, ctx.at) for pid, updated in heads]
    with _LOCK:
        for k in [k for k, (t, _) in _PEER_ROWS.items() if now - t >= PEER_TTL]:
            del _PEER_ROWS[k]
        hits = {k: _PEER_ROWS[k][1] for k in keys if k in _PEER_ROWS}
    fresh = _fresh_stats([k for k in keys if k not in hits], ctx, pending) if len(hits) < len(keys) else {}
    with _LOCK:
        _PEER_ROWS.update({k: (now, v) for k, v in fresh.items()})
        for k in list(_PEER_ROWS)[:max(0, len(_PEER_ROWS) - PEER_MAX)]:
            del _PEER_ROWS[k]
    found = {**hits, **fresh}
    return [found[k] for k in keys if k in found]


def _material(inp: ListingInput) -> dict:
    detected = attributes(" ".join([inp.title, *inp.tags, inp.description]))["material"]
    required = inp.group in MATERIAL_GROUPS
    return {"declared": list(inp.materials), "detected": detected, "required": required,
            "missing": required and not inp.materials and not detected}


def _timeline(base: float, ms, ctx, group) -> list[dict]:
    points = timeline(ms, ctx.trend_series, ctx.at, WEEKS, ctx.group_season.get(group))
    return [{"week_start": p["week_start"].isoformat(), "score": float(np.clip(base * p["demand_factor"], 0, 100)),
             "demand_factor": p["demand_factor"], "events": [e["name"] for e in p["events"]]} for p in points]


def build(inp: ListingInput, at, store_embeddings: bool) -> dict:
    inp = replace(inp, group=inp.group or live_data.group_of(inp.category))
    urls = inp.image_urls[:MAX_IMAGES]
    ctx = fusion.context(at)
    heads, peer_group = _peer_heads(inp)
    pending, approved = live_data.tag_sets()
    stats = peer_stats(heads, ctx, pending)
    title_vec = text_vecs([inp.title])[0]
    loaded = image_load.load_all(urls, store_embeddings)
    main = next((i for i in loaded if i is not None), None)
    feats = assemble(inp, None if main is None else {**main["model"], "vec": main["vec"]}, ctx, title_vec)
    scores = fusion.axis_scores(feats, inp.group)
    images = axes.image_list(urls, loaded, title_vec, inp.group, ctx.prompt_vecs)
    img_vec = None if main is None else main["vec"]
    market = axes.market(inp, img_vec, title_vec, ctx)
    tags_res, verdicts, suggestions = peers.tags_axis(inp, [s[0] for s in stats], ctx, pending, approved)
    ms = trend_matches(inp, title_vec, ctx)
    results = {
        "image": axes.image_axis(scores.get("image"), inp, images),
        "text": axes.text_axis(scores.get("text"), inp, feats, TEXT_COLS),
        "tags": tags_res,
        "market": axes.market_axis(scores.get("market"), market, feats, img_vec is not None),
        "trend": peers.trend_axis(feats["trend_factor"], ms, feats, [s[1] for s in stats]),
    }
    return {"inp": inp, "ctx": ctx, "feats": feats, "results": results, "ms": ms, "market": market,
            "images": images, "verdicts": verdicts, "suggestions": suggestions, "keywords": peers.keywords(inp, ms, ctx),
            "peers": {"group": peer_group, "size": len(stats)}}


def analyze(inp: ListingInput, at, persist: bool, store_embeddings: bool = True) -> dict:
    parts = build(inp, at, store_embeddings)
    results, feats, group = parts["results"], parts["feats"], parts["inp"].group
    material = _material(parts["inp"])
    codes = {i["code"] for r in results.values() for i in r.issues} | ({advice.MATERIAL} if material["missing"] else set())
    impacts = fusion.impacts(feats, group, {c: advice.FIXES[c] for c in codes if c in advice.FIXES})
    evidence = fusion.load_bundle().meta.get("evidence") or {}
    base = fusion.base_score(feats, group)
    out = listing_intel(parts, base, _timeline(base, parts["ms"], parts["ctx"], group), material,
                        advice.build(results, material, evidence, impacts, advice.review_issue(parts["inp"])), evidence, at)
    if persist and parts["inp"].product_id:
        store.save_score(score_doc(out))
    return out
