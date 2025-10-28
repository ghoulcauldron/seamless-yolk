import pandas as pd
import pathlib
import argparse
import re
import json
from collections import Counter
import math # For checking NaN

# --- Logic copied/adapted from enrich_shopify_import.py ---

# --- Filename Processing Logic ---
def get_base_filename(filename: str) -> str:
    """Removes standard suffixes like _ghost_..., _model_..., _hero_..., _swatch..."""
    if not filename or not isinstance(filename, str): return ""
    suffixes = [
        r"_ghost(?:_\d+)?", r"_model_image(?:_\d+)?(?:_\d+)?",
        r"_hero_image(?:__\d+)?", r"_swatch"
    ]
    suffix_pattern = "|".join(suffixes)
    match = re.match(rf"^(.*?)({suffix_pattern})\.jpg$", filename, flags=re.IGNORECASE)
    if match:
        base = match.group(1)
        if base.endswith("_FINAL"): base = base[:-len("_FINAL")]
        return base.strip()
    else:
        base = re.sub(r"_FINAL\.jpg$", ".jpg", filename, flags=re.IGNORECASE)
        return base.rsplit('.', 1)[0].strip() if '.' in base else base.strip()

def check_filename_consistency(filenames: list) -> tuple[bool, str | None, list]:
    """Checks if all filenames share the same base pattern."""
    if not filenames: return True, None, []
    valid_filenames = [f for f in filenames if f and isinstance(f, str)]
    if len(valid_filenames) <= 1: return True, None, []
    base_names = [get_base_filename(f) for f in valid_filenames]
    if not base_names: return True, None, []
    pattern_counter = Counter(base_names)
    most_common_items = pattern_counter.most_common()
    most_common_pattern = sorted(most_common_items, key=lambda x: (-x[1], x[0]))[0][0]
    inconsistent_filenames_data = [
        {"filename": original_fn, "base": base_fn}
        for original_fn, base_fn in zip(valid_filenames, base_names)
        if base_fn != most_common_pattern
    ]
    all_match = not bool(inconsistent_filenames_data)
    return all_match, most_common_pattern, inconsistent_filenames_data

# --- Tag Generation Logic ---
CATEGORY_TAGS_MAP = {
    1: "collection_ready-to-wear, collection_jackets, collection_new-arrivals", 2: "collection_ready-to-wear, collection_jackets, collection_new-arrivals",
    3: "collection_ready-to-wear, collection_dresses, collection_new-arrivals", 4: "collection_ready-to-wear, collection_tops, collection_new-arrivals",
    5: "collection_ready-to-wear, collection_skirts, collection_new-arrivals", 6: "collection_ready-to-wear, collection_pants, collection_new-arrivals",
    9: "collection_accessories, collection_SHOES, collection_new-arrivals", 70: "collection_accessories, collection_Bags, collection_new-arrivals",
    71: "collection_accessories, collection_Bags, collection_new-arrivals", 76: "collection_accessories, collection_belts, collection_new-arrivals",
    79: "collection_accessories, collection_Jewelry, collection_new-arrivals", 81: "collection_ready-to-wear, collection_knitwear, collection_jackets, collection_new-arrivals",
    82: "collection_ready-to-wear, collection_knitwear, collection_jackets, collection_new-arrivals", 83: "collection_ready-to-wear, collection_knitwear, collection_dresses, collection_new-arrivals",
    84: "collection_ready-to-wear, collection_knitwear, collection_tops, collection_new-arrivals", 85: "collection_ready-to-wear, collection_knitwear, collection_skirts, collection_new-arrivals",
    86: "collection_ready-to-wear, collection_knitwear, collection_pants, collection_new-arrivals", 88: "collection_ready-to-wear, collection_knitwear, collection_tops, collection_new-arrivals"
}
CPI_PATTERN_FROM_PRODUCT_ID = re.compile(r"(\d{3,5})\s+[A-Z0-9]+\s+(\d{6})")

def extract_product_id_from_tags(tags_str: str) -> str | None:
    if not isinstance(tags_str, str): return None
    for tag in str(tags_str).split(','):
        tag = tag.strip()
        if tag.count(' ') >= 2: return tag
    return None

