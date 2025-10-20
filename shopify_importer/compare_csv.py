import pandas as pd
import sys

def compare_sections_in_file(comparison_file, handle):
    """
    Reads a single CSV containing 'generated' and 'original' data sections,
    separated by a blank row, and reports the differences for a specific handle.

    Args:
        comparison_file (str): Path to the combined CSV file.
        handle (str): The product handle to isolate for comparison.
    """
    try:
        # Load the single comparison file
        df = pd.read_csv(comparison_file)
    except FileNotFoundError as e:
        print(f"Error loading file: {e}")
        print("Please ensure the comparison CSV file is in the correct directory.")
        return

    print(f"\n--- Starting Comparison for Handle: '{handle}' in file '{comparison_file}' ---")

    # Find the first completely blank row which acts as a separator
    try:
        separator_index = df[df.isnull().all(axis=1)].index[0]
        
        # Split the dataframe into two sections based on the separator
        generated_df = df.iloc[:separator_index]
        original_df = df.iloc[separator_index + 1:]

    except IndexError:
        print("Error: Could not find a blank separator row in the CSV.")
        print("Please ensure the 'generated' and 'original' sections are separated by a completely empty row.")
        return

    # Isolate the relevant rows from both sections
    original_group = original_df[original_df['Handle'] == handle].reset_index(drop=True)
    generated_group = generated_df[generated_df['Handle'] == handle].reset_index(drop=True)

    if original_group.empty:
        print(f"Error: Handle '{handle}' not found in the 'original' section of the file.")
        return
    if generated_group.empty:
        print(f"Error: Handle '{handle}' not found in the 'generated' section of the file.")
        return

    diffs = []
    
    # Use the generated file's columns as the primary reference
    common_columns = [col for col in generated_group.columns if col in original_group.columns]
    
    for i in generated_group.index:
        if i >= len(original_group):
            diffs.append({
                "Row": i + 1,
                "Column": "ENTIRE ROW",
                "Original Value": "Row does not exist",
                "Generated Value": "Row was added"
            })
            continue

        for col in common_columns:
            original_val = original_group.loc[i, col]
            generated_val = generated_group.loc[i, col]
            
            # Treat NaN/None/blank strings as the same
            if (pd.isna(original_val) or str(original_val).strip() == "") and \
               (pd.isna(generated_val) or str(generated_val).strip() == ""):
                continue

            if str(original_val) != str(generated_val):
                diffs.append({
                    "Row": i + 1,
                    "Column": col,
                    "Original Value": str(original_val),
                    "Generated Value": str(generated_val)
                })

    if not diffs:
        print(">>> No differences found. Generated data matches original for all compared fields.")
    else:
        print(f">>> Found {len(diffs)} differences:")
        for diff in diffs:
            print(f"  - Row {diff['Row']}, Column '{diff['Column']}':")
            print(f"    Original : '{diff['Original Value']}'")
            print(f"    Generated: '{diff['Generated Value']}'")
            
    return diffs

if __name__ == '__main__':
    # --- Configuration ---
    # The single file containing both the generated and original data
    COMPARISON_CSV = 'poc_shopify_import_enriched - poc_shopify_import_enriched.csv.csv'
    HANDLE_TO_COMPARE = 'askania-coat-tahini-melange'
    
    # --- Execution ---
    if len(sys.argv) == 3:
        # Example: python compare_csv.py "my_comparison_file.csv" "handle-to-check"
        compare_sections_in_file(sys.argv[1], sys.argv[2])
    else:
        print("Running with hardcoded filename and handle...")
        compare_sections_in_file(COMPARISON_CSV, HANDLE_TO_COMPARE)