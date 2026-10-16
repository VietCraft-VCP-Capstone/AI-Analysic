"""
test_api_contract.py — Giữ 16 endpoint không trôi khỏi docs/API_CONTRACT.md.

Test này KHÔNG kiểm tính năng đúng hay sai. Nó kiểm HÌNH DẠNG: đường dẫn có đúng
hợp đồng không, mọi phản hồi có đủ khối `meta` không, lỗi có đúng mã và đúng body
không. Tính năng của ai người nấy test riêng.

Vì sao cần: hợp đồng là file .md, không ai ép được. 5 người sửa 16 endpoint trong
6 tuần thì chắc chắn có chỗ trôi — đổi tên trường, quên `meta`, trả 0 thay vì
`insufficient_data`. Test đỏ ngay hôm đó rẻ hơn phát hiện lúc ghép với FE.

Chạy:
    .venv/bin/python tests/test_api_contract.py          # không cần pytest
    .venv/bin/python -m pytest tests/ -q                 # sau khi INFRA-02 xong
"""

import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Test tự đặt trạng thái xác thực, KHÔNG để .env của từng máy quyết định — nếu không
# thì ai bật DEV_SHOP_ID trong .env sẽ thấy test_khong_token_thi_401 đỏ mà không hiểu vì sao.
os.environ["DEV_TRUST_SHOP_HEADER"] = "1"   # cần shop_id vì SPEC-04 chưa xong
os.environ["DEV_SHOP_ID"] = ""              # nhưng KHÔNG tắt hẳn xác thực

# Đặt "" chứ không phải pop(): app/.env được nạp lúc import app.config (qua
# _template), tức là SAU đoạn này. `load_dotenv(override=False)` không ghi đè biến
# đã tồn tại — kể cả khi giá trị là chuỗi rỗng — nên đặt "" mới chặn được
# DEV_SHOP_ID trong .env của từng máy. pop() thì .env điền lại và test đỏ oan.

from fastapi.testclient import TestClient

from app.api.v1._template import STATUS_INSUFFICIENT, STATUS_OK, STATUS_PARTIAL, build_meta, insufficient, ok
from app.api.v1.analytics_routes import DA_LAM, ENDPOINTS
from app.main import app

client = TestClient(app, raise_server_exceptions=False)
SHOP = {"X-Debug-Shop-Id": "shp_00017"}

HOP_DONG = ROOT_DIR / "docs" / "API_CONTRACT.md"
BA_TRUONG_CONG_RA = ("computed_at", "model_version", "scope")


def _goi(ep, **kw):
    """Gọi một endpoint trong bảng, thay {id} bằng id mẫu."""
    duong_dan = ep["path"].replace("{id}", "lst_000001")
    return client.request(ep["method"], duong_dan, headers=SHOP, **kw)


# ---------------------------------------------------------------------------

def test_du_16_ma_tinh_nang():
    assert {e["f"] for e in ENDPOINTS} == {f"F{n}" for n in range(26, 42)}


def test_bang_endpoint_khop_voi_tai_lieu():
    """Mọi đường dẫn trong code phải có mặt trong API_CONTRACT.md, và ngược lại.

    Đây là chỗ hay trôi nhất: sửa code quên sửa tài liệu, hoặc ngược lại.
    """
    van_ban = HOP_DONG.read_text(encoding="utf-8")
    thieu = [e["path"] for e in ENDPOINTS if e["path"] not in van_ban]
    assert not thieu, f"code có nhưng API_CONTRACT.md không nhắc: {thieu}"

    trong_tai_lieu = set(re.findall(r"`(?:GET|POST|DELETE)[^`]*?(/api/[\w/{}\-]+)`", van_ban))
    trong_code = {e["path"] for e in ENDPOINTS}
    thua = trong_tai_lieu - trong_code
    assert not thua, f"API_CONTRACT.md có nhưng code chưa dựng: {sorted(thua)}"


