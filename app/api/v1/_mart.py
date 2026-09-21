"""
_mart.py — Lớp đọc dữ liệu dùng chung cho 16 endpoint F26–F41.

Chỉ ĐỌC. Không endpoint nào được ghi (trừ F36 quản lý danh sách theo dõi).
Job chạy đêm ghi bằng `app/core/writer.py`, không phải ở đây.

Vì sao tách ra khỏi `_template.py`: file kia thuần khuôn phản hồi, không đụng
MongoDB, nên test được mà không cần mạng. File này mới là chỗ nối database.
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pymongo import MongoClient

from app.api.v1._template import invalid_param
from app.config import settings

_client: Optional[MongoClient] = None


def db():
    """Một MongoClient dùng chung cho cả tiến trình.

    Tạo client mới mỗi request là mỗi lần bắt tay TLS lại với Atlas — thêm
    khoảng 100ms và tốn kết nối của cụm dùng chung. MongoClient vốn an toàn
    khi dùng nhiều luồng, nên giữ một cái là đúng.
    """
    global _client
    if _client is None:
        _client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=10000,
                              maxPoolSize=20, retryWrites=True)
    return _client[settings.MONGO_DB_SEED]


KHOANG_HOP_LE = {"7d": 7, "30d": 30, "90d": 90}


def doc_khoang(time_range: str) -> int:
    if time_range not in KHOANG_HOP_LE:
        invalid_param("timeRange", " | ".join(KHOANG_HOP_LE))
    return KHOANG_HOP_LE[time_range]


def ngay_moi_nhat(loc: Dict[str, Any], coll: str = "listing_daily") -> Optional[str]:
    """Ngày mới nhất CÓ THẬT trong dữ liệu, ứng với bộ lọc đưa vào.

    Không dùng ngày hôm nay làm mốc. Dữ liệu mồi dừng ở 2026-08-30; lấy mốc là
    hôm nay thì cửa sổ 30 ngày rơi vào vùng trống và mọi KPI ra 0 — người đọc sẽ
    tưởng shop ế chứ không nghĩ là hết dữ liệu. Đây đúng là lỗi `THIẾU ≠ 0`,
    chỉ khác là nó xảy ra ở tầng chọn mốc thời gian.
    """
    d = db()[coll].find_one(loc, {"date": 1}, sort=[("date", -1)])
    return d["date"] if d else None


def cua_so(den_ngay: str, so_ngay: int) -> Tuple[str, str]:
    """Trả (từ_ngày, đến_ngày) cho một cửa sổ, bao gồm cả hai đầu."""
    d = datetime.strptime(den_ngay, "%Y-%m-%d").date()
    return ((d - timedelta(days=so_ngay - 1)).isoformat(), d.isoformat())


def cua_so_truoc(tu_ngay: str, so_ngay: int) -> Tuple[str, str]:
    """Kỳ so sánh: ĐÚNG BẰNG độ dài kỳ đang xem, nằm liền ngay trước nó (BR-175)."""
    d = datetime.strptime(tu_ngay, "%Y-%m-%d").date() - timedelta(days=1)
    return ((d - timedelta(days=so_ngay - 1)).isoformat(), d.isoformat())


def phan_tram_thay_doi(nay: float, truoc: float) -> Optional[float]:
    """Đổi phần trăm so kỳ trước. Kỳ trước bằng 0 thì trả None, KHÔNG trả 0 hay ∞."""
    if not truoc:
        return None
    return round((nay - truoc) / truoc * 100, 1)


def ty_le_chuyen_doi(don: float, luot_xem: float) -> Optional[float]:
    """CR = đơn / lượt xem × 100. Không lượt xem nào thì trả None (BR-176).

    Trả 0 là sai: 0 nghĩa là "có người xem mà không ai mua", còn None nghĩa là
    "chưa ai xem". Hai chuyện khác hẳn nhau với người bán.
    """
    if not luot_xem:
        return None
    return round(don / luot_xem * 100, 2)


def gop(loc: Dict[str, Any], cot: Dict[str, str], coll: str = "listing_daily") -> Dict[str, Any]:
    """Gộp tổng vài cột theo một bộ lọc. Không có dòng nào thì trả dict rỗng."""
    r = list(db()[coll].aggregate([
        {"$match": loc},
        {"$group": {"_id": None, **{k: {"$sum": f"${v}"} for k, v in cot.items()}}},
    ]))
    return {k: r[0].get(k, 0) for k in cot} if r else {}


def tien(x: Any) -> int:
    """Tiền là VND số nguyên, không phần thập phân. Tên trường kết thúc `_vnd`."""
    return int(round(float(x or 0)))


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA MODULE _MART.PY ===")

    assert doc_khoang("30d") == 30
    try:
        doc_khoang("99d"); raise AssertionError("phải chặn timeRange lạ")
    except Exception as e:
        assert getattr(e, "status_code", None) == 400
    print("✓ doc_khoang chặn giá trị ngoài 7d/30d/90d bằng 400")

    assert cua_so("2026-08-30", 30) == ("2026-08-01", "2026-08-30")
    print("✓ cua_so tính đúng, bao gồm cả hai đầu")

    assert cua_so_truoc("2026-08-01", 30) == ("2026-07-02", "2026-07-31")
    print("✓ cua_so_truoc dài đúng bằng kỳ hiện tại và nằm liền trước (BR-175)")

    assert phan_tram_thay_doi(110, 100) == 10.0
    assert phan_tram_thay_doi(50, 0) is None, "kỳ trước = 0 phải trả None, không phải 0 hay vô cực"
    print("✓ phan_tram_thay_doi không chia cho 0")

    assert ty_le_chuyen_doi(12, 400) == 3.0
    assert ty_le_chuyen_doi(0, 0) is None, "0 lượt xem phải trả None (BR-176)"
    assert ty_le_chuyen_doi(0, 100) == 0.0, "có người xem mà không ai mua thì ĐÚNG là 0"
    print("✓ ty_le_chuyen_doi phân biệt 'chưa ai xem' (None) với 'xem mà không mua' (0)")

    assert tien(2508000.0) == 2508000 and isinstance(tien(2508000.0), int)
    assert tien(None) == 0
    print("✓ tien() ép về VND số nguyên")

    print("✅ TẤT CẢ SELF-CHECKS CỦA _MART.PY ĐÃ PASS!")
