"""
F42: nhận diện sản phẩm từ ảnh + hàm gọi Gemini dùng chung. Không gọi mạng.
"""

import base64
import io
import json
import urllib.error

import pytest
from PIL import Image

from app.services.f42 import gemini_client
from app.services.f42.image_recognizer import ImageInputError, _clean, decode_image, recognize_product_image

CATS = ["Áo dài", "Áo thun", "Trang trí", "Ly tách"]


def _png(w=50, h=40) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ------------------------------------------------------------------ ảnh đầu vào
def test_decode_accepts_data_url_and_shrinks_large_images():
    data, mime = decode_image("data:image/png;base64," + _png(3000, 1500))
    assert mime == "image/jpeg" and Image.open(io.BytesIO(data)).size == (1024, 512)


@pytest.mark.parametrize("bad,mime", [("", ""), ("không-phải-base64!!", ""),
                                      (base64.b64encode(b"day khong phai anh").decode(), ""),
                                      (_png(), "image/gif")])
def test_decode_rejects_bad_input(bad, mime):
    with pytest.raises(ImageInputError):
        decode_image(bad, mime)


# ------------------------------------------------------------------ làm sạch kết quả AI
def test_clean_keeps_only_real_category_and_specific_materials():
    r = _clean({"is_product": True, "product_name": "Áo dài lụa đỏ cổ tròn", "product_type": "Áo dài",
                "category": "ao dai", "materials": ["Vải", "lụa"], "colors": ["Đỏ"], "confidence": "high"}, CATS)
    assert (r["product_name"], r["category"], r["materials"]) == ("Áo dài lụa đỏ cổ tròn", "Áo dài", ["Lụa"])
    r2 = _clean({"is_product": True, "product_name": "Bình hoa", "category": "Danh mục bịa"}, CATS)
    assert r2["category"] is None                                     # không nhận danh mục không có trên sàn


def test_clean_not_a_product_clears_fields():
    r = _clean({"is_product": False, "product_name": "Phong cảnh biển", "category": "Trang trí", "materials": ["gỗ"]}, CATS)
    assert r["is_product"] is False and r["product_name"] == "" and r["category"] is None and r["materials"] == []


def test_recognize_uses_caller_and_reports_unavailable():
    seen = {}

    def ok_caller(parts, key, models, **kw):
        seen["parts"] = parts
        return {"is_product": True, "product_name": "Ly sứ trắng có quai", "category": "Ly tách", "confidence": "high"}
    r = recognize_product_image(_png(), "image/png", CATS, caller=ok_caller)
    assert r["product_name"] == "Ly sứ trắng có quai" and r["category"] == "Ly tách"
    assert seen["parts"][0]["inline_data"]["mime_type"] == "image/jpeg" and "Ly tách" in seen["parts"][1]["text"]
    assert "error" in recognize_product_image(_png(), "image/png", CATS, caller=lambda *a, **k: None)


# ------------------------------------------------------------------ gọi Gemini dùng chung
class _Resp:
    def __init__(self, obj):
        self.raw = json.dumps(obj).encode()

    def read(self):
        return self.raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _answer(d):
    return _Resp({"candidates": [{"content": {"parts": [{"text": json.dumps(d)}]}}]})


def _http(code):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b"{}"))


def test_falls_back_to_next_model_on_quota_error():
    calls = []

    def opener(req, timeout):
        model = req.full_url.split("/models/")[1].split(":")[0]
        calls.append(model)
        if model == "m1":
            raise _http(429)
        return _answer({"titles": ["a"]})
    out = gemini_client.generate_json([{"text": "x"}], "key", ["m1", "m2"], timeout_s=10, opener=opener)
    assert out == {"titles": ["a"]} and calls == ["m1", "m2"]


def test_retries_without_thinking_config_on_400():
    bodies = []

    def opener(req, timeout):
        body = json.loads(req.data)
        bodies.append(body)
        if "thinkingConfig" in body["generationConfig"]:
            raise _http(400)                                          # model không nhận tham số này
        return _answer({"ok": 1})
    assert gemini_client.generate_json([{"text": "x"}], "key", ["lite"], timeout_s=10, opener=opener) == {"ok": 1}
    assert len(bodies) == 2 and "thinkingConfig" not in bodies[1]["generationConfig"]


def test_rejected_answer_tries_next_model_and_no_key_returns_none():
    answers = iter([_answer({"titles": []}), _answer({"titles": ["b"]})])
    out = gemini_client.generate_json([{"text": "x"}], "key", ["m1", "m2"], timeout_s=10,
                                      accept=lambda d: bool(d.get("titles")), opener=lambda r, timeout: next(answers))
    assert out == {"titles": ["b"]}
    assert gemini_client.generate_json([{"text": "x"}], "", ["m1"], timeout_s=10) is None


# ------------------------------------------------------------------ nhiều ảnh, nhiều màu
def test_multiple_images_sent_together_and_capped():
    seen = {}

    def caller(parts, key, models, **kw):
        seen["n_images"] = sum(1 for p in parts if "inline_data" in p)
        return {"is_product": True, "product_name": "Áo thun trơn cổ tròn", "category": "Áo thun",
                "colors": [{"name": "Đen", "hex": "#1e1e1e"}, {"name": "xanh navy", "hex": "#273751"},
                           {"name": "Đen", "hex": "#000000"}, {"name": "Be", "hex": "nâu nhạt"}]}
    r = recognize_product_image([_png()] * 4, "", CATS, caller=caller)
    assert seen["n_images"] == 4
    assert r["colors"] == [{"name": "Đen", "hex": "#1E1E1E"}, {"name": "Xanh navy", "hex": "#273751"},
                           {"name": "Be", "hex": ""}]                    # bỏ trùng, hex sai → để trống
    with pytest.raises(ImageInputError):
        recognize_product_image([_png()] * 7, "", CATS, caller=caller)  # tối đa 6 ảnh
    with pytest.raises(ImageInputError):
        recognize_product_image([], "", CATS, caller=caller)


def test_array_answer_one_object_per_image_is_merged():
    # gemini-3.1-flash-lite trả mảng, mỗi ảnh một object → trước đây bị bỏ, báo "ai_unavailable"
    raw = _answer([{"is_product": True, "product_name": "Điện thoại OPPO Reno 15F", "category": "Điện thoại",
                    "colors": [{"name": "Hồng", "hex": "#F2C6CE"}]},
                   {"is_product": True, "product_name": "Điện thoại OPPO Reno 15F", "category": "Điện thoại",
                    "colors": [{"name": "Xanh đen", "hex": "#2E344A"}]}])
    caller = lambda parts, key, models, **kw: gemini_client.generate_json(parts, "key", ["m"], timeout_s=10, accept=kw["accept"],
                                                                         opener=lambda r, timeout: raw)
    r = recognize_product_image([_png(), _png()], "", ["Điện thoại"], caller=caller)
    assert r["product_name"] == "Điện thoại OPPO Reno 15F" and r["category"] == "Điện thoại"
    assert [c["name"] for c in r["colors"]] == ["Hồng", "Xanh đen"]
