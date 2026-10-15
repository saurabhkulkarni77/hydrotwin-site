# HydroTwin — Dev & Production Environments

_Draft prepared 2026-10-13; lands in the hydrotwin-site repo once GitHub write access is restored._

## Production (live, do not experiment here)

- **Branch:** `main` in `saurabhkulkarni77/hydrotwin-site`
- **GitHub Pages:** https://saurabhkulkarni77.github.io/hydrotwin-site/
- **AWS:** S3 bucket `hydrotwin-site-2026` + CloudFront `E29IVO4IMQNKO6` → https://d25g22pcmsbath.cloudfront.net
- **Deploy:** push to `main` triggers `.github/workflows/deploy-aws.yml` (S3 sync + CloudFront invalidation). GitHub Pages serves from `main`.

## Development (safe place to break things)

- **Branch:** `dev` in the same repo
- **URL:** http://hydrotwin-site-dev-2026.s3-website-us-east-1.amazonaws.com
- **AWS:** separate S3 bucket `hydrotwin-site-dev-2026` (static website hosting). No CloudFront, nothing shared with production.
- **Deploy:** push to `dev` triggers `.github/workflows/deploy-dev.yml` (syncs to the dev bucket only).

## Workflow

1. Make changes on `dev` (never directly on `main`).
2. Push — dev deploys itself in ~1 minute.
3. Verify at the dev URL (hard-refresh once; S3 website endpoint has no CDN cache).
4. Promote: merge `dev` → `main`. That single merge deploys to production on both GitHub Pages and AWS.
5. If a change misbehaves in dev, production is untouched — fix or abandon the branch freely.

## Rules

- Production only ever receives merges from `dev`, never direct edits.
- The weekly model retrain (hydrotwin-models repo) is unaffected — it never deploys the site.
- The AWS billing alarm (`billing-exceeds-5-usd`) covers both buckets; dev adds pennies at most.
