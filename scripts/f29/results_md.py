import json
from pathlib import Path

from scripts.f29.results_register import ai_body
from scripts.f29.results_checks import ATTR_FRAME, attr_body
from scripts.f29.results_models import B1_FRAME, B2_FRAME, B3_FRAME, b1_body, b2_body, b3_body
from scripts.f29.results_models import C2_FRAME, c2_body
from scripts.f29.results_models import C_FRAME, C_NOTE, C_PENDING, c_body
from scripts.f29.results_base import load
from scripts.f29.results_checks import I_FRAME, i_body
from scripts.f29.results_checks import neg_body
from scripts.f29.results_register import R3_FRAME, r3_body
from scripts.f29.results_r3b import r3b_body
from scripts.f29.results_base import a_body, glossary, k_body
from scripts.f29.results_checks import TR_FRAME, transfer_body

ROOT = Path(__file__).resolve().parents[3]
MODELS = ROOT / "AI-Analysic/app/core/f29/models"
ARCHIVE = ROOT / "AI-Analysic/archive/f29/models"
ARCHIVED = "đã cất (archive/f29)"
WEIGHTS = ROOT / "AI-Analysic/app/core/f29/config/health_weights.json"
TRANSFER = ROOT / "notes/f29/labels/transfer_metrics.json"
OUT = ROOT / "notes/f29/RESULTS.md"
TRANSFER_NAME = "transfer_metrics.json"
REGISTER = ROOT / "notes/f29/register"
SRC = {"b1": "b1_type/v1/metrics.json", "b2": "b2_material/v1/metrics.json",
       "b3": "b3_mismatch/v1/metrics.json", "i": "i_dupes/v1/metrics.json", "c": "c1_quality/v1/metrics.json",
       "attr": "b3_attr/v1/metrics.json", "c2": "c1_quality/v2/metrics.json"}
HEADER = ("# F29 · Kết quả đo\n\nSinh bởi `scripts/f29/run.py`. Bảng K và A gõ tay (nguồn ghi trong mục); "
          "các bảng khác đọc từ metrics.json, không sửa tay. Ngày khoá tập test: 21/11/2026 (PROTOCOL.md).")


def section(title: str, body: str) -> str:
    return f"## {title}\n\n{body}"


def guarded(title, deps, fn, skel, pending="Chưa có số"):
    missing = next((k for k, v in deps.items() if v is None), None)
    if missing:
        return f"## {title}\n\n{pending} (thiếu {missing}).\n\n{skel}"
    try:
        return section(title, fn(*deps.values()))
    except KeyError as e:
        return f"## {title}\n\n{pending} (thiếu khoá {e.args[0]}).\n\n{skel}"
    except TypeError:
        return f"## {title}\n\n{pending} (dữ liệu không đúng dạng).\n\n{skel}"


def _mode(models: Path, rel: str, default: str = "shadow") -> str:
    return (load(models / rel) or {}).get("mode", default)


def _modes(models: Path) -> dict:
    return {"b3_mismatch": ARCHIVED, "b3_attr": _mode(models, "b3_attr/v1/thresholds.json"), "c1": ARCHIVED}


def r3b_section() -> list[str]:
    m = load(REGISTER / "multi.json")
    if not m or "test" not in m:
        return []
    r5 = (((load(REGISTER / "metrics.json") or {}).get("test") or {}).get("mô phỏng") or {}).get("chính thức", {}).get("r")
    return [section("R3b · Trọng số học từ 3 bộ dữ liệu thật", r3b_body(m, r5))]


def _source() -> dict:
    return json.loads(WEIGHTS.read_text("utf-8"))["learned"]["source"]


def _weights() -> dict:
    w = json.loads(WEIGHTS.read_text("utf-8"))["weights"]
    labels = {"image": "Ảnh", "description": "Mô tả", "tags": "Tag", "review": "Đánh giá", "price": "Giá"}
    return {labels[k]: w[k] for k in labels}


def build(models: Path = MODELS, transfer: Path = TRANSFER, archive: Path = ARCHIVE) -> str:
    b1, b2, b3 = load(models / SRC["b1"]), load(models / SRC["b2"]), load(archive / SRC["b3"])
    i, c, t = load(models / SRC["i"]), load(archive / SRC["c"]), load(transfer)
    a, c2 = load(models / SRC["attr"]), load(archive / SRC["c2"])
    parts = [
        HEADER,
        "### Thuật ngữ trong bảng\n\n" + glossary(),
        section("K · Khung đo chung", k_body()),
        section("A · Kiểm file in", a_body()),
        guarded("B1 · Loại hàng từ ảnh và chữ", {SRC["b1"]: b1}, b1_body, B1_FRAME),
        guarded("B2 · Chất liệu từ tên và mô tả", {SRC["b2"]: b2}, b2_body, B2_FRAME),
        guarded("B3 · Kiểm mâu thuẫn ảnh, chữ, loại hàng", {SRC["b3"]: b3}, b3_body, B3_FRAME),
        guarded("B3b · Thuộc tính ảnh (AI)", {SRC["attr"]: a, TRANSFER_NAME: t}, attr_body, ATTR_FRAME),
        guarded("C · Chất lượng ảnh (bản 1, đã thay bằng C2)", {SRC["c"]: c}, c_body, C_FRAME + "\n\n" + C_NOTE, C_PENDING),
        guarded("C2 · Chất lượng ảnh sản phẩm (AI)", {SRC["c2"]: c2}, c2_body, C2_FRAME),
        guarded("I · Ảnh trùng", {SRC["i"]: i}, i_body, I_FRAME),
        guarded("Chuyển sàn VietCraft", {TRANSFER_NAME: t}, transfer_body, TR_FRAME),
        guarded("R3 · Health Score theo bản đăng ký", {"register/metrics.json": load(REGISTER / "metrics.json")},
                lambda m: r3_body(m, load(REGISTER / "e2e.json"), _source()), R3_FRAME),
        *r3b_section(),
        section("AI quyết định phần nào của điểm", ai_body(_modes(models), _weights())),
        guarded("Kết quả âm", {SRC["b1"]: b1, SRC["b3"]: b3, SRC["i"]: i, TRANSFER_NAME: t},
                lambda b1, b3, i, t: neg_body(b1, b3, i, t, c, a, c2), ""),
    ]
    return "\n\n".join(parts) + "\n"


def write(out: Path = OUT, models: Path = MODELS, transfer: Path = TRANSFER, archive: Path = ARCHIVE) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(models, transfer, archive), "utf-8")
