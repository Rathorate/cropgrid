# Password controls and email recovery

Prepared against GitHub main `4679955c46be05ea51c154602a6ea34fe29a2661`.
This update changes code; it does not configure email credentials or deploy itself.

## Features

- Accessible Show/Hide controls on login, registration, confirmation, current
  password and new password inputs; passwords start hidden and can be pasted.
- Registration confirmation and rejection of whitespace-only passwords.
- Signed-in password change at `/account?mode=change-password`, also linked from
  the signed-in marketplace header. Requires the current password.
- Forgot password via the registered email, with random, hashed, single-use
  recovery tokens expiring after 20 minutes. Never returns an existing password.
- Reset token travels in the email link fragment, then in the API POST body;
  it is removed from browser history when the reset screen loads. Refreshing the
  reset screen requires reopening the email link.
- New-password confirmation; existing sessions and other reset links revoked
  after a successful change. Notification email attempted after a change.
- Generic recovery responses for existing/unknown accounts. Background delivery
  avoids revealing account existence through email-provider response timing.
- Database-backed request limits, origin checking and API `Cache-Control: no-store`.
- Marketplace navigation badge now follows the loaded listing count.

## Apply and test in WSL

From the repository root, inspect your current changes first. Do not reapply the
earlier readiness patch. Back up the staging database before upgrading.

```bash
cd ~/projects/cropgrid
git status --short --branch
git pull --ff-only origin main
PATCH=/mnt/c/Users/l2e/Documents/Codex/2026-10-08/ac/cropgrid-password-recovery-2026-10-20.patch
git apply --check "$PATCH" && git apply "$PATCH"
```

If checking fails, stop and share the error; do not force the patch or discard changes.

```bash
cd ~/projects/cropgrid/apps/backend
source .venv/bin/activate
python scripts/run_tests.py
```

```bash
cd ~/projects/cropgrid/apps/web
pnpm run build && pnpm run lint
```

New tables `password_resets` and `auth_throttles` are created by the existing
startup schema initialization. Existing account passwords are not changed.
Formal, versioned migrations remain required for a production release.

After passing checks, inspect and commit only the update's files:

```bash
cd ~/projects/cropgrid
git add -- PASSWORD_RECOVERY.md apps/backend/.env.example \
  apps/backend/app/models.py apps/backend/app/schemas.py \
  apps/backend/app/main.py apps/backend/app/password_recovery.py \
  apps/backend/tests/test_password_recovery.py \
  apps/web/app/account/account-client.tsx apps/web/app/account/password-field.tsx \
  apps/web/app/account/account.css apps/web/app/account/page.tsx \
  apps/web/app/home-client.tsx
git diff --cached --stat
git commit -m "Add password visibility and email-verified password recovery"
git push origin main
```

Watch both deployments and verify the Render backend is Live on the new commit.
If automatic deploys are disabled, deploy the latest commit in each dashboard.

## Configure Resend with no domain (owner-only acceptance)

1. Create an account at https://resend.com using an email inbox you control.
2. Create a sending API key. Keep it private; do not paste it into chat or Git.
3. Add the following in the Render BACKEND environment dashboard:

   | Variable | Value |
   |---|---|
   | `APP_PUBLIC_URL` | `https://cropgrid-hazel.vercel.app` |
   | `RESEND_API_KEY` | Your private sending API key |
   | `PASSWORD_RESET_FROM_EMAIL` | `CropGrid <onboarding@resend.dev>` for owner-only testing |

4. Keep `AUTH_COOKIE_SECURE=true` and the frontend origin in `CORS_ORIGINS`.
5. Save and deploy the backend. Never put the Resend key in Vercel or `.env.example`.
6. In CropGrid, use an account whose registered email EXACTLY matches the inbox
   associated with your Resend account. Request a reset and check inbox/spam and
   Resend delivery logs. Only use an account and inbox you own.

**Without a verified domain, Resend's test sender can deliver only to the email
associated with your Resend account. This is not recovery for every user.**
The generic API acknowledgment does not prove delivery; provider rejections are
logged without revealing recipients/tokens in application logs. Failed messages
invalidate their token. Monitor the sender provider's delivery status.

Reference: https://resend.com/docs/knowledge-base/403-error-resend-dev-domain

## Enable recovery for all users later

Add a domain you own to Resend, preferably a dedicated sending subdomain. Add only
the DNS records supplied by its dashboard; do not replace unrelated mail records.
Wait for verification, then change `PASSWORD_RESET_FROM_EMAIL` to an address on
that verified domain and redeploy. Disable click/open tracking on reset emails.
Your frontend may remain on Vercel; the email sending domain is a separate setting.

Domain verification: https://resend.com/docs/dashboard/domains/introduction

## Verification and limits

- Local backend: 58 tests pass on disposable SQLite, including 11 recovery/cache
  tests. Email provider calls are mocked. No real recovery email was sent by Codex.
- Production frontend build and TypeScript check pass.
- Browser checks verified login Show/Hide, recovery navigation and registration
  confirmation controls locally. Real-user password changes were not performed.
- Live homepage was observed loading listings with API connected before this
  update. This does not verify payment, email, AI, or every authenticated flow.
- Reset requests: 3/hour per email, 30/hour per connection IP, 100/hour globally.
  Reset attempts: 20/10 minutes per connection IP. Password changes: 10/10 minutes
  per user. Counters use atomic upserts and persist in the database across restarts.
  Proxy connection IPs can be shared; configure trusted edge rate limits for a
  public release. Do not trust arbitrary forwarded headers supplied by clients.
- Email delivery is best effort in-process background work. A durable delivery
  queue/retries, PostgreSQL concurrency acceptance, login/registration abuse
  controls, and email ownership verification during signup remain production work.
- Existing financial restrictions remain: sandbox payments only; no escrow,
  seller fund release, automated refunds or verified produce grading.

## Hosted acceptance after deployment

1. Login and register screens: Show/Hide preserves the typed value and does not
   submit the form. Confirmation mismatch is shown clearly.
2. Sign in; open Change password, reject an incorrect current password, then
   change it. Old sessions must be signed out; only the new password signs in.
3. Request a reset for your own registered email. Follow its email link, confirm
   the new password, then sign in. Reuse of that link must fail.
4. Requesting an unknown email must not reveal whether an account exists.
5. Never share a reset link/token or a password in screenshots/chat.
