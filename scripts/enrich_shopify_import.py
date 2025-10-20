#!/usr/bin/env python3
"""
enrich_shopify_import.py
Merges client tracker, Shopify export, and images_manifest.jsonl.
Skips look_image metafield generation for accessories.
"""

import argparse, json, pathlib, pandas as pd

# ---------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------
def load_manifest(capsule: str) -> pd.DataFrame:
    manifest_path = pathlib.Path(f"capsules/{capsule}/manifests/images_manifest.jsonl")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    records = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
    return pd.DataFrame(records)


def merge_dataframes(df_export, df_tracker, manifest):
    """Join data and expand metafields/asset mappings."""
    df = df_export.merge(df_tracker, how="left", on="Handle")  # or appropriate join key
    df["Swatch_File"] = None
    df["Look_Image_File"] = None
    df["Accessory"] = False

    for _, row in manifest.iterrows():
        # Find matching product row by CPI
        mask = df["CPI"] == row["cpi"]
        if not mask.any():
            continue

        if row["asset_type"] == "swatch":
            df.loc[mask, "Swatch_File"] = row["filename"]
            df.loc[mask, "Accessory"] = row["is_accessory"]

        elif row["asset_type"] == "editorials" and not row["is_accessory"]:
            # only garments receive look_image linkage
            df.loc[mask, "Look_Image_File"] = row["filename"]

    return df


# ---------------------------------------------------------------------
# Main enrichment
# ---------------------------------------------------------------------
def enrich(capsule: str, dry_run: bool = False):
    base = pathlib.Path(f"capsules/{capsule}/inputs")
    df_export = pd.read_csv(base / "products_export_1.csv")
    df_tracker = pd.read_csv(base / "SS26 for Shopify check(By Style).csv")
    manifest = load_manifest(capsule)

    # derive CPI if not already present
    if "CPI" not in df_export.columns:
        df_export["CPI"] = df_export["Handle"].str.extract(r"(\d{4}-\d{6})")

    enriched = merge_dataframes(df_export, df_tracker, manifest)

    # ---------------------------------------------------------------
    # Add/adjust tags and metafield pre-fill columns
    # ---------------------------------------------------------------
    enriched["Tags"] = enriched.apply(lambda r: append_tags(r), axis=1)
    enriched["Metafield: altuzarra.swatch_image [file_reference]"] = enriched["Swatch_File"]

    # Garments only get look_image
    enriched["Metafield: altuzarra.look_image [file_reference]"] = enriched.apply(
        lambda r: r["Look_Image_File"] if not r["Accessory"] else "", axis=1
    )

    # Export
    out = pathlib.Path(f"capsules/{capsule}/outputs/poc_shopify_import_enriched.csv")
    if not dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        enriched.to_csv(out, index=False)
        print(f"✅ Enriched CSV written: {out}")
    else:
        print(enriched.head(10))


def append_tags(row):
    """Append accessory/garment context tags cleanly."""
    tags = str(row.get("Tags", "") or "").split(",")
    tags = [t.strip() for t in tags if t.strip()]
    if row.get("Accessory"):
        tags.append("Accessory")
    else:
        tags.append("Apparel")
    return ", ".join(sorted(set(tags)))


# ---------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--capsule", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    enrich(args.capsule, dry_run=args.dry_run)
