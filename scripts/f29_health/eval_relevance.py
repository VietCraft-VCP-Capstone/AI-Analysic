import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

from app.api.v1._live import LOC_SP_THAT, db_live
from app.core.f29 import query_relevance as qr
from app.core.f29.price_ref import category_of
from app.core.listing_intel.normalize import fold

DOC = Path(__file__).resolve().parents[2] / "docs" / "F29_RELEVANCE_EVAL.md"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
LABEL = "weak supervision, not human-labelled"
HOLDOUT_DAYS = 7
UNSEEN_MOD = 5
K = 5
PRODUCT_FIELDS = {"title": 1, "tags": 1, "categories": 1, "category_ids": 1}


def _load():
    live = db_live()
    products = {p["_id"]: p for p in live["products"].find(LOC_SP_THAT, PRODUCT_FIELDS)}
    logs = list(live["search_logs"].find({}, {"keyword": 1, "clicks": 1, "created_at": 1}))
    return products, logs


def _events(logs, products):
    out = []
    for log in logs:
        q = fold(log.get("keyword"))
        for c in log.get("clicks") or []:
            p = products.get(c.get("product_id"))
            if p and q and category_of(p):
                out.append((q, c["product_id"], log["created_at"], int(c.get("position") or 0)))
    return out


def _held(query):
    return int(hashlib.md5(query.encode("utf-8")).hexdigest(), 16) % UNSEEN_MOD == 0


def _train(events, products):
    return qr.train((q, products[pid].get("title") or "", pos) for q, pid, _, pos in events)


def _rank(query, pid, pool, texts, assoc):
    target = qr.score(query, texts[pid], assoc)
    return 1 + sum(qr.score(query, texts[o], assoc) >= target for o in pool if o != pid)


def _evaluate(train, test, products, texts, by_cat):
    assoc = _train(train, products)
    pairs = sorted({(q, pid) for q, pid, _, _ in test}, key=lambda x: (x[0], str(x[1])))
    if not pairs:
        raise SystemExit("Tập kiểm tra rỗng, không đánh giá được")
    ranks_m, ranks_l, pools = [], [], []
    for q, pid in pairs:
        pool = by_cat[category_of(products[pid])]
        ranks_m.append(_rank(q, pid, pool, texts, assoc))
        ranks_l.append(_rank(q, pid, pool, texts, None))
        pools.append(len(pool))
    return {
        "train_clicks": len(train), "test_clicks": len(test), "test_pairs": len(pairs),
        "test_queries": len({q for q, _ in pairs}), "pool_avg": round(mean(pools), 1),
        "mrr_model": round(mean(1 / r for r in ranks_m), 4),
        "mrr_lexical": round(mean(1 / r for r in ranks_l), 4),
        "recall5_model": round(mean(r <= K for r in ranks_m), 4),
        "recall5_lexical": round(mean(r <= K for r in ranks_l), 4),
    }


def _misses(results):
    return [f"{name} {m}" for name, r in results.items() for m in ("mrr", "recall5")
            if not r[f"{m}_model"] > r[f"{m}_lexical"]]


def _table(results):
    head = ("| Tách | Train click | Test click | Test cặp | Test từ khoá | Ứng viên TB | "
            "MRR model | MRR lexical | Recall@5 model | Recall@5 lexical |")
    rows = [f"| {name} | {r['train_clicks']} | {r['test_clicks']} | {r['test_pairs']} | {r['test_queries']} | "
            f"{r['pool_avg']} | {r['mrr_model']:.3f} | {r['mrr_lexical']:.3f} | "
            f"{r['recall5_model']:.3f} | {r['recall5_lexical']:.3f} |" for name, r in results.items()]
    return [head, "|" + "---|" * 10, *rows]


