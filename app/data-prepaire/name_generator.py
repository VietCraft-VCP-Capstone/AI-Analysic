"""
name_generator.py
Sinh tên + mô tả sản phẩm tiếng Việt cho seeder 5.000 sản phẩm.

Import vào seeder:
    from name_generator import generate_product, generate_batch

    name, desc = generate_product("tshirt_unisex", "tet")
    batch      = generate_batch(200)          # [(name, desc), ...]
"""

import random
from collections import Counter

# ============================================================
# DANH SÁCH 1 — 138 LOẠI SẢN PHẨM THEO ĐÚNG KẾ HOẠCH TUẦN
# Mỗi khóa = product_type_id trong bảng vc_product_type
# Mỗi giá trị = danh sách 2-3 cách gọi khác nhau
# ============================================================

PRODUCT_TYPES: dict[str, list[str]] = {

    # ── Nhóm áo (25 loại) ──────────────────────────────────
    "tshirt_unisex":       ["Áo thun unisex", "Áo phông unisex", "Áo thun cotton unisex"],
    "tshirt_men":          ["Áo thun nam", "Áo phông nam", "Áo thun cổ tròn nam"],
    "tshirt_women":        ["Áo thun nữ", "Áo phông nữ", "Áo thun nữ form ôm"],
    "tshirt_kids":         ["Áo thun trẻ em", "Áo phông bé in hình", "Áo thun kids"],
    "tshirt_longsleeve":   ["Áo thun tay dài", "Áo tay dài in hình", "Áo thun dài tay unisex"],
    "tshirt_oversize":     ["Áo thun oversize", "Áo phông form rộng", "Áo oversize unisex"],
    "tshirt_organic":      ["Áo thun cotton hữu cơ", "Áo thun organic", "Áo thun eco-friendly"],
    "tanktop_men":         ["Áo ba lỗ nam", "Áo tanktop nam", "Áo sát nách nam in hình"],
    "tanktop_women":       ["Áo ba lỗ nữ", "Áo tanktop nữ", "Áo sát nách nữ in họa tiết"],
    "croptop":             ["Áo croptop nữ", "Áo thun ngắn nữ", "Croptop in hình"],
    "polo":                ["Áo polo", "Áo thun cổ bẻ", "Áo polo cotton in logo"],
    "hoodie":              ["Áo hoodie", "Áo hoodie nỉ unisex", "Áo khoác hoodie"],
    "hoodie_zip":          ["Áo hoodie khoá kéo", "Áo zip hoodie", "Áo khoác hoodie có zip"],
    "hoodie_kids":         ["Áo hoodie trẻ em", "Hoodie bé in hình", "Áo hoodie kids"],
    "sweatshirt":          ["Áo nỉ", "Áo sweatshirt", "Áo nỉ dày in họa tiết"],
    "crewneck":            ["Áo nỉ cổ tròn", "Crewneck in hình", "Áo sweater cổ tròn"],
    "jacket_windbreaker":  ["Áo khoác gió", "Jacket chống gió in hình", "Áo gió in logo"],
    "jacket_bomber":       ["Áo khoác bomber", "Bomber jacket in hình", "Áo bomber in họa tiết"],
    "cardigan":            ["Áo len cardigan", "Cardigan in hình", "Áo len mỏng in họa tiết"],
    "shirt":               ["Áo sơ mi", "Sơ mi in họa tiết", "Áo sơ mi dài tay in hình"],
    "jersey":              ["Áo bóng đá", "Áo đá banh in số", "Jersey in tên cầu thủ"],
    "sportshirt":          ["Áo thể thao", "Áo thun thể thao in hình", "Áo tập gym in logo"],
    "baby_bodysuit":       ["Bodysuit em bé", "Áo liền thân bé sơ sinh in hình", "Baby bodysuit in họa tiết"],
    "baby_bib":            ["Yếm em bé", "Yếm bé in hình dễ thương", "Yếm vải bé in họa tiết"],
    "poncho":              ["Áo mưa in hoa văn", "Poncho in hình", "Áo mưa hoodie in họa tiết"],

    # ── Nhóm quần váy (8 loại) ─────────────────────────────
    "jogger":              ["Quần jogger", "Quần thun ống suông in hình", "Quần nỉ jogger in logo"],
    "shorts":              ["Quần short thun", "Quần đùi in hình", "Quần short thể thao"],
    "legging":             ["Quần legging", "Legging thể thao in họa tiết", "Quần tập yoga in hình"],
    "swim_trunks":         ["Quần bơi nam", "Quần bơi in hình", "Quần short bơi họa tiết"],
    "skirt":               ["Chân váy in họa tiết", "Váy in hình", "Chân váy vải in hoa"],
    "dress":               ["Đầm in họa tiết", "Váy đầm in hình", "Đầm vải in hoa"],
    "bikini":              ["Bikini in hình", "Đồ bơi nữ in họa tiết", "Set bikini in hoa văn"],
    "pyjama_set":          ["Bộ đồ ngủ", "Pyjama in hình", "Bộ đồ mặc nhà in họa tiết"],

    # ── Nhóm cốc ly bình (12 loại) ─────────────────────────
    "mug_11oz":            ["Cốc sứ 11oz", "Ly sứ in hình 11oz", "Mug 11oz in họa tiết"],
    "mug_15oz":            ["Cốc sứ 15oz", "Ly sứ lớn 15oz in hình", "Mug 15oz in ảnh"],
    "mug_colorchange":     ["Cốc đổi màu in hình", "Magic mug in họa tiết", "Ly đổi màu khi rót nước nóng"],
    "mug_lid":             ["Cốc có nắp in hình", "Ly sứ nắp tre in họa tiết", "Cốc sứ kèm nắp in ảnh"],
    "mug_espresso":        ["Cốc espresso in hình", "Ly espresso in họa tiết", "Cốc cà phê nhỏ in hình"],
    "glass":               ["Ly thuỷ tinh in hình", "Cốc thuỷ tinh in họa tiết", "Ly thủy tinh borosilicate"],
    "tumbler":             ["Bình giữ nhiệt in hình", "Thermos in họa tiết", "Bình giữ nhiệt inox in laser"],
    "tumbler_straw":       ["Ly giữ nhiệt có ống hút", "Bình giữ nhiệt nắp ống hút in hình", "Tumbler ống hút in họa tiết"],
    "bottle_sport":        ["Bình nước thể thao in hình", "Bình tritan in logo", "Sport bottle in họa tiết"],
    "wine_glass":          ["Ly rượu vang in hình", "Wine glass in họa tiết", "Ly vang khắc tên"],
    "beer_mug":            ["Ca bia in hình", "Beer mug in họa tiết", "Cốc bia in logo"],
    "coaster":             ["Lót ly in hình", "Coaster in họa tiết", "Miếng lót cốc in ảnh"],

    # ── Nhóm tranh & trang trí tường (11 loại) ─────────────
    "poster":              ["Poster in hình", "Tranh in giấy ảnh cao cấp", "Poster trang trí in họa tiết"],
    "poster_framed":       ["Poster có khung gỗ", "Tranh in có khung", "Poster khung gỗ in hình"],
    "canvas":              ["Tranh canvas in hình", "Canvas print in họa tiết", "Tranh in canvas cao cấp"],
    "canvas_multi":        ["Bộ tranh canvas nhiều tấm", "Set tranh canvas in hình", "Combo tranh canvas in họa tiết"],
    "metal_print":         ["Tranh kim loại in hình", "Metal print in họa tiết", "Tranh nhôm in ảnh"],
    "wood_print":          ["Tranh gỗ in hình", "Wood print in họa tiết", "Tranh in trên gỗ tự nhiên"],
    "acrylic_print":       ["Tranh acrylic in hình", "Tranh mica in họa tiết", "Acrylic print in ảnh"],
    "wall_clock":          ["Đồng hồ treo tường in hình", "Wall clock in họa tiết", "Đồng hồ tường in ảnh"],
    "tapestry":            ["Thảm treo tường in hình", "Tapestry in họa tiết", "Thảm vải treo tường in ảnh"],
    "wall_decal":          ["Decal dán tường in hình", "Sticker tường in họa tiết", "Hình dán tường in ảnh"],
    "door_sign":           ["Bảng gỗ treo cửa in hình", "Door sign in họa tiết", "Bảng treo cửa khắc laser"],

    # ── Nhóm túi (10 loại) ─────────────────────────────────
    "tote":                ["Túi tote canvas", "Tote bag canvas in hình", "Túi vải canvas in họa tiết"],
    "tote_zip":            ["Túi tote có khoá kéo", "Tote zip in hình", "Túi vải zip in họa tiết"],
    "drawstring":          ["Túi dây rút in hình", "Túi rút in họa tiết", "Drawstring bag in logo"],
    "backpack":            ["Balo in hình", "Ba lô canvas in họa tiết", "Balo học sinh in ảnh"],
    "crossbody":           ["Túi đeo chéo in hình", "Crossbody bag in họa tiết", "Túi vai in ảnh"],
    "cosmetic_bag":        ["Túi mỹ phẩm in hình", "Cosmetic bag in họa tiết", "Túi make-up in ảnh"],
    "laptop_sleeve":       ["Túi đựng laptop in hình", "Laptop sleeve in họa tiết", "Túi chống sốc laptop in ảnh"],
    "lunch_bag":           ["Túi giữ nhiệt in hình", "Lunch bag in họa tiết", "Túi cơm giữ nhiệt in ảnh"],
    "luggage_tag":         ["Thẻ hành lý in hình", "Luggage tag in họa tiết", "Thẻ vali in tên"],
    "shoe_bag":            ["Túi đựng giày in hình", "Shoe bag in họa tiết", "Túi giày in ảnh"],

    # ── Nhóm phụ kiện công nghệ (10 loại) ──────────────────
    "phonecase_hard":      ["Ốp điện thoại cứng in hình", "Hard case in họa tiết", "Ốp lưng cứng in ảnh"],
    "phonecase_soft":      ["Ốp điện thoại dẻo in hình", "Soft case in họa tiết", "Ốp lưng silicon in ảnh"],
    "phonecase_wallet":    ["Ốp điện thoại có ví in hình", "Wallet case in họa tiết", "Flip case in ảnh"],
    "tablet_case":         ["Ốp máy tính bảng in hình", "Tablet case in họa tiết", "Bao iPad in ảnh"],
    "mousepad":            ["Bàn di chuột in hình", "Mousepad in họa tiết", "Pad chuột in ảnh"],
    "deskmat":             ["Bàn di chuột dài in hình", "Deskmat in họa tiết", "Thảm bàn phím in ảnh"],
    "laptop_sticker":      ["Miếng dán laptop in hình", "Skin laptop in họa tiết", "Decal laptop in ảnh"],
    "powerbank":           ["Sạc dự phòng in hình", "Pin dự phòng in logo", "Powerbank in họa tiết"],
    "bt_speaker":          ["Loa bluetooth in hình", "Loa mini in họa tiết", "Bluetooth speaker in logo"],
    "earbud_case":         ["Ốp hộp tai nghe in hình", "Case airpods in họa tiết", "Hộp tai nghe in ảnh"],

    # ── Nhóm phụ kiện cá nhân (22 loại) ────────────────────
    "keychain_metal":      ["Móc khoá kim loại khắc tên", "Keychain inox in hình", "Móc chìa khoá kim loại in laser"],
    "keychain_acrylic":    ["Móc khoá acrylic in hình", "Keychain mica in họa tiết", "Móc chìa khoá acrylic in ảnh"],
    "pin_badge":           ["Huy hiệu cài áo in hình", "Pin badge in họa tiết", "Ghim áo in ảnh"],
    "sticker":             ["Sticker in hình", "Tem dán in họa tiết", "Sticker vinyl in ảnh"],
    "sticker_pack":        ["Bộ sticker in hình", "Pack sticker in họa tiết", "Set tem dán in ảnh"],
    "cap":                 ["Nón lưỡi trai in hình", "Mũ snapback in logo", "Cap in họa tiết"],
    "bucket_hat":          ["Nón bucket in hình", "Mũ vành tròn in họa tiết", "Bucket hat in ảnh"],
    "beanie":              ["Nón len in hình", "Beanie in họa tiết", "Mũ len thêu hình"],
    "headband":            ["Băng đô in hình", "Headband in họa tiết", "Turban in ảnh"],
    "face_mask":           ["Khẩu trang vải in hình", "Mask in họa tiết", "Khẩu trang cotton in ảnh"],
    "scarf":               ["Khăn quàng cổ in hình", "Khăn len in họa tiết", "Scarf in ảnh"],
    "socks":               ["Tất in hình", "Vớ in họa tiết", "Tất cotton in ảnh"],
    "gloves":              ["Găng tay in hình", "Gloves in họa tiết", "Găng tay len in ảnh"],
    "belt":                ["Thắt lưng in hình", "Dây nịt in họa tiết", "Belt in logo"],
    "slippers":            ["Dép lê in hình", "Dép đi trong nhà in họa tiết", "Slippers in ảnh"],
    "sneakers":            ["Giày sneaker in hình", "Sneaker in họa tiết", "Giày canvas in ảnh"],
    "umbrella":            ["Ô dù in hình", "Dù che nắng in họa tiết", "Ô in ảnh"],
    "sunglasses":          ["Kính râm in logo", "Kính mát in họa tiết", "Sunglasses có in"],
    "watch":               ["Đồng hồ đeo tay in hình", "Watch in họa tiết", "Đồng hồ khắc tên"],
    "bracelet":            ["Vòng tay in hình", "Bracelet in họa tiết", "Vòng đeo tay khắc tên"],
    "lanyard":             ["Dây đeo thẻ in hình", "Lanyard in logo", "Dây thẻ in họa tiết"],
    "wallet":              ["Ví in hình", "Wallet in họa tiết", "Ví da in logo"],

    # ── Nhóm nhà cửa (17 loại) ─────────────────────────────
    "pillow_cover":        ["Vỏ gối in hình", "Áo gối in họa tiết", "Pillowcase in ảnh"],
    "pillow_full":         ["Gối tựa in hình", "Gối ôm in họa tiết", "Cushion in ảnh"],
    "blanket_fleece":      ["Chăn fleece in hình", "Chăn lông cừu in họa tiết", "Blanket fleece in ảnh"],
    "blanket_sherpa":      ["Chăn sherpa in hình", "Chăn hai lớp in họa tiết", "Sherpa blanket in ảnh"],
    "bath_towel":          ["Khăn tắm in hình", "Bath towel in họa tiết", "Khăn bông in ảnh"],
    "hand_towel":          ["Khăn mặt in hình", "Hand towel in họa tiết", "Khăn nhỏ in ảnh"],
    "doormat":             ["Thảm chùi chân in hình", "Doormat in họa tiết", "Thảm cửa in ảnh"],
    "area_rug":            ["Thảm trải sàn in hình", "Area rug in họa tiết", "Thảm sàn in ảnh"],
    "shower_curtain":      ["Rèm phòng tắm in hình", "Shower curtain in họa tiết", "Màn tắm in ảnh"],
    "tablecloth":          ["Khăn trải bàn in hình", "Tablecloth in họa tiết", "Khăn bàn in ảnh"],
    "apron":               ["Tạp dề in hình", "Apron in họa tiết", "Tạp dề bếp in ảnh"],
    "oven_mitt":           ["Găng tay lò nướng in hình", "Oven mitt in họa tiết", "Găng lò vi sóng in ảnh"],
    "cutting_board":       ["Thớt gỗ in hình", "Cutting board in họa tiết", "Thớt khắc laser"],
    "pen_holder":          ["Hộp đựng bút in hình", "Pen holder in họa tiết", "Lọ cắm bút in ảnh"],
    "night_light":         ["Đèn ngủ in hình", "Night light in họa tiết", "Đèn trang trí in ảnh"],
    "plant_pot":           ["Chậu cây in hình", "Plant pot in họa tiết", "Chậu trồng cây in ảnh"],
    "candle":              ["Nến thơm nhãn in hình", "Scented candle in họa tiết", "Nến in ảnh"],

    # ── Nhóm văn phòng phẩm (12 loại) ──────────────────────
    "notebook_hard":       ["Sổ tay bìa cứng in hình", "Notebook bìa cứng in họa tiết", "Sổ ghi bìa cứng in ảnh"],
    "notebook_soft":       ["Sổ tay bìa mềm in hình", "Notebook bìa mềm in họa tiết", "Sổ ghi bìa mềm in ảnh"],
    "spiral_notebook":     ["Sổ lò xo in hình", "Spiral notebook in họa tiết", "Vở lò xo in ảnh"],
    "planner":             ["Sổ kế hoạch in hình", "Planner in họa tiết", "Agenda in ảnh"],
    "desk_calendar":       ["Lịch để bàn in hình", "Desk calendar in họa tiết", "Lịch bàn in ảnh"],
    "wall_calendar":       ["Lịch treo tường in hình", "Wall calendar in họa tiết", "Lịch tường in ảnh"],
    "greeting_card":       ["Thiệp chúc mừng in hình", "Greeting card in họa tiết", "Card thiệp in ảnh"],
    "postcard":            ["Bưu thiếp in hình", "Postcard in họa tiết", "Card du lịch in ảnh"],
    "pen":                 ["Bút in logo", "Pen in họa tiết", "Bút viết in hình"],
    "bookmark":            ["Bookmark in hình", "Đánh dấu sách in họa tiết", "Thẻ đánh dấu in ảnh"],
    "file_folder":         ["Kẹp file in hình", "File folder in họa tiết", "Bìa hồ sơ in ảnh"],
    "sticky_note":         ["Giấy note in hình", "Sticky note in họa tiết", "Giấy dán in ảnh"],

    # ── Nhóm thú cưng (6 loại) ─────────────────────────────
    "pet_bowl":            ["Bát ăn thú cưng in hình", "Pet bowl in họa tiết", "Bát chó mèo in ảnh"],
    "pet_collar":          ["Vòng cổ thú cưng in hình", "Pet collar in họa tiết", "Vòng cổ chó mèo in ảnh"],
    "pet_leash":           ["Dây dắt thú cưng in hình", "Pet leash in họa tiết", "Dây xích chó in ảnh"],
    "pet_shirt":           ["Áo thú cưng in hình", "Pet shirt in họa tiết", "Áo chó mèo in ảnh"],
    "pet_bed":             ["Thảm nằm thú cưng in hình", "Pet bed in họa tiết", "Thảm ngủ chó mèo in ảnh"],
    "pet_tag":             ["Thẻ tên thú cưng in hình", "Pet tag in họa tiết", "Bảng tên chó mèo khắc laser"],

    # ── Nhóm thể thao (5 loại) ─────────────────────────────
    "yoga_mat":            ["Thảm yoga in hình", "Yoga mat in họa tiết", "Thảm tập yoga in ảnh"],
    "sport_bottle":        ["Bình thể thao in hình", "Sport bottle in họa tiết", "Bình nước gym in logo"],
    "sport_towel":         ["Khăn thể thao in hình", "Sport towel in họa tiết", "Khăn gym in logo"],
    "gym_bag":             ["Túi gym in hình", "Gym bag in họa tiết", "Túi thể thao in logo"],
    "camp_chair":          ["Ghế xếp in hình", "Camp chair in logo", "Ghế dã ngoại in họa tiết"],
}

