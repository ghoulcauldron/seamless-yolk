# scripts/preflight_s226.py

import pandas as pd
import re
from collections import defaultdict
import pathlib
from pathlib import Path
import logging
import json
import sys
from datetime import datetime

CAPSULE_DIR = pathlib.Path(f"capsules/S226")
SHOPIFY_EXPORT = CAPSULE_DIR / "inputs/products_export_1.csv"
MASTERFILE = CAPSULE_DIR / "inputs/S226 Shopify upload masterfile.csv"
GHOST_FILES = CAPSULE_DIR / "inputs/ghostFileNames.txt"
MODEL_FILES = CAPSULE_DIR / "inputs/modelFileNames.txt"
OUTPUT_DIR = CAPSULE_DIR / "preflight_outputs/"

CAPSULE_CODE = "S226"

CATEGORY_TAGS_MAP = {
    1: "collection_ready-to-wear, collection_jackets", 2: "collection_ready-to-wear, collection_jackets",
    3: "collection_ready-to-wear, collection_dresses", 4: "collection_ready-to-wear, collection_tops",
    5: "collection_ready-to-wear, collection_skirts", 6: "collection_ready-to-wear, collection_pants",
    9: "collection_accessories, collection_SHOES", 70: "collection_accessories, collection_Bags",
    71: "collection_accessories, collection_Bags", 76: "collection_accessories, collection_belts",
    79: "collection_accessories, collection_Jewelry", 81: "collection_ready-to-wear, collection_knitwear, collection_jackets",
    82: "collection_ready-to-wear, collection_knitwear, collection_jackets", 83: "collection_ready-to-wear, collection_knitwear, collection_dresses",
    84: "collection_ready-to-wear, collection_knitwear, collection_tops", 85: "collection_ready-to-wear, collection_knitwear, collection_skirts",
    86: "collection_ready-to-wear, collection_knitwear, collection_pants", 88: "collection_ready-to-wear, collection_knitwear, collection_tops"
}

# --------------------------------
# Outputs and GO/NO-GO rules:
# --------------------------------
# Outputs:
# - Internal JSON report with detailed per-product status and summary counts
# - Client advisory CSV with per-product summary and recommendation
#
# GO/NO-GO rules:
# - Missing or multiple parent rows => NO-GO
# - Missing or malformed Product ID tag for this capsule => NO-GO
# - Product ID not found in masterfile => NO-GO
# - Missing Variant Price => NO-GO
# - Missing ghost image => NO-GO
# - Invalid image position plan => NO-GO
# - Warnings do not cause NO-GO but are reported
# - Client recommendation depends on errors, image status, and ghost presence

# ----------------------------
# Loaders
# ----------------------------

def load_shopify_export(path: str) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)

def load_masterfile(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, header=0, encoding="cp1252")
    df.set_index("Product ID", inplace=True)
    return df

def load_filenames(path: str) -> list[str]:
    """Load image filenames/paths from a text file.

    Supports:
      - quoted tokens: '...'
      - unquoted paths/filenames containing common image extensions

    Returns a de-duplicated list preserving first-seen order.
    """
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        contents = f.read()

    # 1) Quoted tokens: '...'
    quoted = re.findall(r"'(.*?)'", contents)

    combined = []
    seen = set()

    def _add(item: str) -> None:
        s = str(item).strip()
        if not s:
            return
        if s not in seen:
            seen.add(s)
            combined.append(s)

    # Add quoted first
    for item in quoted:
        _add(item)

    # 2) Line-based parsing for unquoted lists (supports spaces in filenames)
    # Many of our input files are one filename per line.
    for raw_line in contents.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Skip lines that are purely a quoted concat artifact; quoted items already handled.
        # Still, we allow mixed lines and extract image-like substrings below.

        # If the entire line looks like a single image path/filename (even with spaces), keep it.
        if re.search(r"\.(jpg|jpeg|png|webp)$", line, flags=re.IGNORECASE):
            _add(line)
            continue

        # Otherwise, extract any image-like substrings from the line.
        # This supports occasional lines containing multiple tokens.
        for m in re.finditer(r"[^'\"\r\n]+?\.(?:jpg|jpeg|png|webp)", line, flags=re.IGNORECASE):
            _add(m.group(0))

    return combined

# ----------------------------
# Setup logging
# ----------------------------

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

# ----------------------------
# Output helpers
# ----------------------------

