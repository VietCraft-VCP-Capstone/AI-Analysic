"""
_template.py — Vỏ phản hồi chung cho cả 16 endpoint F26–F41.

Đây là file mà 4 người còn lại IMPORT (không phải chép đi sửa). Mọi endpoint
phân tích trả về cùng một hình dạng, chỉ khác phần `data`:

    {"data": ..., "meta": {...}, "error": null}

Vì sao để trong code chứ không chỉ trong `docs/API_CONTRACT.md`: tài liệu là chữ,
không ai ép được. Ở đây `ok()` / `insufficient()` tự gắn đủ khối `meta`, nên một
endpoint viết đúng kiểu là tự động khớp hợp đồng.

  NGUYÊN TẮC SỐ MỘT — THIẾU ≠ 0.
  Không đủ dữ liệu thì gọi insufficient(), KHÔNG trả 0. Shop mới nhìn thấy
  "doanh thu 0đ" thay vì "chưa đủ dữ liệu" là lỗi nặng nhất của loại dashboard này.

Cách dùng trong một router tính năng:

    from app.api.v1._template import (
        ok, insufficient, meta_from_record, mart_not_ready, CurrentShop,
    )

    @router.get("/shop/overview")
    def f26_shop_overview(shop_id: str = CurrentShop, timeRange: str = "30d"):
        doc = db["mart_listing_daily"].find_one({"shop_id": shop_id})
        if doc is None:
            mart_not_ready("mart_listing_daily")          # -> 503, KHÔNG phải 500
        if doc["so_ngay"] < 7:
            return insufficient(
                f"Shop mới, chỉ có {doc['so_ngay']} ngày dữ liệu, cần tối thiểu 7",
                meta_from_record(doc, scope="shop", scope_id=shop_id),
            )
        return ok({"revenue_vnd": doc["revenue_vnd"]},
                  meta_from_record(doc, scope="shop", scope_id=shop_id))

Hợp đồng đầy đủ: docs/API_CONTRACT.md. File này KHÔNG truy vấn MongoDB —
chỉ khuôn phản hồi và xác thực.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Cho phép chạy trực tiếp `python app/api/v1/_template.py` (khối self-check cuối file).
# Cùng cách writer.py, main.py và analytics_routes.py đang làm.
ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import Depends, Header, HTTPException

# Nạp app/.env. Không dùng `settings` ở đây, nhưng import nó là kích hoạt dotenv —
# nếu không, ai import _template mà chưa import app.config sẽ thấy DEV_SHOP_ID trong
# .env bị bỏ qua, rồi ngồi tìm mãi không hiểu vì sao vẫn 401.
from app.config import settings as _nap_env  # noqa: F401

# ---------------------------------------------------------------------------
# HAI QUYẾT ĐỊNH ĐÃ CHỐT (mục 6 của API_CONTRACT.md, câu 2 và 2b)
#
# 1. Bọc {data, meta, error} — KHÔNG trải phẳng. FE đọc một chỗ cho cả 16 màn hình.
#
# 2. `status` chỉ nằm MỘT nơi: meta.status, từ vựng ok · partial · insufficient_data.
#    Trước đây ba tài liệu ghi ba kiểu: API_CONTRACT mục 1 để `quality.status`
#    (ready/limited/insufficient_data), mục "THIẾU ≠ 0" để `status` ở gốc, còn
#    task SPEC-02 để `meta.status`. Ba từ vựng cho cùng một khái niệm thì FE phải
#    viết ba nhánh. Bảng quy đổi cho ai đã đọc bản cũ:
#        quality.status = ready   -> meta.status = ok
#        quality.status = limited -> meta.status = partial
#        insufficient_data        -> giữ nguyên tên
#    `quality` vẫn còn, nhưng chỉ giữ sample_size · identity_linked · confidence.
# ---------------------------------------------------------------------------

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"          # có số nhưng độ tin cậy thấp
STATUS_INSUFFICIENT = "insufficient_data"

SOURCE_MODES = ("live", "seed_demo", "derived")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# KHỐI META
# ---------------------------------------------------------------------------

def build_meta(
    *,
    computed_at: Optional[str] = None,
    model_version: str = "unknown",
    scope: str = "platform",
    scope_id: Optional[str] = None,
    database: str = "vietcraft-seed",
    collection: Optional[str] = None,
    mode: str = "seed_demo",
    attributed_to_live_shop: bool = False,
    sample_size: Optional[int] = None,
    identity_linked: bool = False,
    confidence: str = "medium",
) -> Dict[str, Any]:
    """Dựng khối `meta` đúng hợp đồng. Ba trường cổng ra kiểm là
    computed_at · model_version · scope — không trường nào được để trống."""
    if mode not in SOURCE_MODES:
        raise ValueError(f"source.mode phải thuộc {SOURCE_MODES}, nhận được {mode!r}")

    # Dữ liệu mồi KHÔNG BAO GIỜ được gán cho shop có thật trên sàn.
    # `vietcraft-seed` và `vietcraft` là hai miền khác nhau — xem mục 1 hợp đồng.
    if mode == "seed_demo" and attributed_to_live_shop:
        raise ValueError(
            "mode='seed_demo' mà attributed_to_live_shop=True. Dữ liệu mồi gán cho "
            "shop thật là trình bày sai nguồn — đây là lỗi nghiệm thu, không phải cảnh báo."
        )

    return {
        "status": STATUS_OK,          # ok() / insufficient() ghi đè lại
        "computed_at": computed_at or _now_iso(),
        "model_version": model_version,
        "scope": scope,
        "scope_id": scope_id,
        "source": {
            "database": database,
            "collection": collection,
            "mode": mode,
            "attributed_to_live_shop": attributed_to_live_shop,
        },
        "quality": {
            "sample_size": sample_size,
            "identity_linked": identity_linked,
            "confidence": confidence,
        },
    }


def meta_from_record(
    record: Dict[str, Any],
    *,
    scope: str,
    scope_id: Optional[str] = None,
    collection: Optional[str] = None,
    **kw: Any,
) -> Dict[str, Any]:
    """Lấy computed_at / model_version từ chính bản ghi mart.

    Job ghi vào mart, API chỉ đọc ra — nên ba trường xuất xứ phải lấy TỪ BẢN GHI,
    không phải giờ hiện tại. Lấy giờ hiện tại là nói dối: số có thể đã tính từ hôm kia.
    """
    return build_meta(
        computed_at=record.get("computed_at"),
        model_version=record.get("model_version", "unknown"),
        scope=scope,
        scope_id=scope_id if scope_id is not None else record.get("scope_id"),
        collection=collection,
        **kw,
    )


# ---------------------------------------------------------------------------
# VỎ PHẢN HỒI
# ---------------------------------------------------------------------------

def ok(data: Any, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Có số thật, tin được."""
    meta = meta or build_meta()
    meta["status"] = STATUS_OK
    return {"data": data, "meta": meta, "error": None}


