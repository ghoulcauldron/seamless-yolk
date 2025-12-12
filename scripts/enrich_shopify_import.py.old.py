import pandas as pd
import re
import json
import pathlib
import argparse
from datetime import datetime
from collections import Counter
import math # For checking NaN

# --- Filename Processing Logic (UPDATED for Accessories) ---
def get_base_filename(filename: str) -> str:
    """Removes standard suffixes including specific accessory types."""
    if not filename or not isinstance(filename, str): return ""

    # Define common suffixes more precisely, including accessory types
    suffixes = [
        # General RTW/Common
        r"_ghost(?:_\d+)?",
        r"_model_image(?:_\d+)?(?:_\d+)?",
        r"_hero_image(?:__\d+)?",
        r"_swatch",
        # Specific Accessory Types (often marked as 'ghosts' in manifest)
        # Added complexity to handle potential numbers and '_main' suffix
        r"_ghost_front(?:_\d+)?(?:_main)?",
        r"_ghost_detail(?:_\d+)?(?:_main)?",
        r"_ghost_side(?:_\d+)?(?:_main)?",
        r"_ghost_aerial(?:_\d+)?(?:_main)?",
        r"_Detail" # Handle filenames ending directly with _Detail.jpg
    ]
    # Remove duplicates just in case
    suffixes = list(dict.fromkeys(suffixes))
    suffix_pattern = "|".join(suffixes)

    # Regex: Look for optional _FINAL, then a known suffix, then .jpg at the END.
    # Capture the part BEFORE this pattern.
    # Added (?i) for case-insensitivity within the pattern itself
    match = re.match(rf"^(.*?)(?i:_FINAL)?({suffix_pattern})\.jpg$", filename)

    if match:
        base = match.group(1) # Part before optional _FINAL and suffix
        # Clean potential trailing _FINAL if it wasn't captured in group 1 optional part
        if base.endswith("_FINAL"):
             base = base[:-len("_FINAL")]
        return base.strip()
    else:
        # If no known suffix found, maybe it's just name.jpg or name_FINAL.jpg
        # Use re.sub for case-insensitivity here too
        base = re.sub(r"_FINAL\.jpg$", ".jpg", filename, flags=re.IGNORECASE)
        # Return name without extension, stripped
        return base.rsplit('.', 1)[0].strip() if '.' in base else base.strip()

def check_filename_consistency(filenames: list) -> tuple[bool, str | None, list]:
    """Checks if all filenames share the same base pattern using get_base_filename."""
    if not filenames: return True, None, []
    valid_filenames = [f for f in filenames if f and isinstance(f, str)]
    if len(valid_filenames) <= 1: return True, None, [] # Consistent if 0 or 1 file

    base_names = [get_base_filename(f) for f in valid_filenames]
    if not base_names: return True, None, [] # Should not happen if valid_filenames exist

    pattern_counter = Counter(base_names)
    # Get the most frequent base name. Handle ties by sorting alphabetically.
    most_common_items = pattern_counter.most_common()
    most_common_pattern = sorted(most_common_items, key=lambda x: (-x[1], x[0]))[0][0]

    # Find filenames whose base does not match the most common one
    inconsistent_filenames_data = [
        {"filename": original_fn, "base": base_fn}
        for original_fn, base_fn in zip(valid_filenames, base_names)
        if base_fn != most_common_pattern
    ]
    all_match = not bool(inconsistent_filenames_data) # True if the list is empty
    return all_match, most_common_pattern, inconsistent_filenames_data
# --- END Filename Processing ---


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
    for tag in str(tags_str).split(','): # Added str() for safety
        tag = tag.strip()
        if tag.count(' ') >= 2: return tag
    return None

def extract_cpi_from_product_id(product_id: str) -> str | None:
    if not product_id: return None
    match = CPI_PATTERN_FROM_PRODUCT_ID.search(product_id)
    if match: style, color = match.groups(); return f"{style}-{color}"
    return None