# ============================================================
# DANH SÁCH 2 — DỊP VÀ CHỦ ĐỀ
# Khớp với cột `topic` trong bảng tag_keyword_map và config.py
# Mỗi dịp 2-3 cách viết khác nhau.
# ============================================================

OCCASIONS: dict[str, list[str]] = {
    "tet":           ["Tết 2027", "dịp Tết Nguyên Đán", "quà tặng Tết"],
    "womens_day":    ["ngày 8/3", "Ngày Quốc tế Phụ nữ", "quà tặng 8/3"],
    "vn_womens_day": ["ngày 20/10", "Ngày Phụ nữ Việt Nam", "quà tặng mẹ 20/10"],
    "teachers_day":  ["20/11", "Ngày Nhà giáo Việt Nam", "quà tặng thầy cô"],
    "christmas":     ["Giáng sinh", "Noel 2026", "quà tặng Giáng sinh"],
    "new_year":      ["dịp Năm mới 2027", "đón năm mới", "quà tặng cuối năm"],
    "valentine":     ["Valentine 14/2", "Ngày lễ tình nhân", "quà tặng người yêu"],
    "wedding":       ["quà cưới", "dịp đám cưới", "kỷ niệm ngày cưới"],
    "housewarming":  ["tân gia", "quà tặng nhà mới", "khai trương"],
    "graduation":    ["tốt nghiệp", "dịp ra trường", "quà tặng tốt nghiệp"],
    "birthday":      ["sinh nhật", "quà tặng sinh nhật", "mừng sinh nhật"],
    "friendship":    ["tặng bạn thân", "tình bạn", "quà cho người thân"],
    "back_to_school":["khai giảng", "dịp tựu trường", "quà tặng đầu năm học"],
    "mid_autumn":    ["Trung thu", "rằm tháng 8", "Tết Trung thu"],
    "hung_kings":    ["Giỗ tổ Hùng Vương", "lễ hội truyền thống", "10/3 âm lịch"],
    "lib_day":       ["30/4", "ngày Giải phóng miền Nam", "quà lưu niệm 30/4"],
    "labor_day":     ["1/5", "Ngày Quốc tế Lao động", "quà 1/5"],
    "national_day":  ["2/9", "Ngày Quốc khánh", "quà lưu niệm 2/9"],
    "anime":         ["chủ đề anime Nhật Bản", "phong cách anime", "nhân vật anime"],
    "kpop":          ["chủ đề Kpop", "fan Kpop", "phong cách Hàn Quốc"],
    "streetwear":    ["phong cách streetwear", "thời trang đường phố", "phong cách urban"],
    "vintage":       ["phong cách vintage", "retro cổ điển", "phong cách xưa"],
    "nature":        ["thiên nhiên", "chủ đề hoa lá", "phong cách botanical"],
    "sport":         ["thể thao", "tinh thần thể thao", "đội bóng yêu thích"],
    "travel":        ["du lịch", "quà lưu niệm", "chủ đề khám phá"],
    "zodiac":        ["12 con giáp", "cung hoàng đạo", "chủ đề thiên văn"],
    "cat_lover":     ["yêu mèo", "chủ đề mèo", "hội mèo cute"],
    "dog_lover":     ["yêu chó", "chủ đề cún", "hội chó cute"],
    "minimalist":    ["tối giản", "phong cách minimalist", "thiết kế đơn giản"],
    "local_pride":   ["tự hào Việt Nam", "made in Vietnam", "tinh thần Việt"],
    "office":        ["văn phòng", "quà tặng đồng nghiệp", "dịp họp mặt công ty"],
    "couple":        ["cặp đôi", "quà đôi", "quà tặng nửa kia"],
    "family":        ["gia đình", "quà tặng cả nhà", "dịp sum họp"],
    "group":         ["nhóm bạn", "áo lớp", "đồng phục nhóm"],
}

