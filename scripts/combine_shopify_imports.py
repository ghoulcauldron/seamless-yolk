import pandas as pd
import argparse
import pathlib

def combine_csvs(ready_file_path: str, missing_file_path: str, output_file_path: str):
    """
    Combines the 'ready' Shopify import CSV with the 'missing images' CSV.

    Args:
        ready_file_path: Path to the poc_shopify_import_ready.csv file.
        missing_file_path: Path to the missing_img_src_files.csv file.
        output_file_path: Path where the combined CSV should be saved.
    """
    print(f"Loading 'ready' file: {ready_file_path}")
    try:
        df_ready = pd.read_csv(ready_file_path)
        print(f"  > Loaded {len(df_ready)} rows.")
    except FileNotFoundError:
        print(f"❌ Error: File not found at {ready_file_path}")
        return
    except Exception as e:
        print(f"❌ Error loading {ready_file_path}: {e}")
        return

    print(f"Loading 'missing images' file: {missing_file_path}")
    try:
        df_missing = pd.read_csv(missing_file_path)
        print(f"  > Loaded {len(df_missing)} rows.")
        # Optional: Select only necessary columns if df_missing has extra empty ones
        # Use columns present in df_ready to ensure compatibility
        cols_to_keep = ['Handle', 'Image Src', 'Image Position']
        # Keep only columns that actually exist in df_missing to avoid errors
        cols_present = [col for col in cols_to_keep if col in df_missing.columns]
        df_missing = df_missing[cols_present]

    except FileNotFoundError:
        print(f"ℹ️ Info: File not found at {missing_file_path}. Skipping combination.")
        df_missing = pd.DataFrame() # Create empty DataFrame if missing file is okay
    except Exception as e:
        print(f"❌ Error loading {missing_file_path}: {e}")
        return

    # Combine the DataFrames
    if not df_missing.empty:
        print(f"Combining {len(df_ready)} and {len(df_missing)} rows...")
        df_combined = pd.concat([df_ready, df_missing], ignore_index=True)
        print(f"  > Combined DataFrame has {len(df_combined)} rows.")
    else:
        print("No missing image rows to combine.")
        df_combined = df_ready # Use only the ready df if missing is empty

    # --- CRITICAL STEP: Sort by Handle, then by Image Position ---
    # Convert Image Position to numeric, coercing errors to NaN for safe sorting
    df_combined['Image Position'] = pd.to_numeric(df_combined['Image Position'], errors='coerce')
    # Fill NaN positions with a large number so they sort last if needed, or handle differently
    # Let's keep NA for now and sort, NA values might sort first or last depending on pandas version
    # It's better to sort explicitly, putting NaNs last.
    print("Sorting combined data by Handle and Image Position...")
    df_combined.sort_values(by=['Handle', 'Image Position'], inplace=True, na_position='last')

    # Ensure Image Position is Integer (using nullable Int64) after sorting
    df_combined['Image Position'] = df_combined['Image Position'].astype('Int64')

    # Save the combined and sorted DataFrame
    try:
        # Use the column order from the original ready file
        output_columns = df_ready.columns
        df_combined.to_csv(output_file_path, index=False, columns=output_columns)
        print(f"✅ Combined and sorted CSV saved successfully to: {output_file_path}")
    except Exception as e:
        print(f"❌ Error saving combined file to {output_file_path}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Combine Shopify ready import CSV with missing image rows CSV.")
    parser.add_argument(
        "--ready-file",
        required=True,
        help="Path to the poc_shopify_import_ready.csv file."
    )
    parser.add_argument(
        "--missing-file",
        required=True,
        help="Path to the missing_img_src_files.csv file."
    )
    parser.add_argument(
        "--output-file",
        default=None, # Default is None, will be constructed based on ready-file path
        help="Path for the output combined CSV file (default: poc_shopify_import_combined.csv in same dir as ready-file)."
    )

    args = parser.parse_args()

    # Determine output path if not provided
    output_path = args.output_file
    if output_path is None:
        ready_path = pathlib.Path(args.ready_file)
        output_path = ready_path.parent / "poc_shopify_import_combined.csv"
    else:
        output_path = pathlib.Path(output_path) # Ensure it's a Path object

    # Create parent directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)


    combine_csvs(args.ready_file, args.missing_file, str(output_path))
