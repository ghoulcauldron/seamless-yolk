#!/usr/bin/env python3
"""
enrich_shopify_import.py
Refactored proof-of-concept.
• Reads Shopify export, tracker, and images manifest for a given capsule
• Extracts Product ID from Shopify Tags → tracker lookup
• Restores original tag-building and image-mapping behaviour
"""

import argparse, json, pathlib, pandas as pd, re

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def load_manifest(capsule: str) -> pd.DataFrame:
    path = pathlib.Path(f"capsules/{capsule}/manifests/images_manifest.jsonl")
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    recs = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return pd.DataFrame(recs)


def extract_product_id_from_tags(tags_str: str) -> str | None:
    """Extract Product ID from Shopify tags string (as in original POC)."""
    if not isinstance(tags_str, str):
        return None
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    # Product ID tag usually contains at least three space-separated words
    for tag in tags:
        if len(tag.split()) >= 3:
            return tag
    return None


def build_tags(source_record: pd.Series, existing_tags_str: str) -> str:
    """Re-uses the original tag logic for style, color, season, and collections."""
    category_tags_map = {
        1: "collection_ready-to-wear, collection_jackets, collection_new-arrivals",
        2: "collection_ready-to-wear, collection_jackets, collection_new-arrivals",
        3: "collection_ready-to-wear, collection_dresses, collection_new-arrivals",
        4: "collection_ready-to-wear, collection_tops, collection_new-arrivals",
        5: "collection_ready-to-wear, collection_skirts, collection_new-arrivals",
        6: "collection_ready-to-wear, collection_pants, collection_new-arrivals",
        9: "collection_accessories, collection_SHOES, collection_new-arrivals",
        70: "collection_accessories, collection_Bags, collection_new-arrivals",
        71: "collection_accessories, collection_Bags, collection_new-arrivals",
        76: "collection_accessories, collection_belts, collection_new-arrivals",
        79: "collection_accessories, collection_Jewelry, collection_new-arrivals",
        81: "collection_ready-to-wear, collection_knitwear, collection_jackets, collection_new-arrivals",
        82: "collection_ready-to-wear, collection_knitwear, collection_jackets, collection_new-arrivals",
        83: "collection_ready-to-wear, collection_knitwear, collection_dresses, collection_new-arrivals",
        84: "collection_ready-to-wear, collection_knitwear, collection_tops, collection_new-arrivals",
        85: "collection_ready-to-wear, collection_knitwear, collection_skirts, collection_new-arrivals",
        86: "collection_ready-to-wear, collection_knitwear, collection_pants, collection_new-arrivals",
        88: "collection_ready-to-wear, collection_knitwear, collection_tops, collection_new-arrivals",
    }

    new_tags = []
    if not source_record.empty:
        if pd.notna(source_record.get("Description")):
            style_name = str(source_record["Description"]).title()
            new_tags.append(f"style_{style_name}")
        if pd.notna(source_record.get("SEASON CODE")):
            sc = str(source_record["SEASON CODE"])
            new_tags.append(sc.replace("S1", "SS") if "S1" in sc else sc)
        if pd.notna(source_record.get("Colour")):
            color = " ".join(str(source_record["Colour"]).split(" ")[1:]).lower()
            new_tags.append(f"color_{color}")
        # Prefer knit-specific code if present, otherwise fallback to general category code
        category_code = None

        knit_code = source_record.get("KNIT CATEGORY CODE")
        cat_code = source_record.get("CATEGORY CODE")

        # Try knit first (since it's more specific)
        for val in [knit_code, cat_code]:
            if pd.notna(val):
                try:
                    category_code = int(float(val))
                    break
                except (ValueError, TypeError):
                    continue

        if category_code in category_tags_map:
            new_tags.extend([t.strip() for t in category_tags_map[category_code].split(",")])

    print("DEBUG: CATEGORY CODE =", source_record.get("CATEGORY CODE"),
          "| KNIT CATEGORY CODE =", source_record.get("KNIT CATEGORY CODE"))

    existing = [t.strip() for t in str(existing_tags_str).split(",") if t.strip()]
    combined = list(dict.fromkeys(existing + new_tags))
    return ", ".join(filter(None, combined))

# ---------------------------------------------------------------------
# Main enrichment
# ---------------------------------------------------------------------

