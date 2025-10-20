#!/usr/bin/env python3
"""
validate_capsule.py
Ensures enriched CSV is structurally sound before import.
"""

import argparse, pandas as pd, pathlib

def main(capsule):
    path = pathlib.Path(f"capsules/{capsule}/outputs/poc_shopify_import_enriched.csv")
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    df = pd.read_csv(path)
    errors = []
    if df["Handle"].duplicated().any():
        errors.append("Duplicate handles found.")
    if df["Variant SKU"].duplicated().any():
        errors.append("Duplicate SKUs found.")
    if df["Variant Barcode"].duplicated().any():
        errors.append("Duplicate barcodes found.")
    if df.isnull().any().any():
        errors.append("Null cells detected.")
    if errors:
        print("❌ Validation issues:")
        [print("-", e) for e in errors]
    else:
        print(f"✅ {capsule} CSV validated successfully ({len(df)} rows).")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--capsule", required=True)
    args = p.parse_args()
    main(args.capsule)
