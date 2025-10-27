import pandas as pd
import pathlib
import argparse
import re
import json

# --- NATIVE TRANSLATION of Shopify Tags Guide.csv for validation ---
CATEGORY_TAGS_MAP = {
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
    88: "collection_ready-to-wear, collection_knitwear, collection_tops, collection_new-arrivals"
}

CPI_PATTERN_FROM_PRODUCT_ID = re.compile(r"(\d{3,5})\s+[A-Z0-9]+\s+(\d{6})")


def extract_product_id_from_tags(tags_str: str) -> str | None:
    if not isinstance(tags_str, str): return None
    for tag in tags_str.split(','):
        tag = tag.strip()
        if tag.count(' ') >= 2: return tag
    return None

def extract_cpi_from_product_id(product_id: str) -> str | None:
    if not product_id: return None
    match = CPI_PATTERN_FROM_PRODUCT_ID.search(product_id)
    if match:
        style, color = match.groups()
        return f"{style}-{color}"
    return None

def get_expected_tags(source_record):
    """Replicates the tag building logic from the enrichment script for validation."""
    expected_tags = set()
    category_code_to_use = None
    
    if pd.notna(source_record.get('KNIT CATEGORY CODE')) and str(source_record['KNIT CATEGORY CODE']).strip().lower() not in ['na', 'n/a', '']:
        try: category_code_to_use = int(source_record['KNIT CATEGORY CODE'])
        except (ValueError, TypeError): pass
    
    if category_code_to_use is None and pd.notna(source_record.get('CATEGORY CODE')):
        try: category_code_to_use = int(source_record['CATEGORY CODE'])
        except (ValueError, TypeError): pass

    if pd.notna(source_record.get('Description')):
        expected_tags.add(f"style_{source_record['Description'].title()}")
    if pd.notna(source_record.get('SEASON CODE')):
        expected_tags.add(str(source_record['SEASON CODE']).replace('S1', 'SS'))
    if pd.notna(source_record.get('Colour')):
        expected_tags.add(f"color_{' '.join(str(source_record['Colour']).split(' ')[1:]).lower()}")
    
    if category_code_to_use and category_code_to_use in CATEGORY_TAGS_MAP:
        expected_tags.update([t.strip() for t in CATEGORY_TAGS_MAP[category_code_to_use].split(',')])

    return expected_tags

def check_image_validity(df: pd.DataFrame, manifest_df: pd.DataFrame, handle_to_cpi_map: dict) -> list:
    """Validates Image Src URLs against the manifest and construction rules."""
    errors = []
    CDN_PREFIX = 'https://cdn.shopify.com/s/files/1/0148/9561/2004/files/'
    
    # Create a lookup for manifest files for faster access
    manifest_lookup = manifest_df.groupby('cpi')['filename'].apply(list).to_dict()

    for index, row in df.iterrows():
        image_src = row['Image Src']
        if pd.isna(image_src) or image_src.strip() == '':
            continue # Skip blank image sources

        handle = row['Handle']
        
        # 1. Prefix Check
        if not image_src.startswith(CDN_PREFIX):
            errors.append({'error_type': 'Invalid Image URL Prefix', 'handle': handle, 'details': f"URL '{image_src}' has an incorrect prefix."})
            continue

        filename_from_url = image_src.replace(CDN_PREFIX, '')
        
        # 2. Snake Case Check
        if ' ' in filename_from_url:
            errors.append({'error_type': 'Image URL Contains Spaces', 'handle': handle, 'details': f"Filename '{filename_from_url}' in URL contains spaces instead of underscores."})

        # 3. Manifest Cross-Reference Check
        cpi = handle_to_cpi_map.get(handle)
        if not cpi:
            errors.append({'error_type': 'Cannot Validate Image (No CPI)', 'handle': handle, 'details': f"Could not map handle '{handle}' to a CPI to validate its images."})
            continue
            
        valid_filenames_for_cpi = manifest_lookup.get(cpi, [])
        # Compare by replacing spaces with underscores in the manifest filenames
        valid_shopify_filenames = [fn.replace(' ', '_') for fn in valid_filenames_for_cpi]

        if filename_from_url not in valid_shopify_filenames:
            errors.append({
                'error_type': 'Image Not Found in Manifest', 'handle': handle, 'cpi': cpi,
                'details': f"Filename '{filename_from_url}' for handle '{handle}' is not listed in the manifest for CPI '{cpi}'."
            })
            
    return errors

