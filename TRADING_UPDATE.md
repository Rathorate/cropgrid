# Media, chat, delivery and AI update

This update builds on the text/audio AI patch. Apply the incremental patch from
the repository root with `git apply --check` first, then `git apply`.
Do not use `git am`, `--3way`, or select an entire side of a conflict automatically.
If the check fails, preserve your files and inspect the differences.

## Local setup

1. Stop both development servers with Ctrl+C.
2. In `apps/backend`, activate `.venv`, then run `python -m pip install -r requirements.txt`.
   Pillow is required for image decoding, validation and metadata removal.
3. Edit your existing backend `.env`; keep secrets private:

   ```env
   OPENAI_API_KEY=your-own-key
   OPENAI_LISTING_MODEL=gpt-4o-mini
   OPENAI_TRANSCRIPTION_MODEL=whisper-1
   PAYSTACK_SECRET_KEY=your-own-sk_test-key
   PAYSTACK_CALLBACK_URL=http://localhost:3000/payment/return
   ```

   Do not replace an existing database URL or administrator configuration.
   Run `python scripts/check_ai.py` from `apps/backend` for one small real text
   request. This reports credential/billing/model/connection failures without
   printing the key. API usage may be billed by your provider. A successful text
   check does not establish that a real audio recording has been transcribed.
4. Run the backend tests against a disposable database, not your application database:

   ```bash
   test_db_dir=$(mktemp -d)
   DATABASE_URL="sqlite:///$test_db_dir/test.db" python -m unittest discover -s tests -v
   ```

5. Start the backend:

   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8002 --env-file .env
   ```

6. In another terminal, run frontend checks and start it:

   ```bash
   cd ~/projects/cropgrid/apps/web
   pnpm run lint && pnpm run build
   pnpm dev --hostname 0.0.0.0 --port 3000
   ```

   The frontend `.env.local` must use `NEXT_PUBLIC_API_URL=http://localhost:8002`.

## Acceptance checks

- Create two separate accounts: a seller and a buyer. Use a private browser window
  for the second session. Sample listings have no seller account and cannot receive chats.
- As seller, add a Yam listing with JPEG/PNG/WebP photos and an MP4 or WebM video.
  Limits: six files per listing, 8 MB per photo, 30 MB per video.
  MP4 with H.264 video/AAC audio is recommended for broad browser compatibility.
  Other codecs may need conversion before upload. Media is seller supplied, not verified produce quality.
- Reload, open the gallery and play/seek the real video in your target browsers.
- As buyer, select Chat with seller. Send a message, then check the seller's Messages
  inbox. Messages refresh every four seconds. Support administrators can review them.
- Use AI text `yam, Ibadan, 2 tons`; review the draft. Price must remain unknown
  unless supplied. Try a clear M4A/MP3/WAV audio note too. Authentication, quota,
  connection and model-access failures now have distinct explanations. Keys are not logged.
- Complete Paystack **test** checkout on the real seller listing. Payment verification
  is tested with mocks in automated tests; actual provider credentials still need a sandbox acceptance test.
- Seller marks a paid order dispatched with tracking information. Buyer confirms
  receipt after inspection, or reports a delivery problem. A dispute blocks receipt confirmation.
- Check another unrelated buyer cannot read the conversation or change the delivery.

## Money handling: incomplete and disabled for live marketplace payments

Paystack checkout verifies a charge to the merchant; it does not establish an
escrow deposit inside CropGrid. Delivery state and payment state are separate.
Buyer receipt confirmation does not move money. The release endpoint is disabled,
and live Paystack keys are rejected by marketplace checkout.

The requested flow — buyer deposit, protected holding, delivery, dispute handling,
seller release/refund — requires a provider/partner that explicitly supports that
arrangement for the merchant's jurisdiction and business. Obtain the approved flow,
settlement terms and API credentials before implementing actual custody or payouts.

Paystack's current preauthorization documentation says the feature is available
only to South African businesses and requires enablement. It is not a Nigerian
escrow implementation. Paystack also lists escrow services under unsupported categories:

- https://support.paystack.com/en/articles/10450882
- https://support.paystack.com/en/articles/2127042

No escrow protection, seller payment, wallet balance or refund should be advertised
as available in this version. Admins can inspect disputed delivery records in Orders;
provider-backed dispute resolution and refunds remain launch work.

## Deployment limits

Media is stored in a separate database table to survive backend restarts and work
with a separately deployed frontend. This is a bounded MVP implementation, not a
large video hosting service. Before a public launch, use private object storage with
controlled uploads, a CDN, media transcoding/scanning and retention quotas.
MP4/WebM upload validation currently checks MIME and container signatures; it does
not fully decode or transcode video. Real browser playback checks remain necessary.

New tables are created by existing startup initialization; existing listing and
payment data are preserved. Back up the database before upgrading. Formal versioned
database migrations, PostgreSQL concurrency/load tests, content moderation and
production storage configuration remain deployment work. The automated regression
suite uses SQLite; it does not establish concurrent stock safety on production PostgreSQL.

For separate frontend/backend hosts, use HTTPS and domains such as `app.example.com`
and `api.example.com`, configure exact CORS origins, and verify session cookies in
the deployed browser. The current SameSite=Lax session cookie needs a same-site
domain arrangement; unrelated hosting domains require an authentication deployment change.