# ============================================================
# DANH SÁCH 3 — ĐIỂM NHẤN SẢN PHẨM (14 cụm)
# ============================================================

HIGHLIGHTS: list[str] = [
    "in hình",
    "form rộng",
    "chất cotton 100%",
    "in theo yêu cầu",
    "phong cách vintage",
    "thiết kế độc quyền",
    "vải mềm mát",
    "in chuyển nhiệt bền màu",
    "thêu tay tinh xảo",
    "in UV sắc nét",
    "hoạ tiết phiên bản giới hạn",
    "in cả hai mặt",
    "khắc laser tỉ mỉ",
    "bản phối màu độc quyền",
]

# ============================================================
# DANH SÁCH 4 — TÊN THIẾT KẾ / BỘ SƯU TẬP (28 cái)
# ============================================================

DESIGN_NAMES: list[str] = [
    "Mèo May Mắn",
    "Hoa Đào Xuân",
    "Rồng Việt",
    "Hoạ tiết Hoa Cúc",
    "Bản đồ Việt Nam",
    "Chibi Dễ Thương",
    "Anime Nhật Bản",
    "Thư Pháp Cổ Điển",
    "Xương Rồng Xanh",
    "Hoa Sen Vàng",
    "Nàng Thơ Retro",
    "Phố Cổ Hà Nội",
    "Phong Cảnh Hội An",
    "Con Trâu Vàng",
    "Galaxy Tím Ngắt",
    "Sóng Biển Đà Nẵng",
    "Mặt Trời Lặn Phú Quốc",
    "Lá Thu Vàng",
    "Hổ Dũng Mãnh",
    "Koi Đỏ May Mắn",
    "Cánh Bướm Kỳ Diệu",
    "Đồng Lúa Xanh",
    "Ngọn Núi Huyền Bí",
    "Cây Tre Việt Nam",
    "Mây Trắng Thanh Bình",
    "Pháo Hoa Rực Rỡ",
    "Sắc Màu Lễ Hội",
    "Tứ Linh Việt",
]

