import unittest
from collect_printify import classify

class TestClassifyPrintify(unittest.TestCase):
    def test_stainless_steel_not_tshirt(self):
        """Bug Task 1: 'Stainless Steel' contains 'tee' in 'steel', should NOT be classified as tshirt"""
        steel_mug = "Stainless Steel Travel Mug with Handle"
        result = classify(steel_mug)
        self.assertNotEqual(result, "tshirt", f"'{steel_mug}' was incorrectly classified as tshirt due to 'tee' in 'steel'")
        self.assertEqual(result, "mug")

    def test_stainless_steel_bottle(self):
        steel_bottle = "Stainless Steel Water Bottle"
        result = classify(steel_bottle)
        self.assertNotEqual(result, "tshirt", f"'{steel_bottle}' was incorrectly classified as tshirt")
        self.assertEqual(result, "mug")

    def test_drinkware_variations(self):
        self.assertEqual(classify("Enamel Campfire Mug"), "mug")
        self.assertEqual(classify("Skinny Tumbler 20oz with Straw"), "mug")
        self.assertEqual(classify("Ceramic Coffee Mug 11oz"), "mug")
        self.assertEqual(classify("Insulated Wine Tumbler"), "mug")

    def test_valid_tshirts_and_apparel(self):
        self.assertEqual(classify("Unisex Cotton Crew Tee"), "tshirt")
        self.assertEqual(classify("Men's Classic T-Shirt"), "tshirt")
        self.assertEqual(classify("Women's Fashion Tee"), "tshirt")
        self.assertEqual(classify("Heavyweight T-shirt"), "tshirt")
        self.assertEqual(classify("Unisex Heavy Blend™ Hooded Sweatshirt"), "tshirt")
        self.assertEqual(classify("Unisex Crewneck Sweatshirt"), "tshirt")

    def test_totes_and_bags(self):
        self.assertEqual(classify("Cotton Canvas Tote Bag"), "tote")
        self.assertEqual(classify("All Over Print Drawstring Bag"), "tote")
        self.assertEqual(classify("Unisex Classic Backpack"), "tote")

    def test_posters_and_wallart(self):
        self.assertEqual(classify("Premium Matte Vertical Poster"), "poster")
        self.assertEqual(classify("Stretched Canvas Print"), "poster")
        self.assertEqual(classify("Custom Metal Print"), "poster")

if __name__ == "__main__":
    unittest.main()
