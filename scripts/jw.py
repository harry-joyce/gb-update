"""Shared helpers for reading Governing Body Update availability from jw.org.

Availability comes from the JW media ("mediator") API rather than the news
article, because the API reports both the full language list for a video and a
per-language `firstPublished` timestamp:

    /media-items/E/docid-<docid>_1_VIDEO   -> availableLanguages[] + firstPublished

One request gives the whole language list; a per-language request gives that
language's own publish time.
"""

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MEDIATOR = "https://b.jw-cdn.org/apis/mediator/v1"
LANGUAGES_URL = "https://www.jw.org/en/languages/"


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


def fetch_json(url, **kwargs):
    return json.loads(fetch(url, **kwargs))


# ---- media API ---------------------------------------------------------- #

def media_item(docid, code="E"):
    """One language's record for a video, or None if it has no version yet."""
    url = "%s/media-items/%s/docid-%s_1_VIDEO" % (MEDIATOR, code, docid)
    payload = fetch_json(url)
    media = payload.get("media") or []
    return media[0] if media else None


def available_languages(docid):
    """Every MEPS language code the video is currently published in."""
    item = media_item(docid, "E")
    if not item:
        raise RuntimeError("no English media item for docid %s" % docid)
    codes = item.get("availableLanguages") or []
    return sorted(set(codes)), item


def watch_url(code, docid):
    """A jw.org link to one language's version of the video.

    Built through jw.org's own finder redirect rather than by assembling a path:
    every language localises its URL segments (German /bibliothek/videos/,
    Basque /liburutegia/bideoak/), so a hand-built /<locale>/library/videos/
    path 404s for everything except English.
    """
    return "https://www.jw.org/finder?lank=docid-%s_1_VIDEO&wtlocale=%s" % (docid, code)


def english_video_page(docid, category="StudioNewsReports"):
    """The English media-library page for the video."""
    return "https://www.jw.org/en/library/videos/#en/mediaitems/%s/docid-%s_1_VIDEO" % (
        category, docid
    )


# ---- language metadata --------------------------------------------------- #

def fetch_language_index():
    """MEPS code -> language metadata.

    jw.org's language list keys each entry by `langcode`, which *is* the MEPS
    code the media API uses (English E, German X, Basque BQ), so this resolves
    every code the API returns.
    """
    data = fetch_json(LANGUAGES_URL)
    index = {}
    for lang in data.get("languages", []):
        code = lang.get("langcode")
        if not code:
            continue
        index[code] = {
            "locale": lang.get("symbol") or "",
            "name": lang.get("name") or code,
            "vernacular": lang.get("vernacularName") or lang.get("name") or code,
            "script": lang.get("script") or "",
            "direction": lang.get("direction") or "ltr",
            "sign": bool(lang.get("isSignLanguage")),
        }
    return index


def describe(code, index):
    """Language metadata for a MEPS code, degrading gracefully if unknown."""
    meta = index.get(code)
    if meta:
        return dict(meta, code=code)
    return {
        "code": code,
        "locale": "en",
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


def normalise_ts(value):
    """'2026-09-18T11:39:09.182Z' -> '2026-09-18T11:39:09Z'."""
    if not value:
        return None
    import datetime

    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return (
        dt.astimezone(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
