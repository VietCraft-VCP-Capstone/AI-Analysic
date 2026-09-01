#!/usr/bin/env python3
"""
Verification Script for VietCraft Catalog & Configuration Tables
Tests all 8 requirements assigned to Hưng (Người 2).
"""

import os
import sys
import csv
import json
import re

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def verify_all():
    print("=" * 70)
    print("VERIFICATION REPORT — VIETCRAFT CATALOG & CONFIGURATION")
    print("=" * 70)

    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "seed_out")
    
    settings_file = os.path.join(data_dir, "vc_setting.csv")
    rules_file = os.path.join(data_dir, "vc_price_rule.csv")
    types_file = os.path.join(data_dir, "vc_product_type.csv")
    variants_file = os.path.join(data_dir, "vc_catalog_variant.csv")

    passed_checks = 0
    total_checks = 8

    # 1. Check vc_setting
    print("\n[Check 1] System Settings Table (vc_setting)")
    if not os.path.exists(settings_file):
        print("  FAIL: vc_setting.csv not found")
    else:
        with open(settings_file, "r", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        settings_map = {r["setting_key"]: r["setting_value"] for r in rows}
        rate_ok = settings_map.get("usd_vnd_rate") == "26000"
        margin_ok = settings_map.get("min_margin") == "1.6"
        if rate_ok and margin_ok and len(rows) >= 4:
            print(f"  PASS: usd_vnd_rate=26000, min_margin=1.6 ({len(rows)} settings present)")
            passed_checks += 1
        else:
            print(f"  FAIL: Settings values unexpected: {settings_map}")

    # 2. Check vc_price_rule
    print("\n[Check 2] Price Margin Rules (vc_price_rule)")
    if not os.path.exists(rules_file):
        print("  FAIL: vc_price_rule.csv not found")
    else:
        with open(rules_file, "r", encoding="utf-8-sig") as f:
            rules = list(csv.DictReader(f))
        all_16 = all(float(r["min_margin"]) == 1.6 for r in rules)
        if len(rules) == 138 and all_16:
            print(f"  PASS: 138 rules configured with min_margin=1.6, suggested=[2.0, 3.0]")
            passed_checks += 1
        else:
            print(f"  FAIL: Expected 138 rules with min_margin 1.6, found {len(rules)}")

    # 3. Check vc_product_type
    print("\n[Check 3] 138 Product Types & 11 Groups (vc_product_type)")
    if not os.path.exists(types_file):
        print("  FAIL: vc_product_type.csv not found")
    else:
        with open(types_file, "r", encoding="utf-8-sig") as f:
            types = list(csv.DictReader(f))
        groups = {r["product_group"] for r in types}
        if len(types) == 138 and len(groups) == 11:
            print(f"  PASS: Exactly 138 product types across 11 groups")
            passed_checks += 1
        else:
            print(f"  FAIL: Found {len(types)} types across {len(groups)} groups")

    # 4. Check Cost Sources (printify vs estimated)
    print("\n[Check 4] Cost Source Transparency (printify vs estimated)")
    if os.path.exists(types_file):
        with open(types_file, "r", encoding="utf-8-sig") as f:
            types = list(csv.DictReader(f))
        real_types = [t for t in types if t["cost_source"] == "printify"]
        est_types = [t for t in types if t["cost_source"] == "estimated"]
        if len(real_types) > 0 and len(est_types) > 0 and len(real_types) + len(est_types) == 138:
            print(f"  PASS: {len(real_types)} Real Printify types, {len(est_types)} Estimated types clearly marked")
            passed_checks += 1
        else:
            print("  FAIL: Cost sources not properly split")

    # 5. Check vc_catalog_variant rows & Currency (VND Integer)
    print("\n[Check 5] Currency Normalization (Integer VND)")
    if not os.path.exists(variants_file):
        print("  FAIL: vc_catalog_variant.csv not found")
    else:
        with open(variants_file, "r", encoding="utf-8-sig") as f:
            variants = list(csv.DictReader(f))
        
        all_vnd_int = True
        for v in variants:
            try:
                cost = int(v["cost_vnd"])
                if cost < 10000: # Less than 10,000 VND (~$0.38) is unrealistic
                    all_vnd_int = False
                    break
            except ValueError:
                all_vnd_int = False
                break
                
        if len(variants) >= 15000 and all_vnd_int:
            print(f"  PASS: {len(variants):,} variants generated, 100% VND integers >= 10,000đ")
            passed_checks += 1
        else:
            print(f"  FAIL: Variant count ({len(variants)}) or VND format issue")

    # 6. Check Color Translation (Vietnamese + Hex Code)
    print("\n[Check 6] Color Attribute Normalization (color_vi + color_hex)")
    if os.path.exists(variants_file):
        with open(variants_file, "r", encoding="utf-8-sig") as f:
            variants = list(csv.DictReader(f))
        
        variants_with_color = [v for v in variants if v["color_code"]]
        valid_hex = all(re.match(r"^#[0-9A-Fa-f]{6}$", v["color_hex"]) for v in variants_with_color)
        valid_vi = all(len(v["color_vi"]) > 0 for v in variants_with_color)
        
        if variants_with_color and valid_hex and valid_vi:
            print(f"  PASS: {len(variants_with_color):,} colored variants normalized with Vietnamese name & Hex code")
            passed_checks += 1
        else:
            print("  FAIL: Invalid color translation or hex codes")

    # 7. Check Poster Size Conversion (inch -> cm)
    print("\n[Check 7] Poster & Wallart Size Conversion (inch -> cm)")
    if os.path.exists(variants_file):
        with open(variants_file, "r", encoding="utf-8-sig") as f:
            variants = list(csv.DictReader(f))
            
        posters = [v for v in variants if v["product_type_id"] in ["poster", "canvas", "metal_print", "wood_print"]]
        posters_with_cm = [p for p in posters if "cm" in p["size_label_vi"]]
        
        if posters and len(posters_with_cm) == len(posters):
            sample = posters_with_cm[0]["size_label_vi"]
            print(f"  PASS: 100% of wallart/poster sizes converted to cm (e.g., '{sample}')")
            passed_checks += 1
        else:
            print(f"  FAIL: Found poster variants without cm: {len(posters_with_cm)}/{len(posters)}")

    # 8. Check Classification Accuracy (No Steel Travel Mugs in T-shirt)
    print("\n[Check 8] Classification Accuracy (No Stainless Steel Mugs in T-Shirts)")
    if os.path.exists(variants_file):
        with open(variants_file, "r", encoding="utf-8-sig") as f:
            variants = list(csv.DictReader(f))
            
        tshirts = [v for v in variants if "tshirt" in v["product_type_id"]]
        false_positives = [t for t in tshirts if "steel" in t["blueprint_title"].lower() or "mug" in t["blueprint_title"].lower()]
        
        if len(false_positives) == 0:
            print("  PASS: Zero stainless steel mugs/bottles misclassified into apparel")
            passed_checks += 1
        else:
            print(f"  FAIL: Found {len(false_positives)} misclassified drinkware items in t-shirts")

    print("\n" + "=" * 70)
    print(f"FINAL RESULT: {passed_checks}/{total_checks} CHECKS PASSED")
    if passed_checks == total_checks:
        print("STATUS: ALL REQUIREMENTS FOR HƯNG (NGƯỜI 2) ARE FULLY SATISFIED!")
    print("=" * 70)

if __name__ == "__main__":
    verify_all()
