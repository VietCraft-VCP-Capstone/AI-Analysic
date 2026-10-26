import sys
from pathlib import Path
_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

import unittest
from build_catalog import (
    PRODUCT_TYPES,
    PRODUCT_GROUPS,
    USD_VND_RATE,
    MIN_MARGIN,
    translate_color,
    convert_size_label,
    build_settings_table,
    build_price_rules_table,
    build_product_types_table,
    classify_blueprint,
)

class TestCatalogPipeline(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(USD_VND_RATE, 26000)
        self.assertEqual(MIN_MARGIN, 1.6)

    def test_product_types_count_and_groups(self):
        self.assertEqual(len(PRODUCT_TYPES), 138, f"Expected 138 product types, got {len(PRODUCT_TYPES)}")
        self.assertEqual(len(PRODUCT_GROUPS), 11, f"Expected 11 product groups, got {len(PRODUCT_GROUPS)}")
        
        for pt_id, pt_info in PRODUCT_TYPES.items():
            self.assertIn(pt_info["group"], PRODUCT_GROUPS, f"Type {pt_id} has invalid group {pt_info['group']}")
            self.assertTrue(pt_info["name_vi"], f"Type {pt_id} missing Vietnamese name")
            self.assertIn("has_size", pt_info)
            self.assertIn("has_color", pt_info)

    def test_settings_table(self):
        settings = build_settings_table()
        keys = {s["setting_key"]: s["setting_value"] for s in settings}
        self.assertEqual(keys.get("usd_vnd_rate"), "26000")
        self.assertEqual(keys.get("min_margin"), "1.6")
        self.assertEqual(keys.get("default_margin_low"), "2.0")
        self.assertEqual(keys.get("default_margin_high"), "3.0")

    def test_price_rules_table(self):
        rules = build_price_rules_table()
        self.assertEqual(len(rules), 138)
        for r in rules:
            self.assertEqual(r["min_margin"], 1.6)
            self.assertEqual(r["suggested_margin_low"], 2.0)
            self.assertEqual(r["suggested_margin_high"], 3.0)

    def test_color_translation(self):
        c_vi, c_hex = translate_color("Black")
        self.assertEqual(c_vi, "Đen")
        self.assertEqual(c_hex, "#1A1A1A")

        c_vi, c_hex = translate_color("White")
        self.assertEqual(c_vi, "Trắng")
        self.assertEqual(c_hex, "#FFFFFF")

        c_vi, c_hex = translate_color("Navy")
        self.assertEqual(c_vi, "Xanh tím than")
        self.assertEqual(c_hex, "#000080")

    def test_poster_size_cm(self):
        self.assertEqual(convert_size_label("12\" x 18\"", "poster"), "30 x 45 cm")
        self.assertEqual(convert_size_label("18″ x 24″", "poster"), "45 x 60 cm")
        self.assertEqual(convert_size_label("24\" x 36\"", "poster"), "60 x 90 cm")
        # Non-poster should keep original size
        self.assertEqual(convert_size_label("XL", "tshirt_unisex"), "XL")

    def test_blueprint_classification_examples(self):
        self.assertEqual(classify_blueprint("Unisex Heavy Cotton Tee"), "tshirt_unisex")
        self.assertEqual(classify_blueprint("Stainless Steel Travel Mug"), "tumbler")
        self.assertEqual(classify_blueprint("Matte Vertical Poster"), "poster")
        self.assertEqual(classify_blueprint("Cotton Canvas Tote Bag"), "tote")
        self.assertEqual(classify_blueprint("Ceramic Mug 11oz"), "mug_11oz")

if __name__ == "__main__":
    unittest.main()
