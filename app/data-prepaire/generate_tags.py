import re
import csv
import sys
import os

OFFICIAL_KEYWORDS = [
    "áo thun", "áo phông nam", "áo phông nữ", "in áo thun", "áo đôi",
    "áo nhóm", "áo lớp", "áo đồng phục", "áo gia đình", "túi tote",
    "tranh treo tường", "tranh canvas", "móc khóa", "áo tết", "quà tết",
    "lì xì tết", "trang trí tết", "quà 8/3", "quà tặng mẹ", "quà 20/10",
    "quà 20/11", "quà tặng thầy cô", "quà giáng sinh", "trang trí noel", "quà valentine",
    "quà tặng người yêu", "quà tặng", "quà cưới", "quà tân gia", "quà tặng bạn thân",
    "quà handmade", "quà lưu niệm", "áo anime", "áo oversize", "áo local brand",
    "áo vintage", "áo hoodie", "áo bóng đá việt nam", "áo thun thể thao", "quà sinh nhật"
]

TAG_MAPPINGS = [
    # 1. áo thun
    {"tag_id": "ao-thun", "name_vi": "Áo thun", "category_id": "apparel.evergreen", "source_keywords": "áo thun", 
     "aliases": "ao thun|ao phong|ao tee|tshirt|ao co tron|ao phong tron|ao thun nam nu"},
    {"tag_id": "ao-t-shirt", "name_vi": "Áo T-shirt", "category_id": "apparel.evergreen", "source_keywords": "áo thun", 
     "aliases": "ao t shirt|t-shirt|t shirt vao|ao co coc|ao tee thun|tshirt basic"},
     
    # 2. áo phông nam
    {"tag_id": "ao-phong-nam", "name_vi": "Áo phông nam", "category_id": "apparel.evergreen", "source_keywords": "áo phông nam", 
     "aliases": "ao phong nam|ao thun nam|men shirt|men tee|ao phong cho nam|ao phong basic nam"},
    {"tag_id": "fashion-nam", "name_vi": "Thời trang nam", "category_id": "apparel.evergreen", "source_keywords": "áo phông nam", 
     "aliases": "thoi trang nam|men fashion|clothes nam|do nam|style nam|menswear"},
     
    # 3. áo phông nữ
    {"tag_id": "ao-phong-nu", "name_vi": "Áo phông nữ", "category_id": "apparel.evergreen", "source_keywords": "áo phông nữ", 
     "aliases": "ao phong nu|ao thun nu|women shirt|women tee|ao phong cho nu|ao phong basic nu"},
    {"tag_id": "fashion-nu", "name_vi": "Thời trang nữ", "category_id": "apparel.evergreen", "source_keywords": "áo phông nữ", 
     "aliases": "thoi trang nu|women fashion|clothes nu|do nu|style nu|womenswear"},
     
    # 4. in áo thun
    {"tag_id": "in-ao-thun", "name_vi": "In áo thun", "category_id": "apparel.evergreen", "source_keywords": "in áo thun", 
     "aliases": "in ao thun|in ao phong|in ao|custom tee|in ao quang cao|dich vu in ao"},
    {"tag_id": "in-theo-yeu-cau", "name_vi": "In theo yêu cầu", "category_id": "apparel.evergreen", "source_keywords": "in áo thun", 
     "aliases": "in theo yeu cau|custom print|print on demand|in ao thiet ke|in lay ngay|in ao theo yeu cau"},
     
    # 5. áo đôi
    {"tag_id": "ao-doi", "name_vi": "Áo đôi", "category_id": "apparel.couple", "source_keywords": "áo đôi", 
     "aliases": "ao doi|couple tee|ao tinh nhan|ao thun cap|ao doi dep|ao doi thun"},
    {"tag_id": "ao-cap-doi", "name_vi": "Áo cặp đôi", "category_id": "apparel.couple", "source_keywords": "áo đôi", 
     "aliases": "ao cap doi|ao thun doi|ao thun cap doi|couple shirt|set ao doi|do doi nam nu"},
     
    # 6. áo nhóm
    {"tag_id": "ao-nhom", "name_vi": "Áo nhóm", "category_id": "apparel.group", "source_keywords": "áo nhóm", 
     "aliases": "ao nhom|group tee|ao dong doi|ao thun nhom|ao di bien|set ao nhom"},
    {"tag_id": "ao-team", "name_vi": "Áo team", "category_id": "apparel.group", "source_keywords": "áo nhóm", 
     "aliases": "ao team|ao team building|building tee|team shirt|ao thun team|ao team nhom"},
     
    # 7. áo lớp
    {"tag_id": "ao-lop", "name_vi": "Áo lớp", "category_id": "apparel.school", "source_keywords": "áo lớp", 
     "aliases": "ao lop|ao thun lop|class tee|ao dong phuc lop|ao nien khoa|ao lop dep"},
    {"tag_id": "ao-hoc-sinh", "name_vi": "Áo học sinh", "category_id": "apparel.school", "source_keywords": "áo lớp", 
     "aliases": "ao hoc sinh|ao dong phuc hoc sinh|ao hoc duong|ao thun hoc sinh|do hoc sinh|ao tee hoc sinh"},
     
    # 8. áo đồng phục
    {"tag_id": "ao-dong-phuc", "name_vi": "Áo đồng phục", "category_id": "apparel.school", "source_keywords": "áo đồng phục", 
     "aliases": "ao dong phuc|dong phuc cong ty|uniform|ao group|dong phuc ca nhan|ao thun uniform"},
     
    # 9. áo gia đình
    {"tag_id": "ao-gia-dinh", "name_vi": "Áo gia đình", "category_id": "apparel.family", "source_keywords": "áo gia đình", 
     "aliases": "ao gia dinh|ao thun gia dinh|family tee|set ao gia dinh|ao cho ca nha|ao thun ca nha"},
    {"tag_id": "family-set", "name_vi": "Set gia đình", "category_id": "apparel.family", "source_keywords": "áo gia đình", 
     "aliases": "family set|set do gia dinh|mat do gia dinh|set ao ca nha|do di bien gia dinh|set gia dinh dep"},
     
    # 10. túi tote
    {"tag_id": "tui-tote", "name_vi": "Túi tote", "category_id": "bag.evergreen", "source_keywords": "túi tote", 
     "aliases": "tui tote|tote bag|tui xach tote|tui vai tote|tui tote tron|tui tote in hinh"},
    {"tag_id": "tote-canvas", "name_vi": "Túi vải Canvas", "category_id": "bag.evergreen", "source_keywords": "túi tote", 
     "aliases": "tote canvas|tui canvas|tui vai canvas|canvas bag|tui vai bo|tui tote canvas dep"},
     
    # 11. tranh treo tường
    {"tag_id": "tranh-treo-tuong", "name_vi": "Tranh treo tường", "category_id": "wallart.evergreen", "source_keywords": "tranh treo tường", 
     "aliases": "tranh treo tuong|tranh phong canh|tranh treo|tranh phong khach|tranh phong ngu|wall art"},
    {"tag_id": "tranh-decor", "name_vi": "Tranh decor", "category_id": "wallart.evergreen", "source_keywords": "tranh treo tường", 
     "aliases": "tranh decor|tranh trang tri phong|decor art|tranh treo decor|khung anh decor|tranh thiet ke"},
     
    # 12. tranh canvas
    {"tag_id": "tranh-canvas", "name_vi": "Tranh Canvas", "category_id": "wallart.decor", "source_keywords": "tranh canvas", 
     "aliases": "tranh canvas|decor canvas|canvas print|tranh canvas bo|tranh canvas dep|canvas treo tuong"},
    {"tag_id": "decor-khong-gian", "name_vi": "Trang trí không gian", "category_id": "wallart.decor", "source_keywords": "tranh canvas", 
     "aliases": "decor khong gian|trang tri phong|nhieu khong gian|trang tri nha|decor co dien|space decor"},
     
    # 13. móc khóa
    {"tag_id": "moc-khoa", "name_vi": "Móc khóa", "category_id": "accessory.evergreen", "source_keywords": "móc khóa", 
     "aliases": "moc khoa|keychain|moc xich khoa|moc thoi trang|moc chia khoa|moc balo"},
    {"tag_id": "keychain", "name_vi": "Keychain", "category_id": "accessory.evergreen", "source_keywords": "móc khóa", 
     "aliases": "keychain ca nhan|moc khoa mica|acrylic keychain|moc khoa custom|keychain dep|moc khoa handmade"},
     
    # 14. áo tết
    {"tag_id": "ao-tet", "name_vi": "Áo Tết", "category_id": "apparel.tet", "source_keywords": "áo tết", 
     "aliases": "ao tet|ao thun tet|ao phong tet|ao dai cach tan|ao tet xuan|ao tet in hinh"},
    {"tag_id": "thoi-trang-tet", "name_vi": "Thời trang Tết", "category_id": "apparel.tet", "source_keywords": "áo tết", 
     "aliases": "thoi trang tet|do tet|vay tet|set do di choi tet|style tet|quan ao tet"},
     
    # 15. quà tết
    {"tag_id": "qua-tet", "name_vi": "Quà Tết", "category_id": "drinkware.tet", "source_keywords": "quà tết", 
     "aliases": "qua tet|qua mung nam moi|mung tuoi|qua tet y nghia|qua tang nam moi|tet gift"},
    {"tag_id": "set-qua-tet", "name_vi": "Set quà Tết", "category_id": "drinkware.tet", "source_keywords": "quà tết", 
     "aliases": "set qua tet|gio qua tet|hop qua tet|set qua tet sang trong|qua bieu tet|combo qua tet"},
     
    # 16. lì xì tết
    {"tag_id": "bao-li-xi", "name_vi": "Bao lì xì", "category_id": "accessory.tet", "source_keywords": "lì xì tết", 
     "aliases": "bao li xi|li xi do|lixi|bao li xi doc doc|phong bao li xi|li xi tet"},
    {"tag_id": "li-xi-tet", "name_vi": "Lì xì Tết", "category_id": "accessory.tet", "source_keywords": "lì xì tết", 
     "aliases": "li xi tet|mung tuoi tet|phong li xi|li xi hot|bao mung tuoi|lixi2027"},
     
    # 17. trang trí tết
    {"tag_id": "trang-tri-tet", "name_vi": "Trang trí Tết", "category_id": "wallart.tet", "source_keywords": "trang trí tết", 
     "aliases": "trang tri tet|trang tri xuan|decor tet|treo tet|phu kien tet|trang tri nha ngay tet"},
    {"tag_id": "decor-tet", "name_vi": "Decor Tết", "category_id": "wallart.tet", "source_keywords": "trang trí tết", 
     "aliases": "decor tet|trang tri nha ngay tet|do treo tet|tranh treo tet|tranh tet|decor xuan"},
     
    # 18. quà 8/3
    {"tag_id": "qua-8-3", "name_vi": "Quà 8/3", "category_id": "drinkware.womens_day", "source_keywords": "quà 8/3", 
     "aliases": "qua 8 3|qua quoc te phu nu|8/3 gift|qua tang 8/3|qua tang nu|qua 8 thang 3"},
    {"tag_id": "qua-tang-phu-nu", "name_vi": "Quà tặng Phụ nữ", "category_id": "drinkware.womens_day", "source_keywords": "quà 8/3", 
     "aliases": "qua tang phu nu|qua cho nu|qua nu gioi|qua tang phu nu viet nam|qua cho chi em|women gift"},
     
    # 19. quà tặng mẹ
    {"tag_id": "qua-tang-me", "name_vi": "Quà tặng mẹ", "category_id": "drinkware.womens_day", "source_keywords": "quà tặng mẹ", 
     "aliases": "qua tang me|qua vu lan|sinh nhat me|qua tang me yeu|bao hieu me|mother gift"},
    {"tag_id": "qua-hieu-thao", "name_vi": "Quà hiếu thảo", "category_id": "drinkware.womens_day", "source_keywords": "quà tặng mẹ", 
     "aliases": "qua hieu thao|qua bao hieu|mon qua gia dinh|qua cho cha me|qua chu dao|mon quan y nghia"},
     
    # 20. quà 20/10
    {"tag_id": "qua-20-10", "name_vi": "Quà 20/10", "category_id": "drinkware.womens_day", "source_keywords": "quà 20/10", 
     "aliases": "qua 20 10|qua phu nu viet nam|phu nu viet nam|qua tang 20/10|qua tang nu|20/10 gift"},
     
    # 21. quà 20/11
    {"tag_id": "qua-20-11", "name_vi": "Quà 20/11", "category_id": "stationery.teachers_day", "source_keywords": "quà 20/11", 
     "aliases": "qua 20 11|qua nha giao viet nam|20/11 gift|qua tang 20/11|qua thay co 20/11|teacher day"},
    {"tag_id": "qua-tang-thay-co", "name_vi": "Quà tặng thầy cô", "category_id": "stationery.teachers_day", "source_keywords": "quà 20/11", 
     "aliases": "qua tang thay co|qua thay co giao|tri an|qua bieu thay co|qua luu niem thay co|teacher gift"},
     
    # 22. quà tặng thầy cô
    {"tag_id": "tri-an-thay-co", "name_vi": "Tri ân thầy cô", "category_id": "stationery.teachers_day", "source_keywords": "quà tặng thầy cô", 
     "aliases": "tri an thay co|ton su trong dao|on thay co|tri an nha giao|qua tri an|tranh tri an"},
     
    # 23. quà giáng sinh
    {"tag_id": "qua-giang-sinh", "name_vi": "Quà Giáng sinh", "category_id": "drinkware.christmas", "source_keywords": "quà giáng sinh", 
     "aliases": "qua giang sinh|qua noel|giang sinh gift|christmas gift|noel gift|tang qua giang sinh"},
    {"tag_id": "qua-noel", "name_vi": "Quà Noel", "category_id": "drinkware.christmas", "source_keywords": "quà giáng sinh", 
     "aliases": "qua noel|tang noel|hop qua noel|set qua noel|qua thiet ke noel|quatanggiangsinh"},
     
    # 24. trang trí noel
    {"tag_id": "trang-tri-noel", "name_vi": "Trang trí Noel", "category_id": "wallart.christmas", "source_keywords": "trang trí noel", 
     "aliases": "trang tri noel|trang tri giang sinh|decor noel|phu kien noel|treo noel|tranh noel"},
    {"tag_id": "decor-noel", "name_vi": "Decor Noel", "category_id": "wallart.christmas", "source_keywords": "trang trí noel", 
     "aliases": "decor noel|decor giang sinh|phu kien noel|do trang tri noel|tranh giang sinh|noel decor"},
     
    # 25. quà valentine
    {"tag_id": "qua-valentine", "name_vi": "Quà Valentine", "category_id": "drinkware.valentine", "source_keywords": "quà valentine", 
     "aliases": "qua valentine|qua valentine 14 2|valentine gift|qua tinh nhan|qua le tinh nhan|qua tang valentine"},
    {"tag_id": "qua-le-tinh-nhan", "name_vi": "Quà Lễ tình nhân", "category_id": "drinkware.valentine", "source_keywords": "quà valentine", 
     "aliases": "qua le tinh nhan|qua 14 thang 2|qua tinh nhan|le tinh nhan gift|combo valentine|set valentine"},
     
    # 26. quà tặng người yêu
    {"tag_id": "qua-tang-nguoi-yeu", "name_vi": "Quà tặng người yêu", "category_id": "drinkware.valentine", "source_keywords": "quà tặng người yêu", 
     "aliases": "qua tang nguoi yeu|qua tang gau|qua cho ex|qua tinh yeu|qua valentine nguoi yeu|love gift"},
    {"tag_id": "qua-cho-gau", "name_vi": "Quà cho gấu", "category_id": "drinkware.valentine", "source_keywords": "quà tặng người yêu", 
     "aliases": "qua cho gau|qua tang nguoi thuong|qua crush|qua tang crush|qua tang gaulove|quachogau"},
     
    # 27. quà tặng
    {"tag_id": "qua-tang", "name_vi": "Quà tặng", "category_id": "stationery.gift", "source_keywords": "quà tặng", 
     "aliases": "qua tang|qua doc|quatang|quatangdoc|hop qua tang|gift shop"},
    {"tag_id": "gift-box", "name_vi": "Hộp quà", "category_id": "stationery.gift", "source_keywords": "quà tặng", 
     "aliases": "gift box|hop qua|hop qua tang|set qua tang|hop qua dep|hop carton qua"},
     
    # 28. quà cưới
    {"tag_id": "qua-cuoi", "name_vi": "Quà cưới", "category_id": "home.wedding", "source_keywords": "quà cưới", 
     "aliases": "qua cuoi|qua mung dam cuoi|wedding gift|qua cuoi thiet ke|qua mung cuoi|anniversary gift"},
    {"tag_id": "qua-ki-niem-ngay-cuoi", "name_vi": "Quà kỷ niệm ngày cưới", "category_id": "home.wedding", "source_keywords": "quà cưới", 
     "aliases": "qua ki niem ngay cuoi|ky niem ngay cuoi|anniversary gift|qua cuoi ki niem|tranh ki niem|tranh ky niem"},
     
    # 29. quà tân gia
    {"tag_id": "qua-tan-gia", "name_vi": "Quà tân gia", "category_id": "home.housewarming", "source_keywords": "quà tân gia", 
     "aliases": "qua tan gia|mung tan gia|housewarming gift|qua den nha moi|mon qua tan gia|tang qua tan gia"},
    {"tag_id": "decor-nha-moi", "name_vi": "Decor nhà mới", "category_id": "home.housewarming", "source_keywords": "quà tân gia", 
     "aliases": "decor nha moi|decor nha cap 4|trang tri nha moi|khai truong nha moi|decor phong khach|decor nha"},
     
    # 30. quà tặng bạn thân
    {"tag_id": "qua-tang-ban-than", "name_vi": "Quà tặng bạn thân", "category_id": "accessory.friendship", "source_keywords": "quà tặng bạn thân", 
     "aliases": "qua tang ban than|qua cho ban|ban than tri ki|qua thiet ke ban than|bday ban than|friend gift"},
    {"tag_id": "ban-than", "name_vi": "Bạn thân", "category_id": "accessory.friendship", "source_keywords": "quà tặng bạn thân", 
     "aliases": "ban than|best friend|besties|ban be than thiet|bff gift|bff keychain"},
     
    # 31. quà handmade
    {"tag_id": "qua-handmade", "name_vi": "Quà handmade", "category_id": "stationery.gift", "source_keywords": "quà handmade", 
     "aliases": "qua handmade|do handmade|handmade gift|qua tu lam|diy gift|quacustom"},
    {"tag_id": "do-handmade", "name_vi": "Đồ handmade", "category_id": "stationery.gift", "source_keywords": "quà handmade", 
     "aliases": "do handmade|qua tu lam|diy gift|do decor handmade|handmade decor|tranh handmade"},
     
    # 32. quà lưu niệm
    {"tag_id": "qua-luu-niem", "name_vi": "Quà lưu niệm", "category_id": "sport.travel", "source_keywords": "quà lưu niệm", 
     "aliases": "qua luu niem|souvenir|do luu niem|luu niem viet nam|qua viet nam|vietnam souvenir"},
    {"tag_id": "souvenir", "name_vi": "Souvenir", "category_id": "sport.travel", "source_keywords": "quà lưu niệm", 
     "aliases": "souvenir viet nam|quoc te luu niem|travel gift|vietnam gift|souvenirs|vietnam travel gift"},
     
    # 33. áo anime
    {"tag_id": "ao-anime", "name_vi": "Áo Anime", "category_id": "apparel.anime", "source_keywords": "áo anime", 
     "aliases": "ao anime|ao manga|anime tee|otaku shirt|wibu tee|fan anime"},
    {"tag_id": "otaku", "name_vi": "Otaku", "category_id": "apparel.anime", "source_keywords": "áo anime", 
     "aliases": "otaku|wibu|ao wibu|fan anime|anime fan|shirt otaku"},
     
    # 34. áo oversize
    {"tag_id": "ao-oversize", "name_vi": "Áo Oversize", "category_id": "apparel.streetwear", "source_keywords": "áo oversize", 
     "aliases": "ao oversize|oversized tee|ao rong|ao thun rong|ao form rong|oversize basic"},
    {"tag_id": "unisex-style", "name_vi": "Phong cách Unisex", "category_id": "apparel.streetwear", "source_keywords": "áo oversize", 
     "aliases": "phong cach unisex|thoi trang unisex|unisex cloth|clothes unisex|style unisex|unisex tee"},
     
    # 35. áo local brand
    {"tag_id": "ao-local-brand", "name_vi": "Áo Local Brand", "category_id": "apparel.streetwear", "source_keywords": "áo local brand", 
     "aliases": "ao local brand|local brand viet nam|tee local brand|ao thun local|streetwear localbrand|ao localbrand"},
    {"tag_id": "vietnam-local-brand", "name_vi": "Vietnam Local Brand", "category_id": "apparel.streetwear", "source_keywords": "áo local brand", 
     "aliases": "vietnam local brand|local brand chat|ao thun streetstyle|brand viet|ao brand viet|local brand shirt"},
     
    # 36. áo vintage
    {"tag_id": "ao-vintage", "name_vi": "Áo Vintage", "category_id": "apparel.vintage", "source_keywords": "áo vintage", 
     "aliases": "ao vintage|retrotee|vintage wear|ao thun co dien|classic tee|ao kieu co dien"},
    {"tag_id": "retro-style", "name_vi": "Phong cách Retro", "category_id": "apparel.vintage", "source_keywords": "áo vintage", 
     "aliases": "phong cach retro|co dien|vintage 90s|retro wear|style classic|retro art"},
     
    # 37. áo hoodie
    {"tag_id": "ao-hoodie", "name_vi": "Áo Hoodie", "category_id": "apparel.streetwear", "source_keywords": "áo hoodie", 
     "aliases": "ao hoodie|ao ni co mu|hoodie nam nu|ao lanh hoodie|hoodie tron|ao khoac mu"},
    {"tag_id": "hoodie-unisex", "name_vi": "Hoodie Unisex", "category_id": "apparel.streetwear", "source_keywords": "áo hoodie", 
     "aliases": "hoodie unisex|ao hoodie beo|hoodie oversize|hoodie rong|hoodie form rong|unisex hoodie"},
     
    # 38. áo bóng đá việt nam
    {"tag_id": "ao-bong-da", "name_vi": "Áo bóng đá", "category_id": "apparel.sport", "source_keywords": "áo bóng đá việt nam", 
     "aliases": "ao bong da|ao da banh|football shirt|ao bong da clb|ao sport bong da|jersey bong da"},
    {"tag_id": "viet-nam-vo-dich", "name_vi": "Việt Nam vô địch", "category_id": "apparel.sport", "source_keywords": "áo bóng đá việt nam", 
     "aliases": "viet nam vo dich|co vu viet nam|ao do sao vang|tuyen viet nam|ao co vu|vietnam champion"},
     
    # 39. áo thun thể thao
    {"tag_id": "ao-the-thao", "name_vi": "Áo thể thao", "category_id": "apparel.sport", "source_keywords": "áo thun thể thao", 
     "aliases": "ao the thao|sport tee|clothes training|ao activewear|ao thun the thao|ao chay bo"},
    {"tag_id": "do-tap-gym", "name_vi": "Đồ tập gym", "category_id": "apparel.sport", "source_keywords": "áo thun thể thao", 
     "aliases": "do tap gym|gym wear|quan ao active|ao thun gym|ao gym nam nu|gym tee"},
     
    # 40. quà sinh nhật
    {"tag_id": "qua-sinh-nhat", "name_vi": "Quà sinh nhật", "category_id": "drinkware.gift", "source_keywords": "quà sinh nhật", 
     "aliases": "qua sinh nhat|sinh nhat gift|birthday present|qua bday|mon qua sinh nhat|sinh nhat ban"},
    {"tag_id": "qua-tang-sinh-nhat", "name_vi": "Quà tặng sinh nhật", "category_id": "drinkware.gift", "source_keywords": "quà sinh nhật", 
     "aliases": "qua tang sinh nhat|sinh nhat ban|happy birthday|birthday gift|gift happy birthday|tang qua sinh nhat"},
]

