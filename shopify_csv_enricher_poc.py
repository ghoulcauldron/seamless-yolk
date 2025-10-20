import pandas as pd
import re

def enrich_shopify_import_poc(source_file, scaffold_file, output_file, cdn_prefix):
    """
    Enriches an existing Shopify export scaffold with master data for a single product,
    using the Product ID from the scaffold's tags as the linking key.

    Args:
        source_file (str): Path to the master data CSV (SS26 for Shopify check).
        scaffold_file (str): Path to the existing Shopify export to be enriched.
        output_file (str): Path to save the generated, enriched CSV.
        cdn_prefix (str): The base URL for the Shopify CDN.
    """
    # --- Phase 1: Setup and Data Loading ---
    try:
        # NEW DIAGNOSTIC LINE: This will print to the terminal to confirm this new script is running.
        print("Attempting to read source file with 'cp1252' encoding...")
        source_df = pd.read_csv(source_file, header=1, encoding='cp1252')
        # Load the scaffold file we are going to update
        scaffold_df = pd.read_csv(scaffold_file)
        print("Successfully loaded both CSV files.")
    except FileNotFoundError as e:
        print(f"Error loading file: {e}")
        return
    except Exception as e:
        print(f"An unexpected error occurred while reading the files: {e}")
        return


    # For faster lookups, set the 'Product ID' as the index of our source data
    source_df.set_index('Product ID', inplace=True)

    # --- Phase 2: Reconciliation and Enrichment ---
    test_handle = 'askania-coat-tahini-melange'
    
    # Isolate the target row from the scaffold file using its handle
    target_record = scaffold_df[scaffold_df['Handle'] == test_handle]

    if target_record.empty:
        print(f"Test handle '{test_handle}' not found in the scaffold file '{scaffold_file}'.")
        return
        
    target_row_index = target_record.index[0]
    
    # Extract the linking key (Product ID) from the 'Tags' column
    tags_string = scaffold_df.loc[target_row_index, 'Tags']
    if pd.isna(tags_string):
        print(f"Tags are empty for handle '{test_handle}'. Cannot find linking Product ID.")
        return

    tags_list = [tag.strip() for tag in tags_string.split(',')]
    product_id_tag = None
    for tag in tags_list:
        if tag.count(' ') >= 3:
            product_id_tag = tag
            break

    if not product_id_tag:
        print(f"Could not extract a valid Product ID from the tags for handle '{test_handle}'. Tags found: '{tags_string}'")
        return
    
    print(f"Found linking key. Extracted Product ID '{product_id_tag}' from tags.")

    # Locate the source record in the master DataFrame
    try:
        source_record = source_df.loc[product_id_tag]
        print(f"Successfully found matching data for '{product_id_tag}' in the source file.")
    except KeyError:
        print(f"Product ID '{product_id_tag}' (from tags) not found in source file '{source_file}'.")
        return
    
    # --- Step 2.4: Perform the Data Enrichment ---
    print("Enriching data...")

    scaffold_df.loc[target_row_index, 'Variant SKU'] = product_id_tag
    scaffold_df.loc[target_row_index, 'Variant Price'] = source_record['RRP (USD)']
    
    image_filename = re.sub(r'\s+', '', product_id_tag) + ".jpg"
    full_image_url = cdn_prefix + image_filename
    scaffold_df.loc[target_row_index, 'Image Src'] = full_image_url

    color_name = ' '.join(source_record['Colour'].split(' ')[1:])
    scaffold_df.loc[target_row_index, 'Color (product.metafields.altuzarra.color)'] = color_name
    scaffold_df.loc[target_row_index, 'Swatch: Color (product.metafields.altuzarra.swatch_color)'] = color_name
    scaffold_df.loc[target_row_index, 'Subcategory (product.metafields.altuzarra.subcategory)'] = source_record['TYPE']

    details_html = "<ul>"
    if pd.notna(source_record['FABRIC CONTENT']):
        details_html += f"<li>{source_record['FABRIC CONTENT']}</li>"
    if pd.notna(source_record['COUNTRY OF ORIGIN']):
         details_html += f"<li>Made in {source_record['COUNTRY OF ORIGIN'].title()}</li>"
    details_html += "</ul>"
    scaffold_df.loc[target_row_index, 'Details (product.metafields.altuzarra.details)'] = details_html

    # --- Phase 3: Save the Output ---
    output_df = scaffold_df.iloc[[target_row_index]]
    
    output_df.to_csv(output_file, index=False)
    print(f"\nProof of concept enrichment complete!")
    print(f"File saved as: {output_file}")
    print("\n--- Enriched Data Highlights ---")
    print(output_df[['Handle', 'Variant SKU', 'Variant Price', 'Tags', 'Image Src']].to_string())


if __name__ == '__main__':
    SOURCE_CSV = 'SS26 for Shopify check(By Style).csv'
    SCAFFOLD_CSV = 'products_export_1.csv'
    OUTPUT_CSV = 'poc_shopify_import_enriched.csv'
    CDN_PREFIX_URL = 'https://cdn.shopify.com/s/files/1/0148/9561/2004/files/'
    
    enrich_shopify_import_poc(SOURCE_CSV, SCAFFOLD_CSV, OUTPUT_CSV, CDN_PREFIX_URL)