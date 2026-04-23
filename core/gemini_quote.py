from django.conf import settings


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
1) Estimate a typical current US retail price (or MSRP for new items) for the described item in average used-good condition unless the description says otherwise.
2) Compute SHARE Bear’s buy-back offer as exactly 30% of that retail estimate (one dollar amount, rounded to whole dollars).
3) Explain briefly (2–3 sentences) how you arrived at the retail estimate.

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
