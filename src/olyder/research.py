"""Bounded, allowlisted source retrieval for evidence-based idea assessment.

Only URLs explicitly written in the spec are retrieved. Retrieved content is untrusted.
"""
import hashlib
import html
import re
from urllib import request, error, parse


def collect(sources: list[str], *, network_allowed: bool) -> list[dict]:
    evidence = []
    for url in sources[:12]:
        record = {"url": url, "status": "blocked", "excerpt": "", "sha256": ""}
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
            with opener.open(req, timeout=12) as response:
                data = response.read(80_000)
                record["status"] = "fetched"
                record["sha256"] = hashlib.sha256(data).hexdigest()
                decoded = data.decode("utf-8", errors="replace")
                plain = re.sub(r"<[^>]+>", " ", decoded)
                plain = re.sub(r"\s+", " ", html.unescape(plain))
                record["excerpt"] = plain[:4000]
                record["reason"] = "Fetched excerpt; not independently verified"
        except error.HTTPError as exc:
            record["status"] = "blocked" if 300 <= exc.code < 400 else "error"
            record["reason"] = "Redirect refused; list the destination explicitly in sources" if 300 <= exc.code < 400 else f"HTTP status {exc.code}"
        except (OSError, ValueError, error.URLError) as exc:
            record["status"] = "error"
            record["reason"] = f"Retrieval failed: {type(exc).__name__}"
        evidence.append(record)
    return evidence