def extract_cpi_from_product_id(product_id: str) -> str | None:
    if not product_id: return None
    match = CPI_PATTERN_FROM_PRODUCT_ID.search(product_id)
    if match: style, color = match.groups(); return f"{style}-{color}"
    return None

def get_expected_tags(source_record):
    """Replicates the tag building logic for validation."""
    expected_tags = set()
    category_code_to_use = None
    try:
        knit_cat = source_record.get('KNIT CATEGORY CODE')
        if pd.notna(knit_cat) and str(knit_cat).strip().lower() not in ['na', 'n/a', '']:
             category_code_to_use = int(knit_cat)
    except (ValueError, TypeError): pass
    if category_code_to_use is None:
        try:
            cat_code = source_record.get('CATEGORY CODE')
            if pd.notna(cat_code): category_code_to_use = int(cat_code)
        except (ValueError, TypeError): pass

    if pd.notna(source_record.get('Description')): expected_tags.add(f"style_{source_record['Description'].title()}")
    if pd.notna(source_record.get('SEASON CODE')): expected_tags.add(str(source_record['SEASON CODE']).replace('S1', 'SS'))
    if pd.notna(source_record.get('Colour')): expected_tags.add(f"color_{' '.join(str(source_record['Colour']).split(' ')[1:]).lower()}")
    if category_code_to_use and category_code_to_use in CATEGORY_TAGS_MAP:
        expected_tags.update([t.strip() for t in CATEGORY_TAGS_MAP[category_code_to_use].split(',')])
    return expected_tags

# --- Image Sorting Logic ---
def sort_images(images, is_accessory):
    """Sorts image records based on type and filename, EXCLUDING swatches."""
    def sort_key(img_record):
        filename = img_record.get('filename', '')
        asset_type = img_record.get('asset_type', '')
        if is_accessory:
            return (0, filename) if asset_type == 'ghosts' else (1, filename)
        else: # RTW
            if asset_type == 'ghosts': return (0, filename)
            if 'hero_image' in filename: return (1, filename)
            model_match = re.search(r'model_image_(\d+)', filename)
            if model_match:
                try: return (2, int(model_match.group(1)), filename)
                except ValueError: return (3, filename)
            return (3, filename)
    images_to_sort = [img for img in images if img.get('filename') and img.get('asset_type') != 'swatches']
    return sorted(images_to_sort, key=sort_key)

# --- Constants ---
CDN_PREFIX = 'https://cdn.shopify.com/s/files/1/0148/9561/2004/files/'
EXPECTED_BLANK_COLS = ['Title', 'Body (HTML)', 'Tags', 'Published', 'Option1 Name', 'Option1 Value', 'Option2 Name', 'Option2 Value', 'Option3 Name', 'Option3 Value', 'Variant SKU', 'Variant Barcode', 'Image Alt Text', 'SEO Title', 'SEO Description'] # Add more as needed

# --- Validation Functions ---

def load_override_handles(override_file_path: pathlib.Path) -> set:
    """Loads handles marked for override due to inconsistent filenames."""
    override_handles = set()
    if not override_file_path or not override_file_path.exists():
        print("  > INFO: Override file not provided or not found. No overrides considered.")
        return override_handles
    try:
        df_override = pd.read_csv(override_file_path, dtype=str).fillna('')
        required_cols = ['Handle', 'Override to Import', 'Inconsistent Filenames']
        if not all(col in df_override.columns for col in required_cols):
             print(f"  > WARNING: Override file missing required columns ({required_cols}). Overrides ignored.")
             return override_handles

        df_override_filtered = df_override[
            (df_override['Override to Import'].str.lower() == 'x') &
            (df_override['Inconsistent Filenames'].str.lower() == 'x')
        ]
        override_handles = set(df_override_filtered['Handle'].astype(str).str.strip())
        print(f"  > Loaded {len(override_handles)} handles to override for inconsistent filename checks.")
    except Exception as e:
        print(f"  > WARNING: Could not read override file. Overrides ignored. Error: {e}")
    return override_handles