def test_moi_endpoint_deu_song():
    """Không endpoint nào được trả 404 hay 500. FE phải gọi được cả 16 ngay hôm nay."""
    for ep in ENDPOINTS:
        r = _goi(ep)
        assert r.status_code != 404, f"{ep['f']} {ep['path']} chưa được gắn"
        assert r.status_code < 500 or r.status_code == 503, \
            f"{ep['f']} {ep['path']} trả {r.status_code} — chỉ 503 mart_not_ready mới được phép ở dải 5xx"


def test_chua_co_mart_thi_503_kem_ten_bang():
    """Mart rỗng là chuyện BÌNH THƯỜNG trước lần chạy job đầu -> 503, không phải 500."""
    for ep in ENDPOINTS:
        if ep["f"] in DA_LAM:
            continue
        r = _goi(ep)
        assert r.status_code == 503, f"{ep['f']} trả {r.status_code}, mong 503"
        body = r.json()
        assert body == {"error": "mart_not_ready", "collection": ep["mart"]}, \
            f"{ep['f']} body sai hợp đồng: {body}"


def test_khong_token_thi_401():
    """shop_id LUÔN lấy từ JWT. BR-174 / BR-177."""
    for ep in ENDPOINTS:
        r = client.request(ep["method"], ep["path"].replace("{id}", "lst_000001"))
        assert r.status_code == 401, f"{ep['f']} cho qua khi không có token ({r.status_code})"
        assert r.json() == {"error": "unauthorized"}


def test_khong_endpoint_nao_nhan_shop_id_tu_query():
    """Nhận shopId từ query là ai cũng xem được dữ liệu shop khác."""
    for ep in ENDPOINTS:
        assert "shopId" not in ep["params"] or ep["f"] == "F36", \
            f"{ep['f']} nhận shopId từ query — phải lấy từ JWT"


def test_mac_dinh_xac_thuc_van_bat():
    """Tắt hết cờ dev thì mọi endpoint phải 401. Bảo vệ khỏi việc lỡ tay bật khi deploy."""
    from app.api.v1._template import che_do_xac_thuc
    cu = os.environ.pop("DEV_TRUST_SHOP_HEADER", None)
    try:
        assert not che_do_xac_thuc(), "tắt hết cờ mà xác thực vẫn đang mở"
        r = client.get("/api/analytics/shop/overview", headers=SHOP)
        assert r.status_code == 401, f"header dev vẫn qua được dù đã tắt cờ ({r.status_code})"
    finally:
        if cu is not None:
            os.environ["DEV_TRUST_SHOP_HEADER"] = cu


def test_gateway_be_san():
    """Đường chạy thật: BE sàn xác thực người bán rồi gọi kèm X-Gateway-Secret + X-Shop-Id.

    Secret sai hoặc service chưa đặt secret -> 401, KHÔNG rơi xuống nhánh dev.
    Không cần MongoDB: mọi nhánh dưới đây dừng ở tầng xác thực.
    """
    from fastapi import HTTPException

    from app.api.v1._template import current_shop_id

    def goi(secret, shop="shp_00017"):
        return current_shop_id(authorization=None, x_debug_shop_id=None,
                               x_gateway_secret=secret, x_shop_id=shop)

    def ma_loi(fn):
        try:
            fn()
        except HTTPException as e:
            return e.status_code
        return None

    cu = os.environ.get("AI_GATEWAY_SECRET")
    try:
        os.environ["AI_GATEWAY_SECRET"] = ""
        assert ma_loi(lambda: goi("bat-ky")) == 401, "chưa đặt secret mà gateway vẫn qua"

        os.environ["AI_GATEWAY_SECRET"] = "bi-mat-dung"
        assert goi("bi-mat-dung") == "shp_00017", "secret đúng phải trả X-Shop-Id"
        assert ma_loi(lambda: goi("bi-mat-sai")) == 401, "secret sai phải 401"
        assert ma_loi(lambda: goi("bi-mat-dung", shop="../shp")) == 400, "X-Shop-Id lạ phải 400"

        r = client.get("/api/analytics/shop/overview",
                       headers={**SHOP, "X-Gateway-Secret": "bi-mat-sai", "X-Shop-Id": "shp_00017"})
        assert r.status_code == 401, "secret sai không được rơi xuống nhánh X-Debug-Shop-Id"
        assert r.json() == {"error": "unauthorized"}
    finally:
        if cu is None:
            os.environ.pop("AI_GATEWAY_SECRET", None)
        else:
            os.environ["AI_GATEWAY_SECRET"] = cu


