"""Tải model tách nền cho mockup POD về SEG_MODEL_DIR (chạy một lần; Dockerfile gọi lúc build).

    python -m scripts.seg.fetch_model
"""

import hashlib
import shutil
import sys
import urllib.request

from app.services.segment_service import MODEL_NAME, model_path

BASE = "https://github.com/danielgatis/rembg/releases/download/v0.0.0"
SOURCES = {
    "birefnet-general-lite": (
        "BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx",
        "5600024376f572a557870a5eb0afb1e5961636bef4e1e22132025467d0f03333",
    ),
    "isnet-general-use": (
        "isnet-general-use.onnx",
        None,
    ),
}


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    remote, expected = SOURCES[MODEL_NAME]
    dest = model_path()
    if dest.exists() and (expected is None or sha256(dest) == expected):
        print(f"skip {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(f"{BASE}/{remote}", timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    got = sha256(tmp)
    if expected and got != expected:
        tmp.unlink()
        sys.exit(f"sha256 mismatch: {got}")
    tmp.replace(dest)
    print(f"ok {dest} {dest.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