def enrich(capsule: str, dry_run: bool = False):
    base = pathlib.Path(f"capsules/{capsule}/inputs")
    df_export = pd.read_csv(base / "products_export_1.csv")
    df_tracker = pd.read_csv(base / "SS26 for Shopify check(By Style).csv")
    manifest = load_manifest(capsule)

    # normalise tracker index for quick lookup
    df_tracker.set_index("Product ID", inplace=True, drop=False)

    # derive CPI from handle if needed
    if "CPI" not in df_export.columns:
        df_export["CPI"] = df_export["Handle"].str.extract(r"(\d{4}-\d{6})")

    # extract Product ID from Shopify tags
    df_export["Product ID"] = df_export["Tags"].apply(extract_product_id_from_tags)

    # pre-fill enrichment columns
    df_export["Swatch_File"] = ""
    df_export["Look_Image_File"] = ""
    df_export["Accessory"] = False

    # ---------------------------------------------------------------
    # 1️⃣  Link imagery from manifest
    # ---------------------------------------------------------------
    for _, m in manifest.iterrows():
        if not m["cpi"]:
            continue
        mask = df_export["CPI"] == m["cpi"]
        if not mask.any():
            continue
        if m["asset_type"] == "swatches":
            df_export.loc[mask, "Swatch_File"] = m["filename"]
            df_export.loc[mask, "Accessory"] = m["is_accessory"]
        elif m["asset_type"] == "editorials" and not m["is_accessory"]:
            df_export.loc[mask, "Look_Image_File"] = m["filename"]

    # ---------------------------------------------------------------
    # 2️⃣  Rebuild tags from tracker record
    # ---------------------------------------------------------------
    def tag_row(r):
        pid = r.get("Product ID")
        if pd.isna(pid) or pid not in df_tracker.index:
            return r.get("Tags", "")
        return build_tags(df_tracker.loc[pid], r.get("Tags", ""))

    df_export["Tags"] = df_export.apply(tag_row, axis=1)

    # ---------------------------------------------------------------
    # 3️⃣  Create metafield prefill columns
    # ---------------------------------------------------------------
    df_export["Metafield: altuzarra.swatch_image [file_reference]"] = df_export[
        "Swatch_File"
    ]
    df_export["Metafield: altuzarra.look_image [file_reference]"] = df_export.apply(
        lambda r: r["Look_Image_File"] if not r["Accessory"] else "", axis=1
    )

    # ---------------------------------------------------------------
    # 4️⃣  Assign Image Src and Image Position (non-destructive)
    # ---------------------------------------------------------------
    CDN_PREFIX = "https://cdn.shopify.com/s/files/1/0148/9561/2004/files/"
    ghosts = manifest[manifest["asset_type"] == "ghosts"]

    def sort_order(fname: str, is_accessory: bool) -> int:
        f = fname.lower()
        if is_accessory:
            if "front" in f and "main" in f: return 1
            if "side"  in f and "main" in f: return 2
            if "aerial" in f and "main" in f: return 3
            if "detail" in f: return 4
            return 99
        if "_ghost_" in f: return 1
        if "_hero_"  in f: return 2
        m = re.search(r"model_image_(\d+)", f)
        return 2 + int(m.group(1)) if m else 99

    # guarantee columns exist
    for col in ["Image Src", "Image Position"]:
        if col not in df_export.columns:
            df_export[col] = ""

    for cpi, group in ghosts.groupby("cpi"):
        is_acc = bool(group["is_accessory"].any())
        sorted_files = sorted(group["filename"], key=lambda f: sort_order(f, is_acc))

        # --- robust pattern: look for “8835 000067” inside Product ID ---
        pattern = r"\b" + re.escape(cpi.replace("-", " ")) + r"\b"
        mask = df_export["Product ID"].fillna("").str.contains(pattern, na=False)
        if not mask.any():
            continue

        for pos, fname in enumerate(sorted_files, start=1):
            url = CDN_PREFIX + fname.replace(" ", "_")
            # assign only first free slot per image, not overwrite all
            rows = df_export.index[mask]
            if pos - 1 < len(rows):
                df_export.at[rows[pos - 1], "Image Src"] = url
                df_export.at[rows[pos - 1], "Image Position"] = pos



    # ---------------------------------------------------------------
    # 4️⃣  Write or preview
    # ---------------------------------------------------------------
    out = pathlib.Path(f"capsules/{capsule}/outputs/poc_shopify_import_enriched.csv")
    if dry_run:
        print(df_export.head(10))
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        df_export.to_csv(out, index=False)
        print(f"✅ Enriched CSV written: {out}")

# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--capsule", required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    enrich(a.capsule, dry_run=a.dry_run)