def build_tags(source_record, existing_tags_str):
    new_tags = []
    category_code_to_use = None
    try: # Wrapped in try-except for safety
        knit_cat = source_record.get('KNIT CATEGORY CODE')
        if pd.notna(knit_cat) and str(knit_cat).strip().lower() not in ['na', 'n/a', '']:
             category_code_to_use = int(knit_cat)
    except (ValueError, TypeError): pass
    if category_code_to_use is None:
        try:
            cat_code = source_record.get('CATEGORY CODE')
            if pd.notna(cat_code): category_code_to_use = int(cat_code)
        except (ValueError, TypeError): pass

    if pd.notna(source_record.get('Description')): new_tags.append(f"style_{source_record['Description'].title()}")
    if pd.notna(source_record.get('SEASON CODE')): new_tags.append(str(source_record['SEASON CODE']).replace('S1', 'SS'))
    if pd.notna(source_record.get('Colour')): new_tags.append(f"color_{' '.join(str(source_record['Colour']).split(' ')[1:]).lower()}")
    if category_code_to_use and category_code_to_use in CATEGORY_TAGS_MAP:
        new_tags.extend([t.strip() for t in CATEGORY_TAGS_MAP[category_code_to_use].split(',')])

    existing_tags = [t.strip() for t in str(existing_tags_str).split(',') if t.strip()] # Added str()
    # Use dict.fromkeys for unique preserving order, filter ensures no empty strings
    return ', '.join(filter(None, list(dict.fromkeys(existing_tags + new_tags))))
# --- END Tag Generation ---


# --- Image Sorting Logic (UPDATED for Accessories) ---
def sort_images(images, is_accessory):
    """
    Sorts image records based on type and filename, EXCLUDING swatches.
    RTW Order: Ghost (1), Hero (2), Model (3+ by #), Other Editorials.
    Accessory Order: ghost_front (0), ghost_detail/_Detail (1), ghost_side (2),
                     ghost_aerial (3), other ghosts (4), editorials (5).
    """
    def sort_key(img_record):
        filename = img_record.get('filename', '').lower() # Use lower case for comparisons
        asset_type = img_record.get('asset_type', '')

        if is_accessory:
            # Accessory specific sorting priorities
            if 'ghost_front' in filename: return (0, filename)
            # Check for _detail suffix OR asset_type 'ghosts' AND _detail_ in name
            if filename.endswith('_detail.jpg') or ('ghost_detail' in filename and asset_type == 'ghosts'): return (1, filename)
            if 'ghost_side' in filename: return (2, filename)
            if 'ghost_aerial' in filename: return (3, filename)
            if asset_type == 'ghosts': return (4, filename) # Fallback for other ghosts
            return (5, filename) # Editorials and others last
        else:
            # RTW Sorting Order: Ghost -> Hero -> Model # -> Other
            if asset_type == 'ghosts': return (0, filename) # Ghost is priority 0
            if 'hero_image' in filename: return (1, filename) # Hero is priority 1
            model_match = re.search(r'model_image_(\d+)', filename)
            if model_match:
                try: return (2, int(model_match.group(1)), filename) # Model by number
                except ValueError: return (3, filename) # Fallback if number isn't int
            return (3, filename) # Other editorials are priority 3

    # Filter out swatches BEFORE sorting
    images_to_sort = [
        img for img in images
        if img.get('filename') and img.get('asset_type') != 'swatches'
    ]

    return sorted(images_to_sort, key=sort_key)
# --- END Image Sorting ---


