# Runbook — Post-Upload Reconciliation

This runbook begins **after the client uploads the CSV to Shopify**.

---

## 1. Inspect Shopify Reality

python -m api.inspect_product_images 
–capsule S226 
–cpis 3004-416689 
–pretty \

capsules/S226/outputs/inspect_images_S226.json

Evidence only. No state mutation.

---

## 2. Derive Look Images

python -m api.derive_look_images_from_shopify 
–capsule S226 
–inspect-json capsules/S226/outputs/inspect_images_S226.json

Writes adopted look_images into product_state with provenance.

---

## 3. Reconcile Capsule Assets

python -m api.reconcile_capsule_assets 
–capsule S226 
–cpis 3004-416689 
–inspect-json capsules/S226/outputs/inspect_images_S226.json

Outputs:
- Drift logs (append-only)
- Swatch action queue
- Manual review queue

Updates product_state authorization.

---

## 4. Register Created Swatches

python -m api.register_created_swatches 
–capsule S226 
–cpis 3004-416689

Detects local swatch files and records them in state.

---

## 5. Promote Swatches to Manifest

python -m api.promote_state_swatches_to_manifest 
–capsule S226 
–cpis 3004-416689

Normalizes and appends to `images_manifest.jsonl`.

---

## 6. Enrich Product State with Shopify Tags

At this stage, Shopify may contain authoritative tags (including `style_…`) that were not present in the original local manifests.

This step adopts those tags into `product_state` so downstream writers (collections, size guides) can authorize correctly.

```
python -m utils.enrich_product_state_with_tags \
  S226 \
  --source-csv capsules/S226/exports/shopify_export_post_upload.csv
```

Behavior:
- Reads Shopify-exported CSV as source of truth
- Matches rows by handle
- Adopts missing tags into product_state
- Logs ADOPT / SKIP per product
- Writes updated product_state_{capsule}.json

---

## 7. Promote Static Allowed Actions

Certain actions are always safe once a product exists on Shopify:
- `collection_write`
- `size_guide_write`

This step retroactively promotes those permissions in state.

```
python -m utils.promote_static_allowed_actions S226
```

Behavior:
- Sets `allowed_actions.collection_write = true`
- Sets `allowed_actions.size_guide_write = true`
- Append-only, idempotent
- No Shopify calls

---

## 8. Write Product Metafields (Look Image & Swatch)

With state authorization satisfied, perform the actual metafield writes.

```
python -m api.metafields_writer \
  --capsule S226 \
  [--cpis 3004-416689]
```

Writes:
- `altuzarra.look_image`
- `altuzarra.swatch_image`

Safety guarantees:
- State-gated (`allowed_actions.metafield_write`)
- Idempotent (NOOP if already correct)
- One CPI failure does not stop the run
- Append-only result logs

---

## 9. Create Smart Collections (Per Style)

Smart collections are created **per style**, but only if at least one product in state authorizes `collection_write`.

Source of truth for styles:
- Shopify-exported CSV (post-upload)

Authorization source:
- `product_state.allowed_actions.collection_write`

```
python -m api.smart_collections \
  --capsule S226 \
  --source-csv capsules/S226/exports/shopify_export_post_upload.csv \
  [--dry-run]
```

Behavior:
- Discovers style tags from CSV
- Filters styles via product_state authorization
- NOOPs if collection already exists
- Logs ALLOW / SKIP / CREATE / NOOP per style

---

## 10. Attach Size Guide Pages

Size guide attachment is performed per product and is always allowed once products exist.

```
python size_guide_writer.py \
  --capsule S226 \
  --from-csv capsules/S226/outputs/poc_shopify_import_enriched.csv \
  [--dry-run]
```

Behavior:
- Matches productType → size guide page
- Writes `altuzarra.size_guide_page` metafield
- Logs per-product success / skip / failure

---

## End State

After completing all steps:

- Shopify reflects correct:
  - Images
  - Metafields
  - Smart collections
  - Size guides
- Local state matches Shopify reality
- All actions are logged, append-only, and reproducible

This concludes the post-upload reconciliation workflow.