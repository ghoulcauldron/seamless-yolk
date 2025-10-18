# Swatch Pipeline (ML-Enabled)

This project offers an interactive GUI to manually crop swatches from flat/ghost garment photos, with logging for future ML automation.

## Features

- Load raw ghost/flat images in a gallery
- Click-and-drag to place a 300x300 crop box (swatch window)
- Save swatch as JPEG named from the product's style tag
- Assign garment type (e.g. pants, sweater) on save
- Log crop coordinates and metadata in JSON for ML training

## Folder Structure

- `inputs/ghosts/` — raw garment images
- `outputs/swatches/` — final swatch images
- `logs/swatch_hints.json` — user-drawn crop locations + metadata
- `config/garment_config.json` — presets or bounds per garment type

## Setup

```bash
python -m pip install --upgrade pip
pip install pillow
pip install pyqt5