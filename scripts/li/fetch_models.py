import hashlib
import shutil
import sys
import urllib.request

from app.core.listing_intel.embedder import FILES, MODEL_DIR, MODEL_ID

REVISION = "ba1f3b0843f24bc5417d38e19c37b287d719b2f4"
SHA256 = {
    "onnx/vision_model_int8.onnx": "0dd31785a2713f1113ef2272472165c69d580473dae38d7b47568ac587795e70",
    "onnx/text_model_int8.onnx": "3a0603d3a00c05a80a6ded4743c16aaac7b1e62cdcc7e362e7ce418659b96400",
    "tokenizer.json": "cb9140fae3ac5122c972d37adf83e1248471a38147ad76f8215c8872c6fd8322",
}


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(path: str) -> None:
    dest = MODEL_DIR / path
    if dest.exists() and sha256(dest) == SHA256[path]:
        print(f"skip {path}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    url = f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{path}"
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    got = sha256(tmp)
    if got != SHA256[path]:
        tmp.unlink()
        sys.exit(f"sha256 mismatch for {path}: {got}")
    tmp.replace(dest)
    print(f"ok {path} {dest.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    for p in FILES:
        fetch(p)