def check_image_sequence_and_rows(df: pd.DataFrame, manifest_map: dict, handle_to_cpi_map: dict, override_report_data: dict, override_handles: set) -> list:
    """Validates image positions, ghost rules, overrides, and new row structure."""
    errors = []

    for handle, group in df.groupby('Handle'):
        cpi = handle_to_cpi_map.get(handle)
        if not cpi:
            errors.append({'error_type': 'Image Validation Skipped (No CPI)', 'handle': handle, 'details': f"Cannot validate images for handle '{handle}' as CPI mapping is missing."})
            continue

        images_from_manifest = manifest_map.get(cpi, [])
        if not images_from_manifest:
            # If manifest has no images, the combined file should also have none
            if not group['Image Src'].isna().all():
                 errors.append({'error_type': 'Unexpected Images Found', 'handle': handle, 'cpi': cpi, 'details': f"Manifest has no images for CPI {cpi}, but images found in combined file."})
            continue # Nothing more to check for this handle

        is_accessory = any(img.get('is_accessory', False) for img in images_from_manifest)

        # --- Simulate the expected image list ---
        # 1. Sort images from manifest
        sorted_manifest_images = sort_images(images_from_manifest, is_accessory)

        # 2. Filter ghosts (keep only first)
        expected_image_list_sim = []
        ghost_added = False
        for img in sorted_manifest_images:
            is_ghost = img.get('asset_type') == 'ghosts'
            if is_ghost:
                if not ghost_added:
                    expected_image_list_sim.append(img)
                    ghost_added = True
            else:
                expected_image_list_sim.append(img)

        # 3. Apply override insertion (if applicable)
        filenames_to_check = [img['filename'] for img in images_from_manifest if img.get('asset_type') in ['ghosts', 'editorials'] and img.get('filename')]
        is_consistent, _, inconsistent_data = check_filename_consistency(filenames_to_check)

        if not is_consistent and handle in override_handles:
            override_info = override_report_data.get(handle)
            if override_info:
                inconsistent_filenames = {item['filename'] for item in inconsistent_data}
                # Get NON-GHOST inconsistent files
                files_to_insert_raw = [
                    rec for rec in images_from_manifest
                    if rec.get('filename') in inconsistent_filenames and rec.get('asset_type') != 'ghosts'
                ]

                if files_to_insert_raw:
                    target_pos_str = override_info['position']
                    insert_index = -1
                    num_current_images = len(expected_image_list_sim)
                    num_to_insert = len(files_to_insert_raw)

                    # Calculate insert index (same logic as enrich script)
                    if target_pos_str == 'first': insert_index = 0
                    elif target_pos_str == 'last': insert_index = num_current_images
                    elif target_pos_str.isdigit():
                        target_pos_num = int(target_pos_str)
                        if 1 <= target_pos_num <= num_current_images + num_to_insert: insert_index = target_pos_num - 1
                        else: insert_index = num_current_images # Default last
                    else: insert_index = num_current_images # Default last

                    if insert_index != -1:
                        insert_index = max(0, min(insert_index, num_current_images))
                        temp_is_acc_override = any(img.get('is_accessory', False) for img in files_to_insert_raw + expected_image_list_sim)
                        sorted_files_to_insert = sort_images(files_to_insert_raw, temp_is_acc_override)
                        expected_image_list_sim = expected_image_list_sim[:insert_index] + sorted_files_to_insert + expected_image_list_sim[insert_index:]
            # else: Should not happen if handle is in override_handles based on how override_report_data is built

        # --- Compare actual vs expected ---
        actual_images = group.sort_values('Image Position')[['Image Src', 'Image Position']].dropna(subset=['Image Position'])

        # Check lengths
        if len(actual_images) != len(expected_image_list_sim):
             errors.append({'error_type': 'Image Count Mismatch', 'handle': handle, 'cpi': cpi,
                           'details': f"Expected {len(expected_image_list_sim)} images based on manifest/rules, but found {len(actual_images)} rows with images."})

        # Check sequence and filenames (up to the minimum length)
        min_len = min(len(actual_images), len(expected_image_list_sim))
        for i in range(min_len):
            actual_pos = actual_images.iloc[i]['Image Position']
            actual_src = actual_images.iloc[i]['Image Src']
            expected_pos = i + 1
            expected_filename = expected_image_list_sim[i]['filename'].replace(' ', '_')
            expected_src = CDN_PREFIX + expected_filename

            if actual_pos != expected_pos:
                 errors.append({'error_type': 'Image Position Incorrect', 'handle': handle, 'cpi': cpi,
                               'details': f"Row {i}: Expected Position {expected_pos}, Found {actual_pos}."})
            if actual_src != expected_src:
                 errors.append({'error_type': 'Image Source Mismatch', 'handle': handle, 'cpi': cpi,
                               'details': f"Row {i} (Pos {actual_pos}): Expected Src '{expected_src}', Found '{actual_src}'."})

        # Check structure of potentially new rows (those without a Title)
        child_rows = group[group['Title'].isna() | (group['Title'] == '')]
        original_variant_count = len(group) - len(child_rows) # Simplistic estimate
        
        for index, row in child_rows.iterrows():
             # Check if this row corresponds to an image beyond the original variants
             img_pos = row['Image Position']
             # Check if Image Position is valid number before comparison
             if pd.notna(img_pos):
                 try:
                     # Check if this row represents a newly added image row
                     # Rough check: if its position > initial number of rows (parent + variants)
                     # Note: This isn't perfect if variants were deleted, but best guess here.
                     # A better check might be based on whether core variant info is missing.
                     is_likely_new_row = not any(pd.notna(row[col]) and row[col] != '' for col in ['Option1 Value', 'Variant SKU', 'Variant Barcode'] if col in row)

                     if is_likely_new_row:
                         # Check if other columns expected to be blank are indeed blank
                         for col in EXPECTED_BLANK_COLS:
                             if col in row and pd.notna(row[col]) and row[col] != '':
                                 errors.append({'error_type': 'Unexpected Data in New Row', 'handle': handle, 'row_index': index, 'image_pos': img_pos,
                                                'details': f"Likely new image row (Pos {img_pos}) has non-blank data in column '{col}': '{row[col]}'."})
                 except TypeError:
                      errors.append({'error_type': 'Invalid Image Position Type', 'handle': handle, 'row_index': index,
                                     'details': f"Image Position '{img_pos}' is not a valid number for comparison."})

    return errors


