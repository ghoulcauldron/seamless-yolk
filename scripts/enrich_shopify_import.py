import pandas as pd
import re
import json
import pathlib
import argparse
from datetime import datetime
from collections import Counter# --- Filename Processing Logic (For Consistency Check - NEW) ---
def get_base_filename(filename: str) -> str:
    """Removes standard suffixes like _ghost_..., _model_..., _hero_..., _swatch...
       while preserving core identifiers like color/pattern names."""
    if not filename or not isinstance(filename, str): return ""

    # Define common suffixes more precisely
    suffixes = [
        r"_ghost(?:_\d+)?",
        r"_model_image(?:_\d+)?(?:_\d+)?",
        r"_hero_image(?:__\d+)?",
        r"_swatch"
    ]
    suffix_pattern = "|".join(suffixes)

    # Regex: Look for optional _FINAL, then a known suffix, then .jpg at the END of the string.
    # Capture the part BEFORE this pattern.
    match = re.match(rf"^(.*?)({suffix_pattern})\.jpg$", filename, flags=re.IGNORECASE)

    if match:
        base = match.group(1) # Get the part before the suffix
        # Remove trailing _FINAL if it exists right before the suffix part we removed
        if base.endswith("_FINAL"):
            base = base[:-len("_FINAL")]
        return base.strip() # Return the cleaned base, stripped of spaces
    else:
        # If no known suffix found, maybe it's just name.jpg or name_FINAL.jpg
        base = re.sub(r"_FINAL\.jpg$", ".jpg", filename, flags=re.IGNORECASE) # Remove _FINAL if at end
        # Return name without extension, stripped
        return base.rsplit('.', 1)[0].strip() if '.' in base else base.strip()

def check_filename_consistency(filenames: list) -> tuple[bool, str | None, list]:
    """
    Checks if all filenames share the same base pattern using get_base_filename.
    Returns: (is_consistent, most_common_pattern, inconsistent_filenames_data list of dicts)
    """
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

    # Optional Debug Print:
    # if not all_match:
    #    print(f"DEBUG Consistency Check: CPI={cpi_for_debug}, Common='{most_common_pattern}', All Bases={base_names}, Inconsistent={inconsistent_filenames_data}")

    return all_match, most_common_pattern, inconsistent_filenames_data
# --- END NEW FUNCTIONS ---


# --- NATIVE TRANSLATION of Shopify Tags Guide.csv ---
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



def build_tags(source_record, existing_tags_str):
    new_tags = []
    category_code_to_use = None
    
    if pd.notna(source_record.get('KNIT CATEGORY CODE')) and str(source_record['KNIT CATEGORY CODE']).strip().lower() not in ['na', 'n/a', '']:
        try:
            category_code_to_use = int(source_record['KNIT CATEGORY CODE'])
        except (ValueError, TypeError):
            pass
    
    if category_code_to_use is None and pd.notna(source_record.get('CATEGORY CODE')):
        try:
            category_code_to_use = int(source_record['CATEGORY CODE'])
        except (ValueError, TypeError):
            pass

    if pd.notna(source_record.get('Description')):
        new_tags.append(f"style_{source_record['Description'].title()}")
    if pd.notna(source_record.get('SEASON CODE')):
        new_tags.append(str(source_record['SEASON CODE']).replace('S1', 'SS'))
    if pd.notna(source_record.get('Colour')):
        new_tags.append(f"color_{' '.join(str(source_record['Colour']).split(' ')[1:]).lower()}")
    
    if category_code_to_use and category_code_to_use in CATEGORY_TAGS_MAP:
        new_tags.extend([t.strip() for t in CATEGORY_TAGS_MAP[category_code_to_use].split(',')])

    existing_tags = [t.strip() for t in str(existing_tags_str).split(',') if t.strip()]
    return ', '.join(filter(None, list(dict.fromkeys(existing_tags + new_tags))))

