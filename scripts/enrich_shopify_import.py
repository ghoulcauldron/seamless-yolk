import pandas as pd
import re
import json
import pathlib
import argparse
from datetime import datetime

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
    def sort_key(img):
        filename = img['filename']
        if is_accessory:
            if 'ghost' in filename: return (0, filename)
            return (1, filename)
        else:
            if 'hero_image' in filename: return (0, filename)
            match = re.search(r'model_image_(\d+)', filename)
            if match: return (1, int(match.group(1)))
            return (2, filename)
    return sorted(images, key=sort_key)

def main(capsule: str, dry_run: bool):
    CDN_PREFIX = 'https://cdn.shopify.com/s/files/1/0148/9561/2004/files/'
    anomalous_handles = set()

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

    handle_to_cpi_map = {
        row['Handle']: cpi for _, row in export_df[export_df['Title'].notna()].iterrows()
        if (cpi := extract_cpi_from_product_id(extract_product_id_from_tags(row['Tags'])))
    }
    print(f"✅ Built Handle-to-CPI map for {len(handle_to_cpi_map)} products.")
    
    tracker_df.set_index('Product ID', inplace=True)
    tracker_df['RRP (USD)'] = pd.to_numeric(tracker_df['RRP (USD)'], errors='coerce')

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
            print(f"  > ANOMALY: Product ID '{full_product_id}' not found in tracker file.")
            anomalous_handles.add(handle)
            continue
            
        images_for_cpi = manifest_df[manifest_df['cpi'] == cpi].to_dict('records')
        if not images_for_cpi:
            print(f"  > ANOMALY: No images found in manifest for CPI {cpi}.")
            anomalous_handles.add(handle)
            continue
            
        is_accessory = images_for_cpi[0].get('is_accessory', False)
        sorted_images = sort_images(images_for_cpi, is_accessory)
        
        for i, index in enumerate(product_group.index):
            if i < len(sorted_images):
                filename = sorted_images[i]['filename']
                export_df.loc[index, 'Image Src'] = CDN_PREFIX + filename.replace(' ', '_')
                export_df.loc[index, 'Image Position'] = i + 1
            else:
                export_df.loc[index, 'Image Src'] = ''
                export_df.loc[index, 'Image Position'] = pd.NA
    
    export_df['Image Position'] = export_df['Image Position'].astype('Int64')
    
    # --- 4. Split DataFrame and Save Outputs ---
    output_dir = capsule_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Define the three output dataframes
    full_enriched_df = export_df
    import_ready_df = export_df[~export_df['Handle'].isin(anomalous_handles)]
    anomalies_df = export_df[export_df['Handle'].isin(anomalous_handles)]
    
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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Enrich Shopify CSV using a capsule system.")
    parser.add_argument("--capsule", required=True, help="The capsule code (e.g., S126)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without writing files.")
    args = parser.parse_args()
    main(args.capsule, args.dry_run)