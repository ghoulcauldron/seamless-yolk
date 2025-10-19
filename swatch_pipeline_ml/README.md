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

## Summary of Changes October 18, 2025
Here's a breakdown of the updates based on your requests:

✔️ Filename Fix (#1): The swatch filename now correctly removes _ghost and anything after it.

⌨️ "Return" to Save (#2): You can now press the Return or Enter key to save the current swatch and advance to the next image.

🔒 Stable Crop Box (#3): Changing the garment type in the dropdown will no longer reset the position of your crop box. The box will only reset to the garment's default position when a new image is loaded.

✨ Add Garment Types (#4): A new "Add Type" button allows you to add new garment categories on the fly.

🖼️ "Zoom to Fit" Preview (#5): You can now press and hold the Tab key to see a scaled-down "zoom to fit" preview of the entire garment. Releasing the key restores the full-resolution view.

📝 Filename in Title (#6): The current image's filename is now displayed in the window's title bar for easy reference.

🖱️ Click to Reposition (#7): You can now click anywhere on the image to instantly move the center of the crop box to that point.