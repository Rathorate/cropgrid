# CropGrid deployment guide

This repository is a monorepo with two separately deployable services:

- Frontend: Next.js in `apps/web` (deploy to Vercel).
- Backend: FastAPI in `apps/backend` (deploy as a Docker web service to Render).
- Database: managed PostgreSQL (Render Postgres or another hosted PostgreSQL provider).

The frontend and backend communicate over HTTPS. The browser must be able to reach the public API URL, and the API must allow the exact frontend origin through CORS.

## 1. Deploy the backend and database

1. In Render, create a managed PostgreSQL database. Choose a paid persistent plan for any pilot that stores real supplier or buyer data; free resources are for evaluation and can have availability or persistence limits. Keep the database internal to Render where possible.
2. In Render, create a **Web Service** from `Rathorate/cropgrid` and choose Docker as the runtime.
3. Set the service root directory to `apps/backend`. The Dockerfile is in that directory. Set the health check path to `/api/v1/health`.
4. Add these environment variables in the Render dashboard:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | The database's internal connection URL |
   | `CORS_ORIGINS` | Your exact production frontend origin, e.g. `https://cropgrid.vercel.app` |
   | `CROPGRID_SEED_DEMO` | `false` for a clean production database; use `true` only for a demo |
   | `AUTH_COOKIE_SECURE` | `true` for HTTPS deployments |
   | `ADMIN_EMAIL` | Private administrator email; do not use a public signup for admins |
   | `ADMIN_PASSWORD` | Strong private password (at least 16 characters); stored only in the hosting secret settings |
   | `OPENAI_API_KEY` | Your OpenAI key, if enabling the voice listing feature |
   | `OPENAI_LISTING_MODEL` | `gpt-4o-mini` (optional; this is the default) |
   | `MONNIFY_ENV` | `sandbox` while testing; `production` only after approval and a reviewed launch |
   | `MONNIFY_API_KEY` | Monnify sandbox API key |
   | `MONNIFY_SECRET_KEY` | Monnify sandbox secret key |
   | `MONNIFY_CONTRACT_CODE` | Monnify contract code |
   | `MONNIFY_CALLBACK_URL` | The frontend payment return URL, e.g. `https://<your-site>/payment/return` |

   Keep secret values in the provider dashboard. Do not commit them to GitHub. The API Dockerfile uses the platform-provided `PORT`, and the backend normalizes standard PostgreSQL URL schemes to the installed Psycopg 3 driver.
5. Deploy and open `https://<your-api-service>.onrender.com/api/v1/health`. It should return JSON with `"status":"ok"`. Also open `/docs` to check that the API documentation loads. The API supports buyer/seller registration and login using an HttpOnly session cookie; CORS must list the exact frontend origin and credentials are enabled for that origin.
6. In the Monnify dashboard, configure the transaction completion webhook URL `https://<your-api-service>.onrender.com/api/v1/payments/webhook`. Configure the matching secret in the backend environment. Production signatures are validated and each successful notification is verified with Monnify before updating inventory.

## 2. Deploy the frontend

1. In Vercel, import the same GitHub repository as a new project.
2. Set the **Root Directory** to `apps/web`. Use the detected Next.js framework, `pnpm install --frozen-lockfile` as the install command, and `pnpm run build` as the build command.
3. Add this environment variable for the Production environment (and Preview if you want preview deployments to call the API):

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | The backend base URL, e.g. `https://<your-api-service>.onrender.com` |

   This value is included in the browser bundle at build time, so redeploy after changing it. It is a public URL, not a secret.
4. Deploy. Copy the final Vercel origin (scheme and hostname only, no path) into Render's `CORS_ORIGINS`, then redeploy the backend if needed.
5. Open the Vercel site. Confirm the header says **API connected**, listings load from the API, buyer and seller registration/login work, only a seller can publish a listing, buyer checkout opens Monnify, listing reports can be submitted, and the FAQ is visible. Confirm a new listing remains after a page reload.

## Payment currency and account requirements

The initial checkout prices and charges orders in NGN through Monnify. Payment methods, international card support, settlement details, and fees depend on your merchant contract. This app does not invent an exchange rate or enable USD-priced checkout. Confirm eligibility and settlement with Monnify before live transactions.

After deploying, test using Monnify sandbox credentials, then verify success, cancellation/decline, repeated callback/webhook behavior, amount/currency mismatch, and unavailable inventory. No live money should be processed until authentication, seller payout/split, refunds, disputes, inventory reservation, audit logs, and reconciliation have been designed and tested. Current payment success goes to the CropGrid merchant account; it does not automatically pay suppliers.

## 3. Test voice listing with AI

1. Add `OPENAI_API_KEY` only to the backend environment in Render. Never add it to Vercel or a `NEXT_PUBLIC_` variable.
2. Redeploy the backend after saving the key.
3. In the frontend, choose **Add a listing → Voice draft**, upload a short supported audio file, and review the transcript-derived fields before publishing.
4. Test unclear speech and missing price/location. Confirm uncertain fields stay empty and the interface does not publish until required fields are supplied. Keep a human review step; AI extraction can be wrong.

## 4. Update from WSL after changes

In Ubuntu WSL:

```bash
cd ~/projects/cropgrid
git pull --ff-only origin main
```

For production, push tested commits to `main`; Vercel and Render can deploy from that branch. Do not store production database files in the app container's local filesystem.

## Before accepting real orders or money

This MVP now has buyer/seller accounts, server-side role checks, administrator provisioning, seller ownership for new listings, and a report review queue. It still lacks login rate limits, email verification and recovery, seller payout/splits, automated refunds/disputes, identity checks, verified grading, robust high-concurrency inventory reservations, and compliance integrations. Its sample order rows and market chart remain illustrative. Test payments with Monnify test credentials only. Add abuse protection, account recovery, audit trails, payout controls, reconciliation, and a security review before public launch. Do not advertise escrow or guaranteed quality until those systems exist and have been verified.
