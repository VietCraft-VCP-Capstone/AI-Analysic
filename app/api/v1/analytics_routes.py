"""
analytics_routes.py — Khung 16 endpoint F26–F41.

Mục đích của file này: **FE gọi thật được NGAY**, không phải chờ ai làm xong tính
năng. Mọi đường dẫn đã sống, trả đúng vỏ `{data, meta, error}` của hợp đồng, và
nói thật là chưa có số — bằng `503 mart_not_ready` kèm tên bảng đang chờ.

Nguồn duy nhất của bảng này: `docs/API_CONTRACT.md` mục 3.
`tests/test_api_contract.py` so hai bên với nhau, lệch là test đỏ.

════════════════════════════════════════════════════════════════════════════
CÁCH LÀM TÍNH NĂNG CỦA MÌNH — 3 bước, không sửa file này quá một dòng
════════════════════════════════════════════════════════════════════════════

  1. Viết router riêng, ví dụ `app/api/v1/f26_shop_overview.py`:

        from fastapi import APIRouter
        from app.api.v1._template import ok, insufficient, meta_from_record, CurrentShop

        router = APIRouter()

        @router.get("/api/analytics/shop/overview")
        def shop_overview(shop_id: str = CurrentShop, timeRange: str = "30d"):
            ...

  2. Thêm MỘT dòng vào DA_LAM bên dưới:  "F26": "app.api.v1.f26_shop_overview"

  3. Chạy `.venv/bin/python -m pytest tests/ -q` (hoặc `python tests/test_api_contract.py`)

  Khung tự nhường chỗ: F nào có trong DA_LAM thì router thật thay chỗ khung.
  Không ai phải sửa của ai, và không ai quên đăng ký — test đếm đủ 16.
"""

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List

# Cho phép chạy trực tiếp `python app/api/v1/analytics_routes.py` (khối self-check
# cuối file). Cùng cách writer.py và main.py đang làm.
ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._template import CurrentShop, mart_not_ready

router = APIRouter()


# ---------------------------------------------------------------------------
# BẢNG 16 ENDPOINT — chép từ docs/API_CONTRACT.md mục 3, không thêm bớt.
#
# `mart`: bảng mà endpoint ĐỌC. Chưa có job nào ghi vào thì endpoint trả 503
#         kèm đúng tên này, để người trực biết đang chờ job của ai.
# `owner`: hỏi ai khi số ra lạ.
# ---------------------------------------------------------------------------
ENDPOINTS: List[Dict[str, Any]] = [
    # F,      method,   path,                                            mart,                   owner,  tham số
    {"f": "F26", "method": "GET",    "path": "/api/analytics/shop/overview",             "mart": "listing_daily",       "owner": "Hiếu", "params": ["timeRange"]},
    {"f": "F27", "method": "GET",    "path": "/api/analytics/listings/{id}/timeseries",  "mart": "listing_daily",       "owner": "Hiếu", "params": ["timeRange"]},
    {"f": "F28", "method": "GET",    "path": "/api/analytics/listings/{id}/conversion",  "mart": "mart_listing_quality","owner": "Hạt",  "params": []},
    {"f": "F29", "method": "GET",    "path": "/api/analytics/listings/{id}/health",      "mart": "listing_health",      "owner": "Hạt",  "params": []},
    {"f": "F30", "method": "GET",    "path": "/api/notifications/alerts",                "mart": "anomaly_event",       "owner": "Hiếu", "params": ["period"]},
    {"f": "F31", "method": "GET",    "path": "/api/analytics/shop/categories/revenue",   "mart": "listing_daily",       "owner": "Hiếu", "params": ["timeRange"]},
    {"f": "F32", "method": "GET",    "path": "/api/analytics/competitors",               "mart": "mart_competitor",     "owner": "Nhi",  "params": ["categoryId"]},
    {"f": "F33", "method": "GET",    "path": "/api/analytics/shop-comparison",           "mart": "mart_competitor",     "owner": "Nhi",  "params": []},
    {"f": "F34", "method": "GET",    "path": "/api/analytics/tag-gap",                   "mart": "mart_competitor",     "owner": "Đạt",  "params": ["categoryId"]},
    {"f": "F35", "method": "GET",    "path": "/api/analytics/pricing",                   "mart": "mart_competitor",     "owner": "Nhi",  "params": ["productType", "price"]},
    {"f": "F36", "method": "GET",    "path": "/api/analytics/competitor-tracking",       "mart": "mart_competitor",     "owner": "Đạt",  "params": []},
    {"f": "F36", "method": "POST",   "path": "/api/analytics/competitor-tracking",       "mart": "mart_competitor",     "owner": "Đạt",  "params": ["shopId"]},
    {"f": "F36", "method": "DELETE", "path": "/api/analytics/competitor-tracking",       "mart": "mart_competitor",     "owner": "Đạt",  "params": ["shopId"]},
    {"f": "F37", "method": "GET",    "path": "/api/analytics/forecast/revenue",          "mart": "forecast_point",      "owner": "Đạt",  "params": ["targetId", "window"]},
    {"f": "F38", "method": "GET",    "path": "/api/analytics/forecast/seasonal",         "mart": "seasonal_profile",    "owner": "Hưng", "params": ["categoryId"]},
    {"f": "F39", "method": "GET",    "path": "/api/analytics/forecast/niches",           "mart": "niche_score",         "owner": "Hưng", "params": ["categoryId"]},
    {"f": "F40", "method": "GET",    "path": "/api/analytics/forecast/radar",            "mart": "mart_demand",         "owner": "Hưng", "params": []},
    {"f": "F41", "method": "GET",    "path": "/api/analytics/forecast/recommendations",  "mart": "niche_score",         "owner": "Đạt",  "params": []},
]