def sort_images(images, is_accessory):
    """Sorts image records based on type and filename, EXCLUDING swatches.
       Correct Order: Ghost (1), Hero (2), Model (3+ by #), Other Editorials.
       Accessories: Ghost (1), Others (2+).
    """
    def sort_key(img_record):
        filename = img_record.get('filename', '')
        asset_type = img_record.get('asset_type', '')

        # Swatches are filtered out before this function is called.

        if is_accessory:
            # Accessory sorting: Ghost first, then everything else alphabetically
            if asset_type == 'ghosts':
                return (0, filename)
            else:
                return (1, filename)
        else: # Not accessory (RTW)
            # RTW Sorting Order: Ghost -> Hero -> Model # -> Other
            if asset_type == 'ghosts':
                return (0, filename) # Ghost is priority 0 (Position 1)

            if 'hero_image' in filename:
                return (1, filename) # Hero is priority 1 (Position 2)

            model_match = re.search(r'model_image_(\d+)', filename)
            if model_match:
                try:
                    # Model images are priority 2, sorted by their number
                    return (2, int(model_match.group(1)), filename)
                except ValueError:
                    return (3, filename) # Fallback if number isn't int (treat as 'other')

            # Any remaining editorials are priority 3
            return (3, filename)

    # Filter out swatches BEFORE sorting
    images_to_sort = [
        img for img in images
        if img.get('filename') and img.get('asset_type') != 'swatches'
    ]

    # Sort the filtered list (ghosts and editorials only)
    return sorted(images_to_sort, key=sort_key)

