# Pre–Client Upload Runbook

This runbook documents the end-to-end process from capsule initialization through CSV delivery to the client, ensuring a smooth and consistent workflow.

---

## 1. Purpose & Scope

- Define the steps and files involved in preparing product data and assets before client upload.
- Establish clear boundaries between local truth and Shopify truth.
- Provide guidance on file management and state freezing prior to client delivery.

---

## 2. Capsule Folder Setup

- Capsule directory structure includes:
  - `images/` — raw and processed image assets.
  - `csv/` — initial and generated CSV files.
  - `manifests/` — image manifests and swatch data.
  - `product_map/` — product mapping files.
  - `preflight/` — preflight check outputs and state seeds.

- Expected structure ensures consistency and traceability throughout the process.

---

## 3. Source Inputs

- Raw image assets organized by type and style.
- Style lists and accessory flags that characterize products.
- Initial CSVs containing base product and variant data.

---

## 4. Image Manifests & Swatch Creation

- Image manifests categorize images into:
  - **Ghosts** — placeholder or background images.
  - **Editorials** — styled images for marketing.
  - **Swatches** — color or texture samples.

- Scripts and tools:
  - `build_image_manifests.py` — generates manifests classifying image assets.
  - `swatch_creator` — tool to create swatch images from source assets.

---

## 5. Product Map Construction

- Product map links Capsule Product Identifiers (CPI) to Shopify Product Global IDs (GID).
- Script:
  - `build_product_map.py` — constructs and updates the mapping file.

---

## 6. Preflight & State Seeding

- Preflight checks validate data consistency and completeness before CSV generation.
- Scripts:
  - `seed_product_state_from_preflight.py` — seeds product state based on preflight results.
- Default allowed actions are set to guide permissible changes going forward.

---

## 7. Shopify Import CSV Generation

- Enrich and prepare data for Shopify import:
  - `enrich_shopify_import.py` — enhances CSVs with additional data.
- Generate:
  - Missing images CSV — identifies image assets that need attention.
  - Anomalies CSV — lists inconsistencies or errors detected.
- Combine multiple Shopify import CSVs using:
  - `combine_shopify_imports.py`

---

## 8. Review & Client Delivery

- Deliver files for client review:
  - `REVIEW_import_file_*.csv` — final import CSVs for client approval.
  - `REVIEW_anomalies_file_*.csv` — anomaly reports for transparency.
- Clearly communicate expectations and next steps to the client.

---

## 9. Transition to Post-Upload Phase

- After client uploads:
  - The local truth remains authoritative; Shopify truth may differ until reconciled.
  - Files sent to client are considered frozen and append-only; regenerated files occur only pre-delivery.
- Handoff to the post-upload reconciliation process documented in `post_upload_reconciliation.md`.

---

### Key Emphases

- **Local Truth vs Shopify Truth Boundary**: Local data is the source of truth until client upload and reconciliation.
- **File Management**:
  - Append-only files: anomaly and missing image reports.
  - Regenerated files: manifests, product maps, and import CSVs before delivery.
- **Frozen State**: Once CSVs and reports are sent to the client, these files are frozen to preserve consistency.

---

This runbook ensures clarity and consistency in preparing and delivering product data for client upload.
