import pandas as pd
import argparse
import pathlib

def find_missing_handles(enriched_file_path: str, ready_file_path: str):
    """
    Compares handles in the enriched CSV and the ready CSV to find
    which handles are present in enriched but missing from ready.

    Args:
        enriched_file_path: Path to the poc_shopify_import_enriched.csv file.
        ready_file_path: Path to the poc_shopify_import_ready.csv file.
    """
    print(f"Loading enriched file: {enriched_file_path}")
    try:
        df_enriched = pd.read_csv(enriched_file_path)
        # Ensure Handle column is string and stripped
        df_enriched['Handle'] = df_enriched['Handle'].astype(str).str.strip()
        handles_enriched = set(df_enriched['Handle'].unique())
        print(f"  > Found {len(handles_enriched)} unique handles.")
    except FileNotFoundError:
        print(f"❌ Error: File not found at {enriched_file_path}")
        return
    except Exception as e:
        print(f"❌ Error loading {enriched_file_path}: {e}")
        return

    print(f"Loading ready file: {ready_file_path}")
    try:
        df_ready = pd.read_csv(ready_file_path)
        # Ensure Handle column is string and stripped
        df_ready['Handle'] = df_ready['Handle'].astype(str).str.strip()
        handles_ready = set(df_ready['Handle'].unique())
        print(f"  > Found {len(handles_ready)} unique handles.")
    except FileNotFoundError:
        print(f"❌ Error: File not found at {ready_file_path}")
        handles_ready = set() # Assume empty if not found
    except Exception as e:
        print(f"❌ Error loading {ready_file_path}: {e}")
        return

    # Find handles in enriched but not in ready
    missing_handles = handles_enriched - handles_ready

    if missing_handles:
        print(f"\nHandles present in '{pathlib.Path(enriched_file_path).name}' but MISSING from '{pathlib.Path(ready_file_path).name}':")
        # Sort for consistent output
        for handle in sorted(list(missing_handles)):
            print(f"- {handle}")
        print(f"\nTotal missing handles: {len(missing_handles)}")
    else:
        print("\n✅ All handles from the enriched file are present in the ready file.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare handles between enriched and ready Shopify CSV files.")
    parser.add_argument(
        "--enriched-file",
        required=True,
        help="Path to the poc_shopify_import_enriched.csv file."
    )
    parser.add_argument(
        "--ready-file",
        required=True,
        help="Path to the poc_shopify_import_ready.csv file."
    )
    # Add optional output file argument if needed later
    # parser.add_argument("--output-file", help="Optional path to save the list of missing handles.")

    args = parser.parse_args()

    find_missing_handles(args.enriched_file, args.ready_file)
