# scripts/parse_shotlists.py
import pandas as pd
import json
import pathlib
import re

def find_shotlist_files(base_path: pathlib.Path) -> tuple:
    """
    Finds the master shotlist '(SS26).csv' and the day logs '(DAY 1).csv' / '(DAY 2).csv'.
    """
    master_file = list(base_path.glob("*(SS26).csv"))
    day_logs = list(base_path.glob("*(DAY 1).csv"))
    day_logs.extend(list(base_path.glob("*(DAY 2).csv")))
    
    if not master_file:
        print(f"❌ Error: No master shotlist file ending with '(SS26).csv' found in {base_path}")
        return None, None
    
    if not day_logs:
        print(f"❌ Error: No '(DAY 1).csv' or '(DAY 2).csv' log files found in {base_path}")
        return None, None
        
    return master_file[0], day_logs

def load_master_file(path: pathlib.Path) -> pd.DataFrame:
    """Loads the master (SS26).csv file."""
    print(f"Parsing master shotlist: {path.name}...")
    # Assume header is on the first row for the master file
    df = pd.read_csv(path, dtype=str, header=0) 
    df.columns = [col.strip().lower() for col in df.columns]
    
    required_cols = ["product id", "look #", "hero image (styled)"]
    if not all(col in df.columns for col in required_cols):
        print(f"❌ Error: Master shotlist {path.name} is missing required columns: {required_cols}")
        return None
        
    df.dropna(subset=["product id", "look #"], inplace=True)
    return df

def find_header_row(path: pathlib.Path, max_rows_to_check=20) -> int | None:
    """Reads the first few rows to find the actual header row index."""
    try:
        # Read without assuming header
        df_peek = pd.read_csv(path, header=None, nrows=max_rows_to_check, dtype=str, skip_blank_lines=False)
        for index, row in df_peek.iterrows():
            row_values = [str(val).strip().lower() for val in row.dropna().values]
            # Check if essential columns are present in this row
            has_folder = any('folder name' in val for val in row_values)
            # Be more specific for look number
            has_look = any(val == 'look #' or val == 'look' for val in row_values) 
            if has_folder and has_look:
                return index # Return the row index (0-based)
    except Exception as e:
        print(f"  > ⚠️  Warning: Error peeking into {path.name} to find header: {e}")
    return None

def load_day_logs(paths: list) -> pd.DataFrame:
    """Loads and combines all day log CSVs, finding the correct header row."""
    dfs = []
    for path in paths:
        print(f"Parsing day log: {path.name}...")
        
        header_row_index = find_header_row(path)
        if header_row_index is None:
            print(f"  > ⚠️  Warning: Skipping log file {path.name}. Could not find header row containing 'FOLDER NAME' and 'LOOK #'/'LOOK'.")
            continue
        print(f"  > Found header row at index {header_row_index}.")

        try:
            # Read the full CSV using the found header row index
            df = pd.read_csv(path, dtype=str, header=header_row_index)
            
            # --- FIX: Refined column standardization ---
            standardized_columns = {}
            found_folder = False
            found_look = False
            for col in df.columns:
                cleaned_col = str(col).strip().lower()
                if cleaned_col == 'folder name' and not found_folder:
                    standardized_columns[col] = 'folder name'
                    found_folder = True
                elif (cleaned_col == 'look #' or cleaned_col == 'look') and not found_look:
                     standardized_columns[col] = 'look #'
                     found_look = True
                # Keep other columns as they are initially, just cleaned
                # else:
                #    standardized_columns[col] = cleaned_col
            
            # Rename columns based on the map
            df.rename(columns=standardized_columns, inplace=True)
            # --- END FIX ---

            print(f"  > Standardized columns found: {df.columns.tolist()}") # Keep debug line

            required_cols = ["folder name", "look #"]
            if not all(col in df.columns for col in required_cols):
                print(f"  > ⚠️  Warning: Skipping log file {path.name}. Missing required columns after reading header: {required_cols}. Columns available: {df.columns.tolist()}")
                continue
                
            # Select only the columns we need *after* renaming
            dfs.append(df[required_cols]) 
        except Exception as e:
            print(f"  > ⚠️  Warning: Could not parse {path.name} even after finding header. Error: {e}")
            
    if not dfs:
        return None
        
    # Concatenate using the standardized names
    return pd.concat(dfs, ignore_index=True).dropna(subset=["folder name", "look #"])

def clean_folder_name(folder_name: str) -> str:
    """
    Cleans a 'FOLDER NAME' string to extract the base Product ID.
    e.g., 'S126-5016...BLACK_FINAL_model_image_4' -> 'S126-5016...BLACK'
    """
    if pd.isna(folder_name):
        return None
    # Trim everything from '_FINAL_' onwards
    return re.sub(r"_FINAL_.*$", "", folder_name, flags=re.IGNORECASE).strip()

def main(capsule="S126"):
    base_path = pathlib.Path(f"capsules/{capsule}/inputs/shotlists")
    master_file_path, day_log_paths = find_shotlist_files(base_path)
    
    if not master_file_path or not day_log_paths:
        return

    df_master = load_master_file(master_file_path)
    df_logs = load_day_logs(day_log_paths)
    
    if df_master is None or df_logs is None:
        print("❌ Error: Could not parse required files. Exiting.")
        return

    looks = {}
    
    # Use the master file as the driver
    for look_no, group in df_master.groupby("look #"):
        
        # 1. Find the Hero Product from the master file
        hero_product_id = None
        hero_rows = group[group["hero image (styled)"].notna() & (group["hero image (styled)"] != '')]
        
        if not hero_rows.empty:
            hero_product_id = hero_rows.iloc[0]["product id"]
        else:
            # Fallback logic if no hero is marked
            print(f"  > ⚠️  Warning for Look {look_no}: No 'Hero Image (styled)' marked. Defaulting to first product.")
            hero_product_id = group.iloc[0]["product id"]
        
        # 2. Find all related products from the day logs
        #    Make sure we compare look_no as string, as CSV reads everything as string
        log_rows = df_logs[df_logs["look #"] == str(look_no)] 
        if log_rows.empty:
            print(f"  > ⚠️  Warning for Look {look_no}: No entries found in Day 1/2 logs.")
            continue
            
        # 3. Clean the folder names to get base Product IDs
        related_product_ids = [clean_folder_name(name) for name in log_rows["folder name"]]
        
        # Get a unique, non-null list
        unique_product_ids = sorted(list(set(filter(None, related_product_ids))))
        
        if not unique_product_ids:
            print(f"  > ⚠️  Warning for Look {look_no}: Could not parse any valid product IDs from logs.")
            continue

        looks[f"Look_{look_no}"] = {
            "product_ids": unique_product_ids,
            "hero_product": hero_product_id
        }

    out = {
        "metadata": {"source_files": [p.name for p in [master_file_path] + day_log_paths]},
        "looks": looks
    }
    
    out_path = pathlib.Path(f"capsules/{capsule}/manifests/look_relations.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=2)
    print(f"✅ look_relations.json built with {len(looks)} looks → {out_path}")

if __name__ == "__main__":
    main()