def check_data_consistency_against_sources(df: pd.DataFrame, tracker_df: pd.DataFrame) -> list:
    """Validates enriched data against the master tracker file."""
    errors = []
    tracker_df_indexed = tracker_df.set_index('Product ID')

    for handle, group in df.groupby('Handle'):
        # Find the parent row, which is the only one with a non-blank Title
        parent_rows = group[group['Title'].notna() & (group['Title'] != '')]
        if parent_rows.empty:
            # This case is handled by check_internal_structure, so we can skip here
            continue
        parent_row = parent_rows.iloc[0]
        full_product_id = extract_product_id_from_tags(parent_row['Tags'])

        if not full_product_id or full_product_id not in tracker_df_indexed.index:
            errors.append({
                'error_type': 'Source Record Not Found', 'handle': handle,
                'details': f"Could not find Product ID '{full_product_id}' (from tags) in the tracker CSV."
            })
            continue
        
        source_record = tracker_df_indexed.loc[full_product_id]

        # Validate Variant Price
        try:
            expected_price = float(source_record['RRP (USD)'])
            if not group['Variant Price'].eq(expected_price).all():
                errors.append({
                    'error_type': 'Price Mismatch', 'handle': handle,
                    'details': f"One or more variants do not match tracker RRP (USD) of ${expected_price}."
                })
        except (ValueError, TypeError):
             errors.append({
                'error_type': 'Invalid Price in Source', 'handle': handle,
                'details': f"RRP (USD) value '{source_record['RRP (USD)']}' for Product ID '{full_product_id}' is not a valid number."
            })
            
        # Validate Details Metafield
        expected_details = source_record['PRODUCT DETAILS']
        if pd.notna(expected_details) and parent_row.get('Details (product.metafields.altuzarra.details)') != expected_details:
             errors.append({
                'error_type': 'Details Metafield Mismatch', 'handle': handle,
                'details': f"Details metafield does not match tracker 'PRODUCT DETAILS' column."
            })

        # Validate Tags
        expected_tags = get_expected_tags(source_record)
        actual_tags = set([t.strip() for t in parent_row.get('Tags', '').split(',')])
        missing_tags = expected_tags - actual_tags
        if missing_tags:
            errors.append({
                'error_type': 'Missing Generated Tags', 'handle': handle,
                'details': f"Parent row is missing required generated tags: {', '.join(missing_tags)}"
            })

    return errors


def check_internal_structure(df: pd.DataFrame) -> list:
    """Runs all internal validation checks based on Shopify's CSV structure rules."""
    errors = []
    
    # --- FIX for FutureWarning ---
    # Replaced the deprecated .apply() method with a more modern, explicit loop.
    for handle, group in df.groupby('Handle'):
        min_idx, max_idx, count = group.index.min(), group.index.max(), len(group)
        if (max_idx - min_idx + 1) != count:
            errors.append({'error_type': 'Non-Contiguous Handle Block', 'details': f"Rows for handle '{handle}' are not grouped together."})

    # Check Parent/Child Structure and Unique IDs
    for handle, group in df.groupby('Handle'):
        parent_rows = group[group['Title'].notna() & (group['Title'] != '')]
        
        if len(parent_rows) == 0:
            errors.append({'error_type': 'Missing Parent Row', 'handle': handle, 'details': f"No parent row (with a Title) found for handle '{handle}'."})
            continue # Skip further checks for this malformed group
        if len(parent_rows) > 1:
            errors.append({'error_type': 'Multiple Parent Rows', 'handle': handle, 'details': f"Multiple parent rows (with a Title) found for handle '{handle}'."})

        # Check that child rows have blank titles
        for _, child in group[group['Title'].isna() | (group['Title'] == '')].iterrows():
            if pd.notna(child['Body (HTML)']) and child['Body (HTML)'].strip() != '':
                 errors.append({'error_type': 'Body HTML on Child Row', 'handle': handle, 'sku': child.get('Variant SKU'), 'details': f"Child variant {child.get('Variant SKU')} has Body (HTML)."})
    
    # Check Unique SKU
    if df['Variant SKU'].duplicated().any():
        dupe_skus = df[df['Variant SKU'].duplicated()]['Variant SKU'].tolist()
        errors.append({'error_type': 'Duplicate Variant SKU', 'details': f"Duplicate SKUs found: {', '.join(dupe_skus)}"})
        
    # Check Unique Barcode (if not blank)
    populated_barcodes = df[df['Variant Barcode'].notna() & (df['Variant Barcode'] != '')]
    if populated_barcodes['Variant Barcode'].duplicated().any():
        dupe_barcodes = populated_barcodes[populated_barcodes['Variant Barcode'].duplicated()]['Variant Barcode'].tolist()
        errors.append({'error_type': 'Duplicate Variant Barcode', 'details': f"Duplicate barcodes found: {', '.join(dupe_barcodes)}"})

    return errors


