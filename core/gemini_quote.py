import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings

_USD = re.compile(r"\$[\d,]+(?:\.\d{2})?")
_UNCERTAINTY_PATTERNS = (
    re.compile(r"\bnot enough info(?:rmation)?\b", re.I),
    re.compile(r"\binsufficient information\b", re.I),
    re.compile(r"\buncertain(?:ty)?\b", re.I),
    re.compile(r"\bunable to estimate\b", re.I),
    re.compile(r"\bcannot estimate\b", re.I),
    re.compile(r"\bunknown condition\b", re.I),
)
_CONFIDENCE_PATTERN = re.compile(r"\b(HIGH|MEDIUM|LOW)\b", re.I)


def extract_share_bear_offer_amount(quote_text: str) -> str | None:
    """
    Return the cash offer (e.g. '$150') from a Gemini response that includes
    retail estimate, offer, and notes. Uses section labels first, then a
    two-amount fallback (retail, then 30% offer).
    """
    if not (quote_text or "").strip():
        return None
    text = quote_text.replace("\r\n", "\n")
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.search(r"share\s*bear", s, re.I) and re.search(r"offer", s, re.I):
            m = _USD.search(s)
            if m:
                return m.group(0)
    amounts = _USD.findall(text)
    if len(amounts) >= 2:
        return amounts[1]
    if len(amounts) == 1:
        return amounts[0]
    return None


def extract_confidence_level(quote_text: str) -> str:
    """
    Parse confidence level (HIGH, MEDIUM, LOW) from the Gemini response.
    Returns 'LOW' if not found (safe fallback).
    """
    if not (quote_text or "").strip():
        return "LOW"
    text = quote_text.replace("\r\n", "\n")
    for line in text.splitlines():
        s = line.strip().lower()
        if "confidence" in s:
            m = _CONFIDENCE_PATTERN.search(line)
            if m:
                return m.group(1).upper()
    return "LOW"


def format_share_bear_offer_display(quote_text: str) -> str:
    confidence = extract_confidence_level(quote_text)
    if confidence == "LOW":
        return "$0"
    if is_uncertain_quote_text(quote_text):
        return "$0"
    retail = extract_estimated_retail_amount(quote_text)
    if retail is None:
        return "$0"
    return compute_share_bear_offer_from_retail(retail)


def is_uncertain_quote_text(quote_text: str) -> bool:
    text = (quote_text or "").strip()
    if not text:
        return False
    return any(p.search(text) for p in _UNCERTAINTY_PATTERNS)


def extract_estimated_retail_amount(quote_text: str) -> Decimal | None:
    if not (quote_text or "").strip():
        return None
    text = quote_text.replace("\r\n", "\n")
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.search(r"\bretail\b", s, re.I):
            m = _USD.search(s)
            if m:
                return parse_usd_amount(m.group(0))
    amounts = _USD.findall(text)
    if amounts:
        return parse_usd_amount(amounts[0])
    return None


def parse_usd_amount(raw_amount: str) -> Decimal | None:
    clean = (raw_amount or "").strip().replace("$", "").replace(",", "")
    if not clean:
        return None
    try:
        return Decimal(clean)
    except InvalidOperation:
        return None


def compute_share_bear_offer_from_retail(retail_amount: Decimal) -> str:
    offer = (retail_amount * Decimal("0.30")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"${int(offer):,}"


def build_quote_prompt(*, item_name: str, description: str, make: str, model: str, unknown_make_model: bool) -> str:
    if unknown_make_model:
        identity = (
            "The seller selected a generic quote: make and model are unknown. "
            "Use the item name and description to infer a reasonable product category and typical US retail, "
            "and state uncertainty briefly where appropriate."
        )
    else:
        identity = f"Make/brand: {make}\nModel: {model}"

    return f"""You are a pricing assistant for SHARE Bear, a student direct buy-back program.

Task:
1) First, assess whether this is a recognizable real product you can price with confidence.
2) Estimate a typical current US retail price (or MSRP for new items) for the described item in average used-good condition unless the description says otherwise.
3) Compute SHARE Bear's buy-back offer as exactly 30% of that retail estimate (one dollar amount, rounded to whole dollars).
4) Explain briefly (2–3 sentences) how you arrived at the retail estimate.

Constraints:
- Output in USD.
- The buy-back line must be exactly 30% of your retail estimate.
- If information is missing, make reasonable assumptions and say what you assumed.
- Do not mention percentages or pricing formulas in the final response.

{identity}

Item name: {item_name}
Description:
{description}

Format the reply with clear sections:
- Item confidence: HIGH, MEDIUM, or LOW
  (HIGH = recognizable real product with verifiable market data;
   MEDIUM = item seems real but limited info available;
   LOW = cannot verify this is a real product, description unclear or nonsensical)
- Estimated retail (USD)
- SHARE Bear offer (USD)
- Notes / assumptions
"""


def get_quote_from_gemini(prompt: str) -> str:
    """Call Gemini via the REST API (stdlib only — no `google` package on disk)."""
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    if not settings.GEMINI_API_KEY:
        raise RuntimeError("Gemini is not configured (missing GEMINI_API_KEY).")

    model = settings.GEMINI_MODEL
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={urllib.parse.quote(settings.GEMINI_API_KEY, safe='')}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 1024,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get("error", {}).get("message", err_body)
        except json.JSONDecodeError:
            msg = err_body or str(e.reason)
        raise RuntimeError(msg) from None

    if "error" in body:
        raise RuntimeError(body["error"].get("message", str(body["error"])))

    candidates = body.get("candidates") or []
    if not candidates:
        block = (body.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise RuntimeError(f"Request was blocked ({block}).")
        raise RuntimeError("No response from the model.")

    parts = (candidates[0].get("content") or {}).get("parts") or []
    texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
    text = "".join(texts).strip()
    if not text:
        raise RuntimeError("Empty response from the model.")
    return text
