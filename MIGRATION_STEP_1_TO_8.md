# Migration Deliverables (Step 1 to Step 8)

This file is the execution plan to migrate safely from Oracle-hosted monolith to:
- Frontend on GitHub Pages
- Webhook ingress on Cloudflare
- Data on Supabase
- Optional Python retained for complex processing

Main branch safety:
- Keep current Oracle deployment on `main`
- Execute all migration work on `pages-migration` and `webhook-edge`

## Branch setup (do this first)

```powershell
git checkout -b pages-migration
git push -u origin pages-migration
git checkout -b webhook-edge
git push -u origin webhook-edge
git checkout pages-migration
```

## Step 1: Baseline latency measurement

Deliverables:
- [x] Script: `migration/scripts/latency-baseline.ps1`
- [ ] Capture baseline metrics and commit report to `migration/reports/baseline-YYYYMMDD.md`

Expected impact:
- No user-facing speed change
- Establishes a measurable benchmark for every next step

Acceptance criteria:
- You have p50 and p95 for page load, API load, webhook ack, and end-to-end processing

## Step 2: CDN acceleration for current site

Deliverables:
- [ ] Enable Cloudflare proxy for current domain
- [ ] Add cache rules for static assets
- [ ] Verify no dynamic API routes are cached incorrectly

Expected impact:
- FCP: 10% to 25% faster
- Static asset fetch: 150ms to 600ms faster for India users

Acceptance criteria:
- Static assets served with `cf-cache-status: HIT`

## Step 3: GitHub Pages frontend

Deliverables:
- [x] Starter static frontend: `migration/frontend-static/`
- [x] Pages workflow: `.github/workflows/pages-migration.yml`
- [ ] Configure repo Pages source to GitHub Actions

Expected impact:
- Initial page TTFB often below 100ms from edge
- Perceived first load 20% to 45% faster

Acceptance criteria:
- Frontend loads from Pages URL
- Frontend reads live data from backend/Supabase

## Step 4: Auth migration (cross-domain safe)

Deliverables:
- [ ] Move from server cookie session to token/JWT auth
- [ ] Add auth refresh flow in frontend
- [ ] Add RLS policy tests in Supabase

Expected impact:
- 5% to 15% smoother navigation and fewer auth failures

Acceptance criteria:
- Login works across separate frontend/backend domains
- No session loss during normal use

## Step 5: Webhook ingress on Cloudflare Worker

Deliverables:
- [x] Worker starter: `migration/cloudflare/webhook/worker.js`
- [x] Worker config: `migration/cloudflare/webhook/wrangler.toml`
- [ ] Deploy worker endpoint and update Meta webhook callback URL

Expected impact:
- Webhook acknowledgement 70% to 95% faster
- Typical ack path can drop to 50ms to 250ms from India

Acceptance criteria:
- Meta verification succeeds
- Incoming events are acknowledged immediately

## Step 6: Async AI/document processing

Deliverables:
- [ ] Queue binding enabled on Worker
- [ ] Worker consumer or backend consumer processes queued jobs
- [ ] Retry + dead-letter strategy documented

Expected impact:
- Major perceived UX improvement (instant ack)
- End-to-end processing may be unchanged if AI provider is bottleneck

Acceptance criteria:
- Ack happens immediately; processing continues asynchronously

## Step 7: Supabase analytics migration

Deliverables:
- [x] SQL migration starter: `migration/supabase/001_inventory_views.sql`
- [ ] Create indexes and run EXPLAIN ANALYZE
- [ ] Replace backend analytics calls with Supabase RPC/views

Expected impact:
- Dashboard API queries improve by 120ms to 700ms typically
- Larger datasets may improve 2x to 10x with proper indexes

Acceptance criteria:
- Dashboard uses Supabase query layer and matches old values

## Step 8: Cutover and rollback-safe go-live

Deliverables:
- [ ] Production checklist completed
- [ ] DNS switch plan with rollback window
- [ ] Post-cutover monitoring (48h)

Expected impact:
- Combined frontend + webhook improvements are visible to users

Acceptance criteria:
- p95 metrics improved vs baseline
- Error rate remains stable or better

---

## Suggested execution order by week

- Week 1: Step 1, Step 2, Step 3
- Week 2: Step 4, Step 5, Step 6
- Week 3: Step 7, Step 8

## Rollback rules

- If any step causes >2% error increase, revert only that step.
- Keep Oracle `main` untouched until Step 8 acceptance criteria are met.
