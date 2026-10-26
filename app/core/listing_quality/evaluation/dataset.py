from typing import List
from .schema import LabeledListing

def get_benchmark_dataset() -> List[LabeledListing]:
    return [
        LabeledListing(
            listing_id="pod_clean_001",
            category="ao-thun",
            title="Áo Thun Unisex Cotton Compact 100% In Chữ Minimal",
            description="Chất liệu cotton compact 100% 250gsm dày dặn đứng form, thấm hút mồ hôi. Bảng size S, M, L, XL chuẩn form regular fit. Hướng dẫn giặt máy ở nhiệt độ thường, lộn trái khi giặt để giữ hình in bền màu.",
            images=["https://res.cloudinary.com/test/ao_1.jpg", "https://res.cloudinary.com/test/ao_2.jpg"],
            materials=["cotton"],
            original_price=220000,
            tags=["áo thun", "unisex", "minimal"],
            variants=[
                {"sku": "AT-S", "size": "S", "retail_price": 220000, "is_active": True},
                {"sku": "AT-M", "size": "M", "retail_price": 220000, "is_active": True}
            ],
            ground_truth_issues=[],
            provenance="clean_apparel_standard"
        ),
        LabeledListing(
            listing_id="pod_clean_002",
            category="ly-tach",
            title="Cốc Sứ Bát Tràng Tráng Men Bóng Quà Tặng 350ml",
            description="Chất liệu gốm sứ Bát Tràng tráng men cao cấp, dung tích 350ml dùng uống trà cà phê tiện dụng, chịu nhiệt tốt trong lò vi sóng.",
            images=["https://res.cloudinary.com/test/coc_1.jpg", "https://res.cloudinary.com/test/coc_2.jpg"],
            materials=["sứ"],
            original_price=120000,
            tags=["cốc sứ", "quà tặng", "bát tràng"],
            variants=[{"sku": "CS-01", "retail_price": 120000, "is_active": True}],
            ground_truth_issues=[],
            provenance="clean_drinkware_standard"
        ),
        LabeledListing(
            listing_id="pod_clean_003",
            category="tui",
            title="Túi Tote Canvas Vải Bố Dày Có Khóa Kéo",
            description="Chất liệu vải bố canvas mộc tự nhiên bền bỉ, kích thước 38x42cm đựng vừa laptop 14 inch, có khóa kéo miệng và ngăn nhỏ bên trong.",
            images=["https://res.cloudinary.com/test/tote_1.jpg", "https://res.cloudinary.com/test/tote_2.jpg"],
            materials=["canvas"],
            original_price=95000,
            tags=["túi tote", "canvas", "vintage"],
            variants=[{"sku": "TT-01", "retail_price": 95000, "is_active": True}],
            ground_truth_issues=[],
            provenance="clean_bag_standard"
        ),
        LabeledListing(
            listing_id="pod_issue_req_001",
            category="ao-thun",
            title="",
            description="",
            images=[],
            materials=[],
            original_price=0,
            tags=[],
            variants=[],
            ground_truth_issues=[
                "TITLE_EMPTY",
                "DESCRIPTION_EMPTY",
                "IMAGES_MISSING",
                "PRICE_MISSING",
                "TAGS_MISSING"
            ],
            provenance="blank_listing_defect"
        ),
        LabeledListing(
            listing_id="pod_issue_req_002",
            category="",
            title="Áo đẹp",
            description="Mua ngay",
            images=["https://res.cloudinary.com/test/1.jpg"],
            materials=[],
            original_price=150000,
            tags=[],
            variants=[{"sku": "V-1", "retail_price": 150000, "is_active": True}],
            ground_truth_issues=[
                "TITLE_TOO_SHORT",
                "DESCRIPTION_TOO_SHORT",
                "IMAGES_INSUFFICIENT",
                "CATEGORY_MISSING",
                "TAGS_MISSING",
                "MATERIAL_MISSING",
                "SIZE_INFO_MISSING",
                "CARE_INSTRUCTIONS_MISSING"
            ],
            provenance="sparse_metadata_defect"
        ),
        LabeledListing(
            listing_id="pod_issue_content_001",
            category="ao-thun",
            title="Áo Thun Nam Nữ Form Rộng Streetwear",
            description="Thiết kế trẻ trung phong cách cá tính diện đi chơi dạo phố nổi bật.",
            images=["https://res.cloudinary.com/test/1.jpg", "https://res.cloudinary.com/test/2.jpg"],
            materials=[],
            original_price=180000,
            tags=["áo thun", "streetwear"],
            variants=[{"sku": "ST-1", "retail_price": 180000, "is_active": True}],
            ground_truth_issues=[
                "MATERIAL_MISSING",
                "SIZE_INFO_MISSING",
                "CARE_INSTRUCTIONS_MISSING"
            ],
            provenance="missing_apparel_specs"
        ),
        LabeledListing(
            listing_id="pod_issue_drinkware_001",
            category="ly-tach",
            title="Ly Uống Nước Độc Đáo Mẫu Mới",
            description="Mẫu ly họa tiết sinh động dành cho dân văn phòng hoặc bạn bè.",
            images=["https://res.cloudinary.com/test/1.jpg", "https://res.cloudinary.com/test/2.jpg"],
            materials=[],
            original_price=80000,
            tags=["ly", "quà tặng"],
            variants=[{"sku": "LY-1", "retail_price": 80000, "is_active": True}],
            ground_truth_issues=[
                "DRINKWARE_SPECS_MISSING"
            ],
            provenance="missing_drinkware_specs"
        ),
        LabeledListing(
            listing_id="pod_issue_conflict_001",
            category="ao-thun",
            title="Áo Thun Cotton 100% Phong Cách Hàn Quốc",
            description="Áo thun phong cách trẻ trung năng động thoáng mát.",
            images=["https://res.cloudinary.com/test/1.jpg", "https://res.cloudinary.com/test/2.jpg"],
            materials=["polyester"],
            original_price=190000,
            tags=["áo thun"],
            variants=[{"sku": "V-1", "material": "polyester", "size": "L", "retail_price": 190000, "is_active": True}],
            ground_truth_issues=[
                "MATERIAL_CONTRADICTION",
                "CARE_INSTRUCTIONS_MISSING"
            ],
            provenance="contradictory_material"
        ),
        LabeledListing(
            listing_id="pod_issue_conflict_002",
            category="ao-thun",
            title="Cốc Sứ Quà Tặng Người Thân 350ml",
            description="Chất liệu gốm sứ dày dặn in hình sắc nét độ bền cao.",
            images=["https://res.cloudinary.com/test/1.jpg", "https://res.cloudinary.com/test/2.jpg"],
            materials=["sứ"],
            original_price=90000,
            tags=["cốc sứ"],
            variants=[{"sku": "CS-1", "retail_price": 90000, "is_active": True}],
            ground_truth_issues=[
                "CATEGORY_CONTRADICTION",
                "SIZE_INFO_MISSING",
                "CARE_INSTRUCTIONS_MISSING"
            ],
            provenance="contradictory_category"
        ),
        LabeledListing(
            listing_id="pod_issue_img_001",
            category="ao-thun",
            title="Áo Thun Cotton In Hình Nghệ Thuật",
            description="Chất liệu cotton mềm mại, kích cỡ S/M/L chi tiết. Giặt máy chế độ nhẹ.",
            images=["mock_low_res", "https://res.cloudinary.com/test/2.jpg"],
            materials=["cotton"],
            original_price=160000,
            tags=["áo thun"],
            variants=[{"sku": "AT-1", "size": "M", "retail_price": 160000, "is_active": True}],
            ground_truth_issues=[
                "LOW_IMAGE_RESOLUTION"
            ],
            provenance="low_res_image_defect"
        ),
        LabeledListing(
            listing_id="pod_issue_img_002",
            category="ao-thun",
            title="Áo Thun Cotton Dệt Kim Form Rộng",
            description="Chất liệu cotton mềm mại, kích cỡ S/M/L chi tiết. Giặt máy chế độ nhẹ.",
            images=["mock_aspect", "https://res.cloudinary.com/test/2.jpg"],
            materials=["cotton"],
            original_price=160000,
            tags=["áo thun"],
            variants=[{"sku": "AT-2", "size": "M", "retail_price": 160000, "is_active": True}],
            ground_truth_issues=[
                "EXTREME_ASPECT_RATIO"
            ],
            provenance="distorted_aspect_defect"
        )
    ]
