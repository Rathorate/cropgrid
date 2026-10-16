# Audio-to-listing extraction fix

The text request and audio transcription have succeeded with the configured
provider. The original diagnostic then raised a generic ValueError whenever the
model response lacked a non-empty `crop_name`. That did not distinguish an
unrelated recording from a response-format problem. The recording's actual
contents still need to be checked locally; this update does not assume them.

## Changes

- API and diagnostic now share `app/listing_ai.py` instead of using different prompts.
- The configured Groq GPT-OSS models use a strict, flat JSON schema with nullable
  unknown fields. Other compatible models retain JSON-object mode.
- Older wrapped listing objects can be normalized without inventing values.
- Missing crop details become an actionable input response (HTTP 422), rather than
  a generic provider outage. Malformed/truncated responses have separate explanations.
- `--show-transcript` displays the recognized words locally when requested. Do not
  share private recording contents or credentials.

Groq schema documentation: https://console.groq.com/docs/structured-outputs

## WSL steps

Stop the backend, then apply the focused patch from the repository root:

```bash
cd ~/projects/cropgrid
cropgrid_patch=/mnt/c/Users/l2e/Documents/Codex/2026-10-08/ac/cropgrid-audio-draft-fix.patch
git apply --check "$cropgrid_patch" && git apply "$cropgrid_patch"
cd apps/backend
source .venv/bin/activate
test_db_dir=$(mktemp -d)
DATABASE_URL="sqlite:///$test_db_dir/test.db" python -m unittest discover -s tests -v
python scripts/check_ai.py
python scripts/check_ai.py --audio "/mnt/c/Users/l2e/Downloads/New Recording.m4a" --show-transcript
```

If patch checking fails, preserve the current files and inspect the differences;
do not force it or choose an entire side of a conflict blindly.

If the recognized words do not identify produce, record a new voice note saying:
"I have 2 tons of yam in Abuja at 500000 naira per ton."
Do not expect a listing from arbitrary speech. Speech recognition and model
extraction can still make mistakes, so review crop, quantity, location and price.

After successful diagnostics, restart:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002 --env-file .env
```

Verify the same recording through the browser as a seller and review the draft
before publishing. This patch is backend-only; the frontend need not be rebuilt.

The Groq configuration remains in the private backend `.env`:
`OPENAI_BASE_URL=https://api.groq.com/openai/v1`, the user's Groq key in
`OPENAI_API_KEY`, `OPENAI_LISTING_MODEL=openai/gpt-oss-20b`, and
`OPENAI_TRANSCRIPTION_MODEL=whisper-large-v3-turbo`.

## Push after acceptance

Use the WSL checkout that contains all prior feature updates. Inspect `git status`
and the staged changes before committing. Keep `.env`, `.env.local`, database
files and backups out of the commit. Do not force push or reset the branch to
address a rejected push. Reconcile with the current remote if necessary.

Passing mocked regressions does not prove the user's actual audio or a provider
account will succeed. Real recording acceptance is required before calling this
flow complete. Payment holding/release and the deployment work described in
TRADING_UPDATE.md and SUPPORT_UPDATE.md remain separate launch requirements.