# ============================================================
# DANH SÁCH 5 — MẪU MÔ TẢ (8 mẫu, 80-200 từ/mẫu)
# {product} → tên loại sản phẩm cụ thể
# Đủ 4 thứ bắt buộc: chất liệu · size · cách in · bảo quản
# ============================================================

DESCRIPTION_TEMPLATES: list[str] = [
    # Mẫu 1: Áo thun
    (
        "{product} chất cotton 100%, vải mềm, thấm hút mồ hôi tốt, phù hợp mặc hằng ngày và đi chơi. "
        "Hình in bằng công nghệ in chuyển nhiệt, màu lên chuẩn, bền màu sau nhiều lần giặt. "
        "Có đủ size từ S đến 2XL, form rộng thoải mái, nam nữ mặc đều đẹp. "
        "Sản phẩm được in theo đơn nên thời gian chuẩn bị hàng từ 2 đến 3 ngày làm việc. "
        "Hướng dẫn bảo quản: giặt bằng nước lạnh, lộn trái khi giặt và khi phơi, "
        "không dùng chất tẩy mạnh, không là trực tiếp lên hình in."
    ),
    # Mẫu 2: Cốc sứ
    (
        "{product} chất sứ cao cấp, dày dặn, giữ nhiệt tốt và không thấm mùi. "
        "Hình in bằng công nghệ in nhiệt nung trong lò, màu bám chắc vào men sứ, "
        "không bong tróc dù rửa nhiều lần. "
        "Dung tích phù hợp cho cà phê, trà hoặc nước trái cây. "
        "Có thể in tên hoặc hình theo yêu cầu riêng, thời gian xử lý đơn từ 1 đến 2 ngày làm việc. "
        "Hướng dẫn bảo quản: rửa tay bằng xà phòng nhẹ và nước không quá nóng, "
        "tránh cho vào máy rửa bát và lò vi sóng để giữ màu in đẹp lâu dài."
    ),
    # Mẫu 3: Túi tote / balo
    (
        "{product} chất vải canvas dày, chịu tải tốt, thích hợp đựng sách, laptop và đồ dùng hằng ngày. "
        "Hình in bằng công nghệ in lụa cho nét sắc bén, màu sắc sống động và trung thực. "
        "Quai xách dài chắc chắn, có thể đeo tay hoặc vắt vai. "
        "Không có kích thước riêng theo người, phù hợp mọi vóc dáng. "
        "Lý tưởng đi học, đi chợ, đi làm hoặc làm quà tặng có ý nghĩa. "
        "Hướng dẫn bảo quản: giặt tay bằng nước lạnh, không vắt mạnh, phơi nơi thoáng mát tránh nắng gắt."
    ),
    # Mẫu 4: Poster / tranh canvas
    (
        "{product} in trên chất liệu giấy ảnh cao cấp hoặc canvas bền chắc, "
        "màu sắc trung thực, độ phân giải cao không bị vỡ hạt khi phóng to. "
        "Phù hợp trang trí phòng ngủ, phòng khách, quán cà phê hoặc làm quà tặng ý nghĩa. "
        "Có sẵn các khổ A4, A3, A2 và có thể đặt kích thước tuỳ chọn số lượng lớn. "
        "Thời gian in và giao hàng từ 2 đến 4 ngày làm việc tuỳ khổ in. "
        "Hướng dẫn bảo quản: treo nơi không bị ánh nắng trực tiếp chiếu vào, "
        "tránh ẩm ướt để màu in giữ đẹp theo năm tháng."
    ),
    # Mẫu 5: Móc khoá / phụ kiện nhỏ
    (
        "{product} chất liệu cao cấp, nhẹ, bền theo thời gian và không gỉ. "
        "Hình in hoặc khắc laser tỉ mỉ, sắc nét và giữ nguyên chất lượng dù dùng lâu. "
        "Kích thước nhỏ gọn, dễ gắn vào chìa khoá, balo, túi xách hoặc móc trên xe. "
        "Có thể khắc tên hoặc in theo yêu cầu, phù hợp làm quà tặng cá nhân hoá đặc biệt. "
        "Thời gian xử lý đơn 1 đến 2 ngày. "
        "Hướng dẫn bảo quản: lau bằng khăn mềm khô, tránh tiếp xúc với hoá chất tẩy rửa mạnh."
    ),
    # Mẫu 6: Hoodie / áo nỉ
    (
        "{product} chất nỉ bông dày dặn hai lớp, giữ ấm tốt và co giãn thoải mái. "
        "Hình in bằng công nghệ DTF (Direct to Film), màu lên đẹp, "
        "chi tiết sắc nét và bền sau nhiều lần giặt máy. "
        "Có size từ S đến 3XL, form oversize unisex phù hợp với nhiều vóc dáng. "
        "Mũ hai lớp chắn gió, túi kangaroo tiện lợi. "
        "Hướng dẫn bảo quản: giặt máy chế độ nhẹ, nước lạnh dưới 30°C, "
        "lộn trái trước khi giặt, phơi bóng mát, không sấy nhiệt cao."
    ),
    # Mẫu 7: Sticker / decal
    (
        "{product} in bằng mực UV bền nước, chống trầy xước và chịu được tia UV từ ánh nắng. "
        "Chất liệu vinyl cao cấp, keo dính tốt nhưng không để lại vết bẩn khi tháo ra ở bề mặt phẳng. "
        "Phù hợp dán lên laptop, bình nước, điện thoại, mũ bảo hiểm hoặc vali. "
        "Các mẫu được cắt theo đường viền hình, sắc nét và chuyên nghiệp. "
        "Có thể đặt số lượng lớn theo thiết kế riêng. "
        "Không có hướng dẫn giặt giũ, bảo quản bằng cách tránh để nước ngâm kéo dài."
    ),
    # Mẫu 8: Gối / vỏ gối / đồ nội thất
    (
        "{product} chất liệu vải cotton mềm mịn, không gây kích ứng da khi tiếp xúc lâu. "
        "Hình in bằng công nghệ in thăng hoa nhiệt độ cao, màu sắc sống động, "
        "không bong tróc hay phai màu sau nhiều lần giặt. "
        "Kích thước chuẩn, phù hợp với nhiều loại ruột gối phổ biến trên thị trường. "
        "Phù hợp trang trí sofa, giường ngủ hoặc làm quà tặng nhà mới, quà cưới ý nghĩa. "
        "Hướng dẫn bảo quản: giặt máy chế độ nhẹ, nước lạnh, "
        "không dùng chất tẩy mạnh, phơi bóng mát tránh ánh nắng trực tiếp."
    ),
]

