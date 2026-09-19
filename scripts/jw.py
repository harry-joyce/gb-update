"""Shared helpers for reading Governing Body Update availability from jw.org.

Availability is read from two different JW APIs, because they answer two
different questions about the same video and they do not agree:

    pub-media  GETPUBMEDIALINKS?alllangs=1&docid=<docid>
        Every language that has a media *file* on the CDN. This is the
        endpoint the playback/download selector on the news article uses, and
        it is the earliest public signal a language exists -- a file shows up
        here as soon as it lands. One request returns the whole set, so
        discovery needs no per-language probing at all. This is the PRIMARY
        signal: it is what decides whether someone can watch the video.

    mediator   /media-items/E/docid-<docid>_1_VIDEO
        availableLanguages[] -- every language published in the media
        *catalogue*, which is what the /library/videos/ page lists. This runs
        behind pub-media, sometimes by hours, and is kept as a SECOND series.

Measured 19 Sep 2026, 14:5x UTC: pub-media listed 20 languages, the catalogue
10. The ten extra had live, downloadable files with correct localised titles
and no catalogue entry whatsoever, so counting the catalogue alone understated
what a publisher could actually watch by half.

A per-language request to either API gives that language's own detail: a
localised title from both, `firstPublished` from the mediator, and
`file.modifiedDatetime` per file from pub-media.
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
PUBMEDIA = "https://b.jw-cdn.org/apis/pub-media/GETPUBMEDIALINKS"
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


def fetch(url, attempts=4, timeout=45, allow_missing=False):
    """GET a URL as text, retrying transient failures with backoff.

    With allow_missing, a 404 returns None immediately instead of being
    retried: pub-media answers 404 for a language that simply has no files for
    a document yet, which is an ordinary answer, not a failure worth four
    attempts and nine seconds of backoff.
    """
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept-Language": "en"}
            )
            with urllib.request.urlopen(req, timeout=timeout, context=_CONTEXT) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if allow_missing and exc.code == 404:
                return None
            last = exc
            if i < attempts - 1:
                time.sleep(3 * (i + 1))
        except (urllib.error.URLError, OSError) as exc:
            last = exc
            if i < attempts - 1:
                time.sleep(3 * (i + 1))
    raise RuntimeError("failed to fetch %s: %s" % (url, last))


def fetch_json(url, **kwargs):
    body = fetch(url, **kwargs)
    if body is None:
        return None
    return json.loads(body)


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


# ---- pub-media API (the primary signal) ---------------------------------- #

def _pub_media_url(docid, code, alllangs=False):
    params = [
        ("output", "json"),
        ("docid", str(docid)),
        ("langwritten", code),
        ("txtCMSLang", code),
    ]
    if alllangs:
        params.append(("alllangs", "1"))
    return PUBMEDIA + "?" + urllib.parse.urlencode(params)


def pub_media_languages(docid):
    """Every MEPS code that has a media file for the video.

    One request, the whole set. With alllangs=1 the per-language file lists
    come back as `__deferred` stubs rather than real entries, so this is a
    language *roster* only -- titles and timestamps need pub_media_item().

    Returns (sorted codes, the raw per-language metadata dict). The metadata is
    a usable fallback for a code missing from jw.org's language index, since
    pub-media states each language's own name, locale, script and direction.
    """
    payload = fetch_json(_pub_media_url(docid, "E", alllangs=True))
    languages = (payload or {}).get("languages") or {}
    return sorted(languages), languages


def pub_media_item(docid, code):
    """One language's files, or None if that language has none yet.

    The per-file `modifiedDatetime` is the closest thing pub-media offers to a
    publish time, and the earliest across a language's files is the best
    estimate of when it became watchable. It is only an estimate: the value
    moves when a file is re-encoded and replaced, which is why callers clamp it
    and pin it (see resolve_file_time in track.py).
    """
    payload = fetch_json(_pub_media_url(docid, code), allow_missing=True)
    if not isinstance(payload, dict):
        # A 404 body is a JSON *list* ([{"title": "Not Found", ...}]), so a
        # non-dict answer means "no files", not a malformed response.
        return None
    by_format = (payload.get("files") or {}).get(code) or {}

    # Only the video files count. A language's entry also carries its subtitle
    # track (fileformat AIVTT, mimetype text/vtt), whose `title` is the edition
    # name -- "Ordinarie", not the video's title -- and whose timestamp says
    # nothing about whether the video can be watched.
    entries, formats = [], []
    for fmt, arr in sorted(by_format.items()):
        if not isinstance(arr, list):
            continue  # an alllangs-style __deferred stub
        videos = [e for e in arr if str(e.get("mimetype") or "").startswith("video/")]
        if videos:
            formats.append(fmt)
            entries.extend(videos)
    if not entries:
        return None

    title = ""
    stamps = []
    for entry in entries:
        title = title or (entry.get("title") or "").strip()
        stamp = normalise_pub_ts(((entry.get("file") or {}).get("modifiedDatetime")))
        if stamp:
            stamps.append(stamp)

    return {
        "title": title,
        "modified": min(stamps) if stamps else None,
        "latest_modified": max(stamps) if stamps else None,
        "formats": formats,
        "file_count": len(entries),
    }


def download_api(docid):
    """The pub-media request behind the roster, for citing as a source."""
    return _pub_media_url(docid, "E", alllangs=True)


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


def normalise_pub_ts(value):
    """'2026-09-19 14:49:52' -> '2026-09-19T14:49:52Z'.

    pub-media quotes its file timestamps without a zone; they are UTC. Checked
    against the CDN itself: the Swedish 240p file reported 14:49:52 here and
    `Last-Modified: Sat, 19 Sep 2026 14:49:50 GMT` over HTTP.
    """
    if not value:
        return None
    return normalise_ts(str(value).strip().replace(" ", "T") + "Z")


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
