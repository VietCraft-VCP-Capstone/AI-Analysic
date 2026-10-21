import os
from pathlib import Path

DATA_DIR = Path(
    os.environ.get("LI_DATA_DIR") or Path(__file__).resolve().parents[4] / "data-li"
)


def raw(name: str) -> Path:
    path = DATA_DIR / "raw"
    path.mkdir(parents=True, exist_ok=True)
    return path / name


def clean(name: str) -> Path:
    path = DATA_DIR / "clean"
    path.mkdir(parents=True, exist_ok=True)
    return path / name