# ============================================================
# HÀM CHÍNH
# ============================================================

GROUP_MAP = {
    "apparel_top": [
        "tshirt_unisex", "tshirt_men", "tshirt_women", "tshirt_kids",
        "tshirt_longsleeve", "tshirt_oversize", "tshirt_organic",
        "tanktop_men", "tanktop_women", "croptop", "polo", "hoodie",
        "hoodie_zip", "hoodie_kids", "sweatshirt", "crewneck",
        "jacket_windbreaker", "jacket_bomber", "cardigan", "shirt",
        "jersey", "sportshirt", "baby_bodysuit", "baby_bib", "poncho"
    ],
    "apparel_bottom": ["jogger", "shorts", "legging", "swim_trunks", "skirt", "dress", "bikini", "pyjama_set"],
    "drinkware": [
        "mug_11oz", "mug_15oz", "mug_colorchange", "mug_lid", "mug_espresso", 
        "glass", "tumbler", "tumbler_straw", "bottle_sport", "wine_glass", "beer_mug", "coaster"
    ],
    "wallart": [
        "poster", "poster_framed", "canvas", "canvas_multi", "metal_print", 
        "wood_print", "acrylic_print", "wall_clock", "tapestry", "wall_decal", "door_sign"
    ],
    "bag": ["tote", "tote_zip", "drawstring", "backpack", "crossbody", "cosmetic_bag", "laptop_sleeve", "lunch_bag", "luggage_tag", "shoe_bag"],
    "tech": ["phonecase_hard", "phonecase_soft", "phonecase_wallet", "tablet_case", "mousepad", "deskmat", "laptop_sticker", "powerbank", "bt_speaker", "earbud_case"],
    "accessory": [
        "keychain_metal", "keychain_acrylic", "pin_badge", "sticker", "sticker_pack", 
        "cap", "bucket_hat", "beanie", "headband", "face_mask", 
        "scarf", "socks", "gloves", "belt", "slippers", "sneakers", 
        "umbrella", "sunglasses", "watch", "bracelet", "lanyard", "wallet"
    ],
    "home": [
        "pillow_cover", "pillow_full", "blanket_fleece", "blanket_sherpa", 
        "bath_towel", "hand_towel", "doormat", "area_rug", 
        "shower_curtain", "tablecloth", "apron", "oven_mitt", 
        "cutting_board", "pen_holder", "night_light", "plant_pot", "candle"
    ],
    "stationery": [
        "notebook_hard", "notebook_soft", "spiral_notebook", "planner", 
        "desk_calendar", "wall_calendar", "greeting_card", "postcard", 
        "pen", "bookmark", "file_folder", "sticky_note"
    ],
    "pet": ["pet_bowl", "pet_collar", "pet_leash", "pet_shirt", "pet_bed", "pet_tag"],
    "sport": ["yoga_mat", "sport_bottle", "sport_towel", "gym_bag", "camp_chair"],
}