def partial(data: Any, reason: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Có số nhưng độ tin cậy thấp — FE phải hiện nhãn cảnh báo kèm `reason`."""
    meta = meta or build_meta()
    meta["status"] = STATUS_PARTIAL
    meta["reason"] = reason
    return {"data": data, "meta": meta, "error": None}


def insufficient(reason: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Chưa đủ dữ liệu để tính. `data` là null, KHÔNG phải 0 và KHÔNG phải [].

    Trả HTTP 200 chứ không phải 4xx: người gọi không làm gì sai, dữ liệu chưa đủ thôi.
    `reason` viết cho người bán đọc, nêu rõ thiếu bao nhiêu và cần bao nhiêu.
    """
    meta = meta or build_meta()
    meta["status"] = STATUS_INSUFFICIENT
    meta["reason"] = reason
    return {"data": None, "meta": meta, "error": None}


# ---------------------------------------------------------------------------
# LỖI — bảng mã ở mục 1 hợp đồng
# ---------------------------------------------------------------------------

def mart_not_ready(collection: str) -> None:
    """503 — job chưa chạy lần nào, bảng rỗng.

    KHÔNG dùng 500. Mart rỗng là trạng thái BÌNH THƯỜNG trước lần chạy job đầu
    tiên; 500 làm người trực tưởng hệ thống hỏng. Kèm tên bảng để biết chờ job nào.
    """
    raise HTTPException(status_code=503,
                        detail={"error": "mart_not_ready", "collection": collection})


def invalid_param(field: str, expected: str = "") -> None:
    """400 — tham số sai kiểu hoặc ngoài miền."""
    detail: Dict[str, Any] = {"error": "invalid_param", "field": field}
    if expected:
        detail["expected"] = expected
    raise HTTPException(status_code=400, detail=detail)


def forbidden() -> None:
    """403 — xin dữ liệu của shop khác. BR-174 / BR-177."""
    raise HTTPException(status_code=403, detail={"error": "forbidden"})


def not_found(what: str = "listing") -> None:
    """404 — id không tồn tại."""
    raise HTTPException(status_code=404, detail={"error": "not_found", "resource": what})


# ---------------------------------------------------------------------------
# XÁC THỰC — shop_id LUÔN lấy từ JWT, không nhận từ query
#
# BR-174 / BR-177: người bán chỉ xem được dữ liệu shop mình sở hữu. Nhận shop_id
# từ query thì ai cũng đổi được thành shop người khác — đây là lý do tham số đó
# không tồn tại trong bất kỳ endpoint nào của hợp đồng.
#
# ⚠ Phần GIẢI MÃ token thuộc SPEC-04 (Nhi, hạn 24/09) — chưa có thuật toán, khoá
# ký và tên trường từ sàn. Chỗ nối đã để sẵn ở decode_shop_id() bên dưới: Nhi chỉ
# điền vào một hàm, 16 endpoint không phải sửa dòng nào.
# ---------------------------------------------------------------------------

JWT_SECRET = os.getenv("JWT_SECRET", "")


# ---------------------------------------------------------------------------
# HAI CÁCH TẮT XÁC THỰC LÚC LÀM TÍNH NĂNG — cả hai mặc định TẮT.
#
#   DEV_SHOP_ID=shp_00017      TẮT HẲN xác thực. Mọi request thành shop này,
#                              không cần token, không cần header. Dùng khi đang
#                              viết tính năng và không muốn vướng đăng nhập.
#
#   DEV_TRUST_SHOP_HEADER=1    Vẫn phải gửi header X-Debug-Shop-Id, nhưng đổi
#                              được shop giữa các request. Dùng khi cần thử
#                              BR-174/BR-177: shop A có xem được dữ liệu shop B không.
#
# Đọc lúc GỌI chứ không lúc import, để đổi .env rồi `--reload` là ăn ngay, và để
# test tự đặt được trạng thái của mình.
#
# ⚠ KHÔNG BAO GIỜ bật trên môi trường có dữ liệu thật: bật lên là ai cũng tự xưng
#   shop nào cũng được. `main.py` in cảnh báo to lúc khởi động khi thấy đang bật.
# ---------------------------------------------------------------------------

def _dev_shop_id() -> str:
    return os.getenv("DEV_SHOP_ID", "").strip()


def _dev_tin_header() -> bool:
    return os.getenv("DEV_TRUST_SHOP_HEADER", "").strip() == "1"


def che_do_xac_thuc() -> str:
    """Mô tả một dòng cho banner khởi động. Trả chuỗi rỗng khi xác thực đang BẬT."""
    if _dev_shop_id():
        return f"TAT HOAN TOAN — moi request thanh shop `{_dev_shop_id()}` (DEV_SHOP_ID)"
    if _dev_tin_header():
        return "TIN HEADER X-Debug-Shop-Id, khong kiem token (DEV_TRUST_SHOP_HEADER=1)"
    return ""


def decode_shop_id(token: str) -> str:
    """CHỖ CỦA SPEC-04 — Nhi điền.

    Cần từ repo sàn: thuật toán ký (HS256 / RS256), khoá, tên trường chứa shop
    trong payload, và cách kiểm hạn. Điền xong thì xoá dòng raise này.
    """
    raise HTTPException(
        status_code=501,
        detail={"error": "jwt_not_configured",
                "hint": "SPEC-04 chưa xong — chưa có khoá ký và tên trường shop từ repo sàn. "
                        "Chạy thử tạm: đặt DEV_TRUST_SHOP_HEADER=1 và gửi header X-Debug-Shop-Id."},
    )


def current_shop_id(
    authorization: Optional[str] = Header(default=None),
    x_debug_shop_id: Optional[str] = Header(default=None),
) -> str:
    """Dependency trả về shop_id của người đang gọi."""
    dev = _dev_shop_id()

    # Header đi TRƯỚC DEV_SHOP_ID: DEV_SHOP_ID là giá trị MẶC ĐỊNH cho đỡ phải gõ,
    # không phải cái khoá cứng. Đè ngược lại thì ai đặt DEV_SHOP_ID trong .env sẽ
    # thấy mọi request đều ra cùng một shop dù đã gửi header khác — và số trả về
    # trông vẫn hợp lý nên rất khó phát hiện. Đã dính đúng bẫy này khi thử F34.
    if x_debug_shop_id and (dev or _dev_tin_header()):
        return x_debug_shop_id

    if dev:
        return dev

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})

    return decode_shop_id(authorization.split(" ", 1)[1].strip())


