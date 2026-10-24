from app.core.f29.factors import price_score, ratio_score, review_score


def test_ratio_score_bounds():
    assert ratio_score(None, 6) == 0.0
    assert ratio_score(0, 6) == 0.0
    assert ratio_score(3, 6) == 50.0
    assert ratio_score(6, 6) == 100.0
    assert ratio_score(9, 6) == 100.0


def test_review_score_missing_is_zero():
    assert review_score(0, 0, 0.8, 5) == 0.0


def test_review_score_smoothed():
    assert review_score(5, 5, 0.8, 5) == 90.0


def test_price_score_ramp():
    assert price_score(50, 100, 1.0, 2.0) == 100.0
    assert price_score(100, 100, 1.0, 2.0) == 100.0
    assert price_score(150, 100, 1.0, 2.0) == 50.0
    assert price_score(250, 100, 1.0, 2.0) == 0.0


def test_price_score_missing():
    assert price_score(None, 100, 1.0, 2.0) == 0.0
    assert price_score(100, None, 1.0, 2.0) == 0.0
    assert price_score(0, 100, 1.0, 2.0) == 0.0