# F nào đã có router thật — thêm dòng ở đây là khung tự nhường chỗ.
DA_LAM: Dict[str, str] = {
    "F26": "app.api.v1.f26_shop_overview",
    "F28": "app.api.v1.f28_conversion",
    "F29": "app.api.v1.f29_health",
    "F30": "app.api.v1.f30_alerts",
    "F31": "app.api.v1.f31_category_revenue",
    "F32": "app.api.v1.f32_competitors",
    "F34": "app.api.v1.f34_tag_gap",
    "F27": "app.api.v1.f27_listing_timeseries",
    "F33": "app.api.v1.f33_shop_comparison",
    "F35": "app.api.v1.f35_pricing",
    "F36": "app.api.v1.f36_competitor_tracking",
    "F37": "app.api.v1.f37_forecast_revenue",
    "F38": "app.api.v1.f38_seasonal",
    "F39": "app.api.v1.f39_niches",
    "F40": "app.api.v1.f40_radar",
    "F41": "app.api.v1.f41_recommendations",
}


# ---------------------------------------------------------------------------
# HAI CHỖ HỢP ĐỒNG TỰ MÂU THUẪN — đã chốt ở đây, ghi lại để không ai chốt ngược
#
# 1. `mart_listing_daily` (F26 · F27 · F31).
#    docs/API_CONTRACT.md mục 3 ghi tên này, nhưng app/core/writer.py BLOCKED
#    CHẶN nó: bảng đó là bản sao 1:1 của `listing_daily` 796.025 dòng, đã thử
#    ngày 21/09 và làm cụm Atlas M0 (512 MB, DÙNG CHUNG CẢ NHÓM) vọt lên 526/512
#    rồi chặn ghi với tất cả mọi người.
#    → Khung này đọc thẳng `listing_daily`, đúng như writer.py hướng dẫn.
#      4 cột khoá đã backfill sẵn, index đã có. Hợp đồng phải sửa theo, không
#      phải ngược lại — một bảng bị chặn vì lý do đo được thì không mở lại bằng
#      một dòng trong tài liệu.
#
# 2. Đường dẫn F30 là `/api/notifications/alerts`, KHÔNG phải `/api/analytics/alerts`
#    (mục 6 câu 3). Theo SRS. Nhất quán thua tương thích: FE của sàn đã trỏ theo SRS.
# ---------------------------------------------------------------------------


def _chua_co_so(ep: Dict[str, Any]) -> None:
    """Chưa job nào ghi vào mart -> 503 kèm tên bảng đang chờ.

    Vì sao không phải 200 + insufficient_data: `insufficient_data` nghĩa là ĐÃ
    tính và dữ liệu không đủ — một câu trả lời về shop này. Ở đây chưa ai tính
    lần nào, cho shop nào cả. Hai chuyện khác nhau, FE hiện hai màn hình khác nhau.
    """
    mart_not_ready(ep["mart"])


