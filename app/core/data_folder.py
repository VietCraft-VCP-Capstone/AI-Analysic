
import os
import glob
from typing import List, Optional

import pandas as pd
import pyarrow.parquet as pq

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(os.path.dirname(BASE_DIR))
WORKSPACE = os.path.dirname(ROOT_DIR)
DATA_DIR = os.environ.get("VC_DATA_DIR") or os.path.join(WORKSPACE, "vc-data")


class ThieuDuLieu(FileNotFoundError):
    """Chưa kéo dữ liệu về. Nói rõ cách sửa thay vì ném đường dẫn trống."""


def duong_dan(ten: str) -> str:
    hit = glob.glob(os.path.join(DATA_DIR, "*", f"{ten}.parquet"))
    if not hit:
        co = sorted(os.path.basename(p)[:-8]
                    for p in glob.glob(os.path.join(DATA_DIR, "*", "*.parquet")))
        raise ThieuDuLieu(
            f"Không có `{ten}` trong {DATA_DIR}.\n"
            f"  Đang có: {', '.join(co) if co else '(trống — chưa kéo lần nào)'}\n"
            f"  Kéo về:  cd AI-Analysic && "
            f".venv/bin/python -m app.core.export_data_folder"
        )
    return hit[0]


def nap(ten: str, cot: Optional[List[str]] = None, **loc) -> pd.DataFrame:
    """Nạp một bảng. `cot` để chỉ đọc vài cột. `**loc` để lọc bằng nhau."""
    df = pd.read_parquet(duong_dan(ten), columns=cot)
    for k, v in loc.items():
        if k not in df.columns:
            raise KeyError(f"`{ten}` không có cột `{k}`. Cột đang có: {list(df.columns)}")
        df = df[df[k].isin(v)] if isinstance(v, (list, tuple, set)) else df[df[k] == v]
    return df


def co_gi() -> pd.DataFrame:
    """Liệt kê MỌI file đang có trên đĩa, không chỉ Parquet.

    `reference/` và `samples/` là JSON/CSV chép nguyên, không đổi sang Parquet —
    chúng nhỏ, và `samples/` phải giữ đúng định dạng gốc để làm mỏ neo đối chiếu.
    Bỏ chúng khỏi bảng này thì người đọc tưởng vc-data/ thiếu.
    """
    rows = []
    for p in sorted(glob.glob(os.path.join(DATA_DIR, "*", "*"))):
        if os.path.isdir(p):
            continue
        ten, duoi = os.path.splitext(os.path.basename(p))
        if duoi == ".parquet":
            # Đọc num_rows từ metadata, KHÔNG nạp dữ liệu.
            # read_parquet(columns=[]) trả về 0 dòng chứ không phải số dòng thật.
            dong = pq.ParquetFile(p).metadata.num_rows
        elif duoi == ".csv":
            with open(p, encoding="utf-8-sig", errors="replace") as f:
                dong = sum(1 for _ in f) - 1
        else:
            dong = None          # JSON: đếm dòng không có nghĩa
        rows.append({
            "tên": ten,
            "nhóm": os.path.basename(os.path.dirname(p)),
            "kiểu": duoi.lstrip("."),
            "dòng": dong,
            "MB": round(os.path.getsize(p) / 1048576, 2),
        })
    df = pd.DataFrame(rows)
    # Parquet trước (thứ dùng để tính), rồi tới phần tham chiếu
    thu_tu = {"behavior": 0, "master": 1, "trends": 2, "reference": 3, "samples": 4}
    return df.sort_values(["nhóm", "tên"], key=lambda c: c.map(thu_tu).fillna(9)
                          if c.name == "nhóm" else c).reset_index(drop=True)


if __name__ == "__main__":
    print(f"=== {DATA_DIR} ===")
    print(co_gi().to_string(index=False))
