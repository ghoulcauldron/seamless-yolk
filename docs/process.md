# Capsule Workflow: End-to-End Product Enrichment & Upsert

This document formalizes the standardized workflow for each seasonal capsule (e.g. S126, PF26).  
It replaces the manual file-list process and unifies data, assets, and enrichment logic.

---

## 1. Capsule Folder Layout

```

/capsules/S126/
inputs/
SS26 for Shopify check(By Style).csv
products_export_1.csv
assets/
ghosts/
editorials/
swatches/
manifests/
images_manifest.jsonl
capsule_status.json
outputs/
poc_shopify_import_enriched.csv
anomalies.csv
api_jobs/

````

Each capsule is self-contained: all scripts take `--capsule S126` and read/write within that directory.

---

## 2. Core Workflow

### Step 1 — Build Image Manifest
Auto-generates `images_manifest.jsonl` from the three asset folders.

```bash
python scripts/build_image_manifests.py --capsule S126 [--dry-run]
````

* Scans `/assets/ghosts`, `/assets/editorials`, `/assets/swatches`
* Parses CPI from filenames (`Style-ColorCode`)
* Validates hero/model/swatch coverage
* Writes `manifests/images_manifest.jsonl`
  and updates `capsule_status.json`

---

### Step 2 — Sync Swatch Hints → Garment Config

Learns new garment categories created in the GUI.

```bash
python scripts/sync_swatch_hints.py --capsule S126 [--dry-run]
```

* Reads `logs/swatch_hints.json`
* Merges unseen garment types into `config/garment_config.json`
* Version-bumps config
* Outputs a report of missing/duplicate swatches

---

### Step 3 — Enrich Shopify Import CSV

Merges client tracker + Shopify export + image manifest.

```bash
python scripts/enrich_shopify_import.py --capsule S126 [--only 8835-000067,3019-416102]
```

* Implements Section 2 logic from the Strategic Plan
  (row expansion, tag generation, metafields except file-refs)
* Writes:

  * `outputs/poc_shopify_import_enriched.csv`
  * `outputs/anomalies.csv`
  * updates `capsule_status.json` with a new job entry

---

### Step 4 — Validate Capsule Before Import

```bash
python scripts/validate_capsule.py --capsule S126
```

Checks:

* Handle blocks contiguous
* Unique SKUs & Barcodes
* Valid URLs / filenames
* HTML well-formed
* UTF-8 encoding
* Reports to `outputs/anomalies.csv`

---

### Step 5 — Upload via Shopify Admin Import

Run the enriched CSV import through Shopify’s UI or bulk API importer.
At this point all text metafields are populated; file-reference metafields follow via API.

---

### Step 6 — API Metafields Writer (Phase 2)

```bash
python api/metafields_writer.py --capsule S126 [--dry-run]
```

Uses Shopify Admin API to:

* Upload swatch + hero images to Files
* Update:

  * `product.metafields.altuzarra.swatch_image`
  * `product.metafields.altuzarra.look_image`

Each write is logged to `outputs/api_jobs/<timestamp>_metafields.json`.

---

### Step 7 — Smart Collection Creator (Phase 2)

```bash
python api/smart_collections.py --capsule S126 [--dry-run]
```

Creates or idempotently updates smart collections:

* Condition: `Tag is equal to style_<Style Name>`
* Logs Shopify collection IDs to `capsule_status.json`

---

## 3. Capsule Status Manifest Schema

`manifests/capsule_status.json`

```json
{
  "capsule": "S126",
  "products": {
    "8835-000067": {
      "handle": "askania-coat-storm",
      "stages": {
        "intake": {"tracker": true, "export": true},
        "assets": {"ghost": true, "hero": true, "swatch": true},
        "enrichment": {"csv_ready": true},
        "api": {"metafields": false, "collections": false}
      },
      "audit": {"last_update_job": "job_20251019_2100_enrich"}
    }
  },
  "jobs": [
    {
      "job_id": "job_20251019_2100_enrich",
      "kind": "enrich_csv",
      "inputs": ["inputs/..."],
      "outputs": ["outputs/poc_shopify_import_enriched.csv"],
      "diff_summary": {"rows_added": 42, "rows_changed": 17}
    }
  ]
}
```

---

## 4. CLI Conventions

| Flag               | Description                         |
| ------------------ | ----------------------------------- |
| `--capsule S126`   | Capsule code (required)             |
| `--dry-run`        | Simulate actions without writing    |
| `--only CPI1,CPI2` | Restrict operation to specific CPIs |
| `--verbose`        | Optional: print detailed logs       |

---

## 5. Next Development Priorities

1. **Persistent File Cache** for uploaded metafield images.
2. **Auto-Rollback** of enrichment job via saved diffs.
3. **Dashboard Summary** HTML report per capsule.
4. **Staging Store Tester** for pre-launch verification.

---

## 6. Reference

* `garment_config.json` — garment heuristics & default crop ratios
* `swatch_hints.json` — GUI-logged crops and OTF categories
* `Shopify Tags Guide.csv` — authoritative tag rules
* `Strategic Implementation Plan for Shopify SS26.md` — foundational logic reference