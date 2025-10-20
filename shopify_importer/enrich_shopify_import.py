import pandas as pd
import re

def find_image_filename(product_id, file_contents):
    """
    Generic function to search raw text content of a file to find a filename.
    """
    all_filenames = re.findall(r"'(.*?)'", file_contents)
    for filename in all_filenames:
        if product_id in filename:
            return filename
    return None

def find_and_sort_model_images(product_id, model_file_contents):
    """
    Finds all model images for a product ID and sorts them logically.
    """
    all_filenames = re.findall(r"'(.*?)'", model_file_contents)
    product_images = [fn for fn in all_filenames if product_id in fn]
    
    def sort_key(filename):
        if 'hero_image' in filename:
            return 0
        match = re.search(r'model_image_(\d+)', filename)
        if match:
            return int(match.group(1))
        return 999
        
    return sorted(product_images, key=sort_key)

def build_tags(source_record, existing_tags_str):
    """
    Constructs the complete tag list based on the detailed business logic,
    using a native Python dictionary for collection tags.
    """
    # --- NATIVE TRANSLATION of Shopify Tags Guide.csv ---
    # This dictionary replaces the need for the external CSV file.
    # Note: "collection_new arrivals" from the CSV has been corrected to "collection_new-arrivals"
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
        88: "collection_ready-to-wear, collection_knitwear, collection_tops, collection_new-arrivals"
    }
    
    new_tags = []
    
    # --- Step 1: Generate Dynamic, Product-Specific Tags ---
    if pd.notna(source_record.get('Description')):
        style_name = source_record['Description'].title()
        new_tags.append(f"style_{style_name}")
        
    if pd.notna(source_record.get('SEASON CODE')):
        season_code = str(source_record['SEASON CODE'])
        if 'S1' in season_code:
             new_tags.append(season_code.replace('S1', 'SS'))
        else:
             new_tags.append(season_code)

    if pd.notna(source_record.get('Colour')):
        color_name = ' '.join(str(source_record['Colour']).split(' ')[1:]).lower()
        new_tags.append(f"color_{color_name}")
        
    # --- Step 2: Generate Collection Tags from the native dictionary ---
    if pd.notna(source_record.get('CATEGORY CODE')):
        category_code = int(source_record['CATEGORY CODE'])
        if category_code in category_tags_map:
            collection_tags_str = category_tags_map[category_code]
            collection_tags = [tag.strip() for tag in collection_tags_str.split(',')]
            new_tags.extend(collection_tags)
        
    # --- Step 3: Combine all tags and de-duplicate ---
    existing_tags = [tag.strip() for tag in str(existing_tags_str).split(',') if tag.strip()]
    combined_tags = list(dict.fromkeys(existing_tags + new_tags))
    
    return ', '.join(filter(None, combined_tags))