def main(capsule: str, dry_run: bool, override_file: str = None):
    CDN_PREFIX = 'https://cdn.shopify.com/s/files/1/0148/9561/2004/files/'
    anomalous_handles = set()
    anomaly_details_log = []

    try:
        capsule_dir = pathlib.Path(f"capsules/{capsule}")
        tracker_path = capsule_dir / "inputs/SS26 for Shopify check(By Style).csv"
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
    
    # --- ADD OVERRIDE FILE LOADING ---
    override_data = {} # Lookup dict: Handle -> {'position': 'first'/'last'/'N'}
    if override_file:
        override_path = pathlib.Path(override_file)
        # Default override path relative to capsule outputs if not absolute
        if not override_path.is_absolute():
            capsule_dir_temp = pathlib.Path(f"capsules/{capsule}") # Define capsule_dir earlier if needed
            override_path = capsule_dir_temp / "outputs" / override_file

        # Also allow looking for default name if only flag is provided
        if not override_path.exists() and override_file == 'data_gap_report_override.csv':
            capsule_dir_temp = pathlib.Path(f"capsules/{capsule}")
            default_override_path = capsule_dir_temp / "outputs" / "data_gap_report_override.csv"
            if default_override_path.exists():
                override_path = default_override_path


        if override_path.exists():
            print(f"Loading override data from: {override_path}...")
            try:
                # Expect columns: Handle, Override to Import, Image Position Override, Inconsistent Filenames
                df_override = pd.read_csv(override_path, dtype=str).fillna('')
                required_cols = ['Handle', 'Override to Import', 'Image Position Override', 'Inconsistent Filenames'] # Check for needed cols
                if all(col in df_override.columns for col in required_cols):
                    # Filter for rows marked 'x' AND where inconsistency was the reason
                    df_override_filtered = df_override[
                        (df_override['Override to Import'].str.lower() == 'x') &
                        (df_override['Inconsistent Filenames'].str.lower() == 'x') # Check the specific reason column
                    ]
                    for _, row in df_override_filtered.iterrows():
                        handle_override = row['Handle']
                        position_override = str(row['Image Position Override']).lower().strip()
                        if handle_override and position_override:
                            # Store only the position needed later
                            override_data[handle_override] = {'position': position_override}
                    print(f"  > Loaded overrides for {len(override_data)} handles flagged with inconsistent filenames.")
                else:
                    print(f"  > WARNING: Override file missing required columns ({required_cols}). Overrides ignored.")
            except Exception as e:
                print(f"  > WARNING: Could not read override file. Overrides ignored. Error: {e}")
        else:
            print(f"  > INFO: Override file not found at '{override_path}'. No overrides applied.")
    # --- END OVERRIDE LOADING ---

    handle_to_cpi_map = {
        row['Handle']: cpi for _, row in export_df[export_df['Title'].notna()].iterrows()
        if (cpi := extract_cpi_from_product_id(extract_product_id_from_tags(row['Tags'])))
    }
    print(f"✅ Built Handle-to-CPI map for {len(handle_to_cpi_map)} products.")
    
    tracker_df.set_index('Product ID', inplace=True)
    tracker_df['RRP (USD)'] = pd.to_numeric(tracker_df['RRP (USD)'], errors='coerce')

    # --- PATCH 1: INITIALIZE LIST FOR NEW ROWS (FOR ROW CREATION) ---
    all_new_rows_to_add = [] 
    # --- END PATCH 1 ---

    for handle, product_group in export_df.groupby('Handle'):
        if handle not in handle_to_cpi_map: continue
        cpi = handle_to_cpi_map[handle]
        
        parent_row_filter = product_group['Title'].notna() & (product_group['Title'] != '')
        parent_row_index = product_group[parent_row_filter].index[0]
        full_product_id = extract_product_id_from_tags(product_group.loc[parent_row_index, 'Tags'])

        try:
            source_record = tracker_df.loc[full_product_id]
            new_tags = build_tags(source_record, product_group.loc[parent_row_index, 'Tags'])
            export_df.loc[parent_row_index, 'Tags'] = new_tags
            
            child_indices = product_group[~parent_row_filter].index
            export_df.loc[child_indices, 'Tags'] = ''
            
            if pd.notna(source_record.get('PRODUCT DETAILS')):
                export_df.loc[parent_row_index, 'Details (product.metafields.altuzarra.details)'] = source_record['PRODUCT DETAILS']
            export_df.loc[product_group.index, 'Variant Price'] = source_record['RRP (USD)']
        except KeyError:
            reason = "Product ID Not Found in Tracker"
            print(f"  > ANOMALY: {reason} for '{full_product_id}' (Handle: '{handle}')")
            anomaly_details_log.append({
                "Handle": handle,
                "CPI": cpi if cpi else "N/A", # Include CPI if available
                "Product ID Tag": full_product_id if full_product_id else "N/A",
                "Reason": reason
            })
            anomalous_handles.add(handle) # Keep adding handle for filtering
            # continue
            
        images_for_cpi = manifest_df[manifest_df['cpi'] == cpi].to_dict('records')
        if not images_for_cpi:
            reason = "No Images in Manifest"
            print(f"  > ANOMALY: {reason} for CPI {cpi} (Handle: '{handle}')")
            anomaly_details_log.append({
                "Handle": handle,
                "CPI": cpi,
                "Product ID Tag": full_product_id if full_product_id else "N/A", # Include Product ID
                "Reason": reason
            })
            anomalous_handles.add(handle) # Keep adding handle for filtering
            # continue

        # --- NEW GUARDRAIL: Check if ANY ghost image exists for this CPI ---
        if not any(img.get('asset_type') == 'ghosts' for img in images_for_cpi):
            reason = "Missing Ghost Image" # Use the specific reason for the report
            print(f"  > ANOMALY: {reason} in manifest for CPI {cpi} (Handle: '{handle}')")
            anomaly_details_log.append({
                "Handle": handle,
                "CPI": cpi,
                "Product ID Tag": full_product_id if full_product_id else "N/A",
                "Reason": reason,
                "Manifest Files Found": ", ".join(sorted([r.get('filename','N/A').replace(' ','_') for r in images_for_cpi]))
            })
            anomalous_handles.add(handle) # Add handle to exclude from ready file
            # continue 
        # --- END NEW GUARDRAIL ---

        # --- NEW GUARDRAIL: Check 2: Filename Consistency (Ghosts + Editorials) ---
        override_insert_info = None 
        filenames_to_check = [
            img['filename'] for img in images_for_cpi 
            if img.get('asset_type') in ['ghosts', 'editorials'] and img.get('filename')
        ]
        is_consistent, common_pattern, inconsistent_data = check_filename_consistency(filenames_to_check)

        if not is_consistent:
            override_info_lookup = override_data.get(handle)

            if override_info_lookup:
                print(f"  > INFO: Filename inconsistency found for '{handle}', override rule applied.")
                inconsistent_filenames = {item['filename'] for item in inconsistent_data}
                inconsistent_records_to_insert = [
                    rec for rec in images_for_cpi if rec.get('filename') in inconsistent_filenames
                ]
                override_insert_info = {
                     'files': inconsistent_records_to_insert,
                     'position': override_info_lookup['position']
                 }
            else:
                reason = "Inconsistent Filenames"
                print(f"  > ANOMALY: {reason} in manifest for CPI {cpi} (Handle: '{handle}')")
                anomaly_details_log.append({
                    "Handle": handle, "CPI": cpi, "Product ID Tag": full_product_id or "N/A",
                    "Reason": reason, "Expected Pattern": common_pattern,
                    "Inconsistent Files Data": json.dumps(inconsistent_data),
                    "Manifest Files Found": ", ".join(sorted([r.get('filename','N/A') for r in images_for_cpi]))
                })
                anomalous_handles.add(handle)
                continue 
        # --- END NEW GUARDRAIL ---

        # --- NEW GUARDRAIL: Check 3: Missing Hero or Model Images (Non-Accessories Only) ---
        temp_is_accessory = any(img.get('is_accessory', False) for img in images_for_cpi) 

        if not temp_is_accessory:
            ghosts_editorials = [
                img for img in images_for_cpi
                if img.get('asset_type') in ['ghosts', 'editorials'] and img.get('filename')
            ]
            has_hero = any('hero_image' in img.get('filename','') for img in ghosts_editorials)
            has_model = any('model_image' in img.get('filename','') for img in ghosts_editorials)

            if not has_hero or not has_model:
                reason = "Missing Hero or Model Images" 
                print(f"  > ANOMALY: {reason} for non-accessory CPI {cpi} (Handle: '{handle}')")
                anomaly_details_log.append({
                    "Handle": handle,
                    "CPI": cpi,
                    "Product ID Tag": full_product_id if full_product_id else "N/A",
                    "Reason": reason,
                    "Has Hero": has_hero, 
                    "Has Model": has_model, 
                    "Manifest Files Found (G+E)": ", ".join(sorted([r.get('filename','N/A') for r in ghosts_editorials])) 
                })
                anomalous_handles.add(handle) 
                continue 
        # --- END NEW GUARDRAIL ---
            
        is_accessory = images_for_cpi[0].get('is_accessory', False)
        sorted_images = sort_images(images_for_cpi, is_accessory)

        # --- PATCH 2: GHOST FILTERING (Fix for UnboundLocalError) ---
        # This patch is now *after* sorted_images is created
        final_image_list = [] # Create the new list we will actually use
        ghost_added = False
        for img in sorted_images: # Iterate through the original sorted list
            is_ghost = img.get('asset_type') == 'ghosts'
            if is_ghost:
                if not ghost_added:
                    final_image_list.append(img) # Add the first ghost
                    ghost_added = True
                # Else: Skip subsequent ghosts
            else:
                final_image_list.append(img) # Add all non-ghosts
        # Now 'final_image_list' contains at most one ghost, plus other images
        # --- END PATCH 2 ---


        # --- APPLY OVERRIDE INSERTION (modifying the 'final_image_list') ---
        if override_insert_info:
            files_to_insert_raw = override_insert_info['files']
            target_pos_str = override_insert_info['position']
            insert_index = -1 

            # Filter out any ghosts from the files TO BE INSERTED
            files_to_insert_no_ghosts = [
                img for img in files_to_insert_raw if img.get('asset_type') != 'ghosts'
            ]

            if files_to_insert_no_ghosts: 
                num_current_images = len(final_image_list) # Use final_image_list
                num_to_insert = len(files_to_insert_no_ghosts)

                if target_pos_str == 'first':
                    insert_index = 0
                elif target_pos_str == 'last':
                    insert_index = num_current_images 
                elif target_pos_str.isdigit():
                    target_pos_num = int(target_pos_str)
                    if 1 <= target_pos_num <= num_current_images + num_to_insert:
                        insert_index = target_pos_num - 1 
                    else:
                        print(f"  > WARNING: Invalid override position '{target_pos_str}' for handle '{handle}'. Appending last.")
                        insert_index = num_current_images
                else:
                    print(f"  > WARNING: Unrecognized override position '{target_pos_str}' for handle '{handle}'. Appending last.")
                    insert_index = num_current_images

                if insert_index != -1:
                    insert_index = max(0, min(insert_index, num_current_images))
                    temp_is_accessory_override = any(img.get('is_accessory', False) for img in files_to_insert_no_ghosts + final_image_list)
                    sorted_files_to_insert = sort_images(files_to_insert_no_ghosts, temp_is_accessory_override)
                    
                    # Perform insertion into the final_image_list
                    final_image_list = final_image_list[:insert_index] + sorted_files_to_insert + final_image_list[insert_index:]
                    print(f"  > Inserted {len(files_to_insert_no_ghosts)} overridden inconsistent non-ghost file(s) for '{handle}' at effective index {insert_index}.")
            else:
                 print(f"  > INFO: Override skipped for '{handle}'. Inconsistent files only contained ghosts.")
        # --- END OVERRIDE INSERTION ---
        

        # --- PATCH 3 (REVISED): NEW ASSIGNMENT LOGIC (FOR ROW CREATION) ---
        existing_indices = list(product_group.index)
        num_images = len(final_image_list)
        num_rows = len(existing_indices)
        max_iterations = max(num_images, num_rows)
        
        # Get a copy of the parent row to use as a template for new rows
        # parent_row_index is defined at the start of the loop
        parent_row_template = export_df.loc[parent_row_index].to_dict()
        
        # Clear fields that should be empty for new image-only rows
        # We start by clearing all variant and non-Handle/image fields
        cols_to_clear = [col for col in parent_row_template.keys() if col not in ['Handle', 'Vendor', 'Product Category', 'Type']]
        for col in cols_to_clear:
             parent_row_template[col] = '' # Use empty string for compatibility
        
        # Specifically set Title and Body to empty string for Shopify
        parent_row_template['Title'] = ''
        parent_row_template['Body (HTML)'] = ''
        
        group_new_rows = [] # Rows to add for this specific handle

        for i in range(max_iterations):
            image_exists = i < num_images
            row_exists = i < num_rows

            if image_exists and row_exists:
                # Case 1: Image and Row both exist. Assign image to existing row.
                index = existing_indices[i]
                filename = final_image_list[i]['filename']
                export_df.loc[index, 'Image Src'] = CDN_PREFIX + filename.replace(' ', '_')
                export_df.loc[index, 'Image Position'] = i + 1
            
            elif image_exists and not row_exists:
                # Case 2: Image exists, Row does NOT. Create a new row from template.
                filename = final_image_list[i]['filename']
                
                # Create a copy of the template
                new_row = parent_row_template.copy()
                
                # Set the new image and position
                new_row['Image Src'] = CDN_PREFIX + filename.replace(' ', '_')
                new_row['Image Position'] = float(i + 1) # Force float to match export_df
                
                group_new_rows.append(new_row)

            elif not image_exists and row_exists:
                # Case 3: Row exists, Image does NOT. Clear image from existing row.
                index = existing_indices[i]
                export_df.loc[index, 'Image Src'] = ''
                export_df.loc[index, 'Image Position'] = pd.NA
        
        if group_new_rows:
            all_new_rows_to_add.extend(group_new_rows)
        # --- END PATCH 3 (REVISED) ---
    
    # --- PATCH 4: ADD NEW ROWS TO DATAFRAME ---
    if all_new_rows_to_add:
        print(f"  > INFO: Adding {len(all_new_rows_to_add)} new rows for products with extra images...")
        new_rows_df = pd.DataFrame(all_new_rows_to_add)
        
        # --->>> REMOVE OR COMMENT OUT DEBUG PRINTS <<<---
        # new_row_handles = new_rows_df['Handle'].unique()
        # print(f"DEBUG: Handles intended for new rows: {new_row_handles}")
        # --->>> END DEBUG <<<---

        export_df = pd.concat([export_df, new_rows_df], ignore_index=True)

        # --->>> REMOVE OR COMMENT OUT DEBUG PRINTS <<<---
        # handles_found_after_concat = export_df[export_df['Handle'].isin(new_row_handles)]['Handle'].unique()
        # print(f"DEBUG: Handles found in export_df AFTER concat: {handles_found_after_concat}")
        # missing_handles = set(new_row_handles) - set(handles_found_after_concat)
        # if missing_handles:
        #     print(f"DEBUG: !! Handles MISSING after concat: {missing_handles}")
        # --->>> END DEBUG <<<---

    # --- END PATCH 4 ---

    # --- NEW CLEANUP STEPS ---
    # Ensure Handle column is string type BEFORE filtering
    export_df['Handle'] = export_df['Handle'].astype(str) 
    # Ensure anomalous_handles contains strings just in case
    anomalous_handles_str = {str(h) for h in anomalous_handles} 
    # --- END NEW CLEANUP STEPS ---

    # --- 4. Split DataFrame and Save Outputs ---
    output_dir = capsule_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Define the three output dataframes using cleaned Handle column
    full_enriched_df = export_df
    # Use anomalous_handles_str for filtering
    import_ready_df = export_df[~export_df['Handle'].isin(anomalous_handles_str)].copy() 
    anomalies_df = export_df[export_df['Handle'].isin(anomalous_handles_str)].copy()

    # --- MOVE TYPE CONVERSION HERE ---
    # Apply type conversion AFTER splitting
    import_ready_df['Image Position'] = import_ready_df['Image Position'].astype('Int64')
    anomalies_df['Image Position'] = anomalies_df['Image Position'].astype('Int64')
    # We should also apply it to the full df for consistency before saving
    full_enriched_df['Image Position'] = full_enriched_df['Image Position'].astype('Int64') 
    # --- END MOVE TYPE CONVERSION ---

    # --- NEW: Process anomaly_details_log into the structured report ---
    if anomaly_details_log:
        anomalies_report_prep = []
        # Define the columns based on data_gap_anomalies.csv structure (map simple reasons)
        anomaly_reason_cols_map = {
            'Product ID Not Found in Tracker': 'Product ID Not Found in Tracker',
            'No Images in Manifest': 'No Images in Manifest',
            # Add placeholders for future checks from your request
            'Missing Ghost Image': 'Missing Ghost Image',
            'Inconsistent Filenames': 'Inconsistent Filenames',
            'Missing Hero or Model Images': 'Missing Hero or Model Images' # <<< ADD THIS LINE
        }
        all_report_reason_cols = list(anomaly_reason_cols_map.values())

        # Group anomalies by Handle/CPI/ProductID to consolidate reasons
        grouped_anomalies = {}
        for anomaly in anomaly_details_log:
            key = (anomaly.get('Handle'), anomaly.get('CPI'), anomaly.get('Product ID Tag'))
            if key not in grouped_anomalies:
                grouped_anomalies[key] = {
                    'Handle': anomaly.get('Handle'),
                    'CPI': anomaly.get('CPI'),
                    'Product ID Tag': anomaly.get('Product ID Tag'),
                    **{reason_col: '' for reason_col in all_report_reason_cols} # Initialize reason columns
                }
            # Mark 'X' for the specific reason found
            reason = anomaly.get('Reason')
            mapped_reason_col = anomaly_reason_cols_map.get(reason)
            if mapped_reason_col: # Check if the reason is one we want in the report columns
                 grouped_anomalies[key][mapped_reason_col] = 'X'
            # You could add an 'Other Reason' column here if needed:
            # elif 'Other Reason' not in grouped_anomalies[key] or not grouped_anomalies[key]['Other Reason']:
            #      grouped_anomalies[key]['Other Reason'] = reason


        anomalies_report_prep = list(grouped_anomalies.values())
        anomalies_report_df = pd.DataFrame(anomalies_report_prep)
        # Order columns as per data_gap_anomalies.csv
        report_cols_order = ['Product ID Tag', 'Handle', 'CPI'] + all_report_reason_cols
        # Ensure all expected columns exist, add if missing
        for col in report_cols_order:
            if col not in anomalies_report_df.columns:
                anomalies_report_df[col] = '' # Add missing columns filled with empty string
        anomalies_report_df = anomalies_report_df[report_cols_order] # Apply final order
    else:
        anomalies_report_df = pd.DataFrame() # Empty if no anomalies logged
    # --- END NEW ANOMALY REPORT PROCESSING ---
    
    if dry_run:
        print("\n--- Dry Run Complete ---")
        print(f"\n{len(import_ready_df)} rows are clean and ready for import.")
        print(f"{len(anomalies_df)} rows have data gap anomalies.")
        print("\nDisplaying 'import-ready' data for 'askania-coat-tahini-melange':")
        print(import_ready_df[import_ready_df['Handle'] == 'askania-coat-tahini-melange'][['Handle', 'Image Src', 'Image Position', 'Tags']])
    else:
        # Save the full enriched file
        full_output_path = output_dir / "poc_shopify_import_enriched.csv"
        full_enriched_df.to_csv(full_output_path, index=False)
        print(f"\n✅ Full enriched CSV written successfully to: {full_output_path}")

        # Save the import-ready file
        ready_output_path = output_dir / "poc_shopify_import_ready.csv"
        import_ready_df.to_csv(ready_output_path, index=False)
        print(f"✅ Import-ready CSV ({len(import_ready_df)} rows) written successfully to: {ready_output_path}")

        # Save the anomalies file
        if not anomalies_df.empty:
            anomalies_output_path = output_dir / "poc_shopify_anomalies.csv"
            anomalies_df.to_csv(anomalies_output_path, index=False)
            print(f"⚠️  {len(anomalies_df)} rows with anomalies staged for review in: {anomalies_output_path}")

        # --- NEW: Save the structured anomaly report ---
        if not anomalies_report_df.empty:
            anomalies_report_output_path = output_dir / "data_gap_report.csv" # New filename
            anomalies_report_df.to_csv(anomalies_report_output_path, index=False)
            # Use nunique() on Handle for a count of unique products with issues
            print(f"📊 {anomalies_report_df['Handle'].nunique()} products with anomalies detailed in: {anomalies_report_output_path}")
        elif not anomalies_df.empty: # Only print if the original anomalies_df wasn't empty
             print("ℹ️  Anomaly details logged but structured report is empty (check mappings).")
        # else: # No anomalies were detected at all
        #     print("✨ No anomalies detected to report.") # Already covered by poc_shopify_anomalies.csv message
        # --- END NEW ---

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Enrich Shopify CSV using a capsule system.")
    parser.add_argument("--capsule", required=True, help="The capsule code (e.g., S126)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without writing files.")
    parser.add_argument("--override-file", help="Optional path to the override report CSV (e.g., data_gap_report_override.csv).")
    args = parser.parse_args()

    # --- Construct override path logic (optional, for convenience) ---
    override_file_path = args.override_file
    if args.override_file and not pathlib.Path(args.override_file).exists():
        # If override file arg is given but path doesn't exist, check default location
        default_path = pathlib.Path(f"capsules/{args.capsule}/outputs/data_gap_report_override.csv")
        if default_path.exists():
            override_file_path = str(default_path)
            print(f"  > INFO: Using default override file location: {override_file_path}")
        else:
            # Keep original arg path, loading logic in main will handle 'not found' warning
            pass

    main(args.capsule, args.dry_run, args.override_file)