# Viết gọn cho router: `shop_id: str = CurrentShop`
CurrentShop = Depends(current_shop_id)


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA MODULE _TEMPLATE.PY ===")

    r = ok({"revenue_vnd": 2508000},
           build_meta(model_version="daily-1.0", scope="shop", scope_id="shp_00017",
                      collection="mart_listing_daily", sample_size=547))
    assert set(r) == {"data", "meta", "error"}, r
    assert r["meta"]["status"] == "ok" and r["error"] is None
    for f in ("computed_at", "model_version", "scope"):
        assert r["meta"][f], f"meta.{f} rỗng"
    print("✓ ok() dựng đủ vỏ {data, meta, error} và 3 trường cổng ra")

    r = insufficient("Listing mới tạo 3 ngày, cần tối thiểu 7")
    assert r["data"] is None, "insufficient() phải trả data=null, không phải 0 hay []"
    assert r["meta"]["status"] == "insufficient_data" and r["meta"]["reason"]
    print("✓ insufficient() trả data=null kèm lý do — không trả 0")

    r = partial({"revenue_vnd": 12000}, "Chỉ 9/30 ngày có đơn")
    assert r["meta"]["status"] == "partial" and r["data"] is not None
    print("✓ partial() giữ số nhưng hạ trạng thái")

    rec = {"computed_at": "2026-09-21T06:00:00Z", "model_version": "daily-1.0"}
    m = meta_from_record(rec, scope="listing_day", scope_id="lst_000001")
    assert m["computed_at"] == rec["computed_at"], "phải lấy giờ TỪ bản ghi, không phải giờ hiện tại"
    print("✓ meta_from_record() lấy xuất xứ từ bản ghi mart")

    try:
        build_meta(mode="seed_demo", attributed_to_live_shop=True)
        raise AssertionError("phải chặn: dữ liệu mồi gán cho shop thật")
    except ValueError:
        print("✓ chặn gán dữ liệu mồi cho shop có thật")

    try:
        build_meta(mode="that_bai")
        raise AssertionError("phải chặn source.mode lạ")
    except ValueError:
        print("✓ chặn source.mode ngoài live/seed_demo/derived")

    for fn, code in ((lambda: mart_not_ready("mart_demand"), 503),
                     (lambda: invalid_param("timeRange", "7d|30d|90d"), 400),
                     (lambda: forbidden(), 403),
                     (lambda: not_found("listing"), 404)):
        try:
            fn()
            raise AssertionError(f"phải ném HTTPException {code}")
        except HTTPException as e:
            assert e.status_code == code, (e.status_code, code)
    print("✓ 4 hàm lỗi ném đúng mã 400/403/404/503")

    print("✅ TẤT CẢ SELF-CHECKS CỦA _TEMPLATE.PY ĐÃ PASS!")
