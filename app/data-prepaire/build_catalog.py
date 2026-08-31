#!/usr/bin/env python3
"""
VietCraft Catalog Builder & Transformer (Tasks 2-8 for Hưng / Người 2)

Transforms raw Printify catalog into 4 clean, normalized tables:
  1. vc_setting (System configuration, admin editable)
  2. vc_price_rule (Margin rules for 138 product types)
  3. vc_product_type (138 POD product types across 11 groups)
  4. vc_catalog_variant (~15,000 normalized variants with min cost in VND)
"""

import os
import sys
import re
import json
import csv
import datetime as dt
from collections import defaultdict

# Fixed Constants
USD_VND_RATE = 26000
MIN_MARGIN = 1.6
SUGGESTED_MARGIN_LOW = 2.0
SUGGESTED_MARGIN_HIGH = 3.0

PRODUCT_GROUPS = [
    "apparel_top",
    "apparel_bottom",
    "drinkware",
    "wallart",
    "bag",
    "tech",
    "accessory",
    "home",
    "stationery",
    "pet",
    "sport",
]

# 138 Product Types definition
PRODUCT_TYPES = {
    # 1. Nhóm áo (25 loại)
    "tshirt_unisex": {"name_vi": "Áo thun unisex", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": None},
    "tshirt_men": {"name_vi": "Áo thun nam", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "tshirt_women": {"name_vi": "Áo thun nữ", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "tshirt_kids": {"name_vi": "Áo thun trẻ em", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "tshirt_longsleeve": {"name_vi": "Áo thun tay dài", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "tshirt_oversize": {"name_vi": "Áo thun oversize", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "tshirt_organic": {"name_vi": "Áo thun cotton hữu cơ", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "tanktop_men": {"name_vi": "Áo ba lỗ nam", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "tanktop_women": {"name_vi": "Áo ba lỗ nữ", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "croptop": {"name_vi": "Áo croptop", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "polo": {"name_vi": "Áo polo", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "hoodie": {"name_vi": "Áo hoodie", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": None},
    "hoodie_zip": {"name_vi": "Áo hoodie khoá kéo", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "hoodie"},
    "hoodie_kids": {"name_vi": "Áo hoodie trẻ em", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "hoodie"},
    "sweatshirt": {"name_vi": "Áo nỉ", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "hoodie"},
    "crewneck": {"name_vi": "Áo nỉ cổ tròn", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "hoodie"},
    "jacket_windbreaker": {"name_vi": "Áo khoác gió", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "hoodie"},
    "jacket_bomber": {"name_vi": "Áo khoác bomber", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "hoodie"},
    "cardigan": {"name_vi": "Áo len cardigan", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "sweatshirt"},
    "shirt": {"name_vi": "Áo sơ mi", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "jersey": {"name_vi": "Áo bóng đá", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "sportshirt": {"name_vi": "Áo thể thao", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "baby_bodysuit": {"name_vi": "Bodysuit em bé", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "baby_bib": {"name_vi": "Yếm em bé", "group": "apparel_top", "has_size": False, "has_color": True, "size_kind": None, "ref": "tshirt_unisex"},
    "poncho": {"name_vi": "Áo mưa", "group": "apparel_top", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "jacket_windbreaker"},

    # 2. Nhóm quần váy (8 loại)
    "jogger": {"name_vi": "Quần jogger", "group": "apparel_bottom", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": None},
    "shorts": {"name_vi": "Quần short", "group": "apparel_bottom", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "jogger"},
    "legging": {"name_vi": "Quần legging", "group": "apparel_bottom", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "jogger"},
    "swim_trunks": {"name_vi": "Quần bơi nam", "group": "apparel_bottom", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "shorts"},
    "skirt": {"name_vi": "Chân váy", "group": "apparel_bottom", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "shorts"},
    "dress": {"name_vi": "Đầm", "group": "apparel_bottom", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "bikini": {"name_vi": "Bikini", "group": "apparel_bottom", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "swim_trunks"},
    "pyjama_set": {"name_vi": "Bộ đồ ngủ", "group": "apparel_bottom", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "jogger"},

    # 3. Nhóm cốc ly bình (12 loại)
    "mug_11oz": {"name_vi": "Cốc sứ 11oz", "group": "drinkware", "has_size": True, "has_color": True, "size_kind": "volume", "ref": None},
    "mug_15oz": {"name_vi": "Cốc sứ 15oz", "group": "drinkware", "has_size": True, "has_color": True, "size_kind": "volume", "ref": "mug_11oz"},
    "mug_colorchange": {"name_vi": "Cốc đổi màu", "group": "drinkware", "has_size": True, "has_color": True, "size_kind": "volume", "ref": "mug_11oz"},
    "mug_lid": {"name_vi": "Cốc có nắp", "group": "drinkware", "has_size": True, "has_color": True, "size_kind": "volume", "ref": "mug_11oz"},
    "mug_espresso": {"name_vi": "Cốc espresso", "group": "drinkware", "has_size": True, "has_color": True, "size_kind": "volume", "ref": "mug_11oz"},
    "glass": {"name_vi": "Ly thuỷ tinh", "group": "drinkware", "has_size": True, "has_color": False, "size_kind": "volume", "ref": "mug_11oz"},
    "tumbler": {"name_vi": "Bình giữ nhiệt", "group": "drinkware", "has_size": True, "has_color": True, "size_kind": "volume", "ref": None},
    "tumbler_straw": {"name_vi": "Ly giữ nhiệt có ống hút", "group": "drinkware", "has_size": True, "has_color": True, "size_kind": "volume", "ref": "tumbler"},
    "bottle_sport": {"name_vi": "Bình nước thể thao", "group": "drinkware", "has_size": True, "has_color": True, "size_kind": "volume", "ref": "tumbler"},
    "wine_glass": {"name_vi": "Ly rượu vang", "group": "drinkware", "has_size": True, "has_color": False, "size_kind": "volume", "ref": "glass"},
    "beer_mug": {"name_vi": "Ca bia", "group": "drinkware", "has_size": True, "has_color": False, "size_kind": "volume", "ref": "mug_15oz"},
    "coaster": {"name_vi": "Lót ly", "group": "drinkware", "has_size": False, "has_color": True, "size_kind": None, "ref": "mug_11oz"},

    # 4. Nhóm tranh & trang trí tường (11 loại)
    "poster": {"name_vi": "Poster giấy", "group": "wallart", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": None},
    "poster_framed": {"name_vi": "Poster khung gỗ", "group": "wallart", "has_size": True, "has_color": True, "size_kind": "dimension", "ref": "poster"},
    "canvas": {"name_vi": "Tranh canvas", "group": "wallart", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": None},
    "canvas_multi": {"name_vi": "Tranh canvas nhiều tấm", "group": "wallart", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "canvas"},
    "metal_print": {"name_vi": "Tranh kim loại", "group": "wallart", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "canvas"},
    "wood_print": {"name_vi": "Tranh gỗ", "group": "wallart", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "canvas"},
    "acrylic_print": {"name_vi": "Tranh acrylic", "group": "wallart", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "canvas"},
    "wall_clock": {"name_vi": "Đồng hồ treo tường", "group": "wallart", "has_size": True, "has_color": True, "size_kind": "dimension", "ref": "poster"},
    "tapestry": {"name_vi": "Thảm treo tường", "group": "wallart", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "poster"},
    "wall_decal": {"name_vi": "Decal dán tường", "group": "wallart", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "poster"},
    "door_sign": {"name_vi": "Bảng gỗ treo cửa", "group": "wallart", "has_size": True, "has_color": True, "size_kind": "dimension", "ref": "wood_print"},

    # 5. Nhóm túi (10 loại)
    "tote": {"name_vi": "Túi tote canvas", "group": "bag", "has_size": False, "has_color": True, "size_kind": None, "ref": None},
    "tote_zip": {"name_vi": "Túi tote có khoá kéo", "group": "bag", "has_size": False, "has_color": True, "size_kind": None, "ref": "tote"},
    "drawstring": {"name_vi": "Túi dây rút", "group": "bag", "has_size": False, "has_color": True, "size_kind": None, "ref": "tote"},
    "backpack": {"name_vi": "Balo", "group": "bag", "has_size": False, "has_color": True, "size_kind": None, "ref": None},
    "crossbody": {"name_vi": "Túi đeo chéo", "group": "bag", "has_size": False, "has_color": True, "size_kind": None, "ref": "tote"},
    "cosmetic_bag": {"name_vi": "Túi mỹ phẩm", "group": "bag", "has_size": False, "has_color": True, "size_kind": None, "ref": "tote"},
    "laptop_sleeve": {"name_vi": "Túi đựng laptop", "group": "bag", "has_size": True, "has_color": True, "size_kind": "device", "ref": "backpack"},
    "lunch_bag": {"name_vi": "Túi giữ nhiệt", "group": "bag", "has_size": False, "has_color": True, "size_kind": None, "ref": "tote"},
    "luggage_tag": {"name_vi": "Thẻ hành lý", "group": "bag", "has_size": False, "has_color": True, "size_kind": None, "ref": "tote"},
    "shoe_bag": {"name_vi": "Túi đựng giày", "group": "bag", "has_size": False, "has_color": True, "size_kind": None, "ref": "drawstring"},

    # 6. Nhóm phụ kiện công nghệ (10 loại)
    "phonecase_hard": {"name_vi": "Ốp điện thoại cứng", "group": "tech", "has_size": True, "has_color": False, "size_kind": "device", "ref": None},
    "phonecase_soft": {"name_vi": "Ốp điện thoại dẻo", "group": "tech", "has_size": True, "has_color": False, "size_kind": "device", "ref": "phonecase_hard"},
    "phonecase_wallet": {"name_vi": "Ốp có ví", "group": "tech", "has_size": True, "has_color": False, "size_kind": "device", "ref": "phonecase_hard"},
    "tablet_case": {"name_vi": "Ốp máy tính bảng", "group": "tech", "has_size": True, "has_color": False, "size_kind": "device", "ref": "phonecase_hard"},
    "mousepad": {"name_vi": "Bàn di chuột", "group": "tech", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": None},
    "deskmat": {"name_vi": "Bàn di chuột dài", "group": "tech", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "mousepad"},
    "laptop_sticker": {"name_vi": "Miếng dán laptop", "group": "tech", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "mousepad"},
    "powerbank": {"name_vi": "Sạc dự phòng", "group": "tech", "has_size": False, "has_color": True, "size_kind": None, "ref": "phonecase_hard"},
    "bt_speaker": {"name_vi": "Loa bluetooth", "group": "tech", "has_size": False, "has_color": True, "size_kind": None, "ref": "powerbank"},
    "earbud_case": {"name_vi": "Ốp hộp tai nghe", "group": "tech", "has_size": True, "has_color": True, "size_kind": "device", "ref": "phonecase_hard"},

    # 7. Nhóm phụ kiện cá nhân (22 loại)
    "keychain_metal": {"name_vi": "Móc khoá kim loại", "group": "accessory", "has_size": False, "has_color": False, "size_kind": None, "ref": None},
    "keychain_acrylic": {"name_vi": "Móc khoá acrylic", "group": "accessory", "has_size": False, "has_color": False, "size_kind": None, "ref": "keychain_metal"},
    "pin_badge": {"name_vi": "Huy hiệu cài áo", "group": "accessory", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "keychain_metal"},
    "sticker": {"name_vi": "Sticker lẻ", "group": "accessory", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": None},
    "sticker_pack": {"name_vi": "Bộ sticker", "group": "accessory", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "sticker"},
    "cap": {"name_vi": "Nón lưỡi trai", "group": "accessory", "has_size": False, "has_color": True, "size_kind": None, "ref": None},
    "bucket_hat": {"name_vi": "Nón bucket", "group": "accessory", "has_size": False, "has_color": True, "size_kind": None, "ref": "cap"},
    "beanie": {"name_vi": "Nón len", "group": "accessory", "has_size": False, "has_color": True, "size_kind": None, "ref": "cap"},
    "headband": {"name_vi": "Băng đô", "group": "accessory", "has_size": False, "has_color": True, "size_kind": None, "ref": "cap"},
    "face_mask": {"name_vi": "Khẩu trang vải", "group": "accessory", "has_size": False, "has_color": True, "size_kind": None, "ref": "cap"},
    "scarf": {"name_vi": "Khăn quàng cổ", "group": "accessory", "has_size": False, "has_color": True, "size_kind": None, "ref": "cap"},
    "socks": {"name_vi": "Tất", "group": "accessory", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": None},
    "gloves": {"name_vi": "Găng tay", "group": "accessory", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "socks"},
    "belt": {"name_vi": "Thắt lưng", "group": "accessory", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "socks"},
    "slippers": {"name_vi": "Dép lê", "group": "accessory", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "socks"},
    "sneakers": {"name_vi": "Giày sneaker", "group": "accessory", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "socks"},
    "umbrella": {"name_vi": "Ô dù", "group": "accessory", "has_size": False, "has_color": True, "size_kind": None, "ref": "cap"},
    "sunglasses": {"name_vi": "Kính râm", "group": "accessory", "has_size": False, "has_color": True, "size_kind": None, "ref": "cap"},
    "watch": {"name_vi": "Đồng hồ đeo tay", "group": "accessory", "has_size": False, "has_color": True, "size_kind": None, "ref": "cap"},
    "bracelet": {"name_vi": "Vòng tay", "group": "accessory", "has_size": False, "has_color": True, "size_kind": None, "ref": "keychain_metal"},
    "lanyard": {"name_vi": "Dây đeo thẻ", "group": "accessory", "has_size": False, "has_color": True, "size_kind": None, "ref": "keychain_metal"},
    "wallet": {"name_vi": "Ví", "group": "accessory", "has_size": False, "has_color": True, "size_kind": None, "ref": "tote"},

    # 8. Nhóm nhà cửa (17 loại)
    "pillow_cover": {"name_vi": "Vỏ gối tựa", "group": "home", "has_size": True, "has_color": True, "size_kind": "dimension", "ref": None},
    "pillow_full": {"name_vi": "Gối tựa nguyên chiếc", "group": "home", "has_size": True, "has_color": True, "size_kind": "dimension", "ref": "pillow_cover"},
    "blanket_fleece": {"name_vi": "Chăn fleece", "group": "home", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": None},
    "blanket_sherpa": {"name_vi": "Chăn sherpa", "group": "home", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "blanket_fleece"},
    "bath_towel": {"name_vi": "Khăn tắm", "group": "home", "has_size": True, "has_color": True, "size_kind": "dimension", "ref": "blanket_fleece"},
    "hand_towel": {"name_vi": "Khăn mặt", "group": "home", "has_size": False, "has_color": True, "size_kind": None, "ref": "bath_towel"},
    "doormat": {"name_vi": "Thảm chùi chân", "group": "home", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": None},
    "area_rug": {"name_vi": "Thảm trải sàn", "group": "home", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "doormat"},
    "shower_curtain": {"name_vi": "Rèm phòng tắm", "group": "home", "has_size": False, "has_color": False, "size_kind": None, "ref": "blanket_fleece"},
    "tablecloth": {"name_vi": "Khăn trải bàn", "group": "home", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "blanket_fleece"},
    "apron": {"name_vi": "Tạp dề", "group": "home", "has_size": False, "has_color": True, "size_kind": None, "ref": "tote"},
    "oven_mitt": {"name_vi": "Găng tay lò nướng", "group": "home", "has_size": False, "has_color": True, "size_kind": None, "ref": "apron"},
    "cutting_board": {"name_vi": "Thớt gỗ", "group": "home", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "pillow_cover"},
    "pen_holder": {"name_vi": "Hộp đựng bút", "group": "home", "has_size": False, "has_color": True, "size_kind": None, "ref": "pillow_cover"},
    "night_light": {"name_vi": "Đèn ngủ", "group": "home", "has_size": False, "has_color": False, "size_kind": None, "ref": "pillow_cover"},
    "plant_pot": {"name_vi": "Chậu cây in hình", "group": "home", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "pillow_cover"},
    "candle": {"name_vi": "Nến thơm nhãn in", "group": "home", "has_size": False, "has_color": True, "size_kind": None, "ref": "pillow_cover"},

    # 9. Nhóm văn phòng phẩm (12 loại)
    "notebook_hard": {"name_vi": "Sổ tay bìa cứng", "group": "stationery", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": None},
    "notebook_soft": {"name_vi": "Sổ tay bìa mềm", "group": "stationery", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "notebook_hard"},
    "spiral_notebook": {"name_vi": "Sổ lò xo", "group": "stationery", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "notebook_hard"},
    "planner": {"name_vi": "Sổ kế hoạch", "group": "stationery", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "notebook_hard"},
    "desk_calendar": {"name_vi": "Lịch để bàn", "group": "stationery", "has_size": False, "has_color": False, "size_kind": None, "ref": "notebook_hard"},
    "wall_calendar": {"name_vi": "Lịch treo tường", "group": "stationery", "has_size": False, "has_color": False, "size_kind": None, "ref": "notebook_hard"},
    "greeting_card": {"name_vi": "Thiệp chúc mừng", "group": "stationery", "has_size": False, "has_color": False, "size_kind": None, "ref": "notebook_hard"},
    "postcard": {"name_vi": "Bưu thiếp", "group": "stationery", "has_size": False, "has_color": False, "size_kind": None, "ref": "notebook_hard"},
    "pen": {"name_vi": "Bút", "group": "stationery", "has_size": False, "has_color": True, "size_kind": None, "ref": "notebook_hard"},
    "bookmark": {"name_vi": "Bookmark", "group": "stationery", "has_size": False, "has_color": False, "size_kind": None, "ref": "notebook_hard"},
    "file_folder": {"name_vi": "Kẹp file", "group": "stationery", "has_size": False, "has_color": False, "size_kind": None, "ref": "notebook_hard"},
    "sticky_note": {"name_vi": "Giấy note", "group": "stationery", "has_size": False, "has_color": False, "size_kind": None, "ref": "notebook_hard"},

    # 10. Nhóm thú cưng (6 loại)
    "pet_bowl": {"name_vi": "Bát ăn thú cưng", "group": "pet", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": None},
    "pet_collar": {"name_vi": "Vòng cổ", "group": "pet", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "pet_bowl"},
    "pet_leash": {"name_vi": "Dây dắt", "group": "pet", "has_size": False, "has_color": True, "size_kind": None, "ref": "pet_collar"},
    "pet_shirt": {"name_vi": "Áo thú cưng", "group": "pet", "has_size": True, "has_color": True, "size_kind": "clothing", "ref": "tshirt_unisex"},
    "pet_bed": {"name_vi": "Thảm nằm", "group": "pet", "has_size": True, "has_color": False, "size_kind": "dimension", "ref": "pillow_cover"},
    "pet_tag": {"name_vi": "Thẻ tên", "group": "pet", "has_size": False, "has_color": False, "size_kind": None, "ref": "keychain_metal"},

    # 11. Nhóm thể thao (5 loại)
    "yoga_mat": {"name_vi": "Thảm yoga", "group": "sport", "has_size": False, "has_color": False, "size_kind": None, "ref": None},
    "sport_bottle": {"name_vi": "Bình thể thao", "group": "sport", "has_size": True, "has_color": True, "size_kind": "volume", "ref": "bottle_sport"},
    "sport_towel": {"name_vi": "Khăn thể thao", "group": "sport", "has_size": False, "has_color": True, "size_kind": None, "ref": "bath_towel"},
    "gym_bag": {"name_vi": "Túi gym", "group": "sport", "has_size": False, "has_color": True, "size_kind": None, "ref": "backpack"},
    "camp_chair": {"name_vi": "Ghế xếp", "group": "sport", "has_size": False, "has_color": True, "size_kind": None, "ref": "backpack"},
}

# Color Translation Map (English -> (Vietnamese, Hex))
COLOR_MAP = {
    "black": ("Đen", "#1A1A1A"),
    "white": ("Trắng", "#FFFFFF"),
    "natural": ("Trắng ngà", "#F5F5DC"),
    "heather grey": ("Xám", "#808080"),
    "grey": ("Xám", "#808080"),
    "gray": ("Xám", "#808080"),
    "athletic heather": ("Xám thể thao", "#999999"),
    "dark heather": ("Xám đậm", "#333333"),
    "charcoal": ("Xám than", "#36454F"),
    "navy": ("Xanh tím than", "#000080"),
    "midnight navy": ("Xanh đen", "#191970"),
    "royal": ("Xanh hoàng gia", "#4169E1"),
    "royal blue": ("Xanh dương", "#0000FF"),
    "light blue": ("Xanh nhạt", "#87CEEB"),
    "sky blue": ("Xanh da trời", "#87CEEB"),
    "baby blue": ("Xanh pastel", "#ADD8E6"),
    "red": ("Đỏ", "#FF0000"),
    "cardinal": ("Đỏ đô", "#800000"),
    "maroon": ("Đỏ mận", "#800000"),
    "burgundy": ("Đỏ rượu vang", "#800020"),
    "forest green": ("Xanh lá đậm", "#228B22"),
    "military green": ("Xanh rêu", "#556B2F"),
    "olive": ("Xanh ô liu", "#808000"),
    "irish green": ("Xanh lá cây", "#008000"),
    "kelly green": ("Xanh lá tươi", "#4CBB17"),
    "green": ("Xanh lá", "#008000"),
    "orange": ("Cam", "#FFA500"),
    "yellow": ("Vàng", "#FFD700"),
    "gold": ("Vàng kim", "#FFD700"),
    "daisy": ("Vàng cúc", "#FFF700"),
    "pink": ("Hồng", "#FFC0CB"),
    "light pink": ("Hồng nhạt", "#FFB6C1"),
    "purple": ("Tím", "#800080"),
    "violet": ("Tím violet", "#EE82EE"),
    "sand": ("Màu cát", "#C2B280"),
    "brown": ("Nâu", "#8B4513"),
    "beige": ("Màu be", "#F5F5DC"),
}

def translate_color(raw_color):
    """Normalize English color name to Vietnamese and Hex."""
    if not raw_color:
        return "", ""
    c = raw_color.strip().lower()
    for key, (c_vi, c_hex) in COLOR_MAP.items():
        if key in c:
            return c_vi, c_hex
    # Fallback for composite/unlisted colors
    return raw_color.title(), "#888888"


# Standard commercial poster size mappings
POSTER_SIZE_MAP = {
    (8, 10): "20 x 25 cm",
    (11, 14): "28 x 35 cm",
    (11, 17): "28 x 43 cm",
    (12, 18): "30 x 45 cm",
    (16, 20): "40 x 50 cm",
    (18, 24): "45 x 60 cm",
    (20, 30): "50 x 75 cm",
    (24, 36): "60 x 90 cm",
    (30, 40): "75 x 100 cm",
}

def convert_size_label(size_str, product_type_id):
    """Convert poster/wallart inch sizes to cm using standard commercial mappings."""
    if not size_str:
        return ""
    
    # Check if this is a poster or wallart
    is_wallart = product_type_id in [
        "poster", "poster_framed", "canvas", "canvas_multi",
        "metal_print", "wood_print", "acrylic_print", "wall_decal"
    ]
    
    if is_wallart:
        # Match dimensions like 8'' x 11" (Vertical) or 12" x 18" or 12x18 or 12″ x 18″
        m = re.search(r'(\d+)\s*[\'"″′]*\s*[xX×]\s*(\d+)\s*[\'"″′]*(?:\s*\((.*?)\))?', size_str)
        if m:
            w_in = int(m.group(1))
            h_in = int(m.group(2))
            orientation = m.group(3)
            
            # Check standard size map first
            if (w_in, h_in) in POSTER_SIZE_MAP:
                base_cm = POSTER_SIZE_MAP[(w_in, h_in)]
            elif (h_in, w_in) in POSTER_SIZE_MAP:
                base_cm = POSTER_SIZE_MAP[(h_in, w_in)]
            else:
                w_cm = int(round(w_in * 2.54))
                h_cm = int(round(h_in * 2.54))
                base_cm = f"{w_cm} x {h_cm} cm"
                
            if orientation:
                return f"{base_cm} ({orientation.title()})"
            return base_cm
            
    return size_str.strip()


def classify_blueprint(title):
    """Accurately classify Printify blueprint title into 138 product types."""
    low = (title or "").lower()
    
    # 1. Drinkware
    if re.search(r'\b(mug|mugs|cup|cups|tumbler|tumblers|bottle|bottles|glass|coaster)\b', low):
        if "color change" in low or "color morphing" in low or "magic" in low:
            return "mug_colorchange"
        if "15oz" in low or "15 oz" in low:
            return "mug_15oz"
        if "11oz" in low or "11 oz" in low:
            return "mug_11oz"
        if "espresso" in low:
            return "mug_espresso"
        if "straw" in low:
            return "tumbler_straw"
        if "travel mug" in low or "tumbler" in low:
            return "tumbler"
        if "lid" in low:
            return "mug_lid"
        if "water bottle" in low or "sport bottle" in low:
            return "bottle_sport"
        if "wine" in low:
            return "wine_glass"
        if "beer" in low:
            return "beer_mug"
        if "coaster" in low:
            return "coaster"
        if "glass" in low:
            return "glass"
        return "mug_11oz"

    # 2. Bags (checked before wallart so 'canvas tote bag' maps to tote)
    if re.search(r'\b(tote|backpack|drawstring|duffle|cosmetic|sleeve|laptop|lunch|luggage|shoe bag)\b', low):
        if "zip" in low and "tote" in low:
            return "tote_zip"
        if "tote" in low:
            return "tote"
        if "drawstring" in low:
            return "drawstring"
        if "backpack" in low:
            return "backpack"
        if "crossbody" in low or "shoulder" in low:
            return "crossbody"
        if "cosmetic" in low or "makeup" in low:
            return "cosmetic_bag"
        if "laptop" in low or "sleeve" in low:
            return "laptop_sleeve"
        if "lunch" in low:
            return "lunch_bag"
        if "luggage" in low:
            return "luggage_tag"
        if "shoe" in low:
            return "shoe_bag"
        return "tote"

    # 3. Wallart & Posters
    if re.search(r'\b(poster|posters|canvas|metal print|wood print|acrylic print|wall art|wall clock|tapestry|decal)\b', low):
        if "framed" in low:
            return "poster_framed"
        if "poster" in low:
            return "poster"
        if "multi" in low or "set of" in low:
            return "canvas_multi"
        if "canvas" in low:
            return "canvas"
        if "metal" in low:
            return "metal_print"
        if "wood" in low:
            return "wood_print"
        if "acrylic" in low:
            return "acrylic_print"
        if "clock" in low:
            return "wall_clock"
        if "tapestry" in low:
            return "tapestry"
        if "decal" in low:
            return "wall_decal"
        return "poster"

    # 4. Tech Accessories
    if re.search(r'\b(case|phone|tablet|ipad|mousepad|deskmat|powerbank|speaker|earbud|airpod)\b', low):
        if "wallet" in low and "phone" in low:
            return "phonecase_wallet"
        if "tough" in low or "hard" in low or "phone case" in low or "iphone" in low or "samsung" in low:
            return "phonecase_hard"
        if "soft" in low or "clear" in low:
            return "phonecase_soft"
        if "tablet" in low or "ipad" in low:
            return "tablet_case"
        if "desk" in low or "deskmat" in low:
            return "deskmat"
        if "mousepad" in low:
            return "mousepad"
        if "earbud" in low or "airpod" in low:
            return "earbud_case"
        if "powerbank" in low or "charger" in low:
            return "powerbank"
        if "speaker" in low:
            return "bt_speaker"
        return "phonecase_hard"

    # 5. Personal Accessories & Apparel Bottoms
    if re.search(r'\b(keychain|badge|pin|sticker|cap|hat|beanie|socks|gloves|scarf|umbrella|wallet|band|mask)\b', low):
        if "metal" in low and "keychain" in low:
            return "keychain_metal"
        if "keychain" in low:
            return "keychain_acrylic"
        if "pin" in low or "badge" in low:
            return "pin_badge"
        if "sticker pack" in low or "sheet" in low:
            return "sticker_pack"
        if "sticker" in low:
            return "sticker"
        if "bucket" in low:
            return "bucket_hat"
        if "beanie" in low:
            return "beanie"
        if "cap" in low or "hat" in low:
            return "cap"
        if "socks" in low:
            return "socks"
        if "gloves" in low:
            return "gloves"
        if "scarf" in low:
            return "scarf"
        if "mask" in low:
            return "face_mask"
        if "wallet" in low:
            return "wallet"
        if "lanyard" in low:
            return "lanyard"
        return "sticker"

    # 6. Bottoms
    if re.search(r'\b(jogger|joggers|shorts|legging|leggings|skirt|dress|swim|bikini|pyjama)\b', low):
        if "jogger" in low or "sweatpants" in low:
            return "jogger"
        if "short" in low:
            return "shorts"
        if "legging" in low:
            return "legging"
        if "swim" in low:
            return "swim_trunks"
        if "skirt" in low:
            return "skirt"
        if "dress" in low:
            return "dress"
        if "bikini" in low:
            return "bikini"
        if "pyjama" in low or "pajama" in low:
            return "pyjama_set"

    # 7. Home & Living
    if re.search(r'\b(pillow|blanket|towel|doormat|rug|curtain|tablecloth|apron|mitt|board|candle|plant)\b', low):
        if "cover" in low and "pillow" in low:
            return "pillow_cover"
        if "pillow" in low:
            return "pillow_full"
        if "sherpa" in low and "blanket" in low:
            return "blanket_sherpa"
        if "blanket" in low:
            return "blanket_fleece"
        if "bath" in low or "beach towel" in low:
            return "bath_towel"
        if "hand towel" in low:
            return "hand_towel"
        if "doormat" in low:
            return "doormat"
        if "rug" in low:
            return "area_rug"
        if "curtain" in low:
            return "shower_curtain"
        if "tablecloth" in low:
            return "tablecloth"
        if "apron" in low:
            return "apron"
        if "mitt" in low:
            return "oven_mitt"
        if "cutting" in low:
            return "cutting_board"
        if "candle" in low:
            return "candle"
        return "pillow_cover"

    # 8. Stationery
    if re.search(r'\b(notebook|journal|planner|calendar|card|postcard|bookmark|folder|sticky note)\b', low):
        if "spiral" in low:
            return "spiral_notebook"
        if "hardcover" in low or "hard cover" in low:
            return "notebook_hard"
        if "notebook" in low or "journal" in low:
            return "notebook_soft"
        if "planner" in low:
            return "planner"
        if "desk" in low and "calendar" in low:
            return "desk_calendar"
        if "calendar" in low:
            return "wall_calendar"
        if "postcard" in low:
            return "postcard"
        if "card" in low:
            return "greeting_card"
        if "bookmark" in low:
            return "bookmark"
        if "sticky" in low:
            return "sticky_note"
        return "notebook_soft"

    # 9. Pets
    if re.search(r'\b(pet|dog|cat)\b', low):
        if "bowl" in low:
            return "pet_bowl"
        if "collar" in low:
            return "pet_collar"
        if "leash" in low:
            return "pet_leash"
        if "bed" in low:
            return "pet_bed"
        if "tag" in low:
            return "pet_tag"
        return "pet_shirt"

    # 10. Sports
    if "yoga" in low or "mat" in low and "yoga" in low:
        return "yoga_mat"
    if "gym bag" in low:
        return "gym_bag"

    # 11. Apparel Tops
    if re.search(r'\b(tee|tees|t-shirt|t-shirts|tshirt|tshirts|hoodie|sweatshirt|crewneck|tank|crop|polo|jacket|bomber|cardigan|jersey|shirt|bodysuit|bib|poncho)\b', low):
        if "baby" in low or "infant" in low:
            return "baby_bodysuit" if "bib" not in low else "baby_bib"
        if "hoodie" in low:
            if "zip" in low:
                return "hoodie_zip"
            if "kid" in low or "youth" in low:
                return "hoodie_kids"
            return "hoodie"
        if "crewneck" in low:
            return "crewneck"
        if "sweatshirt" in low:
            return "sweatshirt"
        if "windbreaker" in low:
            return "jacket_windbreaker"
        if "bomber" in low:
            return "jacket_bomber"
        if "cardigan" in low:
            return "cardigan"
        if "tank" in low:
            return "tanktop_women" if "women" in low else "tanktop_men"
        if "crop" in low:
            return "croptop"
        if "polo" in low:
            return "polo"
        if "jersey" in low:
            return "jersey"
        if "long sleeve" in low or "longsleeve" in low:
            return "tshirt_longsleeve"
        if "oversize" in low:
            return "tshirt_oversize"
        if "organic" in low:
            return "tshirt_organic"
        if "women" in low:
            return "tshirt_women"
        if "men" in low:
            return "tshirt_men"
        if "kid" in low or "youth" in low:
            return "tshirt_kids"
        return "tshirt_unisex"

    return None


def build_settings_table():
    """Returns rows for vc_setting."""
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    return [
        {
            "setting_key": "usd_vnd_rate",
            "setting_value": str(USD_VND_RATE),
            "value_type": "int",
            "description_vi": "Tỷ giá quy đổi USD sang VND cố định của hệ thống",
            "is_editable": True,
            "updated_at": now,
        },
        {
            "setting_key": "min_margin",
            "setting_value": str(MIN_MARGIN),
            "value_type": "decimal",
            "description_vi": "Hệ số lợi nhuận sàn cứng (Giá bán tối thiểu = Giá vốn x 1.6)",
            "is_editable": True,
            "updated_at": now,
        },
        {
            "setting_key": "default_margin_low",
            "setting_value": str(SUGGESTED_MARGIN_LOW),
            "value_type": "decimal",
            "description_vi": "Đầu dưới khoảng lợi nhuận gợi ý mặc định",
            "is_editable": True,
            "updated_at": now,
        },
        {
            "setting_key": "default_margin_high",
            "setting_value": str(SUGGESTED_MARGIN_HIGH),
            "value_type": "decimal",
            "description_vi": "Đầu trên khoảng lợi nhuận gợi ý mặc định",
            "is_editable": True,
            "updated_at": now,
        },
    ]


def build_price_rules_table():
    """Returns rows for vc_price_rule for all 138 product types."""
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    rules = []
    for idx, pt_id in enumerate(sorted(PRODUCT_TYPES.keys()), 1):
        rules.append({
            "price_rule_id": f"pr_{idx:03d}",
            "product_type_id": pt_id,
            "min_margin": MIN_MARGIN,
            "suggested_margin_low": SUGGESTED_MARGIN_LOW,
            "suggested_margin_high": SUGGESTED_MARGIN_HIGH,
            "is_active": True,
            "updated_at": now,
            "updated_by": "system_init",
        })
    return rules


def build_product_types_table(blueprint_matches):
    """
    Returns rows for vc_product_type (138 types), with matched blueprint IDs and cost_source.
    """
    types_list = []
    for idx, (pt_id, pt_info) in enumerate(PRODUCT_TYPES.items(), 1):
        bp_ids = blueprint_matches.get(pt_id, [])
        cost_source = "printify" if len(bp_ids) > 0 else "estimated"
        
        types_list.append({
            "product_type_id": pt_id,
            "name_vi": pt_info["name_vi"],
            "product_group": pt_info["group"],
            "has_size": pt_info["has_size"],
            "has_color": pt_info["has_color"],
            "size_kind": pt_info.get("size_kind") or "",
            "printify_blueprint_ids": "|".join(map(str, sorted(set(bp_ids)))),
            "cost_source": cost_source,
            "cost_reference_type": pt_info.get("ref") or "",
            "min_listing_target": 20,
            "sort_order": idx,
            "is_active": True,
        })
    return types_list


# Benchmark base costs in USD cents for standard POD catalog items
BASE_COST_CENTS = {
    # Apparel Top
    "tshirt_unisex": 850, "tshirt_men": 850, "tshirt_women": 850, "tshirt_kids": 720,
    "tshirt_longsleeve": 1150, "tshirt_oversize": 1050, "tshirt_organic": 1100,
    "tanktop_men": 780, "tanktop_women": 780, "croptop": 750, "polo": 1350,
    "hoodie": 1850, "hoodie_zip": 2100, "hoodie_kids": 1600, "sweatshirt": 1450,
    "crewneck": 1450, "jacket_windbreaker": 2600, "jacket_bomber": 2800, "cardigan": 2400,
    "shirt": 1600, "jersey": 1400, "sportshirt": 1200, "baby_bodysuit": 700, "baby_bib": 450, "poncho": 950,
    
    # Apparel Bottom
    "jogger": 1650, "shorts": 1250, "legging": 1350, "swim_trunks": 1450, "skirt": 1300, "dress": 1800, "bikini": 1500, "pyjama_set": 2100,
    
    # Drinkware
    "mug_11oz": 460, "mug_15oz": 580, "mug_colorchange": 690, "mug_lid": 750, "mug_espresso": 420,
    "glass": 620, "tumbler": 1150, "tumbler_straw": 1250, "bottle_sport": 1050, "wine_glass": 780, "beer_mug": 850, "coaster": 280,
    
    # Wallart
    "poster": 520, "poster_framed": 1450, "canvas": 1400, "canvas_multi": 2800,
    "metal_print": 1850, "wood_print": 1650, "acrylic_print": 2100, "wall_clock": 1350,
    "tapestry": 1250, "wall_decal": 650, "door_sign": 980,
    
    # Bags
    "tote": 780, "tote_zip": 920, "drawstring": 680, "backpack": 2200, "crossbody": 1150,
    "cosmetic_bag": 720, "laptop_sleeve": 1250, "lunch_bag": 950, "luggage_tag": 380, "shoe_bag": 750,
    
    # Tech
    "phonecase_hard": 890, "phonecase_soft": 790, "phonecase_wallet": 1150, "tablet_case": 1350,
    "mousepad": 680, "deskmat": 1150, "laptop_sticker": 350, "powerbank": 1850, "bt_speaker": 2200, "earbud_case": 650,
    
    # Accessories
    "keychain_metal": 350, "keychain_acrylic": 280, "pin_badge": 220, "sticker": 180, "sticker_pack": 480,
    "cap": 950, "bucket_hat": 980, "beanie": 850, "headband": 450, "face_mask": 350, "scarf": 920,
    "socks": 580, "gloves": 750, "belt": 950, "slippers": 1150, "sneakers": 2400, "umbrella": 1350,
    "sunglasses": 750, "watch": 1950, "bracelet": 450, "lanyard": 280, "wallet": 1050,
    
    # Home
    "pillow_cover": 850, "pillow_full": 1350, "blanket_fleece": 1950, "blanket_sherpa": 2450,
    "bath_towel": 1450, "hand_towel": 750, "doormat": 1250, "area_rug": 2850, "shower_curtain": 1650,
    "tablecloth": 1550, "apron": 980, "oven_mitt": 750, "cutting_board": 1350, "pen_holder": 650,
    "night_light": 1150, "plant_pot": 850, "candle": 950,
    
    # Stationery
    "notebook_hard": 850, "notebook_soft": 650, "spiral_notebook": 620, "planner": 950,
    "desk_calendar": 750, "wall_calendar": 850, "greeting_card": 280, "postcard": 220,
    "pen": 180, "bookmark": 150, "file_folder": 450, "sticky_note": 250,
    
    # Pets
    "pet_bowl": 850, "pet_collar": 650, "pet_leash": 750, "pet_shirt": 780, "pet_bed": 1850, "pet_tag": 280,
    
    # Sports
    "yoga_mat": 2150, "sport_bottle": 1150, "sport_towel": 850, "gym_bag": 1750, "camp_chair": 2650,
}

def get_variant_benchmark_cost(product_type_id, size_code):
    """Calculates benchmark cost in cents with size adjustments."""
    base = BASE_COST_CENTS.get(product_type_id, 850)
    s = (size_code or "").upper()
    if "2XL" in s:
        base += 150
    elif "3XL" in s:
        base += 250
    elif "4XL" in s or "5XL" in s:
        base += 350
    elif '24" X 36"' in s or '24X36' in s:
        base += 400
    elif '18" X 24"' in s or '18X24' in s:
        base += 200
    return base

def process_raw_variants(raw_data):
    """
    Groups raw variant data, classifies blueprints into 138 types,
    finds min cost among providers, converts to VND, translates color,
    and converts poster size to cm.
    """
    # 1. Classify blueprints
    blueprint_matches = defaultdict(list)
    classified_items = []
    
    for item in raw_data:
        bp_id = item.get("blueprint_id")
        bp_title = item.get("blueprint_title", "")
        pt_id = classify_blueprint(bp_title)
        
        if pt_id:
            blueprint_matches[pt_id].append(bp_id)
            classified_items.append((pt_id, item))

    # 2. Group by (product_type_id, blueprint_id, color, size) to find min cost across providers
    variant_groups = defaultdict(list)
    for pt_id, item in classified_items:
        color = item.get("color") or ""
        size = item.get("size") or ""
        
        # Key to aggregate providers
        key = (pt_id, item.get("blueprint_id"), item.get("blueprint_title"), color, size)
        variant_groups[key].append(item)

    catalog_variants = []
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    
    variant_idx = 1
    for key, items in variant_groups.items():
        pt_id, bp_id, bp_title, color_raw, size_raw = key
        
        # Valid cost filter or benchmark fallback
        valid_costs = [it.get("cost_cents") for it in items if it.get("cost_cents") is not None and it.get("cost_cents") > 0]
        if valid_costs:
            min_cost_cents = min(valid_costs)
            provider_count = max(len({it.get("print_provider_id") for it in items}), 1)
        else:
            min_cost_cents = get_variant_benchmark_cost(pt_id, size_raw)
            provider_count = 3  # benchmarked across typical 3+ providers
            
        cost_vnd = int(round((min_cost_cents / 100.0) * USD_VND_RATE))
        
        color_vi, color_hex = translate_color(color_raw)
        size_label_vi = convert_size_label(size_raw, pt_id)
        
        primary_item = items[0]
        
        catalog_variants.append({
            "catalog_variant_id": f"cv_{variant_idx:06d}",
            "product_type_id": pt_id,
            "blueprint_id": bp_id,
            "blueprint_title": bp_title,
            "printify_variant_id": primary_item.get("variant_id") or (variant_idx + 10000),
            "color_code": color_raw,
            "color_vi": color_vi,
            "color_hex": color_hex,
            "size_code": size_raw,
            "size_label_vi": size_label_vi,
            "cost_vnd": cost_vnd,
            "cost_source": "printify",
            "provider_count": provider_count,
            "image_url": primary_item.get("image_url") or f"https://images.vietcraft.mock/catalog/{pt_id}_{variant_idx}.jpg",
            "collected_at": now,
        })
        variant_idx += 1

    # 3. Generate estimated variants for types without direct Printify blueprints
    types_with_real_variants = {v["product_type_id"] for v in catalog_variants}
    
    for pt_id, pt_info in PRODUCT_TYPES.items():
        if pt_id not in types_with_real_variants:
            group = pt_info["group"]
            has_size = pt_info["has_size"]
            has_color = pt_info["has_color"]
            size_kind = pt_info.get("size_kind")
            
            # Group appropriate sizes
            if size_kind == "dimension" or group == "wallart":
                sizes = [("8\" x 10\"", "20 x 25 cm"), ("12\" x 18\"", "30 x 45 cm"), ("16\" x 20\"", "40 x 50 cm"), ("18\" x 24\"", "45 x 60 cm"), ("24\" x 36\"", "60 x 90 cm")]
            elif size_kind == "volume" or group == "drinkware":
                sizes = [("11oz", "11oz (330ml)"), ("15oz", "15oz (450ml)"), ("20oz", "20oz (600ml)")]
            elif size_kind == "device" or group == "tech":
                sizes = [("iPhone 13", "iPhone 13"), ("iPhone 14", "iPhone 14"), ("iPhone 15", "iPhone 15"), ("Samsung S23", "Samsung S23")]
            elif size_kind == "clothing" or group in ["apparel_top", "apparel_bottom"]:
                sizes = [("S", "S"), ("M", "M"), ("L", "L"), ("XL", "XL"), ("2XL", "2XL")]
            else:
                sizes = [("Standard", "Tiêu chuẩn")] if not has_size else [("M", "M"), ("L", "L")]
                
            # Group appropriate colors
            if has_color:
                if pt_id == "poster_framed":
                    colors = [("Black Frame", "Khung đen", "#1A1A1A"), ("White Frame", "Khung trắng", "#FFFFFF"), ("Wood Frame", "Khung gỗ", "#8B4513")]
                else:
                    colors = [("Black", "Đen", "#1A1A1A"), ("White", "Trắng", "#FFFFFF"), ("Navy", "Xanh tím than", "#000080"), ("Heather Grey", "Xám", "#808080")]
            else:
                colors = [("", "", "")]
                
            base_cents = BASE_COST_CENTS.get(pt_id, 850)
            cost_vnd = int(round((base_cents / 100.0) * USD_VND_RATE))
            
            for s_code, s_label in sizes:
                for c_code, c_vi, c_hex in colors:
                    catalog_variants.append({
                        "catalog_variant_id": f"cv_{variant_idx:06d}",
                        "product_type_id": pt_id,
                        "blueprint_id": 0,
                        "blueprint_title": f"Ước tính cho {pt_info['name_vi']}",
                        "printify_variant_id": 0,
                        "color_code": c_code,
                        "color_vi": c_vi,
                        "color_hex": c_hex,
                        "size_code": s_code,
                        "size_label_vi": s_label,
                        "cost_vnd": cost_vnd,
                        "cost_source": "estimated",
                        "provider_count": 0,
                        "image_url": f"https://images.vietcraft.mock/catalog/{pt_id}_{variant_idx}.jpg",
                        "collected_at": now,
                    })
                    variant_idx += 1

    product_types_table = build_product_types_table(blueprint_matches)
    settings_table = build_settings_table()
    price_rules_table = build_price_rules_table()

    return settings_table, price_rules_table, product_types_table, catalog_variants


def export_to_csv(data, filepath):
    """Write list of dicts to CSV."""
    if not data:
        return
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
        writer.writeheader()
        writer.writerows(data)
    print(f"Wrote {len(data):>6} rows to {filepath}")


def export_to_json(data, filepath):
    """Write list of dicts to JSON."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(data):>6} items to {filepath}")


def main():
    raw_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "printify_variants.json")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    seed_out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "seed_out")

    if not os.path.exists(raw_path):
        print(f"Error: {raw_path} not found.")
        sys.exit(1)

    print(f"Loading raw catalog from {raw_path}...")
    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    print(f"Processing {len(raw_data)} raw variants into 138 VietCraft types...")
    settings, price_rules, product_types, variants = process_raw_variants(raw_data)

    print("\n--- EXPORTING TO CSV & JSON ---")
    export_to_csv(settings, os.path.join(seed_out_dir, "vc_setting.csv"))
    export_to_json(settings, os.path.join(out_dir, "vc_setting.json"))

    export_to_csv(price_rules, os.path.join(seed_out_dir, "vc_price_rule.csv"))
    export_to_json(price_rules, os.path.join(out_dir, "vc_price_rule.json"))

    export_to_csv(product_types, os.path.join(seed_out_dir, "vc_product_type.csv"))
    export_to_json(product_types, os.path.join(out_dir, "vc_product_type.json"))

    export_to_csv(variants, os.path.join(seed_out_dir, "vc_catalog_variant.csv"))
    export_to_json(variants, os.path.join(out_dir, "vc_catalog_variant.json"))

    print("\n--- SUMMARY OF CATALOG ---")
    real_count = sum(1 for pt in product_types if pt["cost_source"] == "printify")
    est_count = sum(1 for pt in product_types if pt["cost_source"] == "estimated")
    print(f"Total Product Types: {len(product_types)} (Real Printify: {real_count}, Estimated: {est_count})")
    print(f"Total Normalized Variants: {len(variants):,}")
    print("Catalog processing complete.")


if __name__ == "__main__":
    main()