def main(capsule: str):
    base_path = pathlib.Path(f"capsules/{capsule}")
    ready_file_path = base_path / "outputs/poc_shopify_import_ready.csv"
    tracker_file_path = base_path / "inputs/SS26 for Shopify check(By Style).csv"
    manifest_path = base_path / "manifests/images_manifest.jsonl"

    try:
        print(f"Validating file: {ready_file_path}...")
        df_ready = pd.read_csv(ready_file_path)
        
        tracker_df_raw = pd.read_csv(tracker_file_path, header=None, encoding='cp1252', keep_default_na=False)
        header_row_index = tracker_df_raw[tracker_df_raw.apply(lambda r: r.astype(str).str.contains('Product ID').any(), axis=1)].index[0]
        df_tracker = tracker_df_raw.copy()
        df_tracker.columns = df_tracker.iloc[header_row_index]
        df_tracker = df_tracker.drop(df_tracker.index[:header_row_index + 1]).reset_index(drop=True)
        df_tracker.columns = df_tracker.columns.str.strip()
        
        manifest_recs = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
        df_manifest = pd.DataFrame(manifest_recs)

    except FileNotFoundError as e:
        print(f"❌ File not found: {e}. Please ensure capsule inputs and outputs exist.")
        return

    # Build the Handle-to-CPI map needed for image validation
    handle_to_cpi_map = {
        row['Handle']: cpi for _, row in df_ready[df_ready['Title'].notna()].iterrows()
        if (cpi := extract_cpi_from_product_id(extract_product_id_from_tags(row['Tags'])))
    }

    all_errors = [] # Initialize the master error list

    # --- Run Internal Structure Check ---
    print("Running internal structure checks...")
    internal_errors = check_internal_structure(df_ready)
    all_errors.extend(internal_errors)
    print(f"  > Internal structure checks complete ({len(internal_errors)} issues found).") # <<< ADDED LOG

    # --- Run Source Consistency Check ---
    print("Running checks against source tracker...")
    source_errors = check_data_consistency_against_sources(df_ready, df_tracker)
    all_errors.extend(source_errors)
    print(f"  > Source consistency checks complete ({len(source_errors)} issues found).") # <<< ADDED LOG

    # --- Run Basic Image Validity Check ---
    print("Running basic image validity checks (URL Prefix, Spaces, Manifest Existence)...")
    basic_image_errors = check_image_validity(df_ready, df_manifest, handle_to_cpi_map)
    all_errors.extend(basic_image_errors)
    print(f"  > Basic image validity checks complete ({len(basic_image_errors)} issues found).") # <<< ADDED LOG

    if all_errors:
        print(f"\n❌ Validation failed with {len(all_errors)} errors:")
        grouped_errors = {}
        for error in all_errors:
            error_type = error['error_type']
            if error_type not in grouped_errors:
                grouped_errors[error_type] = []
            grouped_errors[error_type].append(error)
        
        for error_type, errors_list in sorted(grouped_errors.items()):
            print(f"\n--- {error_type} ({len(errors_list)} issues) ---")
            for error in errors_list:
                print(f"  - {error['details']}")
    else:
        print(f"\n✅ All validation rules passed successfully for {capsule} ({len(df_ready)} rows).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate the structural integrity and data consistency of an enriched Shopify import CSV.")
    parser.add_argument("--capsule", required=True, help="The capsule code (e.g., S126).")
    args = parser.parse_args()
    main(args.capsule)