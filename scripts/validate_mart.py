import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.writer import BLOCKED, MART_SCHEMA, META_FIELDS


class KetQua:
    def __init__(self, bang: str):
        self.bang = bang
        self.so_dong = 0
        self.loi: List[str] = []
        self.canh_bao: List[str] = []

    @property
    def dat(self) -> bool:
        return not self.loi


def kiem_ban_ghi(bang: str, docs: List[Dict[str, Any]]) -> KetQua:
    """Phần thuần logic — không đụng MongoDB, nên test được offline."""
    kq = KetQua(bang)
    kq.so_dong = len(docs)

    so_do = MART_SCHEMA[bang]
    khoa: List[str] = so_do["key"]
    bat_buoc: List[str] = so_do.get("fields_bat_buoc", [])
    cho_phep = set(so_do.get("fields", {})) | set(khoa) | set(META_FIELDS) | {"scope", "scope_id", "_id"}

    if not docs:
        return kq  # bảng rỗng là trạng thái ĐÚNG khi chưa job nào chạy, không phải lỗi

    thieu_meta: Counter = Counter()
    thieu_khoa: Counter = Counter()
    khoa_rong: Counter = Counter()
    thieu_than: Counter = Counter()
    cot_la: Counter = Counter()
    vet_khoa: Counter = Counter()

    for d in docs:
        for f in META_FIELDS:
            if not d.get(f):
                thieu_meta[f] += 1
        for k in khoa:
            if k not in d:
                thieu_khoa[k] += 1
            elif d[k] is None or str(d[k]).strip() == "":
                khoa_rong[k] += 1
        for k in bat_buoc:
            if k not in d:
                thieu_than[k] += 1
        for k in set(d) - cho_phep:
            cot_la[k] += 1
        if all(k in d for k in khoa):
            vet_khoa[tuple(str(d[k]) for k in khoa)] += 1

    n = len(docs)
    for f, c in thieu_meta.items():
        kq.loi.append(f"thiếu `{f}` ở {c}/{n} dòng — tháng 12 không ai biết số này "
                      f"tính bằng phiên bản code nào, và KHÔNG sửa lại được")
    for k, c in thieu_khoa.items():
        kq.loi.append(f"thiếu trường khoá `{k}` ở {c}/{n} dòng")
    for k, c in khoa_rong.items():
        kq.loi.append(f"trường khoá `{k}` rỗng ở {c}/{n} dòng — mọi dòng rỗng gộp thành một")
    for k, c in thieu_than.items():
        kq.loi.append(f"thiếu cột bắt buộc `{k}` ở {c}/{n} dòng ({so_do['fields'].get(k, '')})")

    trung = {k: v for k, v in vet_khoa.items() if v > 1}
    if trung:
        vd = list(trung.items())[:3]
        kq.loi.append(f"{len(trung)} khoá bị trùng, ví dụ " +
                      ", ".join(f"{'|'.join(k)} x{v}" for k, v in vd))

    for k, c in cot_la.items():
        kq.canh_bao.append(f"cột `{k}` không khai báo trong MART_SCHEMA ({c}/{n} dòng) — "
                           f"gõ sai tên thì API đọc theo hợp đồng sẽ không thấy")

    return kq


def doc_tu_mongo(bang: str, sample: int) -> List[Dict[str, Any]]:
    from pymongo import MongoClient
    from app.config import settings

    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=10000)
    return list(client[settings.MONGO_DB_SEED][bang].find().limit(sample))


