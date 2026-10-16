# Listing AI, help assistant and support requests

This incremental update follows the media/chat/delivery update. It does not
replace your `.env`, database or account records.

## What the AI does

1. The listing assistant extracts a draft crop listing from typed text or audio.
   It accepts crop-only text such as `cashew`; missing quantity, price and location
   stay unknown. Sellers must review and supply required fields before publishing.
2. The help assistant explains CropGrid features using the application's reviewed
   help articles. It offers guidance; it cannot change accounts, decide disputes,
   verify crop quality, refund payments or release funds.

The Help center works when AI credit is unavailable: it clearly labels its answer
as a reviewed article. This fallback is not represented as an AI-generated reply.
Users must sign in for guided answers/private support requests; the FAQ remains public.
Unresolved issues can be saved as tickets for an administrator to review later.
Tickets are not proof of resolution and no response time is guaranteed. Admins
open Help center to see the support queue, update status and send a reply.
Users see replies by refreshing their support requests. No email notification is implemented.

## Apply in WSL

Stop backend/frontend processes with Ctrl+C, then:

```bash
cd ~/projects/cropgrid
cropgrid_patch=/mnt/c/Users/l2e/Documents/Codex/2026-10-08/ac/cropgrid-support-ai.patch
git apply --check "$cropgrid_patch" && git apply "$cropgrid_patch"
```

If the check fails, stop and inspect the differences. Do not force a patch or
replace one entire side of a conflict. Existing local changes remain intact when
the check fails. New support tables are created at application startup. Back up
your application database before an upgrade.

Run tests on a disposable database:

```bash
cd ~/projects/cropgrid/apps/backend
source .venv/bin/activate
python -m pip install -r requirements.txt
test_db_dir=$(mktemp -d)
DATABASE_URL="sqlite:///$test_db_dir/test.db" python -m unittest discover -s tests -v
```

The optional backend `OPENAI_SUPPORT_MODEL` setting defaults to the listing model.
It can be set to `gpt-4o-mini`. Keep `OPENAI_API_KEY` only in the backend environment.
The application sends no account records to the model. Basic redaction removes
recognizable API keys and `password=...` patterns, but users must never submit
secrets: redaction is not a general sensitive-data detector.

## Diagnose HTTP 429

The screenshot's 429 is a provider-limit error. A screenshot does not establish
whether it is temporary throttling or an API credit/account limit. The updated
error handler recognizes direct/nested quota and billing codes; temporary limits
send Retry-After and disable repeated listing requests during a visible cooldown.
No automatic SDK retries are used for listing or help requests.

Run one text diagnostic from `apps/backend`:

```bash
python scripts/check_ai.py
```

For an audio-specific diagnostic:

```bash
python scripts/check_ai.py --audio
```

The second command asks for the WSL path to an existing audio file, then checks
transcription and extraction separately. These commands make real billable API
requests and print no API key. Share only their safe error summary/category/request
ID if a request fails. Do not print `.env` or provider request headers.

- Quota/billing errors: the account owner must check API credit, billing and project
  limits in the OpenAI platform. Application code cannot restore exhausted credit.
- Temporary limits: wait for the indicated retry period and make one request.
- Audio-only limits: inspect the transcription model's access and limits as well
  as the listing model's; a successful text check does not validate audio.

Official reference: https://developers.openai.com/api/docs/guides/error-codes

## Start and accept

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002 --env-file .env
```

In another WSL terminal:

```bash
cd ~/projects/cropgrid/apps/web
pnpm run lint && pnpm run build
pnpm dev --hostname 0.0.0.0 --port 3000
```

Hard-refresh the browser. Test `cashew` and a full listing description, then a real
audio clip. Under Help assistant, ask how to add a video. With provider access it
shows AI guidance; without it it shows a reviewed article. Ask about a payment
refund: it must explain limitations and offer human review, never claim to refund.
Create a support request, check it is hidden from another buyer, then reply as
administrator and confirm the original user can see that reply.

AI help requests have application limits: 5/minute and 20/day per user, plus
200/day globally, then reviewed articles remain available. These database checks
are MVP cost controls, not a distributed abuse-prevention system. Production
needs verification/rate limits at the edge and a provider spend budget.

## Still required before public financial launch

Actual AI text/audio acceptance with the user's provider account; sandbox payment
and webhook acceptance; an approved Nigerian holding/release/refund arrangement;
production object storage and video processing; formal database migrations;
deployment, backup/restore, browser/session and PostgreSQL concurrency checks.
The prior TRADING_UPDATE.md restrictions still apply. No claim of a flawless,
production-ready or functioning escrow marketplace is made by this update.