def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def write_internal_report_json(output_dir: Path, report: dict) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = output_dir / f"preflight_S226_internal_{timestamp}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return filename

def write_client_advisory_csv(output_dir: Path, advisory_rows: list[dict]) -> Path:
    import csv
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = output_dir / f"preflight_S226_client_advisory_{timestamp}.csv"
    if advisory_rows:
        keys = list(advisory_rows[0].keys())
    else:
        keys = []
    with open(filename, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in advisory_rows:
            writer.writerow(row)
    return filename

# ----------------------------
# Core utilities and helpers
# ----------------------------

PRODUCT_ID_RE = re.compile(
    r"^S(?P<capsule>\d{3})-(?P<style>\d{4})\s+(?P<style_code>[A-Z0-9]+)\s+(?P<color_code>\d{6})\s+(?P<color_name>.+)$"
)

def extract_product_id(tags: str) -> str | None:
    for tag in str(tags).split(","):
        tag = tag.strip()
        m = PRODUCT_ID_RE.match(tag)
        if m and m.group("capsule") == CAPSULE_CODE[1:]:
            return tag
    # If tags present but none match capsule, treat as malformed for this capsule
    # But only if tags non-empty
    if tags and any(PRODUCT_ID_RE.match(t.strip()) for t in str(tags).split(",")):
        return None
    return None

def parse_product_id(product_id: str) -> dict | None:
    m = PRODUCT_ID_RE.match(product_id)
    if not m:
        return None
    return m.groupdict()

def derive_cpi(product_id: str) -> str:
    parsed = parse_product_id(product_id)
    if not parsed:
        return ""
    return f"{parsed['style']}-{parsed['color_code']}"

def is_valid_season_code(value: str) -> bool:
    if not isinstance(value, str):
        return False
    return bool(re.match(r"^(SS\d{2}|S\d{3})$", value.strip()))

def bulletize_percent_content(text: str) -> tuple[str, int]:
    pattern = re.compile(r"(\d+)%\s*([A-Za-z][A-Za-z\s\-]*)")
    matches = pattern.findall(text)
    lines = []
    for pct, mat in matches:
        mat_clean = " ".join(mat.strip().title().split())
        lines.append(f"- {pct}% {mat_clean}")
    return ("\n".join(lines), len(matches))

def normalize_color(value: str) -> str:
    if not isinstance(value, str):
        return ""
    v = value.strip()
    # Remove leading 6-digit code if present
    if re.match(r"^\d{6}\s+", v):
        v = re.sub(r"^\d{6}\s+", "", v)
    v = " ".join(v.split())
    return v.upper()

def is_accessory_from_master(source_row: pd.Series) -> bool:
    cat_code = source_row.get("CATEGORY CODE")
    if pd.notna(cat_code):
        try:
            cat_int = int(cat_code)
            if cat_int in {9, 70, 71, 76, 79}:
                return True
        except Exception:
            pass
    # Check Product Type column if present
    prod_type = source_row.get("Product Type")
    if isinstance(prod_type, str):
        norm_type = prod_type.strip().upper()
        if norm_type in {"BELT", "BAG", "SHOES", "JEWELRY"}:
            return True
    return False

# ----------------------------
# Image analysis helpers
# ----------------------------

def find_images_for_product(product_id: str, filenames: list[str]) -> list[str]:
    return [fn for fn in filenames if product_id in fn]

def classify_images(image_files: list[str]) -> dict:
    """Classify image files for a product.

    We classify by filename patterns, not by which input list they came from.
    - ghost: contains "ghost" in filename
    - hero: contains "hero_image" in filename
    - model: contains "model_image_" in filename
    - editorial: everything else
    """
    lower = [(f, f.lower()) for f in image_files]

    ghosts = [f for f, lo in lower if "ghost" in lo]
    heroes = [f for f, lo in lower if "hero_image" in lo]
    models = [f for f, lo in lower if "model_image_" in lo]

    # Editorials are the remainder
    classified = set(ghosts) | set(heroes) | set(models)
    editorials = [f for f in image_files if f not in classified]

    return {
        "ghosts": ghosts,
        "heroes": heroes,
        "models": models,
        "editorials": editorials,
        "total": len(image_files),
    }

# ----------------------------
# Preflight per product
# ----------------------------

def preflight_product(
    handle: str,
    group_df: pd.DataFrame,
    master_df: pd.DataFrame,
    ghost_files: list[str],
    model_files: list[str]
) -> dict:

    result = {
        "handle": handle,
        "product_id": None,
        "cpi": None,
        "title": None,
        "is_accessory": False,
        "status": "GO",
        "errors": [],
        "warnings": [],
        "details_source": "NONE",
        "details_ready": False,
        "details_bullet_count": 0,
        "body_status": None,
        "variant_price_present": False,
        "season_code_valid": False,
        "category_code_known": False,
        "color_match": False,
        "ghost_count": 0,
        "hero_count": 0,
        "model_count": 0,
        "editorial_count": 0,
        "total_images": 0,
        "child_row_count": 0,
        "model_overflow_required": 0,
        "image_status": None,
        "client_recommendation": None,
    }

    # Parent rows: Title notna and not empty string
    parent_rows = group_df[group_df["Title"].notna() & (group_df["Title"].str.strip() != "")]
    if len(parent_rows) == 0:
        result["errors"].append("Missing parent row")
        result["status"] = "NO-GO"
        result["client_recommendation"] = "Hold – investigate"
        return result
    if len(parent_rows) > 1:
        result["errors"].append("Multiple parent rows")
        result["status"] = "NO-GO"
        result["client_recommendation"] = "Hold – investigate"
        return result

    parent = parent_rows.iloc[0]
    result["title"] = parent.get("Title")

    # Wholesale-only products (WS Buy) are excluded from DTC
    tags_str = str(parent.get("Tags", ""))
    if "WS Buy" in tags_str:
        result.update({
            "status": "SKIP",
            "client_recommendation": "Wholesale only – excluded from DTC",
            "image_status": "N/A",
        })
        result["warnings"].append("Wholesale product (WS Buy) – skipped")
        return result

    # Product ID extraction and validation
    tags = parent.get("Tags", "")
    product_id = extract_product_id(tags)
    if product_id is None:
        # Check if tags exist but none match regex for this capsule
        if tags and any(PRODUCT_ID_RE.match(t.strip()) for t in str(tags).split(",")):
            result["errors"].append("Malformed Product ID tag")
        else:
            result["errors"].append("Missing Product ID tag")
        result["status"] = "NO-GO"
        result["client_recommendation"] = "Hold – investigate"
        return result

    result["product_id"] = product_id
    result["cpi"] = derive_cpi(product_id)

    # Masterfile join
    if product_id not in master_df.index:
        result["errors"].append("Product ID not found in masterfile")
        result["status"] = "NO-GO"
        result["client_recommendation"] = "Hold – investigate"
        return result

    source = master_df.loc[product_id]

    # Accessory determination
    result["is_accessory"] = is_accessory_from_master(source)

    # Pricing sanity
    variant_price = parent.get("Variant Price")
    variant_price_present = pd.notna(variant_price)
    result["variant_price_present"] = variant_price_present
    if not variant_price_present:
        result["errors"].append("Missing Variant Price")

    # Details readiness
    product_details = source.get("PRODUCT DETAILS")
    textile_content = source.get("Textile Content")
    fabric_content = source.get("Fabric Content")

    details_source = "NONE"
    details_ready = False
    details_bullet_count = 0

    if isinstance(product_details, str) and product_details.strip():
        details_source = "PRODUCT_DETAILS"
        details_ready = True
        # Count lines starting with dash
        details_bullet_count = sum(1 for line in product_details.splitlines() if line.strip().startswith("-"))
    elif isinstance(textile_content, str) and textile_content.strip():
        details_source = "TEXTILE_CONTENT"
        bulletized, count = bulletize_percent_content(textile_content)
        details_bullet_count = count
        if count == 0:
            result["warnings"].append("Textile Content present but could not parse percentages")
            details_ready = False
        else:
            details_ready = True
    elif isinstance(fabric_content, str) and fabric_content.strip():
        details_source = "FABRIC_CONTENT"
        bulletized, count = bulletize_percent_content(fabric_content)
        details_bullet_count = count
        if count == 0:
            result["warnings"].append("Fabric Content present but could not parse percentages")
            details_ready = False
        else:
            details_ready = True
    else:
        result["warnings"].append("No content for Details metafield")

    result["details_source"] = details_source
    result["details_ready"] = details_ready
    result["details_bullet_count"] = details_bullet_count

    # Body readiness
    body_html = parent.get("Body (HTML)")
    product_desc = source.get("Product Description")

    if isinstance(body_html, str) and body_html.strip():
        result["body_status"] = "BODY_AUTHORITATIVE"
    elif isinstance(product_desc, str) and product_desc.strip():
        result["body_status"] = "BODY_WRITE_OK"
    else:
        result["body_status"] = "BODY_MISSING"
        result["warnings"].append("No Body (HTML) or Product Description")

    # Season code validation
    season_code = source.get("SEASON CODE")
    season_code_valid = False
    if isinstance(season_code, str) and is_valid_season_code(season_code):
        season_code_valid = True
    else:
        result["warnings"].append("Invalid or missing SEASON CODE")
    result["season_code_valid"] = season_code_valid

    # Category code known (with knit fallback)
    category_code_known = False
    category_code = source.get("CATEGORY CODE")

    if pd.notna(category_code):
        try:
            cat_int = int(category_code)

            # Knitwear sentinel → defer to KNIT CATEGORY CODE
            if cat_int == 8:
                knit_code = source.get("KNIT CATEGORY CODE")
                if pd.notna(knit_code):
                    try:
                        knit_int = int(knit_code)
                        if knit_int in CATEGORY_TAGS_MAP:
                            category_code_known = True
                        else:
                            result["warnings"].append("Unknown KNIT CATEGORY CODE")
                    except Exception:
                        result["warnings"].append("Unknown KNIT CATEGORY CODE")
                else:
                    result["warnings"].append("Unknown KNIT CATEGORY CODE")

            # Non-knit category
            elif cat_int in CATEGORY_TAGS_MAP:
                category_code_known = True
            else:
                result["warnings"].append("Unknown CATEGORY CODE")

        except Exception:
            result["warnings"].append("Unknown CATEGORY CODE")
    else:
        result["warnings"].append("Unknown CATEGORY CODE")

    result["category_code_known"] = category_code_known

    # Color match
    parsed_pid = parse_product_id(product_id)
    color_name_pid = parsed_pid.get("color_name") if parsed_pid else ""
    color_pid_norm = normalize_color(color_name_pid)
    master_color = source.get("Colour")
    if isinstance(master_color, str) and master_color.strip():
        master_color_norm = normalize_color(master_color)
        color_match = (color_pid_norm == master_color_norm)
        if not color_match:
            result["warnings"].append("Colour mismatch between Product ID and masterfile")
    else:
        color_match = False
        result["warnings"].append("Missing Colour")
    result["color_match"] = color_match

    # Image analysis
    # IMPORTANT: do not trust that ghost/model lists are cleanly separated.
    # Some files may contain mixed image types. Combine and classify by pattern.
    all_image_pool = list(dict.fromkeys(ghost_files + model_files))
    product_images = find_images_for_product(product_id, all_image_pool)

    classified = classify_images(product_images)

    ghost_count = len(classified["ghosts"])
    hero_count = len(classified["heroes"])
    model_count = len(classified["models"])
    editorial_count = len(classified["editorials"])
    total_images = classified["total"]

    result["ghost_count"] = ghost_count
    result["hero_count"] = hero_count
    result["model_count"] = model_count
    result["editorial_count"] = editorial_count
    result["total_images"] = total_images

    # Child row count: all rows except parent
    child_row_count = len(group_df) - 1
    result["child_row_count"] = child_row_count

    non_ghost_count = hero_count + model_count + editorial_count
    model_overflow_required = max(0, non_ghost_count - child_row_count)
    result["model_overflow_required"] = model_overflow_required
    if model_overflow_required > 0:
        result["warnings"].append(f"Image overflow: {model_overflow_required} additional rows required")

    # Ghost image requirement
    if ghost_count == 0:
        result["errors"].append("Missing ghost image")

    if ghost_count > 1:
        result["warnings"].append("Multiple ghost images found")

    # Image position plan simulation
    # planned_positions: ghost at 1, then all non-ghost images (hero, model, editorial) starting at 2
    planned_positions = [1] + list(range(2, 2 + non_ghost_count))
    # Validate positions contiguous, unique, start at 1
    valid_positions = True
    if not planned_positions:
        valid_positions = False
    else:
        if planned_positions[0] != 1:
            valid_positions = False
        if len(planned_positions) != len(set(planned_positions)):
            valid_positions = False
        # Check contiguous increasing by 1
        for i in range(1, len(planned_positions)):
            if planned_positions[i] != planned_positions[i-1] + 1:
                valid_positions = False
                break

    image_status = None
    invalid_position_error = False
    if not valid_positions:
        result["errors"].append("Invalid image position plan")
        invalid_position_error = True

    if invalid_position_error:
        image_status = "IMAGE_INVALID"
    elif ghost_count == 0 or total_images == 0:
        image_status = "IMAGE_INCOMPLETE"
    elif ghost_count >= 1 and non_ghost_count == 0:
        image_status = "IMAGE_MINIMAL"
    elif ghost_count >= 1 and non_ghost_count >= 1:
        image_status = "IMAGE_READY"
    else:
        image_status = "IMAGE_INCOMPLETE"

    result["image_status"] = image_status

    # Status and client recommendation
    if result["errors"]:
        result["status"] = "NO-GO"
    else:
        result["status"] = "GO"

    if result["status"] == "NO-GO" and "Missing ghost image" in result["errors"]:
        result["client_recommendation"] = "Hold – ghost image required"
    elif image_status == "IMAGE_INVALID":
        result["client_recommendation"] = "Hold – investigate"
    elif image_status == "IMAGE_MINIMAL":
        result["client_recommendation"] = "Upload (minimal imagery)"
    elif result["status"] == "GO":
        result["client_recommendation"] = "Upload"
    else:
        result["client_recommendation"] = "Hold – investigate"

    return result

# ----------------------------
# Runner
# ----------------------------

def run_preflight(
    shopify_csv: str,
    masterfile_csv: str,
    ghost_file: str,
    model_file: str
):
    shopify_df = load_shopify_export(shopify_csv)
    master_df = load_masterfile(masterfile_csv)
    ghost_files = load_filenames(ghost_file)
    model_files = load_filenames(model_file)

    logging.warning("Combine step sorts by Handle and Image Position; rows with blank Image Position (variants) may move after image rows.")

    results = []

    for handle, group in shopify_df.groupby("Handle"):
        results.append(
            preflight_product(
                handle,
                group,
                master_df,
                ghost_files,
                model_files
            )
        )

    df = pd.DataFrame(results)

    total_products = len(df)
    go_count = (df["status"] == "GO").sum()
    no_go_count = (df["status"] == "NO-GO").sum()
    skip_count = (df["status"] == "SKIP").sum()
    warning_products_count = (df["warnings"].apply(len) > 0).sum()
    error_products_count = (df["errors"].apply(len) > 0).sum()

    internal_report = {
        "capsule": CAPSULE_CODE,
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "summary": {
            "total_products": total_products,
            "go_count": int(go_count),
            "no_go_count": int(no_go_count),
            "skip_count": int(skip_count),
            "warning_products_count": int(warning_products_count),
            "error_products_count": int(error_products_count),
        },
        "products": results,
    }

    client_advisory_rows = []
    for r in results:
        client_advisory_rows.append({
            "handle": r.get("handle"),
            "product_id": r.get("product_id"),
            "cpi": r.get("cpi"),
            "title": r.get("title"),
            "status": r.get("status"),
            "client_recommendation": r.get("client_recommendation"),
            "errors": "; ".join(r.get("errors", [])),
            "warnings": "; ".join(r.get("warnings", [])),
        })

    return df, internal_report, client_advisory_rows

# ----------------------------
# Main
# ----------------------------

def main() -> None:
    setup_logging()
    ensure_output_dir(OUTPUT_DIR)
    df, internal_report, client_advisory_rows = run_preflight(
        str(SHOPIFY_EXPORT),
        str(MASTERFILE),
        str(GHOST_FILES),
        str(MODEL_FILES)
    )
    internal_path = write_internal_report_json(OUTPUT_DIR, internal_report)
    client_path = write_client_advisory_csv(OUTPUT_DIR, client_advisory_rows)

    total = internal_report["summary"]["total_products"]
    go = internal_report["summary"]["go_count"]
    no_go = internal_report["summary"]["no_go_count"]

    logging.info(f"Preflight completed: Total={total}, GO={go}, NO-GO={no_go}")
    logging.info(f"Internal report saved to: {internal_path}")
    logging.info(f"Client advisory saved to: {client_path}")

    if no_go > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == '__main__':
    main()