TYPE_TO_GROUP = {}
for g, types in GROUP_MAP.items():
    for t in types:
        TYPE_TO_GROUP[t] = g

HIGHLIGHTS_BY_GROUP = {
    "apparel_top": [
        "form rộng", "chất cotton 100%", "in theo yêu cầu", "phong cách vintage", 
        "thiết kế độc quyền", "vải mềm mát", "thêu tay tinh xảo", 
        "hoạ tiết phiên bản giới hạn", "in cả hai mặt", "bản phối màu độc quyền"
    ],
    "apparel_bottom": [
        "form rộng", "in theo yêu cầu", "phong cách vintage", "thiết kế độc quyền", 
        "vải mềm mát", "thêu tay tinh xảo", "hoạ tiết phiên bản giới hạn", 
        "bản phối màu độc quyền"
    ],
    "drinkware": [
        "giữ nhiệt tốt", "chất sứ cao cấp", "in theo yêu cầu", "phong cách vintage", 
        "thiết kế độc quyền", "độc lạ độc đáo", "hoạ tiết phiên bản giới hạn", 
        "bản phối màu độc quyền"
    ],
    "wallart": [
        "giấy ảnh cao cấp", "khung gỗ tự nhiên", "in theo yêu cầu", "phong cách nghệ thuật", 
        "thiết kế độc quyền", "in UV sắc nét", "hoạ tiết phiên bản giới hạn", 
        "bản phối màu độc quyền"
    ],
    "bag": [
        "vải canvas dày", "khóa kéo chắc chắn", "in theo yêu cầu", "phong cách thời trang", 
        "thiết kế độc quyền", "tiện lợi đi học đi chơi", "hoạ tiết phiên bản giới hạn", 
        "bản phối màu độc quyền"
    ],
    "tech": [
        "chống sốc ôm máy", "nhôm sơn tĩnh điện", "in theo yêu cầu", "phong cách hiện đại", 
        "thiết kế độc quyền", "in UV sắc nét", "hoạ tiết phiên bản giới hạn", 
        "bản phối màu độc quyền"
    ],
    "accessory": [
        "acrylic chống xước", "inox mạ chống gỉ", "in theo yêu cầu", "phong cách cá tính", 
        "thiết kế độc quyền", "in UV sắc nét", "hoạ tiết phiên bản giới hạn", 
        "bản phối màu độc quyền", "khắc laser tỉ mỉ"
    ],
    "home": [
        "vải cotton mềm mịn", "chăn lông cừu ấm áp", "in theo yêu cầu", 
        "thiết kế độc quyền", "hoạ tiết phiên bản giới hạn", "bản phối màu độc quyền"
    ],
    "stationery": [
        "giấy chống lóa", "bìa cứng chắc chắn", "in theo yêu cầu", "thiết kế độc quyền", 
        "hoạ tiết phiên bản giới hạn", "bản phối màu độc quyền"
    ],
    "pet": [
        "chất liệu an toàn", "in theo yêu cầu", "thiết kế độc quyền", 
        "dễ thương đáng yêu", "hoạ tiết phiên bản giới hạn"
    ],
    "sport": [
        "chống trơn trượt", "thấm hút mồ hôi", "in theo yêu cầu", "thiết kế độc quyền", 
        "tinh thần thể thao", "hoạ tiết phiên bản giới hạn"
    ],
}

