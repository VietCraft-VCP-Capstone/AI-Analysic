import json
import math
import unicodedata
from pathlib import Path

import pytest

from app.core.listing_intel.lexicon import attributes, banned_hits
from app.core.listing_intel.normalize import fold, ngrams, norm
from app.core.listing_intel.text_axis import text_features, text_issues
from app.core.listing_intel.types import AxisResult, ListingInput


def issue_codes(inp):
    return {i["code"] for i in text_issues(inp, text_features(inp, None))}


def test_norm_nfd_and_nfc_equal():
    nfd = unicodedata.normalize("NFD", "Áo Khoác Len")
    assert norm(nfd) == norm("Áo khoác len") == "áo khoác len"


def test_fold_removes_diacritics():
    assert fold("Đầm Lụa Tơ Tằm") == "dam lua to tam"


def test_emoji_and_caps_stripped():
    assert norm("ÁO THUN 🔥🔥 SALE!!!") == "áo thun sale"


def test_fold_same_for_caps_emoji_nfd_variants():
    variants = ["ÁO THUN 🔥", "ao thun", unicodedata.normalize("NFD", "áo thun")]
    assert len({fold(v) for v in variants}) == 1


def test_ngrams_syllable_level():
    assert ngrams("Túi da nữ") == ["túi", "da", "nữ", "túi da", "da nữ"]


def test_attributes_detect_material_without_diacritics():
    assert attributes("ao khoac da bo nam")["material"] == ["da bò"]


def test_attributes_other_axes():
    a = attributes("Áo thun đen oversize đi học size 40, dài 100cm")
    assert "đen" in a["color"] and "oversize" in a["size"]
    assert "cm" in a["size"] and "size 40" in a["size"] and a["use"] == ["đi học"]


@pytest.mark.parametrize("title", [
    "Túi đa năng", "Áo khoác nam thu đông", "Áo lên dáng chuẩn", "Đầm may đo", "Áo chống lạnh",
])
def test_no_false_material_on_accented_text(title):
    assert attributes(title)["material"] == []


def test_trendy_tre_is_not_material():
    assert attributes("Áo thun trẻ trung")["material"] == ["thun"]


@pytest.mark.parametrize("title", ["Quà trái tim", "Do chất lượng cao"])
def test_no_false_color_on_accented_text(title):
    assert attributes(title)["color"] == []


def test_apostrophe_not_size():
    assert attributes("Women's tee")["size"] == []
    assert attributes("Let's go")["size"] == []


@pytest.mark.parametrize("title", ["Áo len cổ lọ", "ao len co lo"])
def test_len_material(title):
    assert attributes(title)["material"] == ["len"]


def test_tone_placement_variants_match():
    assert attributes("Ly thuỷ tinh")["material"] == ["thủy tinh"]
    assert attributes("Ly thủy tinh")["material"] == ["thủy tinh"]
    assert attributes("ly thuy tinh")["material"] == ["thủy tinh"]
    assert norm("quý toán thuỷ") == "quý toán thủy"


def test_extra_size_terms():
    for title in ("Áo free size", "Áo XXXL", "Áo 3XL"):
        assert attributes(title)["size"], title


def test_none_title_and_description_do_not_crash():
    inp = ListingInput(title=None, description=None, group="fashion")
    feats = text_features(inp, None)
    assert feats["title_len"] == 0 and feats["desc_len"] == 0
    assert "title_short" in {i["code"] for i in text_issues(inp, feats)}


def test_empty_group_table_is_nan():
    f = text_features(ListingInput(title="Túi da nữ", group="bags"), {"bags": {}})
    assert math.isnan(f["kw_lift_sum"]) and math.isnan(f["kw_lift_terms"])


def test_missing_material_issue_only_for_fashion_groups():
    fashion = ListingInput(title="Áo nam đẹp", group="fashion")
    home = ListingInput(title="Áo nam đẹp", group="home")
    declared = ListingInput(title="Áo nam đẹp", group="fashion", materials=["cotton"])
    assert "missing_material" in issue_codes(fashion)
    assert "missing_material" not in issue_codes(home)
    assert "missing_material" not in issue_codes(declared)


def test_color_size_issues_only_fashion_and_shoes():
    assert {"missing_color", "missing_size"} <= issue_codes(ListingInput(title="Giày", group="shoes"))
    assert not {"missing_color", "missing_size"} & issue_codes(ListingInput(title="Túi", group="bags"))


def test_keyword_stuffing():
    inp = ListingInput(title="túi túi túi xách túi đẹp túi")
    assert "keyword_stuffing" in issue_codes(inp)


def test_length_issues():
    assert "title_short" in issue_codes(ListingInput(title="Áo"))
    assert "title_long" in issue_codes(ListingInput(title="a" * 121))
    assert "desc_short" in issue_codes(ListingInput(title="Áo", description="ngắn"))


def test_banned_word_detected_on_folded_text():
    assert banned_hits("Áo SEX giá rẻ") == ["sex"]
    assert banned_hits("Giày đi học") == []
    assert "banned_word" in issue_codes(ListingInput(title="Ma tuý đá"))


def test_banned_dirty_word_accent_aware():
    assert banned_hits("con đĩ") == ["đĩ"]
    assert banned_hits("Giày đi học") == []
    assert banned_hits("Điện thoại di động") == []
    assert banned_hits("ma tuy da") == ["ma túy", "ma túy đá"]


def test_banned_data_ported():
    data = json.loads(Path("app/core/listing_intel/data/banned_vi.json").read_text("utf-8"))
    assert len(data["phrases"]) == 87 and len(data["words"]) == 16


def test_kw_lift_nan_without_table():
    assert math.isnan(text_features(ListingInput(title="Túi da nữ"), None)["kw_lift_sum"])


def test_kw_lift_uses_group_table():
    inp = ListingInput(title="Túi da nữ", group="bags")
    f = text_features(inp, {"bags": {"túi da": 1.2, "da": 0.3}})
    assert f["kw_lift_sum"] == pytest.approx(1.5)
    assert f["kw_lift_max"] == 1.2
    assert f["kw_lift_terms"] == 2


def test_types_defaults():
    inp = ListingInput(title="x")
    assert inp.tags == [] and inp.image_urls == [] and inp.group is None
    assert AxisResult(score=None, missing_reason="r").issues == []
