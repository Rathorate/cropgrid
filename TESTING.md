# CropGrid acceptance and launch checklist

## Audit performed 19 October 2026

Baseline: GitHub main `01d07e2559233b5a4234098fcdb62ab1605b37b1`.
The audit used an isolated Windows copy of the pushed source, not your WSL database.

### Automated evidence

- 47 backend tests pass on SQLite. AI and Paystack responses are mocked.
- Added eight payment checks: signed success/duplicate webhook, currency mismatch,
  reference mismatch, late success, failed payment, reservation exclusion,
  expired reservation reuse, and untrusted checkout URL rejection.
- Fixed late successful payments: after the 20-minute reservation expires they
  require `PAID_REVIEW`, without deducting stock. A paid-review record is not a refund.
- Next.js 15.5.28 / React 19.3.1: TypeScript check and production build pass.
- Production `pnpm audit`: no known advisories on the checked lockfile/date.
  PostCSS is overridden to 8.5.23 in `apps/web/pnpm-workspace.yaml`.
  This is an advisory database check, not a guarantee against all vulnerabilities.
- Local Python runtime versions, including Pillow 12.3.0, were checked against
  OSV: no findings for application libraries. The local pip 25.0.1 installer had
  advisories; upgrade pip separately. Your WSL versions were not inspected.
- Headless Edge, production frontend connected to a real local API:
  seller and buyer registration/cookies; publishing with a PNG; persistence after
  reload; gallery image loading; checkout preview; buyer message received by
  seller; AI text/audio controls; help center; mobile width at 390px.
  No uncaught JavaScript errors or HTTP 5xx responses in those flows.
- Removed leftover Monnify wording from the payment return screen; kept Paystack
  host validation in the checkout redirect.

### Re-run in WSL

From the repository root:

```bash
cd ~/projects/cropgrid/apps/backend
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
python scripts/run_tests.py
```

The runner creates a temporary SQLite database and clears provider credentials
inside its process. It does not load `.env`, touch the app database, or charge providers.

In another terminal:

```bash
cd ~/projects/cropgrid/apps/web
pnpm install --frozen-lockfile
pnpm run build
pnpm run lint
pnpm audit --prod
```

`lint` currently runs TypeScript checking, not ESLint. The production build must
run first in a clean checkout to generate Next route types. Keep the workspace
override file together with package.json and the lockfile. Do not use a different
package manager without applying the same PostCSS override and regenerating its lock.

## Required real-provider acceptance (not completed by this audit)

1. Start API on port 8002 and frontend on 3000. Check `/api/v1/health`, then
   confirm the browser says API connected. Use separate seller and buyer accounts.
2. AI: run `python scripts/check_ai.py` from the backend. Text was previously
   confirmed by the owner; this audit did not use their key. Record an actual crop
   sentence and run `python scripts/check_ai.py --audio "/full/path/file.m4a"`.
   Confirm transcription AND extraction, blank unknown fields, and manual review
   before publishing. Then repeat using the browser upload.
3. Paystack: configure a TEST secret only on the backend; callback must point to
   the frontend `/payment/return`. Complete a provider test checkout and verify
   NGN total, successful return page, paid record, and stock reduced once.
4. On HTTPS staging, configure Paystack's signed webhook to the backend
   `/api/v1/payments/webhook`. Verify delivery, duplicates, declined/cancelled
   transactions, pending transactions and delayed success. Reconcile against the
   provider dashboard. Unit tests are not proof of provider connectivity.
5. Upload real JPEG/PNG/WebP images and MP4/WebM videos. Check playback, seeking,
   upload limits, reload persistence and failed-upload retry on desktop and mobile.
   Video container checks are not malware scanning or transcoding.
6. Browser-test login/logout, role restrictions, chat from both accounts,
   listing report/admin review, support ticket/admin reply, seller dispatch,
   buyer receipt and dispute. Delivery records do not move money.

## Remaining launch gates

This release is a local/sandbox MVP, not a completed live-money marketplace.

- Implement an approved payment custody/payout/refund/dispute flow. Escrow,
  protected deposits and delivery-based fund release are NOT implemented.
  Live Paystack keys intentionally remain blocked.
- Test inventory/payment concurrency on PostgreSQL, including simultaneous
  checkouts and webhook/callback races. SQLite sequential tests cannot establish this.
- Add reviewed database migrations, backups/restore rehearsal, dependency locks
  for Python, and persistent production media storage with scanning/transcoding.
- Add login/registration abuse limits, email verification/password recovery,
  seller verification, moderation and operational audit/reconciliation tools.
- Deploy frontend and backend separately to HTTPS staging. Current cookies use
  SameSite=Lax: use app/API subdomains of the same site, or a reviewed same-origin
  proxy. Unrelated default Vercel/Render hostnames are not a verified login setup.
- Run the acceptance list again on staging, including accessibility/mobile
  interactions and real provider events. Configure monitoring and error alerts.

Only count a gate complete when its evidence is recorded. A passing build or a
successful Git push does not establish production readiness.
