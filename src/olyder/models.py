"""Optional OpenAI-compatible chat API client. Never transmit source files by default."""
from __future__ import annotations

import json
import os
from urllib import request, error, parse

from .quota import Budget
from .control import current


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
    control = current.get()
    if control:
        control.check()
    if control and control.model_provider is not None:
        reservation = budget.reserve(system + prompt, max_tokens)
        try:
            provider = control.model_provider
            if provider.api_version != 1:
                raise ValueError('Incompatible model provider protocol')
            response = provider.complete(prompt, system=system, max_tokens=max_tokens)
            content = response['content']
            if not isinstance(content, str):
                raise ValueError('Model content must be text')
            usage = response.get('usage', {})
            total = usage.get('total_tokens')
            budget.settle(reservation, total if type(total) is int and total >= 0 else None)
            control.model_observations.append(_observation(usage, response.get('model'),
                response.get('provider','custom'), response.get('estimated_cost_usd')))
            control.check()
            return content
        except (KeyError, ValueError, TypeError, OSError) as exc:
            if reservation.ticket in budget._active:
                budget.settle(reservation, None)
            raise ModelError('Custom model provider failed: '+type(exc).__name__) from exc
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
        timeout = max(.01, min(45, control.deadline - __import__('time').monotonic())) if control else 45
        with _open_model_request(req, timeout=timeout) as resp:
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
    if control:
        control.model_observations.append(_observation(obj.get('usage', {}), model, 'openai_compatible'))
        control.check()
    return content if isinstance(content, str) else json.dumps(content)


def _observation(usage, model, provider, estimate=None):
    if not isinstance(usage,dict):
        usage={}
    inp, out = usage.get('prompt_tokens',usage.get('input_tokens')), usage.get('completion_tokens',usage.get('output_tokens'))
    valid = all(type(x) is int and x >= 0 for x in (inp,out))
    details=usage.get('prompt_tokens_details')
    cache = details.get('cached_tokens') if isinstance(details,dict) else None
    if type(cache) is not int or cache<0 or not valid or cache>inp:
        cache=None
    return {'provider':provider,'model':model,'input_tokens':inp if valid else None,
            'output_tokens':out if valid else None,'cached_tokens':cache,
            'observed_tokens':inp+out if valid else None,'usage_complete':valid,
            'estimated_cost_usd':estimate,'billed_cost_usd':None,'origin':'model_response'}