def _report(stats, results, cut, enabled):
    misses = _misses(results)
    t = results["temporal"]
    decision = ("Model thắng lexical ở cả MRR và Recall@5 trên cả hai cách tách, nên bật (`enabled = true`)."
                if enabled else
                "Model không thắng lexical trên mọi chỉ số ở cả hai cách tách, nên `enabled = false` "
                "và production dùng lexical. Không đạt: " + ", ".join(misses) + ".")
    return "\n".join([
        f"Ảnh chụp số liệu ngày {datetime.now(VN_TZ):%Y-%m-%d %H:%M} (Asia/Ho_Chi_Minh); số liệu thay đổi theo log mới.",
        "# F29 — Đánh giá độ liên quan của từ khoá",
        "",
        f"> Nhãn: **{LABEL}**. Nhãn lấy từ click trong `search_logs`, không có người chấm.",
        "> Sinh bởi `scripts/f29_health/eval_relevance.py`. Số liệu in nguyên từ script.",
        "",
        "## Dữ liệu",
        f"- search_logs: {stats['logs']} lượt tìm, {stats['logs_with_clicks']} lượt có click, "
        f"{stats['clicks']} click tổng.",
        f"- Click dùng để đánh giá (sản phẩm thật, có danh mục): {stats['events']}.",
        f"- Từ khoá duy nhất (đã bỏ dấu): {stats['queries']}. Cặp (từ khoá, sản phẩm): {stats['pairs']}.",
        f"- Khoảng thời gian: {stats['first']:%Y-%m-%d} → {stats['last']:%Y-%m-%d}.",
        f"- Mốc tách: {cut:%Y-%m-%d %H:%M}. Tách theo thời gian: 7 ngày cuối làm test, trước đó làm train.",
        "- Tách theo từ khoá chưa thấy: 1 trong 5 từ khoá (md5) làm test, các từ khoá còn lại làm train.",
        "",
        "## Cách đo",
        "- Ứng viên: mọi sản phẩm thật cùng danh mục chính (`categories[0]`) với sản phẩm được click.",
        "- Lexical: tỉ lệ token của từ khoá có trong tên và tag sản phẩm.",
        "- Model: token của từ khoá được tính điểm theo tần suất token trong tên sản phẩm đã click cho từ khoá đó, "
        "click ở vị trí p được tính trọng số 1/(p+1).",
        "- Hoà điểm được tính bất lợi cho sản phẩm được click, với cả hai phương pháp.",
        "- MRR và Recall@5 tính trên từng cặp (từ khoá, sản phẩm được click), lấy trung bình.",
        "",
        "## Kết quả",
        *_table(results),
        "",
        "## Quyết định",
        decision,
        "",
        "## Giới hạn",
        "- Dữ liệu nhỏ, và vài từ khoá chiếm phần lớn lượt tìm, nên số liệu dao động mạnh.",
        "- Không có nhãn người chấm. Mọi số ở đây là weak supervision.",
        "- Model trong `relevance_model.json` chỉ học từ dữ liệu trước mốc tách, không dùng 7 ngày test.",
        f"- Tách theo thời gian: {t['train_clicks']} click để train, {t['test_clicks']} click để test. "
        "Khi train quá ít, kết quả tách này không đáng tin.",
        "",
    ])


def main() -> None:
    products, logs = _load()
    texts = {pid: qr.product_text(p) for pid, p in products.items()}
    by_cat = defaultdict(list)
    for pid, p in products.items():
        by_cat[category_of(p)].append(pid)
    events = _events(logs, products)
    cut = max(log["created_at"] for log in logs) - timedelta(days=HOLDOUT_DAYS)
    splits = {
        "temporal": ([e for e in events if e[2] <= cut], [e for e in events if e[2] > cut]),
        "unseen_query": ([e for e in events if not _held(e[0])], [e for e in events if _held(e[0])]),
    }
    results = {name: _evaluate(tr, te, products, texts, by_cat) for name, (tr, te) in splits.items()}
    enabled = not _misses(results)
    model = {"version": f"weak-{cut:%Y-%m-%d}", "enabled": enabled, "label": LABEL,
             "trained_before": cut.isoformat(), "metrics": results,
             "assoc": _train(splits["temporal"][0], products)}
    qr.MODEL_PATH.write_text(json.dumps(model, ensure_ascii=False, indent=1), "utf-8")
    stats = {
        "logs": len(logs), "logs_with_clicks": sum(1 for log in logs if log.get("clicks")),
        "clicks": sum(len(log.get("clicks") or []) for log in logs), "events": len(events),
        "queries": len({e[0] for e in events}), "pairs": len({(e[0], e[1]) for e in events}),
        "first": min(log["created_at"] for log in logs), "last": max(log["created_at"] for log in logs),
    }
    DOC.write_text(_report(stats, results, cut, enabled), "utf-8")
    print(json.dumps({"stats": {k: str(v) for k, v in stats.items()}, "results": results,
                      "enabled": enabled}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
