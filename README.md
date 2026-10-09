# CropGrid

CropGrid is a runnable full-stack MVP for Nigerian agricultural commodity trade, based on the supplied CropGrid architecture specification. It includes a responsive marketplace, inventory APIs, local SQLite persistence, OpenAI voice listing extraction, and a Paystack hosted checkout integration in NGN. International cardholders can pay against NGN prices and their issuer may convert the charge; explicit USD-denominated pricing is not enabled by default.

## Run locally

Requirements: Python 3.11+ and Node.js 20+.

1. In a terminal, from this folder, create and activate a Python virtual environment, install `apps/backend/requirements.txt`, and copy `apps/backend/.env.example` to `apps/backend/.env`.
2. Start the API with `uvicorn app.main:app --reload --app-dir apps/backend --env-file apps/backend/.env`.
3. In a second terminal, run `pnpm install` and `pnpm dev` from `apps/web`.
4. Open `http://localhost:3000`. API docs are at `http://localhost:8000/docs`.

The default database is a local SQLite file for development. Set `DATABASE_URL` to a PostgreSQL URL for deployment. The backend `.env.example` includes `OPENAI_API_KEY=` and `PAYSTACK_SECRET_KEY=`; copy it to `.env` and paste provider keys after the equals signs. Set `OPENAI_API_KEY` to enable voice transcription and structured listing extraction. Set a Paystack **test** secret key (`sk_test_...`) in `PAYSTACK_SECRET_KEY` to test hosted checkout; use the Paystack dashboard's test cards and never use a live key during development. Without keys, the AI and payment endpoints return clear not-configured errors.

Public registration supports buyer and seller roles only. Provision the first administrator privately by setting `ADMIN_EMAIL` and a strong `ADMIN_PASSWORD` (at least 16 characters) in the backend environment before startup. Admin accounts cannot be self-registered. Set `AUTH_COOKIE_SECURE=true` for HTTPS deployments; keep it `false` for local HTTP development.

## Product boundaries

- Paystack checkout can collect test or live payment only when configured with the corresponding merchant credentials. It is not escrow: funds go to the CropGrid merchant account. Pending checkouts reserve the requested inventory for 20 minutes and verified successful payments reduce available stock. No seller split, marketplace payout, automated refund, dispute, or reconciliation workflow is implemented.
- Export document preview is a draft checklist, not an official NXP form or certificate.
- Quality grades are seller supplied and unverified in this MVP. The architecture's image grading is a future human-reviewed AI feature, not a verified result.
- Do not switch to live payment before merchant activation, end-to-end webhook testing, authentication, authorization, audit trails, seller payout design, refund/dispute handling, compliance review, and security controls.

## Architecture

- `apps/web`: Next.js App Router, TypeScript, responsive dashboard UI.
- `apps/backend`: FastAPI, Pydantic schemas, SQLAlchemy persistence, listing and order APIs, optional OpenAI audio parser.
- `docker-compose.yml`: local Postgres and API services.

## Deploy frontend and backend separately

See [DEPLOYMENT.md](DEPLOYMENT.md) for the Vercel frontend + Render FastAPI + managed PostgreSQL setup, required environment variables, CORS configuration, AI key handling, and production boundaries. The API service and database must be reachable before the deployed frontend can load live listings.

## API

- `GET /api/v1/health`
- `POST /api/v1/auth/register` (buyer or seller registration; admin is never public)
- `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `POST /api/v1/auth/logout` (HttpOnly session cookie)
- `GET /api/v1/inventories`
- `POST /api/v1/inventories` (seller or admin session required)
- `POST /api/v1/inventories/{id}/reports` (signed-in users; admin review at `/api/v1/admin/reports`)
- `POST /api/v1/ai/parse-audio` (seller/admin session and `OPENAI_API_KEY` required)
- `POST /api/v1/orders/escrow-initiate` (simulated demo state)
- `GET /api/v1/orders/me` (signed-in buyer purchases, seller listing orders, or admin order records)
- `POST /api/v1/payments/initialize` (buyer/admin session; server-side Paystack checkout initialization; NGN)
- `GET /api/v1/payments/verify/{reference}` (server-side verification before marking paid)
- `POST /api/v1/payments/webhook` (Paystack HMAC-SHA512 signature validation plus provider verification)
- `GET /api/v1/export/form-nxp/{order_id}` (draft checklist only)

Paystack secrets remain on the backend. Payment is recorded as successful only after checking the provider's reference, success status, currency, and exact amount. Prices are denominated in NGN; international card issuers may bill their cardholder in a local equivalent. Explicit USD-priced checkout requires merchant eligibility and USD settlement setup, so it is currently disabled.
## Checks

From `apps/backend`, run `python -m unittest discover -s tests -v` after installing `requirements.txt`. The API suite checks authentication and role rules, report review, health, inventory search, validation, draft-only export responses, mocked successful AI extraction, Paystack request construction, webhook signatures, amount mismatch handling, and idempotent stock reduction. Provider communication is mocked in automated tests; perform real provider sandbox calls with your own keys before deployment. From `apps/web`, run `pnpm run lint` and `pnpm run build` sequentially.

`CROPGRID_SEED_DEMO=false` disables the sample inventory seed for a deployment database.

## Run on Ubuntu in WSL

Keep the checkout in the Linux home directory (for example `~/projects/cropgrid`) for better file-watching performance. Install Git, Python 3.11+, Node.js 20+, and pnpm in Ubuntu first.

### First checkout

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/Rathorate/cropgrid.git cropgrid
cd cropgrid
```