def main():
    print("=== VietCraft tags.csv Generator & Validator ===")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    categories_path = os.path.join(script_dir, "categories.csv")
    tags_path = os.path.join(script_dir, "tags.csv")
    
    if not os.path.exists(categories_path):
        print(f"Error: categories.csv does not exist at {categories_path}. Run generate_categories.py first.")
        sys.exit(1)
        
    print(f"Loading categories from {categories_path}...")
    valid_categories = set()
    with open(categories_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            valid_categories.add(row["category_id"])
            
    print(f"Found {len(valid_categories)} valid categories.")
    
    num_tags = len(TAG_MAPPINGS)
    print(f"\nEvaluating tags count: {num_tags} tags")
    if not (60 <= num_tags <= 80):
        print(f"FAIL: Total tag count {num_tags} is out of bounds (60-80).")
        sys.exit(1)
    print("✅ PASS: Tag count is within [60, 80] range.")
    
    tag_ids = [t["tag_id"] for t in TAG_MAPPINGS]
    duplicates = [t for t in set(tag_ids) if tag_ids.count(t) > 1]
    if duplicates:
        print(f"FAIL: Found duplicate tag IDs: {duplicates}")
        sys.exit(1)
    print("✅ PASS: All tag IDs are unique.")
    
    bad_formats = []
    for t in TAG_MAPPINGS:
        tid = t["tag_id"]
        if not re.match(r"^[a-z0-9-]+$", tid):
            bad_formats.append(tid)
    if bad_formats:
        print(f"FAIL: Tag IDs with invalid naming format: {bad_formats}")
        sys.exit(1)
    print("✅ PASS: All tag IDs use the valid slug format.")
    
    invalid_cats = []
    for t in TAG_MAPPINGS:
        cat_id = t["category_id"]
        if cat_id not in valid_categories:
            invalid_cats.append((t["tag_id"], cat_id))
    if invalid_cats:
        print(f"FAIL: Tags containing invalid or non-existent category IDs: {invalid_cats}")
        sys.exit(1)
    print("✅ PASS: All mapped category IDs exist in categories.csv.")
    
    # Check that all aliases lists have > 5 items
    under_5_aliases = []
    for t in TAG_MAPPINGS:
        parts = t["aliases"].split("|")
        if len(parts) <= 5:
            under_5_aliases.append((t["tag_id"], len(parts)))
    if under_5_aliases:
        print(f"FAIL: The following tags have <= 5 aliases: {under_5_aliases}")
        sys.exit(1)
    print("✅ PASS: All tags have more than 5 aliases (each contains >= 6 variations).")
    
    mapped_kws = set()
    for t in TAG_MAPPINGS:
        skw = t["source_keywords"]
        mapped_kws.add(skw)
        
    missing_kws = set(OFFICIAL_KEYWORDS) - mapped_kws
    if missing_kws:
        print(f"FAIL: The following forecast-eligible keywords are not mapped to any tags: {missing_kws}")
        sys.exit(1)
    print(f"✅ PASS: All {len(OFFICIAL_KEYWORDS)} official keywords are fully mapped to at least 1 tag.")
    
    avg_tags = num_tags / len(OFFICIAL_KEYWORDS)
    print(f"Tag average per keyword: {avg_tags:.1f}")
    
    header = ["tag_id", "name_vi", "category_id", "source_keywords", "aliases"]
    with open(tags_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for row in TAG_MAPPINGS:
            writer.writerow(row)
            
    print(f"\nSUCCESS: Mapped tags written to {tags_path} successfully!")
    
if __name__ == "__main__":
    main()
