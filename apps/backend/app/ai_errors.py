"""Safe, actionable errors; never return upstream request bodies or API keys."""
import logging
import re
from fastapi import HTTPException

logger = logging.getLogger("cropgrid.ai")

def safe_error_codes(exc):
    body = getattr(exc, "body", None)
    bodies = [body] if isinstance(body, dict) else []
    if bodies and isinstance(body.get("error"), dict):
        bodies.append(body["error"])
    values = [getattr(exc, "code", None), getattr(exc, "type", None)]
    values.extend(value for item in bodies for value in (item.get("code"), item.get("type")))
    known = {"insufficient_quota", "billing_hard_limit_reached", "billing_not_active", "usage_limit_reached", "rate_limit_exceeded", "tokens", "requests", "credit_balance_exhausted", "project_spend_limit_exceeded", "organization_spend_limit_exceeded", "organization_usage_limit_exceeded", "slow_down"}
    return {value for value in values if isinstance(value, str) and value in known}

def provider_error(exc):
    from openai import AuthenticationError, PermissionDeniedError, NotFoundError, RateLimitError, APIConnectionError, APITimeoutError, BadRequestError
    logger.warning("AI provider failure type=%s status=%s request_id=%s", type(exc).__name__, getattr(exc, "status_code", None), getattr(exc, "request_id", None))
    if isinstance(exc, AuthenticationError):
        return HTTPException(503, "AI credentials were rejected. The site owner must check OPENAI_API_KEY in the backend environment and restart the API.")
    if isinstance(exc, RateLimitError):
        codes = safe_error_codes(exc)
        logger.warning("AI limit category=%s", ",".join(sorted(codes)) or "unspecified_429")
        if "credit_balance_exhausted" in codes:
            return HTTPException(503, "The API organization has no prepaid credit remaining. The site owner must add API credit; generating another key in the same organization will not restore access.")
        if codes & {"project_spend_limit_exceeded", "organization_spend_limit_exceeded"}:
            return HTTPException(503, "An enforced API project or organization spending limit was reached. The site owner must review that limit and its budget before retrying.")
        if "organization_usage_limit_exceeded" in codes:
            return HTTPException(503, "The API organization's approved usage limit was reached. The account owner must review its approved usage limit with OpenAI.")
        if codes & {"insufficient_quota", "billing_hard_limit_reached", "billing_not_active", "usage_limit_reached"}:
            return HTTPException(503, "AI API credit or spending limit is exhausted. The site owner must check the OpenAI API billing balance and limits.")
        response = getattr(exc, "response", None)
        raw_retry = response.headers.get("retry-after", "60") if response is not None else "60"
        retry = str(min(3600, max(1, int(raw_retry)))) if re.fullmatch(r"\d{1,6}", raw_retry) else "60"
        return HTTPException(429, "The AI provider request limit was reached. Pause before retrying. If one request still fails, check the project's API limits and billing.", headers={"Retry-After": retry})
    if isinstance(exc, (PermissionDeniedError, NotFoundError)):
        return HTTPException(503, "The configured AI model or project is unavailable. The site owner must check model access and OPENAI_LISTING_MODEL / OPENAI_TRANSCRIPTION_MODEL.")
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return HTTPException(503, "The API server could not reach the AI provider. Check the server internet connection and retry.")
    if isinstance(exc, BadRequestError):
        return HTTPException(422, "The AI provider could not process this input. For audio, try a clear MP3 or WAV recording; otherwise check the configured model.")
    return HTTPException(502, "AI returned an unexpected response. Ask the site owner to check the backend log for the error type and request ID.")
