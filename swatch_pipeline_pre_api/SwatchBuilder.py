import os
import re
import json
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(SCRIPT_DIR, 'inputs', 'ghosts')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'outputs', 'swatches')
CROP_SIZE = 300
HINT_FILE = os.path.join(SCRIPT_DIR, 'swatch_hint.json')

def build_swatch(input_path):
    base_name, ext = os.path.splitext(os.path.basename(input_path))
    if ext.lower() not in ['.jpg', '.jpeg']:
        return None
    new_base_name = re.sub(r'(_ghost.*)$', '', base_name, flags=re.IGNORECASE)
    output_filename = new_base_name + '_swatch.jpg'
    output_path = os.path.join(os.path.dirname(input_path), output_filename)
    return output_path

def crop_center(img, crop_width, crop_height):
    img_width, img_height = img.size
    left = (img_width - crop_width) // 2
    top = (img_height - crop_height) // 2
    right = left + crop_width
    bottom = top + crop_height
    return img.crop((left, top, right, bottom))

def crop_hinted(img, garment_type, hint_data):
    if garment_type not in hint_data:
        garment_type = "default"
    crop = hint_data[garment_type]
    img_width, img_height = img.size
    left = int(crop["left_ratio"] * img_width)
    top = int(crop["top_ratio"] * img_height)
    right = left + CROP_SIZE
    bottom = top + CROP_SIZE
    return img.crop((left, top, right, bottom))

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(HINT_FILE, 'r') as f:
        hint_data = json.load(f)

    for root, dirs, files in os.walk(INPUT_DIR):
        for filename in files:
            if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                continue
            rel_path = os.path.relpath(root, INPUT_DIR)
            garment_type = rel_path.split(os.sep)[0] if rel_path and rel_path != '.' else 'default'

            style_tag = os.path.splitext(filename)[0]
            img_path = os.path.join(root, filename)
            with Image.open(img_path) as img:
                try:
                    cropped = crop_hinted(img, garment_type, hint_data)
                except Exception:
                    cropped = crop_center(img, CROP_SIZE, CROP_SIZE)

                output_filename = f"{style_tag}_swatch.jpg"
                output_path = os.path.join(OUTPUT_DIR, output_filename)
                cropped.convert('RGB').save(output_path, 'JPEG')

if __name__ == '__main__':
    main()
