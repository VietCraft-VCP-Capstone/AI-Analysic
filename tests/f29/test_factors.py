import pytest
from app.core.f29.factors import desc_words, ratio_score, review_score



def test_ratio_score_bounds():
    assert ratio_score(None, 6) == 0.0
    assert ratio_score(0, 6) == 0.0
    assert ratio_score(3, 6) == 50.0
    assert ratio_score(6, 6) == 100.0
    assert ratio_score(9, 6) == 100.0


def test_desc_words():
    assert desc_words("a " * 570) == 0
    real_desc = " ".join(f"word{i}" for i in range(80))
    assert desc_words(real_desc) == 80
    assert ratio_score(desc_words(real_desc), 80) == 100.0
    sentence = "Áo thun cotton cao cấp thoáng mát bền đẹp"
    assert desc_words(f"{sentence}. {sentence}.") == desc_words(sentence)


def test_review_score_missing_is_zero():
    assert review_score(0, 0, 0.8, 5) == 0.0


def test_review_score_smoothed():
    assert review_score(5, 5, 0.8, 5) == 90.0