def test_body_loi_khong_boc_trong_detail():
    """Hợp đồng ghi body phẳng {'error': ...}, không phải {'detail': {...}}."""
    r = client.get("/api/analytics/shop/overview", headers=SHOP)
    assert "detail" not in r.json(), f"còn lớp bọc detail: {r.json()}"


def test_khong_lot_loi_goc_python():
    """Không địa chỉ nào được để lọt traceback hay thông báo lỗi gốc ra ngoài."""
    for ep in ENDPOINTS:
        r = _goi(ep)
        van_ban = r.text.lower()
        for dau_hieu in ("traceback", "mongodb+srv://", 'file "/', "pymongo"):
            assert dau_hieu not in van_ban, f"{ep['f']} lọt nội dung nội bộ: {dau_hieu}"


def test_vo_phan_hoi_du_ba_truong_cong_ra():
    """Mọi phản hồi 200 phải có meta đủ computed_at · model_version · scope."""
    mau = [
        ok({"revenue_vnd": 1}, build_meta(model_version="daily-1.0", scope="shop", scope_id="shp_1")),
        insufficient("Shop mới, 3/7 ngày"),
    ]
    for r in mau:
        assert set(r) == {"data", "meta", "error"}, r
        assert r["error"] is None
        for truong in BA_TRUONG_CONG_RA:
            assert r["meta"].get(truong), f"meta.{truong} rỗng trong {r}"
        assert r["meta"]["status"] in (STATUS_OK, STATUS_PARTIAL, STATUS_INSUFFICIENT)


def test_thieu_khac_khong():
    """Quy ước quan trọng nhất: chưa đủ dữ liệu thì data=null, KHÔNG phải 0."""
    r = insufficient("Listing mới tạo 3 ngày, cần tối thiểu 7")
    assert r["data"] is None
    assert r["data"] != 0 and r["data"] != [] and r["data"] != {}
    assert r["meta"]["reason"], "phải nói rõ thiếu bao nhiêu, cần bao nhiêu"


def test_openapi_dung_va_go_het_endpoint_gia():
    """Swagger /docs là thứ hội đồng bấm thử. Không được còn endpoint mô hình chưa train."""
    paths = app.openapi()["paths"]
    for ep in ENDPOINTS:
        assert ep["path"] in paths and ep["method"].lower() in paths[ep["path"]], \
            f"{ep['method']} {ep['path']} không lên sơ đồ OpenAPI"
    assert not [p for p in paths if "forecasting" in p], \
        "endpoint LSTM chưa train vẫn còn trên Swagger — xem API-99"


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== KIỂM 16 ENDPOINT CÓ KHỚP API_CONTRACT.MD KHÔNG ===")
    cac_test = [(t, v) for t, v in sorted(globals().items())
                if t.startswith("test_") and callable(v)]
    hong = 0
    for ten, ham in cac_test:
        try:
            ham()
            print(f"  ✓ {ten}")
        except AssertionError as e:
            hong += 1
            print(f"  ✗ {ten}\n      {e}")
    print()
    if hong:
        print(f"❌ {hong}/{len(cac_test)} TEST HỎNG")
        sys.exit(1)
    print(f"✅ {len(cac_test)}/{len(cac_test)} TEST PASS — khung API khớp hợp đồng")