TEMPLATES_BY_GROUP = {
    "apparel_top": [
        (
            "{product} chất cotton 100%, vải mềm, thấm hút mồ hôi tốt, phù hợp mặc hằng ngày và đi chơi. "
            "Hình in bằng công nghệ in chuyển nhiệt, màu lên chuẩn, bền màu sau nhiều lần giặt. "
            "Có đủ size từ S đến 3XL, form rộng thoải mái, nam nữ mặc đều đẹp. "
            "Sản phẩm được in theo đơn nên thời gian chuẩn bị hàng từ 2 đến 3 ngày làm việc. "
            "Hướng dẫn bảo quản: giặt bằng nước lạnh, lộn trái khi giặt và khi phơi, "
            "không dùng chất tẩy mạnh, không là trực tiếp lên hình in."
        ),
        (
            "{product} chất nỉ bông dày dặn hai lớp, giữ ấm tốt và co giãn thoải mái. "
            "Hình in bằng công nghệ DTF (Direct to Film), màu lên đẹp, "
            "chi tiết sắc nét và bền sau nhiều lần giặt máy. "
            "Có size từ S đến 3XL, form oversize unisex phù hợp với nhiều vóc dáng. "
            "Mũ hai lớp chắn gió, túi kangaroo tiện lợi. "
            "Hướng dẫn bảo quản: giặt máy chế độ nhẹ, nước lạnh dưới 30°C, "
            "lộn trái trước khi giặt, phơi bóng mát, không sấy nhiệt cao."
        )
    ],
    "apparel_bottom": [
        (
            "{product} chất liệu thun nỉ hoặc cotton cao cấp, mềm mại và co giãn tốt, mang lại sự thoải mái tối đa cho người mặc. "
            "Đường may tỉ mỉ, chắc chắn, phù hợp cho mọi hoạt động thể thao hay đi chơi. "
            "Thiết kế hiện đại, trẻ trung, dễ dàng phối hợp với nhiều trang phục khác nhau. "
            "Sản phẩm được hoàn thiện tinh tế từng chi tiết để hướng đến trải nghiệm mặc tối ưu nhất. "
            "Có nhiều size lựa chọn từ S đến XXL. "
            "Hướng dẫn bảo quản: giặt tay hoặc giặt máy bằng nước lạnh, lộn trái sản phẩm khi giặt, "
            "tránh ánh nắng gay gắt trực tiếp."
        )
    ],
    "drinkware": [
        (
            "{product} chất sứ hoặc kim loại giữ nhiệt cao cấp, dày dặn, an toàn cho sức khỏe và không thấm mùi. "
            "Hình in bằng công nghệ hiện đại bền màu nung nhiệt độ cao, bám chắc không lo bong tróc dù rửa nhiều lần. "
            "Thiết kế đẹp mắt tiện lợi và dung tích phù hợp cho cà phê, trà hay các loại nước uống khác nhau. "
            "Thời gian xử lý in đơn hàng từ 1 đến 2 ngày làm việc. "
            "Hướng dẫn bảo quản: rửa nhẹ nhàng bằng nước rửa chén thông thường, tránh cọ xát sắt nhọn lên bề mặt hình in."
        )
    ],
    "wallart": [
        (
            "{product} in trên chất liệu giấy ảnh cao cấp hoặc canvas bền chắc, màu sắc trung thực, độ phân giải cao không bị vỡ hạt. "
            "Phù hợp trang trí phòng ngủ, phòng khách, quán cà phê hoặc làm quà tặng ý nghĩa. "
            "Có sẵn các khổ A4, A3, A2 và có thể đặt kích thước tuỳ chọn số lượng lớn. "
            "Thời gian in và giao hàng từ 2 đến 4 ngày làm việc tuỳ khổ in. "
            "Hướng dẫn bảo quản: treo nơi khô ráo thoáng mát, tránh ẩm ướt và ánh nắng trực tiếp chiếu vào để giữ màu lâu dài."
        )
    ],
    "bag": [
        (
            "{product} chất vải canvas hoặc polyester cao cấp chịu tải tốt, thích hợp đựng sách, laptop và đồ dùng hằng ngày. "
            "Hình in sắc nét sinh động bằng công nghệ hiện đại, bền đẹp không phai màu hay nứt vỡ khi giặt. "
            "Quai đeo chắc chắn êm ái, khoang chứa rộng rãi đáp ứng nhiều nhu cầu học tập, làm việc hay du lịch dã ngoại. "
            "Hướng dẫn bảo quản: giặt tay nhẹ nhàng bằng nước lạnh, không vắt mạnh, phơi nơi thoáng mát tránh ánh nắng gay gắt."
        )
    ],
    "tech": [
        (
            "{product} chất liệu nhựa cứng hoặc silicon cao cấp dẻo bảo vệ hoàn hảo cho phụ kiện công nghệ của bạn. "
            "Công nghệ in UV tiên tiến cho hình ảnh sắc nét, màu sắc tươi tắn và khó bong tróc hay bay màu. "
            "Các chi tiết hoàn thiện tỉ mỉ ôm sát máy vô cùng tinh tế và cá tính. "
            "Khớp nối chuẩn xác dễ tháo lắp. Thiết kế mỏng nhẹ không làm tăng đáng kể độ dày của thiết bị mà vẫn đem lại sự bảo vệ tối đa. "
            "Hướng dẫn bảo quản: lau chùi thường xuyên bằng vải mềm ẩm, tránh tiếp xúc gần nguồn nhiệt cao hay dung môi tẩy rửa."
        )
    ],
    "accessory": [
        (
            "{product} chất liệu chọn lọc cao cấp (mica acrylic, kim loại chống rỉ hoặc vải sợi chất lượng), sử dụng lâu dài bền đẹp. "
            "Hình ảnh in rõ nét chi tiết tạo dấu ấn cá tính thời trang đặc trưng riêng phù hợp làm quà tặng bạn bè thân thiết. "
            "Đồ dùng tiện dụng, nhỏ gọn dễ dàng kết hợp nâng tầm phong cách sống hằng ngày. "
            "Thiết kế nhỏ gọn, mang tính ứng dụng cao, dễ dàng mang theo bên người mọi lúc mọi nơi. "
            "Hướng dẫn bảo quản: lau sản phẩm bằng khăn khô mềm, cất giữ nơi khô ráo, tránh các chất tẩy rửa hóa học mạnh."
        )
    ],
    "home": [
        (
            "{product} chất liệu vải cotton hoặc fleece mềm mịn không gây kích ứng da, an toàn khi sử dụng lâu dài trong phòng ngủ phòng khách. "
            "Hình in thăng hoa sắc nét tràn viền không phai nhạt dù giặt nhiều lần. "
            "Mang đến cảm giác thư giãn thoải mái đồng thời trang trí nhà cửa thêm ấm cúng sinh động. "
            "Hướng dẫn bảo quản: giặt bằng tay hoặc giặt máy chế độ nhẹ, lộn bề trái hình in phơi bóng mát để màu sắc luôn bền đẹp."
        )
    ],
    "stationery": [
        (
            "{product} chất lượng giấy cao cấp chống lóa giúp viết trơn mượt không thấm nhòe mực, chống mỏi mắt tốt khi học tập làm việc. "
            "Bìa in sắc nét màu sắc tươi sáng mang cảm hứng sáng tạo tràn đầy. "
            "Lựa chọn tuyệt vời để làm quà tặng ghi chép hay lên kế hoạch. "
            "Sản phẩm đồng hành cùng bạn trên con đường chinh phục tri thức và công việc mỗi ngày. "
            "Hướng dẫn bảo quản: bảo quản nơi khô ráo không ẩm ướt, tránh gập nếp gãy góc sổ sách ảnh hưởng thẩm mỹ."
        )
    ],
    "pet": [
        (
            "{product} chất liệu an toàn mềm mại, thân thiện và thoải mái không gây cọ xát tổn thương da của cún miêu. "
            "Độ bền cao thích hợp hoạt động chạy nhảy vui chơi. "
            "Hình in sắc nét đáng yêu làm nổi bật cá tính cưng xỉu của bé. "
            "Hãy dành tặng cho thú cưng của bạn sự chăm sóc chu đáo tốt đẹp nhất bằng sản phẩm này. "
            "Hướng dẫn bảo quản: giặt sạch bằng tay hoặc túi giặt chế độ nhẹ với xà phòng trung tính, phơi khô ráo hoàn toàn trước khi dùng."
        )
    ],
    "sport": [
        (
            "{product} thiết kế chuyên dụng bền chắc cho các buổi luyện tập năng lượng. "
            "Chất liệu chống trơn trượt có đàn hồi cao chịu lực tốt nâng đỡ tuyệt vời. "
            "In ấn sắc sảo đẹp mắt tạo sự hứng khởi khi rèn luyện thể chất hằng ngày. "
            "Sản phẩm giúp tối ưu hóa hiệu suất luyện tập và mang đến nguồn cảm hứng vận động dồi dào. "
            "Hướng dẫn bảo quản: lau khô sau khi sử dụng bằng khăn ẩm sạch, cuộn gọn hoặc đặt cất giữ nơi khô thoáng."
        )
    ],
}

