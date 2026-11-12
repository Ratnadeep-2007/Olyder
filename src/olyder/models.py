"""Optional OpenAI-compatible chat API client. Never transmit source files by default."""
import json
import os
from urllib import request, error

from .quota import Budget


class ModelError(RuntimeError):
    pass


def chat(prompt: str, budget: Budget, *, system: str, model: str | None = None, max_tokens: int = 500) -> str:
    model = model or os.getenv("OLYDER_MODEL")
    api_key = os.getenv("OLYDER_API_KEY")
    base = os.getenv("OLYDER_BASE_URL", "https://api.openai.com/v1")
    if not model or not api_key:
        raise ModelError("Set OLYDER_MODEL and OLYDER_API_KEY to enable independent AI verification")
    if not base.startswith("https://") and not (base.startswith("http://127.0.0.1:") or base.startswith("http://localhost:")):
        raise ModelError("Model endpoint must use HTTPS (except localhost)")
    # Estimate full request conservatively, including system instructions.
    reservation = budget.reserve(system + prompt, max_tokens)
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0
    }
    req = request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=45) as resp:
            obj = json.loads(resp.read(2_000_000))
        content = obj["choices"][0]["message"]["content"]
        usage = obj.get("usage", {}).get("total_tokens")
        budget.settle(reservation, usage if isinstance(usage, int) else None)
        return content if isinstance(content, str) else json.dumps(content)
    except (error.URLError, KeyError, ValueError, TypeError) as exc:
        # Request may have been processed even if disconnected: conservatively charge reserved amount.
        budget.settle(reservation, None)
        raise ModelError(f"Model request failed: {type(exc).__name__}") from exc
