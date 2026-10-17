from datetime import timedelta

from bson import ObjectId

from app.core.f29.todos import build_sales_warnings
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import NOW, PRODUCT_ID


def detail(views, carts=0, orders=0, cr=None, base=None):
    return {"views_30d": views, "carts_30d": carts, "orders_30d": orders, "min_views": 100,
            "conversion_rate": cr, "baseline_rate": base}


def product(days):
    return {"created_at": NOW - timedelta(days=days)}


def test_it_luot_xem_chi_bao_khi_san_pham_da_dang_du_lau():
    canh_bao = build_sales_warnings(product(20), detail(30), None, NOW)
    assert [w["field"] for w in canh_bao] == ["title"] and canh_bao[0]["current_value"] == 30
    assert build_sales_warnings(product(5), detail(30), None, NOW) == []
    assert build_sales_warnings(product(20), detail(150), None, NOW) == []


def test_mua_it_do_khach_khong_them_gio():
    canh_bao = build_sales_warnings(product(30), detail(200, 4, 2, 0.01, 0.03), 30.0, NOW)
    assert canh_bao[0]["field"] == "variants.retail_price" and "2.0% thêm vào giỏ" in canh_bao[0]["message"]
    assert canh_bao[0]["current_value"] == 1.0 and canh_bao[0]["target"] == 3.0


def test_mua_it_do_khach_bo_gio():
    canh_bao = build_sales_warnings(product(30), detail(200, 40, 2, 0.01, 0.03), 30.0, NOW)
    assert canh_bao[0]["field"] == "shipping" and "5.0% đặt mua" in canh_bao[0]["message"]


def test_ti_le_mua_on_thi_khong_bao():
    assert build_sales_warnings(product(30), detail(200, 20, 6, 0.03, 0.03), 50.0, NOW) == []


def test_dem_luot_them_gio_vao_chi_tiet_chuyen_doi():
    oid = ObjectId(PRODUCT_ID)
    events = ([{"product_id": oid, "event_type": "view", "created_at": NOW}] * 3
              + [{"product_id": oid, "event_type": "add_to_cart", "created_at": NOW}] * 2)
    calc = make_calculator(products=[{"_id": oid}], product_events=events)
    chi_tiet = calc._get_conversion(PRODUCT_ID)[1]
    assert chi_tiet["views_30d"] == 3 and chi_tiet["carts_30d"] == 2