def check_ghost_hero_model_rules(df: pd.DataFrame, manifest_map: dict, handle_to_cpi_map: dict) -> list:
    """Validates Ghost position and Hero/Model existence for RTW."""
    errors = []
    for handle, group in df.groupby('Handle'):
        cpi = handle_to_cpi_map.get(handle)
        if not cpi: continue # Skip if no CPI mapping

        images_from_manifest = manifest_map.get(cpi, [])
        if not images_from_manifest: continue # Skip if no manifest images

        is_accessory = any(img.get('is_accessory', False) for img in images_from_manifest)

        # 1. Ghost Check (All Products)
        pos1_row = group[group['Image Position'] == 1]
        if pos1_row.empty:
            if not group['Image Src'].isna().all(): # Only error if images ARE expected
                 errors.append({'error_type': 'Missing Image at Position 1', 'handle': handle, 'cpi': cpi, 'details': f"No image found at Position 1."})
        else:
            pos1_src = pos1_row.iloc[0]['Image Src']
            if pd.notna(pos1_src):
                pos1_filename = pos1_src.replace(CDN_PREFIX, '')
                # Find corresponding manifest entry
                manifest_entry = next((img for img in images_from_manifest if img['filename'].replace(' ', '_') == pos1_filename), None)
                if not manifest_entry or manifest_entry.get('asset_type') != 'ghosts':
                     errors.append({'error_type': 'Image at Position 1 Not Ghost', 'handle': handle, 'cpi': cpi, 'filename': pos1_filename,
                                   'details': f"Image '{pos1_filename}' at Position 1 is not classified as 'ghosts' in the manifest."})

        # 2. Hero/Model Check (RTW Only)
        if not is_accessory:
            manifest_filenames = {img['filename'].replace(' ', '_') for img in images_from_manifest}
            has_hero = any('hero_image' in fn for fn in manifest_filenames)
            has_model = any('model_image' in fn for fn in manifest_filenames)

            # Check if hero/model images from manifest are actually present in the group's Image Src
            group_filenames = set(group['Image Src'].dropna().str.replace(CDN_PREFIX, ''))

            found_hero_in_group = any('hero_image' in fn for fn in group_filenames)
            found_model_in_group = any('model_image' in fn for fn in group_filenames)

            if has_hero and not found_hero_in_group:
                 errors.append({'error_type': 'Missing Hero Image (RTW)', 'handle': handle, 'cpi': cpi, 'details': f"Manifest lists hero image(s), but none found assigned in the combined file."})
            if has_model and not found_model_in_group:
                 errors.append({'error_type': 'Missing Model Image (RTW)', 'handle': handle, 'cpi': cpi, 'details': f"Manifest lists model image(s), but none found assigned in the combined file."})
            # Also check the original guardrail condition: if manifest *should* have them
            if not has_hero:
                 errors.append({'error_type': 'Missing Hero Image from Manifest (RTW)', 'handle': handle, 'cpi': cpi, 'details': f"RTW product is missing a hero image in the manifest."})
            if not has_model:
                 errors.append({'error_type': 'Missing Model Image from Manifest (RTW)', 'handle': handle, 'cpi': cpi, 'details': f"RTW product is missing a model image in the manifest."})


    return errors


