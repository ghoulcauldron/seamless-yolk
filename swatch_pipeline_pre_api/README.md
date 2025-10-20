# swatch_pipeline_pre_api/README.md

# Swatch Pipeline Pre-API

This directory contains scripts and folder structures to prepare swatch images and metadata before uploading to Shopify.

## Folder Structure

- `inputs/ghosts/` — Store ghost images here (input images).
- `inputs/exports/` — Place raw Shopify product CSV exports here.
- `outputs/swatches/` — Cropped swatch images are saved here.
- `outputs/csvs/` — Metafield upload CSV files are saved here.
- `intermediates/` — Lookup dictionaries and intermediate files.

## Scripts

1. **SwatchBuilder.py**
   - Loads ghost images from `inputs/ghosts/`.
   - Auto-crops a centered 300x300 pixel region.
   - Saves cropped JPEG swatches to `outputs/swatches/` with filenames `[STYLE_TAG]_swatch.jpg`.
   - Future enhancement (in planning): Introduce a garment-aware cropping layer using a `swatch_hint.json` configuration file.
     This system allows per-garment cropping logic (e.g., sweaters, pants, coats) based on predefined regions.
     Images can be grouped into folders by garment type. The script will read `swatch_hint.json` and apply a corresponding
     crop box or ruleset, instead of defaulting to the center crop.
     This prepares the ground for eventual ML-based zone detection.

2. **HandleResolver.py**
   - Loads a Shopify product export CSV from `inputs/exports/products.csv`.
   - Builds a dictionary mapping `{style_tag: handle}` by exact matching the full style tag in the Tags column.
   - Saves this mapping as `intermediates/handle_lookup.json`.

3. **SwatchUploadTracker.py**
   - Reads swatch files from `outputs/swatches/`.
   - Reads `intermediates/handle_lookup.json`.
   - Outputs `outputs/csvs/metafield_upload.csv` with columns: Handle, Namespace, Key, Type, Value.
   - Uses fixed values:
     - Namespace = `altuzarra`
     - Key = `swatch_image`
     - Type = `file`
     - Value = `files/[SWATCH_FILENAME]`

## Workflow Order

1. Run `SwatchBuilder.py` to generate cropped swatch images.
• Optionally define garment-specific cropping hints in `swatch_hint.json` for better accuracy before running `SwatchBuilder.py`
2. Run `HandleResolver.py` to create the handle lookup JSON.
3. Run `SwatchUploadTracker.py` to produce the metafield upload CSV ready for Shopify import.
