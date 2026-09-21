"""
F41 · GET /api/analytics/forecast/recommendations — 5 câu khuyên nên làm sản phẩm gì.

Đỉnh kim tự tháp: gộp `niche_score` (cầu) + `mart_competitor` (vị thế) +
`listing_health` (chất lượng) thành việc cụ thể.

  BR-214  PHẢI cá nhân hoá theo lịch sử — không gợi ý loại phôi mà shop có 0% chuyển đổi
  BR-215  tối đa 5 khuyến nghị
  Shop mới chưa có lịch sử -> khuyến nghị chung toàn sàn, scope: "platform"

⚠ TIÊU CHÍ THÀNH CÔNG chưa được nghiệm thu. Bản đăng ký ban đầu định nhờ hai
  chuyên gia POD chấm điểm; nhóm đã quyết định không tuyển chuyên gia. Thay bằng
  backtest khuyến nghị (sinh tại T chỉ bằng dữ liệu <= T, đo 30 ngày sau) —
  CHƯA CHẠY. Mọi phản hồi của endpoint này gắn `validated: false`.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import APIRouter

from app.api.v1._mart import db, tien
from app.api.v1._template import CurrentShop, mart_not_ready, meta_from_record, ok

router = APIRouter()

TOI_DA = 5           # BR-215


@router.get("/api/analytics/forecast/recommendations", tags=["F41 · Đạt"])
def recommendations(shop_id: str = CurrentShop):
    ngach = list(db()["niche_score"].find({}, {"_id": 0}).sort("gap_score", -1).limit(30))
    if not ngach:
        mart_not_ready("niche_score")

    cua_toi = list(db()["mart_competitor"].find(
        {"shop_id": shop_id},
        {"_id": 0, "listing_id": 1, "product_type_id": 1, "category_id": 1, "tags": 1,
         "est_sales_90d": 1, "views_90d": 1, "orders_90d": 1, "revenue_90d_vnd": 1,
         "rank_in_cat": 1, "n_in_cat": 1}))

    meta = meta_from_record(ngach[0], scope="shop" if cua_toi else "platform",
                            scope_id=shop_id if cua_toi else "all",
                            collection="niche_score", mode="derived",
                            sample_size=len(cua_toi), confidence="low")

    # Shop mới -> khuyến nghị chung toàn sàn. Nói rõ là chung, không giả vờ cá nhân hoá.
    if not cua_toi:
        return ok({
            "shop_id": shop_id,
            "scope": "platform",
            "personalised": False,
            "recommendations": [{
                "priority": i,
                "action": "explore",
                "target": {"type": "keyword", "id": n["keyword"], "tag_id": n.get("tag_id")},
                "why": [f"cầu ở phân vị {n['demand_pct']}% nhưng cung chỉ {n['supply_pct']}%",
                        f"hiện có {n['n_listings']} listing mang tag này"],
                "expected": "chưa đo được — shop chưa có lịch sử để so",
                "confidence": "low",
            } for i, n in enumerate(ngach[:TOI_DA], 1)],
            "validated": False,
            "validation_note": ("Chưa chạy backtest khuyến nghị. Mốc so sánh bắt buộc là "
                                "'cứ làm tiếp thứ đang bán chạy nhất' — nếu không thắng "
                                "được câu ngây thơ đó thì phải báo cáo thẳng."),
        }, meta)

    # BR-214: loại loại phôi mà shop đã thử và KHÔNG bán được cái nào dù có lượt xem.
    # Gợi ý làm thêm thứ đã chứng minh là không chuyển đổi là lời khuyên có hại.
    da_that_bai = {r["product_type_id"] for r in cua_toi
                   if (r.get("views_90d") or 0) >= 50 and not (r.get("orders_90d") or 0)}
    tag_toi = {t for r in cua_toi for t in r.get("tags") or []}
    loai_toi = {r["product_type_id"] for r in cua_toi}

    manh = sorted((r for r in cua_toi if r.get("rank_in_cat")),
                  key=lambda r: r["rank_in_cat"])[:3]

    khuyen = []

    # 1. Mở rộng sang ngách cầu cao mà shop CHƯA có tag
    for n in ngach:
        if len(khuyen) >= TOI_DA - len(manh[:2]):
            break
        if n.get("tag_id") in tag_toi or not n.get("tag_id"):
            continue
        khuyen.append({
            "priority": len(khuyen) + 1,
            "action": "expand",
            "target": {"type": "tag", "id": n["tag_id"], "keyword": n["keyword"]},
            "why": [f"cầu phân vị {n['demand_pct']}% vs cung {n['supply_pct']}% (gap {n['gap_score']})",
                    f"shop chưa có listing nào mang tag này",
                    f"xu hướng {n['trend']}"],
            "expected": "chưa đo được — cần backtest",
            "confidence": "low",
        })

    # 2. Đẩy mạnh thứ đang xếp hạng tốt sẵn
    for r in manh[:2]:
        if r["product_type_id"] in da_that_bai:
            continue
        khuyen.append({
            "priority": len(khuyen) + 1,
            "action": "scale",
            "target": {"type": "product_type", "id": r["product_type_id"]},
            "why": [f"đang hạng {r['rank_in_cat']}/{r['n_in_cat']} trong {r['category_id']}",
                    f"bán {r['est_sales_90d']} cái / 90 ngày",
                    f"doanh thu {tien(r.get('revenue_90d_vnd')):,}đ"],
            "expected": "chưa đo được — cần backtest",
            "confidence": "low",
        })

    return ok({
        "shop_id": shop_id,
        "scope": "shop",
        "personalised": True,
        "recommendations": khuyen[:TOI_DA],
        "excluded_product_types": sorted(da_that_bai),
        "exclusion_reason": "có từ 50 lượt xem trong 90 ngày mà không bán được cái nào (BR-214)",
        "my_listings_analysed": len(cua_toi),
        "validated": False,
        "validation_note": ("Chưa chạy backtest khuyến nghị. Mốc so sánh bắt buộc là "
                            "'cứ làm tiếp thứ đang bán chạy nhất'. Mọi `expected` để "
                            "'chưa đo được' thay vì hứa một con số chưa kiểm chứng."),
    }, meta)