def _pick(lst: list) -> str:
    """Bốc ngẫu nhiên một phần tử."""
    return random.choice(lst)


def generate_product(
    product_type: str | None = None,
    topic: str | None = None,
) -> tuple[str, str]:
    # Loại sản phẩm
    if product_type is None:
        product_type = _pick(list(PRODUCT_TYPES.keys()))
    product_label = _pick(PRODUCT_TYPES[product_type])

    # Dịp / chủ đề
    if topic is None:
        topic = _pick(list(OCCASIONS.keys()))
    occasion_label = _pick(OCCASIONS[topic])

    # Dynamic highlight selection
    group = TYPE_TO_GROUP.get(product_type, "accessory")
    highlights = HIGHLIGHTS_BY_GROUP.get(group, ["thiết kế độc quyền"])
    
    # Avoid duplicate "in" words
    has_print_in_label = any(x in product_label.lower() for x in ["in hình", "in ảnh", "in logo", "in họa tiết", "in decal"])
    if has_print_in_label:
        highlights_filtered = [h for h in highlights if "in " not in h.lower()]
        if not highlights_filtered:
            highlights_filtered = highlights
    else:
        highlights_filtered = highlights
        
    highlight = _pick(highlights_filtered)

    # Ghép tên: [Loại SP] [Điểm nhấn] [Dịp] — [Tên thiết kế]
    name = f"{product_label} {highlight} {occasion_label} — {_pick(DESIGN_NAMES)}"

    # Mô tả theo nhóm
    templates = TEMPLATES_BY_GROUP.get(group, TEMPLATES_BY_GROUP["apparel_top"])
    description = _pick(templates).format(product=product_label)

    return name, description


def generate_batch(n: int = 200) -> list[tuple[str, str]]:
    """Sinh n cặp (tên, mô tả)."""
    return [generate_product() for _ in range(n)]


# ============================================================
# TỰ KIỂM — python name_generator.py
# ============================================================

def _word_count(text: str) -> int:
    return len(text.split())


def self_check(n: int = 200, sample: int = 20, seed: int | None = None) -> None:
    if seed is not None:
        random.seed(seed)

    print(f"\n{'='*62}")
    print(f"  VietCraft · name_generator.py · Tự kiểm ({n} mẫu)")
    print(f"{'='*62}\n")

    batch = generate_batch(n)
    names = [name for name, _ in batch]

    # Tiêu chí 1: In 20 tên ngẫu nhiên
    print(f"▶ {sample} tên ngẫu nhiên:\n")
    for name in random.sample(names, min(sample, len(names))):
        print(f"  • {name}")

    # Tiêu chí 2: Tỷ lệ tên trùng < 2 %
    counter = Counter(names)
    dups = sum(c - 1 for c in counter.values() if c > 1)
    rate = dups / n * 100
    print(f"\n▶ Tên trùng nhau: {dups}/{n} ({rate:.1f}%)", end="  ")
    print("✅ ĐẠT" if rate <= 2.0 else "❌ VƯỢT 2% — cần mở rộng danh sách")

    # Tiêu chí 3: Mô tả 80-200 từ
    wcs = [_word_count(desc) for _, desc in batch]
    mn, mx, avg = min(wcs), max(wcs), sum(wcs) / len(wcs)
    bad = [(i, w) for i, w in enumerate(wcs) if not (80 <= w <= 200)]
    print(f"\n▶ Độ dài mô tả: min={mn} · max={mx} · trung bình={avg:.0f} từ", end="  ")
    print("✅ ĐẠT" if not bad else f"❌ {len(bad)} mô tả ngoài khoảng 80-200 từ")

    # Tiêu chí 4: Đủ 138 loại
    total_types = len(PRODUCT_TYPES)
    print(f"\n▶ Số loại sản phẩm: {total_types}/138", end="  ")
    print("✅ ĐẠT" if total_types >= 138 else f"❌ Còn thiếu {138 - total_types} loại")

    # Thống kê nhóm
    group_map = {
        "apparel_top":    [k for k in PRODUCT_TYPES if k in (
            "tshirt_unisex","tshirt_men","tshirt_women","tshirt_kids",
            "tshirt_longsleeve","tshirt_oversize","tshirt_organic",
            "tanktop_men","tanktop_women","croptop","polo","hoodie",
            "hoodie_zip","hoodie_kids","sweatshirt","crewneck",
            "jacket_windbreaker","jacket_bomber","cardigan","shirt",
            "jersey","sportshirt","baby_bodysuit","baby_bib","poncho")],
        "apparel_bottom": ["jogger","shorts","legging","swim_trunks","skirt","dress","bikini","pyjama_set"],
        "drinkware":      ["mug_11oz","mug_15oz","mug_colorchange","mug_lid","mug_espresso","glass","tumbler","tumbler_straw","bottle_sport","wine_glass","beer_mug","coaster"],
        "wallart":        ["poster","poster_framed","canvas","canvas_multi","metal_print","wood_print","acrylic_print","wall_clock","tapestry","wall_decal","door_sign"],
        "bag":            ["tote","tote_zip","drawstring","backpack","crossbody","cosmetic_bag","laptop_sleeve","lunch_bag","luggage_tag","shoe_bag"],
        "tech":           ["phonecase_hard","phonecase_soft","phonecase_wallet","tablet_case","mousepad","deskmat","laptop_sticker","powerbank","bt_speaker","earbud_case"],
        "accessory":      ["keychain_metal","keychain_acrylic","pin_badge","sticker","sticker_pack","cap","bucket_hat","beanie","headband","face_mask","scarf","socks","gloves","belt","slippers","sneakers","umbrella","sunglasses","watch","bracelet","lanyard","wallet"],
        "home":           ["pillow_cover","pillow_full","blanket_fleece","blanket_sherpa","bath_towel","hand_towel","doormat","area_rug","shower_curtain","tablecloth","apron","oven_mitt","cutting_board","pen_holder","night_light","plant_pot","candle"],
        "stationery":     ["notebook_hard","notebook_soft","spiral_notebook","planner","desk_calendar","wall_calendar","greeting_card","postcard","pen","bookmark","file_folder","sticky_note"],
        "pet":            ["pet_bowl","pet_collar","pet_leash","pet_shirt","pet_bed","pet_tag"],
        "sport":          ["yoga_mat","sport_bottle","sport_towel","gym_bag","camp_chair"],
    }
    print(f"\n▶ Phân bổ theo 11 nhóm:")
    for grp, types in group_map.items():
        print(f"   {grp:<20} {len(types):3d} loại")
    total_in_groups = sum(len(v) for v in group_map.values())
    print(f"   {'TỔNG':<20} {total_in_groups:3d} loại")

    print(f"\n{'='*62}\n")


if __name__ == "__main__":
    self_check(n=200, sample=20)