### Start the API

```bash
cd ~/projects/cropgrid/apps/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
test -f .env || cp .env.example .env
nano .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env
```

In `nano`, set `OPENAI_API_KEY` and/or `PAYSTACK_SECRET_KEY` to your own keys. For local payments, use only the Paystack test key beginning `sk_test_`. Save with Ctrl+O, Enter, then exit with Ctrl+X. Keep `.env` private and restart Uvicorn after changing it.

### Start the web app

Open a second Ubuntu terminal:

```bash
cd ~/projects/cropgrid/apps/web
corepack enable
pnpm install --frozen-lockfile
cp .env.example .env.local
pnpm dev --hostname 0.0.0.0
```

Open `http://localhost:3000` in the Windows browser and `http://localhost:8000/docs` for the API documentation. Next.js reads `.env.local`, not `.env.example`; the copied file points the frontend at the API on port 8000. If you run the API on another port, update `NEXT_PUBLIC_API_URL` in `.env.local` and restart the web dev server. Keep OpenAI and Paystack keys only in `apps/backend/.env`; do not commit that file.

### Resolve `Address already in use` on port 8000

First check whether the backend is already running:

```bash
curl -i http://127.0.0.1:8000/api/v1/health
```

If it returns `200` and `{"status":"ok",...}`, leave that backend running and continue with the frontend. If the port belongs to another service, identify it before stopping anything:

```bash
sudo ss -ltnp 'sport = :8000'
docker ps --filter publish=8000 --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Ports}}'
```

If the listener is an old CropGrid Uvicorn process, stop it with Ctrl+C in its original terminal. If Docker shows another container publishing the port, stop only that named container if you are sure it is safe, for example `docker stop movie_chromadb`; this pauses that container without deleting it. Then confirm the port is free with `sudo ss -ltnp 'sport = :8000'`. If you need that other service to keep running, use port 8001 for CropGrid instead:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001 --env-file .env
```

Then set `NEXT_PUBLIC_API_URL=http://localhost:8001` in `apps/web/.env.local` and restart the Next.js dev server. Open the **frontend** at `http://localhost:3000`; opening `http://localhost:8000/` shows `{"detail":"Not Found"}` because the API has no homepage route. Test the backend at `http://localhost:8000/api/v1/health` or `http://localhost:8000/docs`.

### Test Paystack and AI locally

For Paystack sandbox, put your own `sk_test_...` key in `apps/backend/.env` as `PAYSTACK_SECRET_KEY=...`. Never use a live key locally and never paste a secret into GitHub or chat. Buyers must register and sign in before checkout. Checkout is NGN-denominated; international cardholders may see the issuer's currency conversion. Direct USD settlement is not enabled unless your merchant account is approved for it. In the UI, choose a listing, click **Buy**, and continue to Paystack. Test success, cancellation, and decline using Paystack's test methods. The backend verifies provider reference, amount, currency, and status before reducing inventory.

For AI, sign in with a seller account, set `OPENAI_API_KEY` in the same backend `.env`, restart Uvicorn, and use **AI assistant → Choose voice note** with a short audio recording. Review the transcript and extracted fields, then choose **Continue to new listing**. The AI tool is separate from the manual **Add a listing** form. Without keys, tests verify that AI/payment routes report the features as unconfigured rather than pretending a request succeeded.

### Pull updates later

```bash
cd ~/projects/cropgrid
git pull --ff-only origin main
cd apps/web && pnpm install --frozen-lockfile
cd ../backend && source .venv/bin/activate && pip install -r requirements.txt
```

Restart the API and web dev server after pulling. Replace `origin` or `main` if your repository uses a different remote name or default branch.
