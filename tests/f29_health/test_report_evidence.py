from scripts.f29_health.report_evidence import BETTER, TIE, tie_text


def _p(tiki, shopee):
    return {"gate": {"per_market": {"tiki_test": {"vs_equal_ci": tiki}, "shopee_test": {"vs_equal_ci": shopee}}}}


def test_tie_text_when_both_cis_contain_zero():
    assert tie_text(_p([-0.006, 0.009], [-0.005, 0.016])) == TIE


def test_tie_text_when_one_ci_excludes_zero():
    assert tie_text(_p([-0.006, 0.009], [0.01, 0.03])) == BETTER