def enrich_shopify_import_poc(source_file, scaffold_file, ghost_file, model_file, output_file, cdn_prefix):
    """
    Enriches an existing Shopify export scaffold with master data for a single product.
    """
    try:
        print("Attempting to read source files...")
        source_df = pd.read_csv(source_file, header=1, encoding='cp1252')
        scaffold_df = pd.read_csv(scaffold_file)
        with open(ghost_file, 'r') as f:
            ghost_file_contents = f.read()
        with open(model_file, 'r') as f:
            model_file_contents = f.read()
        print("Successfully loaded all source files.")
    except FileNotFoundError as e:
        print(f"Error loading file: {e}. Please ensure all required files are in the directory.")
        return
    except Exception as e:
        print(f"An unexpected error occurred while reading the files: {e}")
        return

    source_df.set_index('Product ID', inplace=True)

    test_handle = 'askania-coat-tahini-melange'
    
    product_group_df = scaffold_df[scaffold_df['Handle'] == test_handle].copy()

    if product_group_df.empty:
        print(f"Test handle '{test_handle}' not found in the scaffold file.")
        return

    parent_row_filter = product_group_df['Title'].notna() & (product_group_df['Title'] != '')
    parent_row = product_group_df[parent_row_filter]
    
    if parent_row.empty:
        print(f"Could not find a parent row for handle '{test_handle}'.")
        return
        
    parent_row_index = parent_row.index[0]
    
    tags_string = scaffold_df.loc[parent_row_index, 'Tags']
    if pd.isna(tags_string):
        print(f"Tags are empty for handle '{test_handle}'.")
        return

    product_id_tag = next((tag.strip() for tag in tags_string.split(',') if tag.strip().count(' ') >= 3), None)

    if not product_id_tag:
        print(f"Could not extract a valid Product ID from tags for handle '{test_handle}'.")
        return
    
    print(f"Found linking key. Extracted Product ID '{product_id_tag}' from tags.")

    try:
        source_record = source_df.loc[product_id_tag]
        print(f"Successfully found matching data for '{product_id_tag}' in the source file.")
    except KeyError:
        print(f"Product ID '{product_id_tag}' not found in source file '{source_file}'.")
        return
    
    print("Enriching data for the product group...")
    
    child_rows = product_group_df[~parent_row_filter]
    model_image_files = find_and_sort_model_images(product_id_tag, model_file_contents)
    
    # --- Enrich Parent Row ---
    # Call the updated build_tags function which no longer needs the tags guide
    product_group_df.loc[parent_row_index, 'Tags'] = build_tags(source_record, tags_string)

    ghost_filename = find_image_filename(product_id_tag, ghost_file_contents)
    if ghost_filename:
        shopify_ghost_filename = ghost_filename.replace(' ', '_')
        full_image_url = cdn_prefix + shopify_ghost_filename
        product_group_df.loc[parent_row_index, 'Image Src'] = full_image_url
        product_group_df.loc[parent_row_index, 'Image Position'] = 1
        print(f"  > Updated Image Src for parent: {full_image_url}")
    else:
        print(f"  > WARNING: No ghost image found for {product_id_tag}")

    if pd.notna(source_record.get('PRODUCT DETAILS')):
        product_group_df.loc[parent_row_index, 'Details (product.metafields.altuzarra.details)'] = source_record['PRODUCT DETAILS']
    
    product_group_df.loc[parent_row_index, 'Variant Price'] = source_record['RRP (USD)']
    
    # --- Enrich Child Rows ---
    for i, (index, row) in enumerate(child_rows.iterrows()):
        if i < len(model_image_files):
            model_filename = model_image_files[i]
            shopify_model_filename = model_filename.replace(' ', '_')
            full_image_url = cdn_prefix + shopify_model_filename
            product_group_df.loc[index, 'Image Src'] = full_image_url
            product_group_df.loc[index, 'Image Position'] = i + 2
        else:
            product_group_df.loc[index, 'Image Src'] = ''
            product_group_df.loc[index, 'Image Position'] = ''
            
        product_group_df.loc[index, 'Variant Price'] = source_record['RRP (USD)']

    # --- Phase 3: Final Data Cleaning and Save ---
    
    product_group_df['Image Position'] = product_group_df['Image Position'].replace('', pd.NA)
    product_group_df['Image Position'] = product_group_df['Image Position'].astype('Int64')

    output_df = product_group_df
    
    output_df.to_csv(output_file, index=False)
    print(f"\nProof of concept enrichment complete!")
    print(f"File saved as: {output_file}")
    print("\n--- Enriched Data Highlights (Parent Row) ---")
    print(output_df[parent_row_filter][['Handle', 'Variant SKU', 'Tags', 'Image Src', 'Image Position']].to_string())
    print("\n--- Enriched Data Highlights (Child Rows) ---")
    print(output_df[~parent_row_filter][['Handle', 'Variant SKU', 'Image Src', 'Image Position']].to_string())
    print(f"\nTotal rows in output for this handle: {len(output_df)}")


if __name__ == '__main__':
    SOURCE_CSV = 'SS26 for Shopify check(By Style).csv'
    SCAFFOLD_CSV = 'products_export_1.csv'
    GHOST_FILE = 'ghostFileNames.txt'
    MODEL_FILE = 'modelFileNames.txt'
    OUTPUT_CSV = 'poc_shopify_import_enriched.csv'
    CDN_PREFIX_URL = 'https://cdn.shopify.com/s/files/1/0148/9561/2004/files/'
    
    # The tags guide file is no longer needed for the main function
    enrich_shopify_import_poc(SOURCE_CSV, SCAFFOLD_CSV, GHOST_FILE, MODEL_FILE, OUTPUT_CSV, CDN_PREFIX_URL)