def _dang_ky(ep: Dict[str, Any]) -> None:
    """Đăng ký một đường dẫn khung."""
    mo_ta = f"[{ep['f']}] khung — chờ {ep['owner']}. Đọc mart `{ep['mart']}`."

    # Bắt `ep` bằng closure, KHÔNG bằng tham số mặc định `ep=ep`: FastAPI đọc mọi
    # tham số của handler là tham số của API, nên `ep=ep` lòi ra Swagger thành một
    # ô nhập `ep` mà người gọi tưởng là thật.
    def tao_handler(ep_: Dict[str, Any], co_id: bool):
        if co_id:
            def handler(id: str, shop_id: str = CurrentShop):
                _chua_co_so(ep_)
        else:
            def handler(shop_id: str = CurrentShop):
                _chua_co_so(ep_)
        return handler

    handler = tao_handler(ep, co_id="{id}" in ep["path"])

    handler.__name__ = f"{ep['f'].lower()}_{ep['method'].lower()}_khung"
    router.add_api_route(
        ep["path"], handler,
        methods=[ep["method"]],
        summary=mo_ta,
        tags=[f"{ep['f']} · {ep['owner']}"],
    )


def gan_vao(app) -> Dict[str, str]:
    """Gắn 16 endpoint vào app. Router thật (DA_LAM) được ưu tiên, còn lại là khung.

    Trả về bảng {F: "that" | "khung"} để `main.py` in ra lúc khởi động — nhìn log
    là biết hôm nay đã có mấy tính năng chạy thật.
    """
    trang_thai: Dict[str, str] = {}

    for f, module_path in DA_LAM.items():
        mod = importlib.import_module(module_path)
        app.include_router(mod.router, tags=[f])
        trang_thai[f] = "that"

    for ep in ENDPOINTS:
        if ep["f"] in DA_LAM:
            continue
        _dang_ky(ep)
        trang_thai.setdefault(ep["f"], "khung")

    app.include_router(router)
    return trang_thai


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA MODULE ANALYTICS_ROUTES.PY ===")

    ma_f = {e["f"] for e in ENDPOINTS}
    mong_doi = {f"F{n}" for n in range(26, 42)}
    assert ma_f == mong_doi, f"thiếu/thừa: {mong_doi ^ ma_f}"
    print(f"✓ đủ 16 mã tính năng F26–F41 ({len(ENDPOINTS)} đường dẫn, F36 có 3 method)")

    assert "mart_listing_daily" not in {e["mart"] for e in ENDPOINTS}, \
        "mart_listing_daily BỊ CHẶN trong writer.py — xem ghi chú mâu thuẫn ở trên"
    print("✓ không endpoint nào trỏ vào bảng đã bị chặn")

    trung = [e for e in ENDPOINTS
             if sum(1 for x in ENDPOINTS if x["path"] == e["path"] and x["method"] == e["method"]) > 1]
    assert not trung, f"trùng method+path: {trung}"
    print("✓ không trùng method+path")

    from fastapi import FastAPI
    app = FastAPI()
    tt = gan_vao(app)
    # Đọc qua sơ đồ OpenAPI, không qua app.routes: starlette 1.6 bọc router lại nên
    # app.routes không trải phẳng nữa. OpenAPI cũng chính là thứ FE nhìn thấy.
    paths = app.openapi()["paths"]
    for e in ENDPOINTS:
        assert e["path"] in paths, f"chưa gắn {e['path']}"
        assert e["method"].lower() in paths[e["path"]], f"chưa gắn {e['method']} {e['path']}"
    print(f"✓ gắn đủ {len(ENDPOINTS)} đường dẫn vào app (kiểm qua sơ đồ OpenAPI)")
    print(f"✓ trạng thái: {sum(1 for v in tt.values() if v == 'that')} thật · "
          f"{sum(1 for v in tt.values() if v == 'khung')} khung")

    print("✅ TẤT CẢ SELF-CHECKS CỦA ANALYTICS_ROUTES.PY ĐÃ PASS!")