def check_internal_structure(df: pd.DataFrame) -> list:
    """Runs internal validation checks (Contiguous blocks, Parent/Child, Unique IDs)."""
    errors = []
    # Check Contiguous Handle Blocks
    last_handle = None
    block_start_index = 0
    for index, row in df.iterrows():
        current_handle = row['Handle']
        if last_handle is not None and current_handle != last_handle:
            # Check if the previous block was contiguous
            prev_group_indices = df.loc[block_start_index : index-1].index
            if len(prev_group_indices) > 0:
                 min_idx, max_idx = prev_group_indices.min(), prev_group_indices.max()
                 if (max_idx - min_idx + 1) != len(prev_group_indices):
                     errors.append({'error_type': 'Non-Contiguous Handle Block', 'handle': last_handle, 'details': f"Rows for handle '{last_handle}' are not grouped contiguously."})
            block_start_index = index
        last_handle = current_handle
    # Check the last block
    if last_handle is not None:
         last_group_indices = df.loc[block_start_index:].index
         if len(last_group_indices) > 0:
             min_idx, max_idx = last_group_indices.min(), last_group_indices.max()
             if (max_idx - min_idx + 1) != len(last_group_indices):
                  errors.append({'error_type': 'Non-Contiguous Handle Block', 'handle': last_handle, 'details': f"Rows for handle '{last_handle}' are not grouped contiguously."})


    # Check Parent/Child Structure
    for handle, group in df.groupby('Handle'):
        parent_rows = group[group['Title'].notna() & (group['Title'] != '')]
        child_rows = group[group['Title'].isna() | (group['Title'] == '')]

        if len(parent_rows) == 0:
            errors.append({'error_type': 'Missing Parent Row', 'handle': handle, 'details': f"No parent row (with a Title) found."})
            continue
        if len(parent_rows) > 1:
            errors.append({'error_type': 'Multiple Parent Rows', 'handle': handle, 'details': f"Multiple parent rows found."})

        # Check child rows
        for _, child in child_rows.iterrows():
             # Body HTML should be blank on non-parent rows
             if pd.notna(child['Body (HTML)']) and str(child['Body (HTML)']).strip() != '':
                 errors.append({'error_type': 'Body HTML on Child Row', 'handle': handle, 'sku': child.get('Variant SKU'), 'details': f"Child variant has Body (HTML)."})
             # Tags should generally be blank on non-parent rows (unless newly added image rows)
             is_likely_new_row = not any(pd.notna(child[col]) and child[col] != '' for col in ['Option1 Value', 'Variant SKU', 'Variant Barcode'] if col in child)
             if not is_likely_new_row and pd.notna(child['Tags']) and str(child['Tags']).strip() != '':
                  errors.append({'error_type': 'Tags on Child Row', 'handle': handle, 'sku': child.get('Variant SKU'), 'details': f"Child variant row has Tags populated."})

    # Check Unique SKU (ignore blanks)
    populated_skus = df[df['Variant SKU'].notna() & (df['Variant SKU'] != '')]['Variant SKU']
    if populated_skus.duplicated().any():
        dupe_skus = populated_skus[populated_skus.duplicated()].unique().tolist()
        errors.append({'error_type': 'Duplicate Variant SKU', 'details': f"Duplicate SKUs found: {dupe_skus}"})

    # Check Unique Barcode (ignore blanks)
    populated_barcodes = df[df['Variant Barcode'].notna() & (df['Variant Barcode'] != '')]['Variant Barcode']
    if populated_barcodes.duplicated().any():
        dupe_barcodes = populated_barcodes[populated_barcodes.duplicated()].unique().tolist()
        errors.append({'error_type': 'Duplicate Variant Barcode', 'details': f"Duplicate barcodes found: {dupe_barcodes}"})

    return errors


