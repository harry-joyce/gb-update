"""Shared helpers for scraping jw.org language availability."""

import html
import json
import re
import ssl
import time
import urllib.error
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

LANGUAGES_URL = "https://www.jw.org/en/languages/"

# <link rel="alternate" type="text/html" title="..." hreflang="..." href="..." />
_LINK_RE = re.compile(r"<link\b[^>]*\brel=\"alternate\"[^>]*>", re.I)
_ATTR_RE = re.compile(r"(\w[\w:-]*)\s*=\s*\"([^\"]*)\"")
_PUBDATE_RE = re.compile(
    r"<p[^>]*class=\"[^\"]*newsPublishDate[^\"]*\"[^>]*>(.*?)</p>", re.I | re.S
)
_DOCID_RE = re.compile(r"\bdocId-(\d+)")
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)


def _ssl_context():
    """Verified TLS context. Some Python installs (notably python.org builds on
    macOS) ship without a usable CA bundle, so fall back to certifi's."""
    context = ssl.create_default_context()
    paths = ssl.get_default_verify_paths()
    if not (paths.cafile or paths.capath):
        try:
            import certifi

            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            pass
    return context


_CONTEXT = _ssl_context()


def fetch(url, attempts=4, timeout=45):
    """GET a URL as text, retrying transient failures with backoff."""
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept-Language": "en"}
            )
            with urllib.request.urlopen(req, timeout=timeout, context=_CONTEXT) as resp:
                return resp.read().decode("utf-8", "replace")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            last = exc
            if i < attempts - 1:
                time.sleep(3 * (i + 1))
    raise RuntimeError("failed to fetch %s: %s" % (url, last))


def parse_alternates(page):
    """Extract {langcode: {title, url}} from a jw.org article's hreflang links.

    jw.org emits one rel=alternate link per language the article has actually
    been published in, so this set *is* the availability list.
    """
    out = {}
    for tag in _LINK_RE.findall(page):
        attrs = dict(_ATTR_RE.findall(tag))
        code = attrs.get("hreflang", "").strip()
        href = attrs.get("href", "").strip()
        if not code or code == "x-default" or not href:
            continue
        out[code] = {
            "title": html.unescape(attrs.get("title", "")).strip(),
            "url": href,
        }
    return out


def parse_release_date(page):
    """The date shown on the article. jw.org shows the update's release date
    here, identical across languages -- not a per-language publish date."""
    m = _PUBDATE_RE.search(page)
    if not m:
        return None
    # The element holds the date, then a <br> and a category link.
    raw = re.split(r"<br\b[^>]*>", m.group(1), maxsplit=1)[0]
    text = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(html.unescape(text).split()) or None


def parse_doc_id(page):
    m = _DOCID_RE.search(page)
    return m.group(1) if m else None


def parse_title(page):
    m = _TITLE_RE.search(page)
    return " ".join(html.unescape(m.group(1)).split()) if m else None


def fetch_language_index():
    """symbol -> language metadata, trimmed to the fields the report uses."""
    data = json.loads(fetch(LANGUAGES_URL))
    index = {}
    for lang in data.get("languages", []):
        symbol = lang.get("symbol")
        if not symbol:
            continue
        index[symbol] = {
            "name": lang.get("name") or symbol,
            "vernacular": lang.get("vernacularName") or lang.get("name") or symbol,
            "script": lang.get("script") or "",
            "direction": lang.get("direction") or "ltr",
            "sign": bool(lang.get("isSignLanguage")),
        }
    return index


def describe(code, index):
    """Language metadata for a code, degrading gracefully for unknown codes."""
    meta = index.get(code)
    if meta:
        return dict(meta, code=code)
    return {
        "code": code,
        "name": code,
        "vernacular": code,
        "script": "",
        "direction": "ltr",
        "sign": False,
    }


def utcnow():
    """Current UTC time as a stable ISO-8601 string."""
    import datetime

    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
