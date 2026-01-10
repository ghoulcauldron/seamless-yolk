# Runbook — Shopify Mutation

This runbook covers **all Shopify writes**.

---

## 1. Metafields Writer

python -m api.metafields_writer 
–capsule S226 
–cpis 3004-416689

Writes:
- look_image
- swatch_image

Only if authorized by state.

---

## 2. Size Guide Writer

python -m api.size_guide_writer 
–capsule S226 
–from-csv enriched_import.csv

Notes:
- Never gated
- Always safe once product exists

---

## 3. Smart Collections

scripts/smart_collections.py

Creates one collection per `style_` tag.

---

## 4. QA Validation

qa_tracker.py

Confirms:
- Assets present
- Metafields set
- Collections exist

---