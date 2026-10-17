import hmac
import os
import re
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

from app.config import settings as _nap_env  # noqa: F401

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_INSUFFICIENT = "insufficient_data"

SOURCE_MODES = ("live", "seed_demo", "derived")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    unlock: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Dựng khối `meta` đúng hợp đồng. Ba trường cổng ra kiểm là
    computed_at · model_version · scope — không trường nào được để trống.
    `unlock`: tiến độ {"requirement", "current", "target", "unit"}, None nếu không áp dụng.
    """
    if mode not in SOURCE_MODES:
        raise ValueError(f"source.mode phải thuộc {SOURCE_MODES}, nhận được {mode!r}")

    # Dữ liệu mồi KHÔNG BAO GIỜ được gán cho shop có thật trên sàn.
    # `vietcraft-seed` và `vietcraft` là hai miền khác nhau — xem mục 1 hợp đồng.
    if mode == "seed_demo" and attributed_to_live_shop:
        raise ValueError(
            "mode='seed_demo' mà attributed_to_live_shop=True. Dữ liệu mồi gán cho "
            "shop thật là trình bày sai nguồn — đây là lỗi nghiệm thu, không phải cảnh báo."
        )

    meta: Dict[str, Any] = {
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
    if unlock is not None:
        meta["unlock"] = unlock
    return meta


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


JWT_SECRET = os.getenv("JWT_SECRET", "")


def _dev_shop_id() -> str:
    return os.getenv("DEV_SHOP_ID", "").strip()


def _dev_tin_header() -> bool:
    return os.getenv("DEV_TRUST_SHOP_HEADER", "").strip() == "1"


_SHOP_ID_HOP_LE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _gateway_secret() -> str:
    return os.getenv("AI_GATEWAY_SECRET", "").strip()


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
    x_gateway_secret: Optional[str] = Header(default=None),
    x_shop_id: Optional[str] = Header(default=None),
) -> str:
    """Dependency trả về shop_id của người đang gọi."""
    if x_gateway_secret is not None:
        bi_mat = _gateway_secret()
        # compare_digest: so theo thời gian hằng số, không lộ độ dài khớp qua độ trễ.
        if not bi_mat or not hmac.compare_digest(x_gateway_secret.encode(), bi_mat.encode()):
            raise HTTPException(status_code=401, detail={"error": "unauthorized"})
        shop = x_shop_id or ""
        if not _SHOP_ID_HOP_LE.match(shop):
            invalid_param("X-Shop-Id", "mã shop do gateway gửi, [A-Za-z0-9_-]{1,64}")
        return shop

    dev = _dev_shop_id()

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

    m = build_meta(unlock={"requirement": "đơn thật", "current": 3, "target": 20, "unit": "đơn"})
    assert m["unlock"] == {"requirement": "đơn thật", "current": 3, "target": 20, "unit": "đơn"}
    assert "unlock" not in build_meta(), "không truyền unlock thì không được tự bịa ra field này"
    print("✓ build_meta(unlock=...) gắn đúng field, mặc định không có")

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
