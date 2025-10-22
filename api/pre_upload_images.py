#!/usr/bin/env python3
"""
pre_upload_images.py

Reads a Shopify import CSV (needed files) and a JSONL manifest (available files),
verifies them against each other, and uploads only the matched files from a
local server to Shopify.

It then creates a *new* CSV file with the correct, permanent
Shopify CDN URLs, ready for import.
"""

import argparse
import pandas as pd
import pathlib
import time
import socket
import http.server
import socketserver
import threading
import urllib.parse
import json  # <-- ADD THIS IMPORT
import csv   # <-- ADD THIS IMPORT
from shopify_client import ShopifyClient

# --- Local Web Server (Unchanged) ---
def start_server(path: str, port: int):
    """Starts a simple HTTP server in a thread to serve files from `path`."""
    
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(path), **kwargs)

    try:
        httpd = socketserver.TCPServer(("", port), Handler)
        print(f"--- 🚀 Starting local file server at http://127.0.0.1:{port} ---")
        print(f"--- Serving files from: {path} ---")
        httpd.serve_forever()
    except OSError as e:
        print(f"❌ CRITICAL ERROR: Could not start server. Port {port} may be in use.")
        print(f"  > {e}")
        global server_error
        server_error = True

def get_local_ip():
    """Gets the local IP address of the machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

# --- NEW: Manifest Loader ---
def load_manifest_map(manifest_path: str) -> dict:
    """
    Reads a .jsonl manifest and returns a map of
    {standardized_filename: relative_source_path}
    e.g., {'file_name.jpg': 'capsules/S126/assets/ghosts/file name.jpg'}
    """
    print(f"Loading and standardizing manifest from '{manifest_path}'...")
    file_map = {}
    
    try:
        with open(manifest_path, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                filename_with_spaces = data.get('filename')
                source_dir = data.get('source_dir') # e.g., "capsules/S126/assets/ghosts"
                
                if not filename_with_spaces or not source_dir:
                    print(f"  > Skipping manifest line (missing data): {line.strip()}")
                    continue
                
                # Standardize: "file name.jpg" -> "file_name.jpg"
                standardized_name = filename_with_spaces.replace(' ', '_')
                
                # Create the relative path: "capsules/S126/assets/ghosts/file name.jpg"
                # Use pathlib.Path to join paths correctly, then convert back to string
                relative_path = str(pathlib.Path(source_dir) / filename_with_spaces)
                
                file_map[standardized_name] = relative_path

    except FileNotFoundError:
        print(f"❌ Error: Manifest file not found at {manifest_path}")
        exit(1)
    except Exception as e:
        print(f"❌ Error reading manifest file: {e}")
        exit(1)
    
    print(f"Found {len(file_map)} files in manifest.")
    return file_map

# --- Main Script (Updated) ---
def main(csv_path: str, base_dir: str, manifest_path: str, output_csv: str, port: int, dry_run: bool = False):
    global server_error
    server_error = False

    # 1. Resolve paths
    base_dir_path = pathlib.Path(base_dir).resolve()
    if not base_dir_path.is_dir():
        print(f"❌ Error: Base directory not found at {base_dir_path}")
        return

    # 4. Load CSV to get NEEDED files
    client = ShopifyClient()
    # 4. Load existing Shopify files
    print("Fetching existing files from Shopify to prevent duplicates...")
    existing_files_with_urls = client.get_staged_uploads_map_with_urls()
    existing_shopify_files = set(existing_files_with_urls.keys())
    print(f"Found {len(existing_shopify_files)} files already on Shopify.")
    df = pd.read_csv(csv_path, low_memory=False)
    
    if 'Image Src' not in df.columns:
        print(f"❌ Error: CSV must contain an 'Image Src' column.")
        return
    
    # Get a list of all unique, non-empty filenames from 'Image Src'
    # We strip the placeholder URL to get just the filename
    needed_files = set(df['Image Src'].dropna().apply(lambda x: x.split('/')[-1]).unique())
    print(f"Found {len(needed_files)} unique images needed by the CSV.")

    # 5. Load Manifest to get AVAILABLE files
    manifest_map = load_manifest_map(manifest_path)
    available_files = set(manifest_map.keys())

    # 6. VERIFICATION STEP
    
    # Files in CSV and Manifest
    verified_local_files = needed_files.intersection(available_files)
    
    # Files that also need to be uploaded (i.e., not already on Shopify)
    files_to_upload = verified_local_files - existing_shopify_files
    
    # Files that are already on Shopify
    files_to_skip = verified_local_files.intersection(existing_shopify_files)
    
    # Files in CSV but not in Manifest
    files_missing_in_manifest = needed_files - available_files
    
    print("--- 📋 Verification Report ---")
    print(f"  > ✅ {len(files_to_upload)} files are matched and will be uploaded.")
    print(f"  > ℹ️  {len(files_to_skip)} files will be skipped (already exist on Shopify).")
    
    if files_missing_in_manifest:
        print(f"  > ⚠️  {len(files_missing_in_manifest)} files are in your CSV but NOT in the manifest:")
        for i, filename in enumerate(list(files_missing_in_manifest)[:5]):
            print(f"    - {filename}")
        if len(files_missing_in_manifest) > 5:
            print(f"    ... and {len(files_missing_in_manifest) - 5} more.")
            
    if not files_to_upload and not files_to_skip:
        print("  > ⚠️  No files in your CSV were found in the manifest or on Shopify. Nothing to do. Exiting.")
        return

    print("------------------------------")

    # --- DRY RUN CHECK ---
    if dry_run:
        print("\n--- 🔎 DRY RUN ---")
        
        # Report files to upload
        print(f"Would attempt to upload the following {len(files_to_upload)} files:")
        if files_to_upload:
            for i, filename in enumerate(sorted(list(files_to_upload))):
                print(f"  {i+1}. {filename}")
        else:
            print("  (None)")
        
        # Report files to skip
        print(f"\nWould SKIP the following {len(files_to_skip)} files (already on Shopify):")
        if files_to_skip:
            # Show first 10 for brevity
            for i, filename in enumerate(sorted(list(files_to_skip))[:10]):
                print(f"  {i+1}. {filename}")
            if len(files_to_skip) > 10:
                print(f"  ... and {len(files_to_skip) - 10} more.")
        else:
            print("  (None)")

        print("--- End of Dry Run ---")
        return # Exit before starting server or uploading
    # --- END OF DRY RUN ---

    time.sleep(2) # Pause for user to read

    # --- START SERVER (Moved from above) ---
    # 2. Start the local file server
    httpd = socketserver.TCPServer(("", port), http.server.SimpleHTTPRequestHandler)
    server_thread = threading.Thread(
        target=start_server, 
        args=(base_dir_path, port), 
        daemon=True
    )
    server_thread.start()
    time.sleep(1) 
    
    if server_error:
        print("Exiting due to server error.")
        return

    # 3. Get local IP for constructing public-facing URLs
    local_ip = get_local_ip()
    local_url_prefix = f"http://{local_ip}:{port}"
    print(f"--- 🌎 Files will be uploaded from: {local_url_prefix}/<filename> ---")

    # 7. Upload files and build a {filename: cdn_url} map
    # PRE-POPULATE the map with files we are skipping
    url_map = {filename: existing_files_with_urls[filename] for filename in files_to_skip}
    print(f"Pre-populated URL map with {len(url_map)} existing files.")
    # 'filename' here is the standardized name (e.g., file_name.jpg)
    for filename in files_to_upload:
        
        # Look up the real relative path (e.g., 'capsules/S126/assets/ghosts/file name.jpg')
        relative_path = manifest_map[filename]
        
        # Check if the file *actually* exists at that path
        local_file = base_dir_path / relative_path
        if not local_file.exists():
            print(f"  > ⚠️  SKIPPING: File '{filename}' was verified but not found at {local_file}")
            continue

        # URL-encode the *relative path* (which contains spaces)
        encoded_path = urllib.parse.quote(relative_path)
        resource_url = f"{local_url_prefix}/{encoded_path}"
        alt_text = filename.split('.')[0].replace('_', ' ').title()

        try:
            print(f"Uploading '{filename}'...")
            file_gid = client.upload_file(resource_url, alt_text)
            cdn_url = client.wait_for_file_ready(file_gid)
            
            print(f"  > ✅ Success: {cdn_url}")
            url_map[filename] = cdn_url
            
        except Exception as e:
            print(f"  > ❌ FAILED to upload '{filename}': {e}")
            url_map[filename] = "" # Mark as failed

    print("--- 🛑 Upload process complete. Shutting down local server. ---")

    # 8. Create the new CSV
    print(f"Mapping {len(url_map)} new URLs to CSV...")
    
    # Create a new 'Image Src' column based on the map
    # This rebuilds the column from scratch
    df['Image Src'] = df['Image Src'].apply(
        lambda x: url_map.get(x.split('/')[-1], "")
    )
    
    # Save the new CSV
    df.to_csv(output_csv, index=False, quoting=csv.QUOTE_ALL)
    
    print(f"--- ✨ Done! Your new file is ready: {output_csv} ---")
    print("You can now import this file into Shopify.")
    # Final validation
    missing_urls = df[df['Image Src'] == '']['Image Src'].count()
    if missing_urls > 0:
        print(f"  > ⚠️  WARNING: {missing_urls} rows in the new CSV have a blank 'Image Src'.")
        print("    This is likely because they were in the CSV but not in the manifest.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify, pre-upload local images, and create an import-ready CSV.")
    parser.add_argument('--csv', required=True, help='Path to your "poc_shopify_import_ready.csv" file.')
    parser.add_argument('--base-dir', default='.', help='Path to the project root (default: current directory).')
    # --- ADD THIS LINE ---
    parser.add_argument('--manifest', required=True, help='Path to the images_manifest.jsonl file for verification.')
    
    parser.add_argument('--output-csv', default='import_with_urls.csv', help='Name of the final, import-ready CSV file to create.')
    parser.add_argument('--port', type=int, default=8000, help='Port to run the local file server on.')
    
    # --- ADD THIS LINE ---
    parser.add_argument('--dry-run', action='store_true', help='Run verification and show what files would be uploaded.')

    args = parser.parse_args()
    
    # --- UPDATE THIS LINE ---
    main(args.csv, args.base_dir, args.manifest, args.output_csv, args.port, dry_run=args.dry_run)