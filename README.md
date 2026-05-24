# AI-Inventory-Management

## Migration Pack (GitHub Pages + Cloudflare + Supabase)

This repository now includes a step-by-step migration kit to improve user-facing latency for India users while keeping your existing Oracle deployment untouched until final cutover.

Start here:
- `MIGRATION_STEP_1_TO_8.md`
- `migration/CUTOVER_CHECKLIST.md`

Key artifacts:
- Baseline script: `migration/scripts/latency-baseline.ps1`
- GitHub Pages workflow: `.github/workflows/pages-migration.yml`
- Static frontend starter: `migration/frontend-static/`
- Cloudflare webhook starter: `migration/cloudflare/webhook/`
- Supabase SQL starter: `migration/supabase/001_inventory_views.sql`

Backend update included:
- `app/main.py` now supports configurable CORS (`ALLOWED_ORIGINS`) for cross-domain frontend migration.
- `app/main.py` includes `/health` endpoint for baseline and uptime checks.