def check_data_consistency_against_sources(df: pd.DataFrame, tracker_df: pd.DataFrame) -> list:
    """Validates Price, Details, Tags against the master tracker, skipping price checks on image-only rows and stripping details."""
    errors = []
    try:
        # Pre-process tracker for faster lookups
        tracker_df['Product ID'] = tracker_df['Product ID'].astype(str).str.strip()
        tracker_df_indexed = tracker_df.set_index('Product ID')
        # Pre-calculate expected tags for all source records
        expected_tags_map = {idx: get_expected_tags(row) for idx, row in tracker_df_indexed.iterrows()}
    except KeyError:
         errors.append({'error_type': 'Setup Failed', 'details': "Could not find 'Product ID' column in tracker."})
         return errors
    except Exception as e:
         errors.append({'error_type': 'Setup Failed', 'details': f"Error processing tracker: {e}"})
         return errors


    for handle, group in df.groupby('Handle'):
        parent_rows = group[group['Title'].notna() & (group['Title'] != '')]
        if parent_rows.empty: continue # Handled by internal structure check
        parent_row = parent_rows.iloc[0]

        # Extract Product ID carefully, handle potential NaN/None
        tags_str = parent_row.get('Tags')
        full_product_id = extract_product_id_from_tags(tags_str) if pd.notna(tags_str) else None

        if not full_product_id:
            if group['Image Src'].notna().any():
                 errors.append({'error_type': 'Missing Product ID Tag', 'handle': handle, 'details': f"Could not extract Product ID tag from parent row tags: '{tags_str}'"})
            continue

        full_product_id = full_product_id.strip()

        if full_product_id not in tracker_df_indexed.index:
            errors.append({'error_type': 'Source Record Not Found', 'handle': handle, 'product_id': full_product_id, 'details': f"Product ID '{full_product_id}' not found in tracker."})
            continue

        source_record = tracker_df_indexed.loc[full_product_id]

        # --- Validate Variant Price (Loop through all rows but skip image-only rows) ---
        try:
            expected_price_str = source_record.get('RRP (USD)')
            if pd.isna(expected_price_str) or str(expected_price_str).strip() == '':
                 expected_price = None
            else:
                 expected_price = float(expected_price_str)

            for index, row in group.iterrows():
                 # Check if this row is likely an image-only row
                 sku = row.get('Variant SKU')
                 opt1 = row.get('Option1 Value')
                 is_likely_image_row = (pd.isna(sku) or str(sku).strip() == '') and \
                                       (pd.isna(opt1) or str(opt1).strip() == '')

                 if is_likely_image_row:
                     continue # Skip price check for this row

                 # Proceed with price check only for likely variant rows
                 actual_price = row.get('Variant Price')

                 if expected_price is None:
                     if pd.notna(actual_price) and actual_price != '':
                         errors.append({
                             'error_type': 'Price Mismatch', 'handle': handle, 'sku': sku or f"RowIndex_{index}",
                             'details': f"Expected blank price based on tracker, found '{actual_price}'."})
                 elif pd.isna(actual_price) or actual_price == '' or float(actual_price) != expected_price:
                     errors.append({
                         'error_type': 'Price Mismatch', 'handle': handle, 'sku': sku or f"RowIndex_{index}",
                         'details': f"Expected price ${expected_price}, found '{actual_price}'."})

        except (ValueError, TypeError):
             errors.append({
                'error_type': 'Invalid Price in Source', 'handle': handle, 'product_id': full_product_id,
                'details': f"Tracker RRP (USD) '{source_record.get('RRP (USD)')}' is not a valid number."
            })
        except Exception as e:
            errors.append({
                'error_type': 'Price Check Error', 'handle': handle, 'product_id': full_product_id,
                'details': f"Unexpected error during price validation: {e}"
            })

        # --- Validate Details Metafield (only on parent row, ADD .strip()) ---
        expected_details = source_record.get('PRODUCT DETAILS', '')
        actual_details = parent_row.get('Details (product.metafields.altuzarra.details)', '')
        # Normalize NaN/None to empty string
        if pd.isna(expected_details): expected_details = ''
        if pd.isna(actual_details): actual_details = ''

        # --- ADDED .strip() to both sides of the comparison ---
        if str(actual_details).strip() != str(expected_details).strip():
             errors.append({
                'error_type': 'Details Metafield Mismatch', 'handle': handle,
                'details': f"Details mismatch after stripping whitespace. Expected: '{expected_details}', Found: '{actual_details}'"})
        # --- END .strip() ADDITION ---

        # --- Validate Tags (only on parent row) ---
        expected_tags = expected_tags_map.get(full_product_id, set())
        actual_tags_list = [t.strip() for t in str(tags_str).split(',') if t.strip()] if pd.notna(tags_str) else []
        actual_tags_set = set(actual_tags_list)

        missing_generated_tags = expected_tags - actual_tags_set
        if missing_generated_tags:
            errors.append({
                'error_type': 'Missing Generated Tags', 'handle': handle,
                'details': f"Parent row missing expected tags: {missing_generated_tags}"})

    return errors

