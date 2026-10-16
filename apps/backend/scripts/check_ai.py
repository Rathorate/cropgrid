"""Run from apps/backend. Makes one small real AI request; prints no credentials."""
import os
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
from app.ai_errors import provider_error
from app.listing_ai import extract_listing_draft, NoListingFound, ListingResponseError

if not os.getenv("OPENAI_API_KEY", "").strip():
    raise SystemExit("OPENAI_API_KEY is missing from the backend environment/.env.")

parser = argparse.ArgumentParser(description="Check AI access without printing credentials.")
parser.add_argument("--audio", nargs="?", const="", help="Optional WSL audio file path; omit the value to enter it at a prompt.")
parser.add_argument("--show-transcript", action="store_true", help="Show your transcript locally so you can check recognition. Do not share private contents.")
args = parser.parse_args()
stage = "text extraction"
try:
    from openai import OpenAI
    client = OpenAI(timeout=60, max_retries=0)
    text = "yam, Ibadan, 2 tons"
    if args.audio is not None:
        stage = "audio transcription"
        path = Path(args.audio or input("Enter the WSL path to your audio file: ").strip()).expanduser()
        types = {".mp3":"audio/mpeg", ".mp4":"audio/mp4", ".m4a":"audio/mp4", ".mpeg":"audio/mpeg", ".mpga":"audio/mpeg", ".wav":"audio/wav", ".webm":"audio/webm", ".ogg":"audio/ogg", ".flac":"audio/flac"}
        if not path.is_file() or path.suffix.lower() not in types:
            raise SystemExit("Choose an existing MP3, MP4, M4A, MPEG, MPGA, WAV, WebM, OGG or FLAC file.")
        if not 0 < path.stat().st_size <= 20_000_000:
            raise SystemExit("Audio must be non-empty and at most 20 MB.")
        with path.open("rb") as handle:
            data = handle.read(20_000_001)
        if len(data) > 20_000_000:
            raise SystemExit("Audio file exceeds 20 MB.")
        text = client.audio.transcriptions.create(model=os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1"), file=(path.name, data, types[path.suffix.lower()])).text
        print("Audio transcription succeeded.")
        if args.show_transcript:
            print("Recognized transcript (review locally):")
            print(text or "[No speech detected]")
        stage = "text extraction after transcription"
    draft = extract_listing_draft(text, client=client)
    import json
    print("Listing extraction succeeded. Review this draft:")
    print(json.dumps(draft, indent=2))
except NoListingFound as exc:
    print(f"The provider responded, but this input did not produce a crop listing: {exc}")
    if args.audio is not None and not args.show_transcript:
        print("Rerun with --show-transcript to check what was recognized, or record the example listing sentence.")
    raise SystemExit(2)
except ListingResponseError as exc:
    print(f"AI response validation failed during {stage}: {exc}")
    raise SystemExit(1)
except Exception as exc:
    error = provider_error(exc)
    print(f"AI check failed during {stage} ({error.status_code}): {error.detail}")
    raise SystemExit(1)
