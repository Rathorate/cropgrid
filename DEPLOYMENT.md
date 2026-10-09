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
   | `OPENAI_API_KEY` | Your OpenAI key, if enabling the voice listing feature |
   | `OPENAI_LISTING_MODEL` | `gpt-4o-mini` (optional; this is the default) |
   | `PAYSTACK_SECRET_KEY` | Paystack **test** secret key for sandbox testing; switch to a live key only after merchant approval and a reviewed launch |
   | `PAYSTACK_CALLBACK_URL` | The frontend payment return URL, e.g. `https://<your-site>/payment/return` |

   Keep secret values in the provider dashboard. Do not commit them to GitHub. The API Dockerfile uses the platform-provided `PORT`, and the backend normalizes standard PostgreSQL URL schemes to the installed Psycopg 3 driver.
5. Deploy and open `https://<your-api-service>.onrender.com/api/v1/health`. It should return JSON with `"status":"ok"`. Also open `/docs` to check that the API documentation loads.
6. In the Paystack dashboard, register the webhook URL `https://<your-api-service>.onrender.com/api/v1/payments/webhook`. Configure the same Paystack secret key in the backend environment. The endpoint validates Paystack's HMAC-SHA512 signature and verifies the transaction with Paystack before updating inventory.

## 2. Deploy the frontend

1. In Vercel, import the same GitHub repository as a new project.
2. Set the **Root Directory** to `apps/web`. Use the detected Next.js framework, `pnpm install --frozen-lockfile` as the install command, and `pnpm run build` as the build command.
3. Add this environment variable for the Production environment (and Preview if you want preview deployments to call the API):

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | The backend base URL, e.g. `https://<your-api-service>.onrender.com` |

   This value is included in the browser bundle at build time, so redeploy after changing it. It is a public URL, not a secret.
4. Deploy. Copy the final Vercel origin (scheme and hostname only, no path) into Render's `CORS_ORIGINS`, then redeploy the backend if needed.
5. Open the Vercel site. Confirm the header says **API connected**, listings load from the API, and a valid new listing appears after submitting the form. Confirm it remains after a page reload.

## Payment currency and account requirements

The initial checkout prices and charges orders in NGN. Nigerian Paystack merchants that have international payments enabled can accept eligible international cards; the cardholder's bank may convert the NGN charge to the card's currency while the merchant receives local-currency settlement. Direct USD-denominated settlement is a separate account capability and may require a USD domiciliary account. This app does not present an invented USD conversion rate or enable USD-priced checkout by default. Confirm account eligibility and settlement details with Paystack before enabling live transactions. Fees are not added to the buyer total by CropGrid; configure merchant pricing and fees with the provider.

After deploying, test using Paystack test credentials and test payment methods, then verify a success, a declined/cancelled payment, repeat callback/webhook behavior, amount/currency mismatches, and unavailable inventory. No live money should be processed until authentication, seller payout/split, refunds, disputes, inventory reservation, audit logs, and reconciliation have been designed and tested. Current payment success goes to the CropGrid merchant account; it does not automatically pay suppliers.

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

This MVP does not yet have user accounts, roles, listing ownership, seller payout/splits, automated refunds/disputes, identity checks, verified grading, inventory reservation across concurrent checkouts, or compliance integrations. Its sample order rows and market chart are illustrative. Test payments with Paystack test credentials only. Add authentication/authorization, payout controls, reconciliation, and abuse protection before opening listing creation to the public. Do not advertise escrow or guaranteed quality until those systems exist and have been verified.
