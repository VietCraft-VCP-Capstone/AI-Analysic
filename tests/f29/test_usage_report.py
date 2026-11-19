from datetime import datetime

from scripts.f29_health import usage_report as ur

T1 = datetime(2026, 11, 1, 10, 0)


def ev(pid, rid, action="open", at=T1, shop="s1"):
    return {"product_id": pid, "shop_id": shop, "recommendation_id": rid, "action": action, "created_at": at}


def doc(pid, day, rids=(), covered=0):
    queries = [{"query": f"q{i}", "covered": i < covered} for i in range(covered + 1)]
    return {"product_id": pid, "date": datetime(2026, 11, day),
            "recommendations": [{"id": r} for r in rids], "search": {"queries": queries}}


def test_click_rate_counts_only_shown_pairs():
    docs = [doc("p1", 1, ["image:a", "info:b"]), doc("p2", 1, ["image:a"])]
    events = [ev("p1", "image:a"), ev("p1", "image:a", at=datetime(2026, 11, 2)), ev("p3", "image:z"),
              ev("p1", "info:b", action="apply")]
    assert ur.click_rate(events, docs) == (1, 3)


def test_implementation_when_rec_gone_in_later_doc():
    docs = [doc("p1", 1, ["image:a", "info:b"]), doc("p1", 2, ["info:b"]),
            doc("p2", 1, ["info:b"]), doc("p2", 2, ["info:b"])]
    events = [ev("p1", "image:a"), ev("p2", "info:b")]
    assert ur.implementation(events, docs) == (1, 2)


def test_implementation_needs_doc_within_14_days():
    docs = [doc("p1", 1, ["image:a"]), doc("p1", 30, [])]
    assert ur.implementation([ev("p1", "image:a")], docs) == (0, 0)


def test_implementation_needs_rec_shown_before_click():
    docs = [doc("p1", 1, []), doc("p1", 2, [])]
    assert ur.implementation([ev("p1", "image:a")], docs) == (0, 0)


def test_coverage_rise_skips_single_doc_products():
    docs = [doc("p1", 1, covered=1), doc("p1", 3, covered=2),
            doc("p2", 1, covered=2), doc("p2", 2, covered=1),
            doc("p3", 1, covered=1)]
    assert ur.coverage_rise(docs) == (1, 2)


def test_returning_shops_need_two_days_within_7():
    events = [ev("p1", "a", at=datetime(2026, 11, 1), shop="s1"), ev("p1", "a", at=datetime(2026, 11, 5), shop="s1"),
              ev("p1", "a", at=datetime(2026, 11, 1), shop="s2"), ev("p1", "a", at=datetime(2026, 11, 20), shop="s2"),
              ev("p1", "a", at=datetime(2026, 11, 1), shop="s3"), ev("p1", "a", at=datetime(2026, 11, 1, 12), shop="s3")]
    assert ur.returning_shops(events) == (1, 3)


def test_no_data_prints_placeholder():
    text = "\n".join(ur.lines(ur.metrics([], [])))
    assert text.count(ur.NO_DATA) == 5
