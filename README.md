# CropGrid

CropGrid is a runnable full-stack MVP for Nigerian agricultural commodity trade, based on the supplied CropGrid architecture specification. The application includes a responsive buyer/supplier marketplace, inventory creation and management, search and filters, a FastAPI JSON API, local SQLite persistence, and optional OpenAI voice parsing. It clearly labels escrow and export paperwork as simulated until real regulated integrations are configured.

## Run locally

Requirements: Python 3.11+ and Node.js 20+.

1. In a terminal, from this folder, create and activate a Python virtual environment, install `apps/backend/requirements.txt`, and copy `apps/backend/.env.example` to `apps/backend/.env`.
2. Start the API with `uvicorn app.main:app --reload --app-dir apps/backend --env-file apps/backend/.env`.
3. In a second terminal, run `pnpm install` and `pnpm dev` from `apps/web`.
4. Open `http://localhost:3000`. API docs are at `http://localhost:8000/docs`.

The default database is a local SQLite file for development. Set `DATABASE_URL` to a PostgreSQL URL for deployment. Set `OPENAI_API_KEY` in the backend `.env` file to enable voice transcription and structured listing extraction. Without a key the listing form remains usable and does not pretend transcription occurred.

## Product boundaries

- Escrow checkout is an explicitly simulated demo; it never collects or holds money.
- Export document preview is a draft checklist, not an official NXP form or certificate.
- Quality grades are seller supplied and unverified in this MVP. The architecture's image grading is a future human-reviewed AI feature, not a verified result.
- Do not use for real transactions or sensitive personal data before adding production authentication, authorization, audit trails, provider integrations, compliance review, and security controls.

## Architecture

- `apps/web`: Next.js App Router, TypeScript, responsive dashboard UI.
- `apps/backend`: FastAPI, Pydantic schemas, SQLAlchemy persistence, listing and order APIs, optional OpenAI audio parser.
- `docker-compose.yml`: local Postgres and API services.

## API

- `GET /api/v1/health`
- `GET /api/v1/inventories`
- `POST /api/v1/inventories`
- `POST /api/v1/ai/parse-audio` (requires `OPENAI_API_KEY`)
- `POST /api/v1/orders/escrow-initiate` (simulated demo state)
- `GET /api/v1/export/form-nxp/{order_id}` (draft checklist only)

The implementation keeps external payment and government services behind explicit integration boundaries; it does not fabricate successful Paystack, Stripe, CBN, NEPC, or NAQS actions.
## Checks

From `apps/backend`, run `python -m unittest discover -s tests -v` after installing `requirements.txt`. The API suite checks health, seeded inventory search, schema validation, quantity limits, draft-only export responses, and the unconfigured AI path. From `apps/web`, run `pnpm run lint` and `pnpm run build`.

`CROPGRID_SEED_DEMO=false` disables the sample inventory seed for a deployment database.

## Run on Ubuntu in WSL

Keep the checkout in the Linux home directory (for example `~/projects/cropgrid`) for better file-watching performance. Install Git, Python 3.11+, Node.js 20+, and pnpm in Ubuntu first.

### First checkout

```bash
mkdir -p ~/projects
cd ~/projects
git clone <REPOSITORY_URL> cropgrid
cd cropgrid
```

### Start the API

```bash
cd ~/projects/cropgrid/apps/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env
```

### Start the web app

Open a second Ubuntu terminal:

```bash
cd ~/projects/cropgrid/apps/web
corepack enable
pnpm install --frozen-lockfile
pnpm dev --hostname 0.0.0.0
```

Open `http://localhost:3000` in the Windows browser and `http://localhost:8000/docs` for the API documentation. The web `.env.example` points the frontend at the API on port 8000. Add an OpenAI key only to `apps/backend/.env` if you want to exercise the optional voice parser; do not commit that `.env` file.

### Pull updates later

```bash
cd ~/projects/cropgrid
git pull --ff-only origin main
cd apps/web && pnpm install --frozen-lockfile
cd ../backend && source .venv/bin/activate && pip install -r requirements.txt
```

Restart the API and web dev server after pulling. Replace `origin` or `main` if your repository uses a different remote name or default branch.
