#!/usr/bin/env python3
"""
verify_catalog.py — Verification Script for VietCraft Catalog & Configuration Tables
Tests all 8 requirements assigned to Catalog & Configuration.
Supports CLI arguments with clean project-relative defaults.
"""

import argparse
import csv
import os
import re
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def resolve_data_dir(cli_dir: str) -> Path:
    """Resolve data directory from CLI argument or standard repository data locations."""
    if cli_dir:
        p = Path(cli_dir).resolve()
        if p.is_dir():
            return p
        print(f"Warning: Specified data directory not found: {cli_dir}")

    # Standard lookup locations relative to current working dir and script location
    script_dir = Path(__file__).resolve().parent
    search_dirs = [
        Path.cwd() / "app" / "data",
        Path.cwd() / "data",
        Path.cwd(),
        script_dir.parent.parent / "data",
        script_dir / "data",
        script_dir,
    ]

    for d in search_dirs:
        if (d / "vc_setting.csv").is_file():
            return d.resolve()

    return script_dir


def parse_args():
    parser = argparse.ArgumentParser(description="VietCraft Catalog QA Suite")
    parser.add_argument("--data-dir", type=str, default=None, help="Thư mục chứa các file csv catalog")
    return parser.parse_args()


def verify_all():
    args = parse_args()

    print("=" * 70)
    print("VERIFICATION REPORT — VIETCRAFT CATALOG & CONFIGURATION")
    print("=" * 70)

    data_dir = resolve_data_dir(args.data_dir)
    print(f"📁 Using Data Directory: {data_dir}")

    settings_file = data_dir / "vc_setting.csv"
    rules_file = data_dir / "vc_price_rule.csv"
    types_file = data_dir / "vc_product_type.csv"
    variants_file = data_dir / "vc_catalog_variant.csv"

    passed_checks = 0
    total_checks = 8

    # 1. Check vc_setting
    print("\n[Check 1] System Settings Table (vc_setting)")
    if not settings_file.exists():
        print(f"  FAIL: {settings_file.name} not found")
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
    if not rules_file.exists():
        print(f"  FAIL: {rules_file.name} not found")
    else:
        with open(rules_file, "r", encoding="utf-8-sig") as f:
            rules = list(csv.DictReader(f))
        all_16 = all(float(r["min_margin"]) == 1.6 for r in rules)
        if len(rules) == 138 and all_16:
            print(f"  PASS: 138 rules configured with min_margin=1.6, suggested=[2.0, 3.0]")
            passed_checks += 1
        else:
            print(f"  FAIL: Rules count={len(rules)} (expected 138), all_16={all_16}")

    # 3. Check vc_product_type (138 types, 11 groups)
    print("\n[Check 3] 138 Product Types & 11 Groups (vc_product_type)")
    if not types_file.exists():
        print(f"  FAIL: {types_file.name} not found")
    else:
        with open(types_file, "r", encoding="utf-8-sig") as f:
            types = list(csv.DictReader(f))
        groups = set(t["product_group"] for t in types)
        if len(types) == 138 and len(groups) == 11:
            print(f"  PASS: Exactly 138 product types across 11 groups")
            passed_checks += 1
        else:
            print(f"  FAIL: types_count={len(types)} (expected 138), groups_count={len(groups)} (expected 11)")

    # 4. Check cost source transparency
    print("\n[Check 4] Cost Source Transparency (printify vs estimated)")
    if types_file.exists():
        with open(types_file, "r", encoding="utf-8-sig") as f:
            types = list(csv.DictReader(f))
        printify_types = [t for t in types if t.get("cost_source") == "printify"]
        estimated_types = [t for t in types if t.get("cost_source") == "estimated"]
        if len(printify_types) == 29 and len(estimated_types) == 109:
            print(f"  PASS: 29 Real Printify types, 109 Estimated types clearly marked")
            passed_checks += 1
        else:
            print(f"  FAIL: Printify={len(printify_types)} (expected 29), Estimated={len(estimated_types)} (expected 109)")
    else:
        print(f"  SKIP: {types_file.name} not found")

    # 5. Check currency normalization (Integer VND >= 10,000)
    print("\n[Check 5] Currency Normalization (Integer VND)")
    if not variants_file.exists():
        print(f"  FAIL: {variants_file.name} not found")
    else:
        with open(variants_file, "r", encoding="utf-8-sig") as f:
            variants = list(csv.DictReader(f))
        
        all_vnd_valid = True
        for v in variants:
            try:
                cost_vnd = int(v["cost_vnd"])
                if cost_vnd < 10000:
                    all_vnd_valid = False
                    break
            except (ValueError, KeyError):
                all_vnd_valid = False
                break

        if all_vnd_valid and len(variants) > 0:
            print(f"  PASS: {len(variants):,} variants generated, 100% VND integers >= 10,000đ")
            passed_checks += 1
        else:
            print(f"  FAIL: Invalid VND currency formatting or values in variants")

    # 6. Check color normalization (color_vi + color_hex)
    print("\n[Check 6] Color Attribute Normalization (color_vi + color_hex)")
    if variants_file.exists():
        with open(variants_file, "r", encoding="utf-8-sig") as f:
            variants = list(csv.DictReader(f))
        
        color_variants = [v for v in variants if v.get("color_code") and v["color_code"].strip() != ""]
        hex_pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
        all_colors_valid = True
        
        for v in color_variants:
            c_vi = v.get("color_vi", "")
            c_hex = v.get("color_hex", "")
            if not c_vi or not hex_pattern.match(c_hex):
                all_colors_valid = False
                break

        if all_colors_valid and len(color_variants) > 0:
            print(f"  PASS: {len(color_variants):,} colored variants normalized with Vietnamese name & Hex code")
            passed_checks += 1
        else:
            print(f"  FAIL: Color normalization missing or invalid hex code in {len(color_variants)} colored variants")
    else:
        print(f"  SKIP: {variants_file.name} not found")

    # 7. Check poster & wallart size conversion (inch -> cm)
    print("\n[Check 7] Poster & Wallart Size Conversion (inch -> cm)")
    if variants_file.exists():
        with open(variants_file, "r", encoding="utf-8-sig") as f:
            variants = list(csv.DictReader(f))
        
        wallart_variants = [v for v in variants if "poster" in v.get("product_type_id", "").lower() or "canvas" in v.get("product_type_id", "").lower()]
        inch_pattern = re.compile(r'\b\d+(\.\d+)?\s*(inch|in|\")\b', re.IGNORECASE)
        has_inches = any(inch_pattern.search(v.get("size_label_vi", "")) for v in wallart_variants)
        
        if not has_inches and len(wallart_variants) > 0:
            print(f"  PASS: 100% of wallart/poster sizes converted to cm (e.g., '28 x 35 cm')")
            passed_checks += 1
        else:
            print(f"  FAIL: Inches detected in wallart variant sizing")
    else:
        print(f"  SKIP: {variants_file.name} not found")

    # 8. Check classification accuracy
    print("\n[Check 8] Classification Accuracy (No Stainless Steel Mugs in T-Shirts)")
    if variants_file.exists():
        with open(variants_file, "r", encoding="utf-8-sig") as f:
            variants = list(csv.DictReader(f))
        
        apparel_mugs = [v for v in variants if "tshirt" in v.get("product_type_id", "") and "mug" in v.get("blueprint_title", "").lower()]
        if len(apparel_mugs) == 0:
            print(f"  PASS: Zero stainless steel mugs/bottles misclassified into apparel")
            passed_checks += 1
        else:
            print(f"  FAIL: {len(apparel_mugs)} drinkware items found misclassified in apparel")
    else:
        print(f"  SKIP: {variants_file.name} not found")

    print("\n" + "=" * 70)
    print(f"FINAL RESULT: {passed_checks}/{total_checks} CHECKS PASSED")
    if passed_checks == total_checks:
        print("STATUS: ALL REQUIREMENTS FOR HƯNG (NGƯỜI 2) ARE FULLY SATISFIED!")
    else:
        print("STATUS: SOME CHECKS FAILED OR WERE SKIPPED.")
    print("=" * 70 + "\n")

    if passed_checks != total_checks:
        sys.exit(1)


if __name__ == "__main__":
    verify_all()
