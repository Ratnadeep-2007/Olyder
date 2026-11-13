"""Bounded, allowlisted source retrieval for evidence-based idea assessment.

Only URLs explicitly written in the spec are retrieved. Retrieved content is untrusted.
"""
import hashlib
import html
import re
import time
from datetime import UTC, datetime
from urllib import error, parse, request


def collect(sources: list[str], *, network_allowed: bool) -> list[dict]:
    evidence = []
    for url in sources[:12]:
        from .control import current
        control = current.get()
        if control:
            control.check()
        record = {"url": url, "status": "blocked", "excerpt": "", "sha256": "",
                  "classification":"unanswered", "retrieved_at":datetime.now(UTC).isoformat()}
        if not network_allowed:
            record["reason"] = "External retrieval disabled; pass --allow-network"
            evidence.append(record)
            continue
        if parse.urlparse(url).scheme != "https":
            record["reason"] = "Only HTTPS sources are supported"
            evidence.append(record)
            continue
        try:
            req = request.Request(url, headers={"User-Agent": "Olyder/0.1"})
            class RefuseRedirect(request.HTTPRedirectHandler):
                # Do not follow redirects at all: a public URL may redirect to an
                # internal/metadata host, or pass through auth-bearing URLs.
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            opener = request.build_opener(RefuseRedirect)
            timeout=max(.01,min(12,control.deadline-time.monotonic())) if control else 12
            with opener.open(req, timeout=timeout) as response:
                data = response.read(80_000)
                record["status"] = "fetched"
                record["sha256"] = hashlib.sha256(data).hexdigest()
                decoded = data.decode("utf-8", errors="replace")
                plain = re.sub(r"<[^>]+>", " ", decoded)
                plain = re.sub(r"\s+", " ", html.unescape(plain))
                record["excerpt"] = plain[:4000]
                record["reason"] = "Fetched excerpt; not independently verified"
                record['classification'] = 'observed_not_corroborated'
        except error.HTTPError as exc:
            record["status"] = "blocked" if 300 <= exc.code < 400 else "error"
            record["reason"] = "Redirect refused; list the destination explicitly in sources" if 300 <= exc.code < 400 else f"HTTP status {exc.code}"
        except (OSError, ValueError, error.URLError) as exc:
            record["status"] = "error"
            record["reason"] = f"Retrieval failed: {type(exc).__name__}"
        evidence.append(record)
        if control:
            control.check()
    return evidence
