import pandas as pd
import argparse
import pathlib
from datetime import datetime # Import datetime

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
        # Explicitly set low_memory=False if there are mixed type warnings during load
        df_ready = pd.read_csv(ready_file_path, low_memory=False)
        print(f"  > Loaded {len(df_ready)} rows.")
    except FileNotFoundError:
        print(f"❌ Error: File not found at {ready_file_path}")
        return
    except Exception as e:
        print(f"❌ Error loading {ready_file_path}: {e}")
        return

    print(f"Loading 'missing images' file: {missing_file_path}")
    try:
        df_missing = pd.read_csv(missing_file_path, low_memory=False)
        print(f"  > Loaded {len(df_missing)} rows.")
        # Select only necessary columns to avoid type conflicts
        cols_to_keep = ['Handle', 'Image Src', 'Image Position']
        # Keep only columns that actually exist in df_missing
        cols_present = [col for col in cols_to_keep if col in df_missing.columns]
        df_missing = df_missing[cols_present]

    except FileNotFoundError:
        print(f"ℹ️ Info: File not found at {missing_file_path}. Skipping combination.")
        df_missing = pd.DataFrame() # Create empty DataFrame
    except Exception as e:
        print(f"❌ Error loading {missing_file_path}: {e}")
        return

    # Combine the DataFrames
    if not df_missing.empty:
        print(f"Combining {len(df_ready)} and {len(df_missing)} rows...")
        # Ensure 'Handle' is string in both before concat
        df_ready['Handle'] = df_ready['Handle'].astype(str)
        df_missing['Handle'] = df_missing['Handle'].astype(str)
        df_combined = pd.concat([df_ready, df_missing], ignore_index=True)
        print(f"  > Combined DataFrame has {len(df_combined)} rows.")
    else:
        print("No missing image rows to combine.")
        df_combined = df_ready.copy() # Use a copy

    # --- CRITICAL STEP: Sort by Handle, then by Image Position ---
    # Ensure Handle is string before sorting
    df_combined['Handle'] = df_combined['Handle'].astype(str)
    # Convert Image Position to numeric, coercing errors to NaN
    df_combined['Image Position'] = pd.to_numeric(df_combined['Image Position'], errors='coerce')

    print("Sorting combined data by Handle and Image Position...")
    # Sort, placing NaN positions last
    df_combined.sort_values(by=['Handle', 'Image Position'], inplace=True, na_position='last')

    # Reset index after sorting if desired (optional)
    # df_combined.reset_index(drop=True, inplace=True)

    # Ensure Image Position is Integer (using nullable Int64) after sorting
    # Handle potential All-NA slice warning if converting a column full of NaNs
    if pd.api.types.is_numeric_dtype(df_combined['Image Position']):
         df_combined['Image Position'] = df_combined['Image Position'].astype('Int64')
    else:
         # If it became object due to mix types or errors, try coercing again
         df_combined['Image Position'] = pd.to_numeric(df_combined['Image Position'], errors='coerce').astype('Int64')


    # Save the combined and sorted DataFrame
    try:
        # Use the column order from the original ready file if possible
        output_columns = df_ready.columns if not df_ready.empty else df_combined.columns
        df_combined.to_csv(output_file_path, index=False, columns=output_columns)
        print(f"✅ Combined and sorted CSV saved successfully to: {output_file_path}")
    except Exception as e:
        print(f"❌ Error saving combined file to {output_file_path}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Combine Shopify ready import CSV with missing image rows CSV.")
    parser.add_argument(
        "--ready-file",
        required=True,
        help="Path to the poc_shopify_import_ready*.csv file (timestamp can be included)."
    )
    parser.add_argument(
        "--missing-file",
        required=True,
        help="Path to the missing_img_src_files*.csv file (timestamp should match ready-file)."
    )
    parser.add_argument(
        "--output-file",
        default=None, # Default is None, will be constructed
        help="Optional: Full path for the output combined CSV file (timestamp will be added if not included)."
    )

    args = parser.parse_args()

    # --- Add timestamp ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Determine output path
    output_path_str = args.output_file
    if output_path_str is None:
        # Default: Place next to ready file with timestamp
        ready_path = pathlib.Path(args.ready_file)
        output_dir = ready_path.parent
        output_filename = f"poc_shopify_import_combined_{timestamp}.csv"
        output_path = output_dir / output_filename
    else:
        # If path provided, ensure it ends with .csv and add timestamp if missing
        output_path = pathlib.Path(output_path_str)
        # Check if filename already seems to have a similar timestamp structure
        stem = output_path.stem # Filename without extension
        suffix = output_path.suffix

        # Simple check if stem ends with _YYYYMMDD_HHMMSS
        if not re.search(r'_\d{8}_\d{6}$', stem):
            output_filename = f"{stem}_{timestamp}{suffix}"
            output_path = output_path.with_name(output_filename)

    # Create parent directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert path back to string for the function call
    combine_csvs(args.ready_file, args.missing_file, str(output_path))