# Step 8 Cutover Checklist

## Pre-cutover
- [ ] Baseline report exists from Step 1
- [ ] GitHub Pages deployment green
- [ ] Cloudflare webhook verification green
- [ ] Supabase SQL migration applied in staging and prod
- [ ] Alerting dashboards configured (latency and error rate)

## Cutover window
- [ ] Freeze non-critical deployments for 30 minutes
- [ ] Update DNS / webhook callback endpoint
- [ ] Smoke test login, dashboard, inventory, webhook image flow

## Rollback triggers
- [ ] p95 latency is worse than baseline by >20% for 15 minutes
- [ ] 5xx error rate >2% sustained for 10 minutes
- [ ] Webhook failures from Meta exceed acceptable retries

## Rollback steps
- [ ] Point webhook callback back to previous endpoint
- [ ] Repoint frontend origin if needed
- [ ] Re-enable previous route in Cloudflare rules

## Post-cutover (48h)
- [ ] Compare p50/p95 against baseline every 6h
- [ ] Verify no data-loss gaps in receipts or ledger
- [ ] Record final migration report in `migration/reports/`