# --- Main Execution ---

def main(capsule: str, input_filename: str, override_filename: str):
    base_path = pathlib.Path(f"capsules/{capsule}")
    input_file_path = base_path / f"outputs/{input_filename}"
    tracker_file_path = base_path / "inputs/SS26 for Shopify check(By Style).csv"
    manifest_path = base_path / "manifests/images_manifest.jsonl"
    override_file_path = base_path / f"outputs/{override_filename}" if override_filename else None

    all_errors = [] # Master error list

    # --- Load Files ---
    try:
        print(f"Loading target CSV: {input_file_path}...")
        df_target = pd.read_csv(input_file_path)
        # Basic cleanup
        df_target['Handle'] = df_target['Handle'].astype(str).str.strip()
        print(f"  > Loaded {len(df_target)} rows.")

        print(f"Loading tracker: {tracker_file_path}...")
        tracker_df_raw = pd.read_csv(tracker_file_path, header=None, encoding='cp1252', keep_default_na=False)
        header_row_index = tracker_df_raw[tracker_df_raw.apply(lambda r: r.astype(str).str.contains('Product ID').any(), axis=1)].index[0]
        df_tracker = tracker_df_raw.copy()
        df_tracker.columns = df_tracker.iloc[header_row_index]
        df_tracker = df_tracker.drop(df_tracker.index[:header_row_index + 1]).reset_index(drop=True)
        df_tracker.columns = df_tracker.columns.str.strip()
        print(f"  > Loaded tracker data.")

        print(f"Loading manifest: {manifest_path}...")
        manifest_recs = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
        df_manifest = pd.DataFrame(manifest_recs)
        # Create CPI -> [images] map
        manifest_map = df_manifest.groupby('cpi').apply(lambda x: x.to_dict('records')).to_dict()
        print(f"  > Loaded manifest data for {len(manifest_map)} CPIs.")

    except FileNotFoundError as e:
        print(f"❌ File not found: {e}. Cannot proceed with validation.")
        return
    except Exception as e:
        print(f"❌ Error loading files: {e}")
        return

    # --- Load Overrides ---
    print("Loading override report...")
    override_handles = load_override_handles(override_file_path)
    # Load full override data for position info
    override_report_data = {}
    if override_file_path and override_file_path.exists():
         try:
            df_override_full = pd.read_csv(override_file_path, dtype=str).fillna('')
            if all(c in df_override_full for c in ['Handle', 'Image Position Override']):
                 override_report_data = df_override_full.set_index('Handle')['Image Position Override'].str.lower().str.strip().to_dict()
         except Exception as e:
            print(f"  > WARNING: Could not fully parse override positions: {e}")


    # Build Handle-to-CPI map from the *target* dataframe (parent rows only)
    handle_to_cpi_map = {}
    for _, row in df_target[df_target['Title'].notna() & (df_target['Title'] != '')].iterrows():
        cpi = extract_cpi_from_product_id(extract_product_id_from_tags(row['Tags']))
        if cpi:
            handle_to_cpi_map[row['Handle']] = cpi

    print(f"Built Handle-to-CPI map for {len(handle_to_cpi_map)} products from target file.")


    # --- Run Validation Checks ---
    print("\nStarting Validation...")

    print("1. Running internal structure checks...")
    internal_errors = check_internal_structure(df_target)
    all_errors.extend(internal_errors)
    print(f"  > Found {len(internal_errors)} issues.")

    print("2. Running checks against source tracker (Price, Details, Tags)...")
    source_errors = check_data_consistency_against_sources(df_target, df_tracker)
    all_errors.extend(source_errors)
    print(f"  > Found {len(source_errors)} issues.")

    print("3. Running Image Sequence/Positioning checks (incl. Ghosts, Overrides, New Rows)...")
    sequence_errors = check_image_sequence_and_rows(df_target, manifest_map, handle_to_cpi_map, override_report_data, override_handles)
    all_errors.extend(sequence_errors)
    print(f"  > Found {len(sequence_errors)} issues.")

    print("4. Running Ghost Position and RTW Hero/Model Existence checks...")
    ghm_errors = check_ghost_hero_model_rules(df_target, manifest_map, handle_to_cpi_map)
    all_errors.extend(ghm_errors)
    print(f"  > Found {len(ghm_errors)} issues.")

    # --- Report Results ---
    if all_errors:
        print(f"\n❌ Validation failed with {len(all_errors)} errors:")
        # Group errors for better readability
        grouped_errors = {}
        for error in all_errors:
            error_type = error['error_type']
            grouped_errors.setdefault(error_type, []).append(error)

        for error_type, errors_list in sorted(grouped_errors.items()):
            print(f"\n--- {error_type} ({len(errors_list)} issues) ---")
            # Limit details shown per type for brevity, maybe just show handles/SKUs
            details_shown = 0
            max_details_per_type = 10
            unique_handles = set()
            for error in errors_list:
                handle = error.get('handle', 'N/A')
                unique_handles.add(handle)
                if details_shown < max_details_per_type:
                    print(f"  - Handle: {handle} | Details: {error['details']}")
                    details_shown += 1
            if len(errors_list) > max_details_per_type:
                 print(f"  ... and {len(errors_list) - max_details_per_type} more issues of this type.")
            print(f"  Affected Handles: {', '.join(sorted(list(unique_handles)))}")

        # Optional: Save errors to a file
        # error_df = pd.DataFrame(all_errors)
        # error_output_path = base_path / "outputs/validation_errors.csv"
        # error_df.to_csv(error_output_path, index=False)
        # print(f"\nError details saved to: {error_output_path}")

    else:
        print(f"\n✅ All validation rules passed successfully for {input_filename} ({len(df_target)} rows).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate combined Shopify import CSV.")
    parser.add_argument("--capsule", required=True, help="Capsule code (e.g., S126).")
    parser.add_argument(
        "--input-file",
        default="poc_shopify_import_combined.csv",
        help="Filename of the combined import CSV within the capsule's output directory (default: poc_shopify_import_combined.csv)."
    )
    parser.add_argument(
        "--override-file",
        default="data_gap_report_override.csv",
        help="Filename of the override report CSV within the capsule's output directory (default: data_gap_report_override.csv)."
    )
    args = parser.parse_args()
    main(args.capsule, args.input_file, args.override_file)