# --- Main Execution ---
def main(capsule: str, dry_run: bool, override_file: str = None):
    CDN_PREFIX = 'https://cdn.shopify.com/s/files/1/0148/9561/2004/files/'
    anomalous_handles = set()
    anomaly_details_log = []

    # --- ADD TIMESTAMP ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # --- END TIMESTAMP ---

    try:
        capsule_dir = pathlib.Path(f"capsules/{capsule}")
        # Define output_dir early
        output_dir = capsule_dir / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)

        tracker_path = capsule_dir / "inputs/S226 Shopify upload masterfile.csv"
        tracker_df_raw = pd.read_csv(tracker_path, header=None, encoding='cp1252', keep_default_na=False)
        header_row_index = tracker_df_raw[tracker_df_raw.apply(lambda r: r.astype(str).str.contains('Product ID').any(), axis=1)].index[0]
        tracker_df = tracker_df_raw.copy()
        tracker_df.columns = tracker_df.iloc[header_row_index]
        tracker_df = tracker_df.drop(tracker_df.index[:header_row_index + 1]).reset_index(drop=True)
        tracker_df.columns = tracker_df.columns.str.strip()

        export_df = pd.read_csv(capsule_dir / "inputs/products_export_1.csv")
        manifest_path = capsule_dir / "manifests/images_manifest.jsonl"
        manifest_recs = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
        manifest_df = pd.DataFrame(manifest_recs)
        print("✅ Successfully loaded all source files.")
    except (FileNotFoundError, IndexError) as e:
        print(f"❌ Error loading or parsing files: {e}")
        return
    except Exception as e: # Catch other potential loading errors
        print(f"❌ Unexpected error loading files: {e}")
        return

    # --- ADD OVERRIDE FILE LOADING ---
    override_data = {} # Lookup dict: Handle -> {'position': 'first'/'last'/'N'}
    override_file_path = None # Initialize
    if override_file:
        # Check explicit path first
        potential_path = pathlib.Path(override_file)
        if potential_path.is_absolute() and potential_path.exists():
            override_file_path = potential_path
        else:
            # Check relative to outputs
            potential_path = output_dir / override_file
            if potential_path.exists():
                override_file_path = potential_path
            else:
                 # Check default name in outputs if only flag used
                 default_path = output_dir / "data_gap_report_override.csv"
                 if override_file == "data_gap_report_override.csv" and default_path.exists():
                     override_file_path = default_path

        if override_file_path:
            print(f"Loading override data from: {override_file_path}...")
            try:
                df_override = pd.read_csv(override_file_path, dtype=str).fillna('')
                required_cols = ['Handle', 'Override to Import', 'Image Position Override', 'Inconsistent Filenames']
                if all(col in df_override.columns for col in required_cols):
                    df_override_filtered = df_override[
                        (df_override['Override to Import'].str.lower() == 'x') &
                        (df_override['Inconsistent Filenames'].str.lower() == 'x')
                    ]
                    for _, row in df_override_filtered.iterrows():
                        handle_override = str(row['Handle']).strip() # Ensure stripped handle
                        position_override = str(row['Image Position Override']).lower().strip()
                        if handle_override and position_override:
                            override_data[handle_override] = {'position': position_override}
                    print(f"  > Loaded overrides for {len(override_data)} handles flagged with inconsistent filenames.")
                else:
                    print(f"  > WARNING: Override file missing required columns ({required_cols}). Overrides ignored.")
            except Exception as e:
                print(f"  > WARNING: Could not read override file. Overrides ignored. Error: {e}")
        else:
             print(f"  > INFO: Override file '{override_file}' not found. No overrides applied.")
    # --- END OVERRIDE LOADING ---

    handle_to_cpi_map = {
        str(row['Handle']).strip(): cpi # Ensure handles are stripped strings
        for _, row in export_df[export_df['Title'].notna()].iterrows()
        if pd.notna(row.get('Handle')) and (cpi := extract_cpi_from_product_id(extract_product_id_from_tags(row['Tags'])))
    }
    print(f"✅ Built Handle-to-CPI map for {len(handle_to_cpi_map)} products.")

    # Ensure Product ID in tracker is string for lookup
    tracker_df['Product ID'] = tracker_df['Product ID'].astype(str).str.strip()
    tracker_df.set_index('Product ID', inplace=True)
    tracker_df['RRP (USD)'] = pd.to_numeric(tracker_df['RRP (USD)'], errors='coerce')

    # --- Initialize list for new rows ---
    all_new_rows_to_add = []
    missing_image_rows = [] # For the separate CSV file

    # Ensure Handle in export_df is stripped string before grouping
    export_df['Handle'] = export_df['Handle'].astype(str).str.strip()

    for handle, product_group in export_df.groupby('Handle'):
        # Skip processing if handle couldn't be mapped (e.g., missing Product ID tag initially)
        if handle not in handle_to_cpi_map:
            print(f"  > WARNING: Skipping handle '{handle}' as it could not be mapped to a CPI (check parent row tags).")
            # Flag these rows as anomalous directly?
            # anomalous_handles.add(handle) # Optional: Treat unmappable handles as anomalies
            continue
        cpi = handle_to_cpi_map[handle]

        parent_row_filter = product_group['Title'].notna() & (product_group['Title'] != '')
        # Handle cases where a group might somehow lack a parent row
        parent_row_indices = product_group[parent_row_filter].index
        if parent_row_indices.empty:
             print(f"  > ANOMALY: No parent row (with Title) found for handle '{handle}'. Skipping.")
             anomalous_handles.add(handle)
             anomaly_details_log.append({"Handle": handle, "CPI": cpi, "Reason": "Missing Parent Row"})
             continue
        parent_row_index = parent_row_indices[0] # Take the first if multiple somehow exist
        full_product_id = extract_product_id_from_tags(product_group.loc[parent_row_index, 'Tags'])

        # Enrich data from Tracker
        try:
            # Strip product ID before lookup
            full_product_id_clean = str(full_product_id).strip() if full_product_id else None
            if not full_product_id_clean:
                 raise KeyError("Product ID tag missing or invalid.") # Treat as lookup failure

            source_record = tracker_df.loc[full_product_id_clean]
            new_tags = build_tags(source_record, product_group.loc[parent_row_index, 'Tags'])
            export_df.loc[parent_row_index, 'Tags'] = new_tags

            child_indices = product_group[~parent_row_filter].index
            export_df.loc[child_indices, 'Tags'] = '' # Clear tags on child rows

            if pd.notna(source_record.get('PRODUCT DETAILS')):
                export_df.loc[parent_row_index, 'Details (product.metafields.altuzarra.details)'] = source_record['PRODUCT DETAILS']
            # Apply price to ALL rows in the group
            export_df.loc[product_group.index, 'Variant Price'] = source_record['RRP (USD)']

        except KeyError: # Catch lookup failure (Product ID not in tracker or missing tag)
            reason = "Product ID Not Found in Tracker"
            details = f"Product ID '{full_product_id_clean}' (from tags) not found in tracker." if full_product_id_clean else "Could not extract valid Product ID from parent row tags."
            print(f"  > ANOMALY: {reason} for handle '{handle}'. {details}")
            anomaly_details_log.append({"Handle": handle, "CPI": cpi, "Product ID Tag": full_product_id_clean or "N/A", "Reason": reason, "Details": details})
            anomalous_handles.add(handle)
            # DO NOT continue here, let it proceed to check images if they exist

        # --- Image Processing ---
        images_for_cpi = manifest_df[manifest_df['cpi'] == cpi].to_dict('records')
        final_image_list = [] # Reset for each product
        override_insert_info = None # Reset for each product

        # Determine is_accessory status early
        # Handle cases where images_for_cpi might be empty AFTER filtering anomalies
        is_accessory = any(img.get('is_accessory', False) for img in images_for_cpi) if images_for_cpi else False

        # --- Guardrails ---
        run_image_assignment = True # Flag to control if image processing should proceed

        if not images_for_cpi:
            reason = "No Images in Manifest"
            print(f"  > ANOMALY: {reason} for CPI {cpi} (Handle: '{handle}')")
            anomaly_details_log.append({"Handle": handle, "CPI": cpi, "Product ID Tag": full_product_id or "N/A", "Reason": reason})
            anomalous_handles.add(handle)
            run_image_assignment = False # Cannot assign images

        # Check for *any* image usable as a primary ghost (ghost for RTW, ghost_front for Acc)
        has_primary_ghost = False
        if images_for_cpi:
            if is_accessory:
                has_primary_ghost = any('ghost_front' in img.get('filename','').lower() for img in images_for_cpi if img.get('asset_type') == 'ghosts')
            else: # RTW
                has_primary_ghost = any(img.get('asset_type') == 'ghosts' for img in images_for_cpi)

        if run_image_assignment and not has_primary_ghost:
            reason = "Missing Primary Ghost Image" # More specific reason
            ghost_type = "'ghost_front'" if is_accessory else "'ghosts'"
            print(f"  > ANOMALY: {reason} (type {ghost_type}) in manifest for CPI {cpi} (Handle: '{handle}')")
            anomaly_details_log.append({
                "Handle": handle, "CPI": cpi, "Product ID Tag": full_product_id or "N/A", "Reason": reason,
                "Manifest Files Found": ", ".join(sorted([r.get('filename','N/A').replace(' ','_') for r in images_for_cpi]))
            })
            anomalous_handles.add(handle)
            run_image_assignment = False # Cannot guarantee correct first image

        if run_image_assignment:
            filenames_to_check = [img['filename'] for img in images_for_cpi if img.get('asset_type') in ['ghosts', 'editorials'] and img.get('filename')]
            is_consistent, common_pattern, inconsistent_data = check_filename_consistency(filenames_to_check)

            if not is_consistent:
                override_info_lookup = override_data.get(handle) # Use stripped handle for lookup
                if override_info_lookup:
                    print(f"  > INFO: Filename inconsistency found for '{handle}', override rule applied.")
                    inconsistent_filenames = {item['filename'] for item in inconsistent_data}
                    inconsistent_records_to_insert = [rec for rec in images_for_cpi if rec.get('filename') in inconsistent_filenames]
                    override_insert_info = {'files': inconsistent_records_to_insert, 'position': override_info_lookup['position']}
                else:
                    reason = "Inconsistent Filenames"
                    print(f"  > ANOMALY: {reason} in manifest for CPI {cpi} (Handle: '{handle}')")
                    anomaly_details_log.append({
                        "Handle": handle, "CPI": cpi, "Product ID Tag": full_product_id or "N/A", "Reason": reason,
                        "Expected Pattern": common_pattern, "Inconsistent Files Data": json.dumps(inconsistent_data),
                        "Manifest Files Found": ", ".join(sorted([r.get('filename','N/A') for r in images_for_cpi]))
                    })
                    anomalous_handles.add(handle)
                    run_image_assignment = False # Stop image processing due to inconsistency without override

        if run_image_assignment and not is_accessory: # RTW Check
            ghosts_editorials = [img for img in images_for_cpi if img.get('asset_type') in ['ghosts', 'editorials'] and img.get('filename')]
            has_hero = any('hero_image' in img.get('filename','').lower() for img in ghosts_editorials)
            has_model = any('model_image' in img.get('filename','').lower() for img in ghosts_editorials)
            if not has_hero or not has_model:
                reason = "Missing Hero or Model Images"
                print(f"  > ANOMALY: {reason} for non-accessory CPI {cpi} (Handle: '{handle}')")
                anomaly_details_log.append({
                    "Handle": handle, "CPI": cpi, "Product ID Tag": full_product_id or "N/A", "Reason": reason,
                    "Has Hero": has_hero, "Has Model": has_model,
                    "Manifest Files Found (G+E)": ", ".join(sorted([r.get('filename','N/A') for r in ghosts_editorials]))
                })
                anomalous_handles.add(handle)
                run_image_assignment = False # Stop processing RTW without required images


        # --- Image Sorting and Assignment (only if run_image_assignment is True) ---
        if run_image_assignment:
            # 1. Sort all available images for the CPI
            sorted_images = sort_images(images_for_cpi, is_accessory)

            # 2. Filter ghosts (conditionally for RTW)
            if not is_accessory: # Apply filtering ONLY for RTW
                temp_image_list = []
                ghost_added = False
                for img in sorted_images:
                    # Check asset type for RTW ghost filtering
                    is_ghost = img.get('asset_type') == 'ghosts'
                    if is_ghost:
                        if not ghost_added:
                            temp_image_list.append(img)
                            ghost_added = True
                    else:
                        temp_image_list.append(img)
                final_image_list = temp_image_list # Use the filtered list for RTW
            else: # For accessories, use the fully sorted list directly
                final_image_list = sorted_images

            # 3. Apply override insertion (if applicable)
            if override_insert_info:
                files_to_insert_raw = override_insert_info['files']
                target_pos_str = override_insert_info['position']
                insert_index = -1

                # --- Conditional Filtering for Override Insertion ---
                if not is_accessory: # RTW: Filter ALL ghosts based on asset_type
                    files_to_insert_filtered = [img for img in files_to_insert_raw if img.get('asset_type') != 'ghosts']
                else: # Accessories: Filter only 'ghost_front' based on filename
                    files_to_insert_filtered = [
                        img for img in files_to_insert_raw
                        if 'ghost_front' not in img.get('filename', '').lower()
                    ]
                # --- End Conditional Filtering ---

                if files_to_insert_filtered:
                    num_current_images = len(final_image_list)
                    num_to_insert = len(files_to_insert_filtered)

                    # Calculate insert index
                    if target_pos_str == 'first': insert_index = 0
                    elif target_pos_str == 'last': insert_index = num_current_images
                    elif target_pos_str.isdigit():
                        target_pos_num = int(target_pos_str)
                        if 1 <= target_pos_num <= num_current_images + num_to_insert: insert_index = target_pos_num - 1
                        else: insert_index = num_current_images # Default last
                    else: insert_index = num_current_images # Default last

                    if insert_index != -1:
                        insert_index = max(0, min(insert_index, num_current_images))
                        # Determine accessory status based on combined list for sorting insertables
                        temp_is_acc_override = any(img.get('is_accessory', False) for img in files_to_insert_filtered + final_image_list)
                        sorted_files_to_insert_potentially_duplicate = sort_images(files_to_insert_filtered, temp_is_acc_override) # Rename variable

                        # --- NEW: Prevent inserting duplicates ---
                        # Get filenames already in the main list BEFORE insertion
                        existing_filenames = {img.get('filename') for img in final_image_list if img.get('filename')}
                        
                        # Filter the files to insert, keeping only those NOT already present
                        unique_files_to_insert = [
                            img for img in sorted_files_to_insert_potentially_duplicate
                            if img.get('filename') not in existing_filenames
                        ]
                        # --- END NEW ---

                        # Only insert if there are unique files left
                        if unique_files_to_insert:
                            final_image_list = final_image_list[:insert_index] + unique_files_to_insert + final_image_list[insert_index:]
                            # Update print message to reflect unique count
                            print(f"  > Inserted {len(unique_files_to_insert)} unique overridden inconsistent file(s) (filtered) for '{handle}' at effective index {insert_index}.")
                        else:
                            print(f"  > INFO: Override insertion skipped for '{handle}'. Inconsistent files were already present or filtered out.")
                            
                # else block remains the same
                else:
                     print(f"  > INFO: Override insertion skipped for '{handle}'. Filtered files list was empty (contained only primary ghosts).")

            # 4. Assign Images and Create New Rows for separate CSV
            existing_indices = list(product_group.index)
            num_images = len(final_image_list)
            num_rows = len(existing_indices)
            max_iterations = max(num_images, num_rows)

            parent_row_template = None # Define outside loop
            if num_images > num_rows: # Prepare template only if needed
                 parent_row_template = export_df.loc[parent_row_index].to_dict()
                 cols_to_preserve = ['Handle', 'Vendor', 'Product Category', 'Type', 'Variant Price']
                 for col in parent_row_template:
                     if col not in cols_to_preserve: parent_row_template[col] = ''
                 parent_row_template['Title'] = ''
                 parent_row_template['Body (HTML)'] = ''
                 parent_row_template['Image Position'] = pd.NA
                 parent_row_template['Variant Grams'] = pd.NA
                 parent_row_template['Gift Card'] = False
                 parent_row_template['Variant Requires Shipping'] = pd.NA
                 parent_row_template['Variant Taxable'] = pd.NA

            # group_new_rows = [] # Not needed if not concatenating

            for i in range(max_iterations):
                image_exists = i < num_images
                row_exists = i < num_rows

                if image_exists and row_exists:
                    index = existing_indices[i]
                    filename = final_image_list[i]['filename']
                    export_df.loc[index, 'Image Src'] = CDN_PREFIX + filename.replace(' ', '_')
                    export_df.loc[index, 'Image Position'] = i + 1 # Assign as int
                elif image_exists and not row_exists:
                    if parent_row_template is None:
                         print(f"  > ERROR: Cannot create missing image row for handle '{handle}' - template missing.")
                         continue
                    filename = final_image_list[i]['filename']
                    new_row = parent_row_template.copy()
                    new_row['Image Src'] = CDN_PREFIX + filename.replace(' ', '_')
                    new_row['Image Position'] = float(i + 1) # Assign as float for now
                    missing_image_rows.append(new_row) # Add to list for separate CSV

                elif not image_exists and row_exists:
                    index = existing_indices[i]
                    export_df.loc[index, 'Image Src'] = ''
                    export_df.loc[index, 'Image Position'] = pd.NA
        else: # If run_image_assignment was false
             export_df.loc[product_group.index, 'Image Src'] = ''
             export_df.loc[product_group.index, 'Image Position'] = pd.NA


    # --- Save Missing Image Rows to Separate CSV ---
    if missing_image_rows:
        print(f"  > INFO: Found {len(missing_image_rows)} extra image rows to save separately.")
        missing_rows_df = pd.DataFrame(missing_image_rows)

        # Define filename with timestamp
        missing_filename = f"missing_img_src_files_{timestamp}.csv"
        missing_output_path = output_dir / missing_filename

        # Convert position before saving
        missing_rows_df['Image Position'] = pd.to_numeric(missing_rows_df['Image Position'], errors='coerce').astype('Int64')

        template_df = pd.DataFrame(columns=export_df.columns)
        # Ensure only essential columns are kept from missing_rows_df before concat
        cols_to_keep_missing = ['Handle', 'Image Src', 'Image Position']
        full_missing_df = pd.concat([template_df, missing_rows_df[cols_to_keep_missing]], ignore_index=True)
        full_missing_df.fillna('', inplace=True)
        # Re-apply type conversion after fillna might change it back to float/object
        full_missing_df['Image Position'] = pd.to_numeric(full_missing_df['Image Position'], errors='coerce').astype('Int64')

        full_missing_df.to_csv(missing_output_path, index=False, columns=export_df.columns)
        print(f"✅ Missing image rows CSV ({len(missing_rows_df)} rows) written successfully to: {missing_output_path}")
    else:
        print("  > INFO: No extra image rows found to save separately.")
    # --- END Save Missing ---


    # --- Final Cleanup and Splitting ---
    export_df['Handle'] = export_df['Handle'].astype(str).str.strip()
    anomalous_handles_str = {str(h).strip() for h in anomalous_handles}

    # Split DataFrames
    full_enriched_df = export_df.copy()
    import_ready_df = export_df[~export_df['Handle'].isin(anomalous_handles_str)].copy()
    anomalies_df = export_df[export_df['Handle'].isin(anomalous_handles_str)].copy()

    # Apply type conversion AFTER splitting
    try: import_ready_df['Image Position'] = import_ready_df['Image Position'].astype('Int64')
    except Exception as e: print(f"Warning: Could not convert Image Position in ready_df: {e}")
    try: anomalies_df['Image Position'] = anomalies_df['Image Position'].astype('Int64')
    except Exception as e: print(f"Warning: Could not convert Image Position in anomalies_df: {e}")
    try: full_enriched_df['Image Position'] = full_enriched_df['Image Position'].astype('Int64')
    except Exception as e: print(f"Warning: Could not convert Image Position in full_enriched_df: {e}")


    # --- Anomaly Report Processing ---
    if anomaly_details_log:
        anomalies_report_prep = []
        anomaly_reason_cols_map = {
            'Product ID Not Found in Tracker': 'Product ID Not Found in Tracker', 'No Images in Manifest': 'No Images in Manifest',
            'Missing Ghost Image': 'Missing Ghost Image', 'Missing Primary Ghost Image': 'Missing Primary Ghost Image', # Added specific reason
            'Inconsistent Filenames': 'Inconsistent Filenames',
            'Missing Hero or Model Images': 'Missing Hero or Model Images', 'Missing Parent Row': 'Missing Parent Row'
        }
        all_report_reason_cols = list(anomaly_reason_cols_map.values())
        grouped_anomalies = {}
        for anomaly in anomaly_details_log:
            key = (anomaly.get('Handle'), anomaly.get('CPI'), anomaly.get('Product ID Tag'))
            if key not in grouped_anomalies:
                grouped_anomalies[key] = {
                    'Handle': anomaly.get('Handle'), 'CPI': anomaly.get('CPI'), 'Product ID Tag': anomaly.get('Product ID Tag'),
                    **{reason_col: '' for reason_col in all_report_reason_cols}
                }
            reason = anomaly.get('Reason')
            mapped_reason_col = anomaly_reason_cols_map.get(reason)
            if mapped_reason_col: grouped_anomalies[key][mapped_reason_col] = 'X'

        anomalies_report_prep = list(grouped_anomalies.values())
        anomalies_report_df = pd.DataFrame(anomalies_report_prep)
        report_cols_order = ['Product ID Tag', 'Handle', 'CPI'] + all_report_reason_cols
        for col in report_cols_order:
            if col not in anomalies_report_df.columns: anomalies_report_df[col] = ''
        anomalies_report_df = anomalies_report_df[report_cols_order]
    else:
        anomalies_report_df = pd.DataFrame()
    # --- END Anomaly Report ---

    # --- Save Outputs ---
    if dry_run:
        print("\n--- Dry Run Complete ---")
        # Add timestamp to simulated filenames
        ready_filename_dry = f"poc_shopify_import_ready_{timestamp}.csv"
        anomalies_filename_dry = f"poc_shopify_anomalies_{timestamp}.csv"
        report_filename_dry = f"data_gap_report_{timestamp}.csv"
        missing_filename_dry = f"missing_img_src_files_{timestamp}.csv"

        print(f"\n{len(import_ready_df)} rows would be saved to '{ready_filename_dry}'.")
        print(f"{len(anomalies_df)} rows would be saved to '{anomalies_filename_dry}'.")
        if missing_image_rows:
            print(f"{len(missing_image_rows)} rows would be saved to '{missing_filename_dry}'.")
        if not anomalies_report_df.empty:
            print(f"{anomalies_report_df['Handle'].nunique()} products detailed in '{report_filename_dry}'.")

        print("\nDisplaying sample 'import-ready' data for 'askania-coat-tahini-melange':")
        if 'askania-coat-tahini-melange' in import_ready_df['Handle'].values:
            print(import_ready_df[import_ready_df['Handle'] == 'askania-coat-tahini-melange'][['Handle', 'Image Src', 'Image Position', 'Tags']])
        else:
            print("'askania-coat-tahini-melange' not found in import-ready data (likely anomalous).")
    else:
        # --- Add timestamp suffix to output filenames ---
        full_filename = f"poc_shopify_import_enriched_{timestamp}.csv"
        ready_filename = f"poc_shopify_import_ready_{timestamp}.csv"
        anomalies_filename = f"poc_shopify_anomalies_{timestamp}.csv"
        report_filename = f"data_gap_report_{timestamp}.csv"
        # missing_filename is already defined with timestamp where it's saved

        full_output_path = output_dir / full_filename
        full_enriched_df.to_csv(full_output_path, index=False)
        print(f"\n✅ Full enriched CSV ({len(full_enriched_df)} rows) written successfully to: {full_output_path}")

        ready_output_path = output_dir / ready_filename
        import_ready_df.to_csv(ready_output_path, index=False)
        print(f"✅ Import-ready CSV ({len(import_ready_df)} rows) written successfully to: {ready_output_path}")

        if not anomalies_df.empty:
            anomalies_output_path = output_dir / anomalies_filename
            anomalies_df.to_csv(anomalies_output_path, index=False)
            print(f"⚠️  {len(anomalies_df)} rows with anomalies staged for review in: {anomalies_output_path}")

        if not anomalies_report_df.empty:
            anomalies_report_output_path = output_dir / report_filename
            anomalies_report_df.to_csv(anomalies_report_output_path, index=False)
            print(f"📊 {anomalies_report_df['Handle'].nunique()} products with anomalies detailed in: {anomalies_report_output_path}")
        elif not anomalies_df.empty:
             print("ℹ️  Anomaly details logged but structured report generation failed or resulted empty.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Enrich Shopify CSV using a capsule system.")
    parser.add_argument("--capsule", required=True, help="The capsule code (e.g., S126)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without writing files.")
    parser.add_argument("--override-file", help="Optional name or path for the override report CSV (e.g., data_gap_report_override.csv).")
    args = parser.parse_args()

    main(args.capsule, args.dry_run, args.override_file)