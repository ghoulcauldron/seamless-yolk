import pandas as pd
import argparse
import pathlib

def find_duplicate_image_src(file_path: str):
    """
    Finds and prints duplicate non-blank Image Src values and their row numbers in a CSV.

    Args:
        file_path: Path to the Shopify import CSV file.
    """
    print(f"Loading file: {file_path}")
    try:
        # Load the CSV, ensure Image Src is treated as string, handle potential mixed types
        df = pd.read_csv(file_path, low_memory=False, dtype={'Image Src': str})
        print(f"  > Loaded {len(df)} rows.")
    except FileNotFoundError:
        print(f"❌ Error: File not found at {file_path}")
        return
    except Exception as e:
        print(f"❌ Error loading {file_path}: {e}")
        return

    # Fill NaN in 'Image Src' with empty string for consistent filtering
    df['Image Src'] = df['Image Src'].fillna('')

    # Filter out rows where Image Src is blank
    df_with_images = df[df['Image Src'] != ''].copy()

    if df_with_images.empty:
        print("No rows with Image Src found.")
        return

    # Find duplicates based on 'Image Src', keep all occurrences marked as True
    duplicates_mask = df_with_images.duplicated(subset=['Image Src'], keep=False)

    # Filter the DataFrame to get only the rows that are duplicates
    duplicate_rows = df_with_images[duplicates_mask]

    if duplicate_rows.empty:
        print("✅ No duplicate Image Src values found.")
    else:
        print(f"\n⚠️ Found {len(duplicate_rows['Image Src'].unique())} Image Src values with duplicates:")
        # Group by the duplicate Image Src to report them together
        grouped_duplicates = duplicate_rows.groupby('Image Src')

        for image_src, group in grouped_duplicates:
            # Get the original indices from the loaded DataFrame (df)
            # Add 2 for 1-based indexing + header row
            row_numbers = [index + 2 for index in group.index]
            print(f"\n  - Image Src: {image_src}")
            print(f"    Found on Rows: {row_numbers}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find duplicate Image Src entries in a Shopify import CSV.")
    parser.add_argument(
        "--input-file",
        required=True,
        help="Path to the poc_shopify_import_combined_{timestamp}.csv file."
    )

    args = parser.parse_args()

    input_path = pathlib.Path(args.input_file)

    if not input_path.exists():
        print(f"❌ Error: Input file not found at {args.input_file}")
    else:
        find_duplicate_image_src(str(input_path))