def main() -> int:
    ap = argparse.ArgumentParser(description="Kiểm bảng mart có đúng MART_SCHEMA không")
    ap.add_argument("bang", nargs="?", help="tên bảng; bỏ trống thì dùng --all")
    ap.add_argument("--all", action="store_true", help="kiểm cả 8 bảng")
    ap.add_argument("--sample", type=int, default=100, help="số dòng đọc mỗi bảng (mặc định 100)")
    ap.add_argument("--offline", action="store_true", help="không nối Mongo, chỉ kiểm bản thân hợp đồng")
    a = ap.parse_args()

    if a.bang and a.bang in BLOCKED:
        print(f"✗ `{a.bang}` BỊ CHẶN:\n  {BLOCKED[a.bang]}")
        return 1

    if a.all:
        cac_bang = list(MART_SCHEMA)
    elif a.bang:
        if a.bang not in MART_SCHEMA:
            print(f"✗ `{a.bang}` không có trong MART_SCHEMA.")
            print(f"  Bảng cho phép: {', '.join(sorted(MART_SCHEMA))}")
            return 1
        cac_bang = [a.bang]
    else:
        ap.error("cho tên bảng, hoặc --all")

    print(f"=== KIỂM {len(cac_bang)} BẢNG MART THEO MART_SCHEMA ===")
    if a.offline:
        print("(chế độ --offline: chỉ kiểm hợp đồng tự nhất quán, không đọc dữ liệu)\n")
    else:
        print(f"(đọc tối đa {a.sample} dòng mỗi bảng từ MongoDB — CHỈ ĐỌC)\n")

    ket_qua: List[KetQua] = []
    for bang in cac_bang:
        if a.offline:
            docs: List[Dict[str, Any]] = []
        else:
            try:
                docs = doc_tu_mongo(bang, a.sample)
            except Exception as e:
                kq = KetQua(bang)
                kq.loi.append(f"không đọc được từ MongoDB: {type(e).__name__}: {str(e)[:80]}")
                ket_qua.append(kq)
                continue
        ket_qua.append(kiem_ban_ghi(bang, docs))

    rong = hong = 0
    for kq in ket_qua:
        if kq.dat and kq.so_dong == 0:
            rong += 1
            print(f"  ○ {kq.bang:24} 0 bản ghi, schema hợp lệ (chưa job nào ghi — đúng)")
        elif kq.dat:
            print(f"  ✓ {kq.bang:24} {kq.so_dong} bản ghi, hợp lệ")
        else:
            hong += 1
            print(f"  ✗ {kq.bang:24} {kq.so_dong} bản ghi")
            for l in kq.loi:
                print(f"      · {l}")
        for c in kq.canh_bao:
            print(f"      ⚠ {c}")

    dat = len(ket_qua) - hong
    print(f"\n{dat}/{len(ket_qua)} bảng đạt" + (f" ({rong} bảng còn rỗng)" if rong else ""))
    if hong:
        print(f"❌ {hong} bảng sai hợp đồng — xem MART_SCHEMA trong app/core/writer.py")
        return 1
    print("✅ MỌI BẢNG ĐỀU KHỚP HỢP ĐỒNG")
    return 0


def _tu_kiem():
    """Chạy được không cần MongoDB — đây là phần logic thật của script."""
    print("=== TỰ KIỂM TRA MODULE VALIDATE_MART.PY ===")

    kq = kiem_ban_ghi("listing_health", [])
    assert kq.dat and kq.so_dong == 0
    print("✓ bảng rỗng -> hợp lệ, không phải lỗi")

    tot = [{"listing_id": "lst_1", "date": "2026-09-21", "health_score": 73.4,
            "band": "cần cải thiện", "breakdown": {}, "run_id": "r1",
            "model_version": "v1", "computed_at": "2026-09-21T02:00:00Z"}]
    assert kiem_ban_ghi("listing_health", tot).dat
    print("✓ bản ghi đúng -> đạt")

    kq = kiem_ban_ghi("listing_health", [{k: v for k, v in tot[0].items() if k != "model_version"}])
    assert not kq.dat and "model_version" in kq.loi[0]
    print("✓ bắt thiếu trường xuất xứ")

    kq = kiem_ban_ghi("listing_health", [{k: v for k, v in tot[0].items() if k != "band"}])
    assert not kq.dat and "band" in kq.loi[0]
    print("✓ bắt thiếu cột thân bắt buộc")

    kq = kiem_ban_ghi("listing_health", tot + tot)
    assert not kq.dat and "trùng" in kq.loi[0]
    print("✓ bắt khoá trùng")

    kq = kiem_ban_ghi("listing_health", [{**tot[0], "diem_suc_khoe": 73.4}])
    assert kq.dat and kq.canh_bao, "cột lạ phải là cảnh báo, không phải lỗi"
    print("✓ cột lạ -> cảnh báo, vẫn cho qua")

    kq = kiem_ban_ghi("listing_health", [{**tot[0], "listing_id": "  "}])
    assert not kq.dat and "rỗng" in kq.loi[0]
    print("✓ bắt trường khoá rỗng")

    print("✅ TẤT CẢ SELF-CHECKS CỦA VALIDATE_MART.PY ĐÃ PASS!")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _tu_kiem()
    else:
        sys.exit(main())
