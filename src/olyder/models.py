"""Optional OpenAI-compatible chat API client. Never transmit source files by default."""
from __future__ import annotations

import json
import os
from urllib import request, error, parse

from .quota import Budget


class ModelError(RuntimeError):
    pass


class _NoModelRedirects(request.HTTPRedirectHandler):
    """Even same-origin redirects are refused to prevent credential forwarding."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_model_request(req: request.Request, timeout: float):
    # Dedicated opener: never install a process-global urllib handler.
    return request.build_opener(_NoModelRedirects).open(req, timeout=timeout)


def chat(prompt: str, budget: Budget, *, system: str, model: str | None = None, max_tokens: int = 500) -> str:
    model = model or os.getenv("OLYDER_MODEL")
    api_key = os.getenv("OLYDER_API_KEY")
    base = os.getenv("OLYDER_BASE_URL", "https://api.openai.com/v1")
    if not model or not api_key:
        raise ModelError("Set OLYDER_MODEL and OLYDER_API_KEY to enable independent AI verification")
    parsed = parse.urlsplit(base)
    is_loopback_http = parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if not (parsed.scheme == "https" or is_loopback_http) or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ModelError("Model endpoint must use HTTPS (except loopback), without credentials or query")
    # Validate the port before reserving any quota.
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ModelError("Invalid model endpoint port") from exc
    reservation = budget.reserve(system + prompt, max_tokens)
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    try:
        req = request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
        with _open_model_request(req, timeout=45) as resp:
            obj = json.loads(resp.read(2_000_000))
        content = obj["choices"][0]["message"]["content"]
        usage = obj.get("usage", {}).get("total_tokens")
        if not isinstance(content, (str, list, dict)):
            raise TypeError("Unsupported model response content")
    except (error.HTTPError, error.URLError, OSError, KeyError, ValueError, TypeError, IndexError) as exc:
        # A provider may have processed the request before a connection failure.
        budget.settle(reservation, None)
        raise ModelError(f"Model request failed: {type(exc).__name__}") from exc
    budget.settle(reservation, usage if type(usage) is int and usage >= 0 else None)
    return content if isinstance(content, str) else json.dumps(content)
