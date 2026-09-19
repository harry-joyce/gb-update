#!/usr/bin/env python3
"""Check which languages the tracked Governing Body Update video is published in.

Reads the JW media API: one request returns the video's full language list, and
one request per *newly seen* language returns that language's own publish time
and translated title. Results accumulate in data/report.json, the site's only
data source.

Writes a `should_commit` flag to $GITHUB_OUTPUT so CI records a commit only
when something actually changed (or the report has gone stale).
"""

import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jw  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_MAX_AGE_DAYS = 7
# Languages probed directly per run, and the pause between those probes. At 60
# per hour the ~440 pending languages are fully covered roughly every 7 hours,
# at about one request a minute.
SWEEP_SIZE = 60
SWEEP_PAUSE_SECONDS = 0.1


def load(rel, default=None):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def language_index():
    """Cached MEPS language metadata, refreshed at most weekly."""
    cached = load("data/languages.json")
    fetched = parse_iso((cached or {}).get("fetched"))
    fresh = fetched and (
        datetime.datetime.now(datetime.timezone.utc) - fetched
    ) < datetime.timedelta(days=INDEX_MAX_AGE_DAYS)
    if cached and fresh:
        return cached["languages"], False
    try:
        index = jw.fetch_language_index()
    except RuntimeError as exc:
        if cached:
            print("warning: language index refresh failed (%s); using cache" % exc)
            return cached["languages"], False
        raise
    if len(index) < 500 and cached:
        print("warning: language index looked truncated; using cache")
        return cached["languages"], False
    return index, True


def main():
    config = load("config.json")
    tracked = config["tracked"]
    docid = tracked["docid"]
    category = tracked.get("category", "StudioNewsReports")
    baseline = load("data/baseline.json") or {}
    overrides = (load("data/overrides.json") or {}).get("times") or {}
    previous = load("data/report.json")
    now = jw.utcnow()

    listed, english_item = jw.available_languages(docid)
    if not listed:
        raise SystemExit(
            "refusing to write report: the media API returned no languages for "
            "docid %s. The item or API may have changed." % docid
        )

    index, refreshed = language_index()

    # Each language's detail is fetched exactly once, and the API timestamp it
    # returned is then PINNED forever. That is deliberate: the media API
    # rewrites firstPublished to a single bulk value once an item is finished
    # (all 449 of Update #5's languages report 2026-07-31T13:24:54), which
    # would otherwise flatten this update's whole rollout history on the day it
    # completes. Pinning means such a rewrite cannot reach data already banked.
    baseline_codes = set(baseline.get("codes") or [])
    known = {e["code"]: e for e in (previous or {}).get("published", [])}
    archive = {e["code"]: e for e in (previous or {}).get("removed", [])}

    release = tracked.get("release") or jw.normalise_ts(english_item.get("firstPublished"))

    # The English record is refetched every run as a side effect of listing the
    # languages, so comparing it against its pinned value detects a bulk
    # rewrite for free -- without which a pin would protect old data silently
    # while new languages kept trusting a poisoned API.
    prior_integrity = (previous or {}).get("integrity") or {}
    english_api_now = jw.normalise_ts(english_item.get("firstPublished"))
    english_api_pinned = (
        (prior_integrity.get("english_api_first_published") or {}).get("pinned")
        or english_api_now
    )
    api_reset = bool(
        english_api_pinned and english_api_now and english_api_now != english_api_pinned
    )
    reset_detected_at = prior_integrity.get("api_reset_detected_at")
    if api_reset and not reset_detected_at:
        reset_detected_at = now

    # availableLanguages is treated as *discovery only*, never as proof of
    # removal: Kannada vanished from it while its own media item stayed live,
    # so trusting it to un-publish would delete a real language and its banked
    # publish time. A language that drops out of the listing is verified
    # directly, and only a missing per-language item counts as removal.
    candidates = set(listed) | set(known)
    published, removed_entries, lagging = [], [], []

    def build_entry(code, item, prior, in_listing):
        """Assemble one published-language record."""
        meta = jw.describe(code, index)
        if prior and prior.get("api_published_at") is not None:
            api_ts = prior["api_published_at"]
            title = prior.get("title") or meta["name"]
            first_observed = prior.get("first_observed") or now
        else:
            api_ts = jw.normalise_ts((item or {}).get("firstPublished"))
            title = ((item or {}).get("title") or "").strip() or meta["name"]
            first_observed = (prior or {}).get("first_observed") or now

        published_at, source, note = resolve_time(
            code, overrides, api_ts, first_observed, release, api_reset, prior
        )
        meta.update(
            title=title,
            url=jw.watch_url(code, docid),
            published_at=published_at,
            published_at_source=source,
            published_at_note=note,
            api_published_at=api_ts,
            first_observed=first_observed,
            listed_by_api=in_listing,
            beyond_baseline=bool(baseline.get("codes")) and code not in set(baseline["codes"]),
        )
        return meta

    for code in sorted(candidates):
        prior = known.get(code) or archive.get(code)
        in_listing = code in listed
        item = None

        if not in_listing:
            item = jw.media_item(docid, code)
            if item is None:
                if prior:
                    removed_entries.append(
                        dict(prior, removed_at=now, removed_reason="no media item")
                    )
                continue
            lagging.append(code)
        elif not (prior and prior.get("api_published_at") is not None):
            item = jw.media_item(docid, code)

        published.append(build_entry(code, item, prior, in_listing))

    current = {p["code"] for p in published}
    added = sorted(c for c in current if c not in known)
    removed = sorted(e["code"] for e in removed_entries)

    # Keep anything previously archived that has not come back.
    for code, entry in archive.items():
        if code not in current and code not in removed:
            removed_entries.append(entry)

    # availableLanguages is served from a cache that varies by edge: the same
    # request can report 9 languages from one location and 10 from another,
    # and CI runners were seen lagging behind a local machine by minutes. So
    # the listing alone would let a published language stay invisible. Each run
    # therefore probes a rotating slice of the still-pending languages
    # directly, which is authoritative -- Amharic's own record was fetchable
    # while the listing omitted it. The whole pending set is covered every
    # SWEEP_SIZE-th of a cycle rather than in one expensive burst.
    pending_codes = sorted(baseline_codes - current)
    sweep_prior = (previous or {}).get("sweep") or {}
    offset = int(sweep_prior.get("offset") or 0)
    swept, discovered = [], []
    if pending_codes:
        if offset >= len(pending_codes):
            offset = 0
        slice_codes = pending_codes[offset:offset + SWEEP_SIZE]
        if len(slice_codes) < SWEEP_SIZE:
            slice_codes += pending_codes[:SWEEP_SIZE - len(slice_codes)]
        for code in slice_codes:
            swept.append(code)
            try:
                item = jw.media_item(docid, code)
            except RuntimeError as exc:
                print("warning: sweep could not check %s (%s)" % (code, exc))
                continue
            if item is not None:
                entry = build_entry(code, item, archive.get(code), False)
                entry["discovered_by"] = "sweep"
                published.append(entry)
                discovered.append(code)
            time.sleep(SWEEP_PAUSE_SECONDS)
        offset = (offset + SWEEP_SIZE) % len(pending_codes)

    if discovered:
        current = {p["code"] for p in published}
        added = sorted(c for c in current if c not in known)
        pending_codes = sorted(baseline_codes - current)

    published.sort(key=lambda p: (p["published_at"] or "", p["name"].lower()))

    pending = sorted(
        (jw.describe(c, index) for c in baseline_codes - current),
        key=lambda p: p["name"].lower(),
    )

    history = build_history(published, release)
    events = build_events(published)
    target = baseline.get("count") or len(baseline_codes) or None

    report = {
        "generated": now,
        "last_checked": now,
        "source": {
            "page": jw.english_video_page(docid, category),
            "api": "%s/media-items/E/docid-%s_1_VIDEO" % (jw.MEDIATOR, docid),
        },
        "update": {
            "label": tracked["label"],
            "short": tracked["short"],
            "docid": docid,
            "url": jw.english_video_page(docid, category),
            "release": release,
            "release_source": "confirmed" if tracked.get("release") else "api",
            "api_first_published": jw.normalise_ts(english_item.get("firstPublished")),
            "duration": english_item.get("durationFormattedMinSec"),
        },
        "baseline": {
            "label": baseline.get("label"),
            "short": baseline.get("short"),
            "url": baseline.get("url"),
            "count": target,
            "sign_language_count": baseline.get("sign_language_count"),
        },
        "sweep": {
            "offset": offset,
            "size": SWEEP_SIZE,
            "last_checked_count": len(swept),
            "pending_total": len(pending_codes),
            "discovered": discovered,
        },
        "integrity": {
            "api_reset_detected": api_reset,
            "listing_lag": sorted(lagging),
            "listing_count": len(listed),
            "api_reset_detected_at": reset_detected_at,
            "english_api_first_published": {
                "pinned": english_api_pinned,
                "latest": english_api_now,
            },
            "last_full_verification": prior_integrity.get("last_full_verification"),
            "drift_count": prior_integrity.get("drift_count"),
            "drifted": prior_integrity.get("drifted") or [],
        },
        "counts": {
            "confirmed_times": sum(1 for p in published if p["published_at_source"] == "confirmed"),
            "api_times": sum(1 for p in published if p["published_at_source"] == "api"),
            "clamped_times": sum(1 for p in published if p["published_at_source"] == "api_clamped"),
            "observed_times": sum(1 for p in published if p["published_at_source"] == "observed"),
            "sign_languages": sum(1 for p in published if p["sign"]),
        },
        "stats": build_stats(len(current), target, release, published),
        "published": published,
        "removed": sorted(removed_entries, key=lambda e: e.get("removed_at") or ""),
        "pending": pending,
        "history": history,
        "events": events,
    }

    if refreshed:
        write("data/languages.json", {"fetched": now, "count": len(index), "languages": index})
    write("data/report.json", report)

    should_commit = bool(added or removed) or previous is None or refreshed
    if not should_commit:
        # Any change to a resolved publish time (e.g. a new override) counts too.
        old_times = {e["code"]: e.get("published_at") for e in (previous or {}).get("published", [])}
        new_times = {p["code"]: p["published_at"] for p in published}
        should_commit = (
            sorted(prior_integrity.get("listing_lag") or []) != sorted(lagging)
        ) or old_times != new_times or (
            api_reset and not prior_integrity.get("api_reset_detected")
        )
    if not should_commit:
        last = parse_iso((previous or {}).get("last_checked"))
        max_age = datetime.timedelta(hours=config.get("min_commit_interval_hours", 6))
        should_commit = not last or (
            datetime.datetime.now(datetime.timezone.utc) - last
        ) >= max_age

    summary = "%d languages" % len(current)
    if target:
        summary += " of %d (%.1f%%)" % (target, 100.0 * len(current) / target)
    if added:
        names = ", ".join(jw.describe(c, index)["name"] for c in added)
        summary += " | +%d: %s" % (len(added), names)
    if removed:
        summary += " | -%d: %s" % (len(removed), ", ".join(removed))
    if discovered:
        print(
            "sweep found %d language(s) the API listing had omitted: %s"
            % (len(discovered), ", ".join(discovered))
        )
    if lagging:
        print(
            "note: %d language(s) missing from availableLanguages but still live, "
            "kept published: %s" % (len(lagging), ", ".join(sorted(lagging)))
        )
    if api_reset:
        print(
            "WARNING: the media API rewrote firstPublished for English "
            "(pinned %s, now %s). Banked times are kept; new languages will fall "
            "back to first-sighting times." % (english_api_pinned, english_api_now)
        )
    print(summary)
    print("should_commit=%s" % ("true" if should_commit else "false"))

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("should_commit=%s\n" % ("true" if should_commit else "false"))
            fh.write("count=%d\n" % len(current))
            fh.write("added=%d\n" % len(added))
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("### %s\n\n%s\n" % (tracked["label"], summary))


def resolve_time(code, overrides, api_ts, first_observed, release, api_reset, prior):
    """Decide a language's publish time, and say where it came from.

    Precedence: a hand-confirmed time, then the API's own timestamp, then the
    moment the tracker first saw the language. A time already resolved from a
    trustworthy API reading keeps its value even after a reset is detected.
    """
    override = overrides.get(code)
    if override:
        return jw.normalise_ts(override), "confirmed", None

    # A value banked before any reset stays put.
    if prior and prior.get("published_at_source") in ("api", "api_clamped"):
        return prior["published_at"], prior["published_at_source"], prior.get("published_at_note")

    if not api_ts:
        return first_observed, "observed", "the API reported no publish time"

    if api_reset:
        return (
            first_observed,
            "observed",
            "the API's timestamps were rewritten, so its value is not trustworthy; "
            "this is when the tracker first saw the language",
        )

    # firstPublished records CDN arrival, which can precede public release.
    if release and api_ts < release:
        return (
            release,
            "api_clamped",
            "the API reported %s, before the release; clamped to the release time" % api_ts,
        )

    return api_ts, "api", None


def build_history(published, release):
    """Cumulative count keyed on real publish times, not on when we polled."""
    stamps = sorted(p["published_at"] for p in published if p["published_at"])
    points = []
    start = min([release] + stamps[:1]) if stamps else release
    if start:
        points.append({"t": start, "count": 0})
    count = 0
    for stamp in stamps:
        count += 1
        if points and points[-1]["t"] == stamp:
            points[-1]["count"] = count
        else:
            points.append({"t": stamp, "count": count})
    return points


def build_events(published):
    """Publishes grouped into UTC hour buckets, oldest first."""
    buckets = {}
    for p in published:
        stamp = p["published_at"]
        if not stamp:
            continue
        bucket = stamp[:13] + ":00:00Z"
        buckets.setdefault(bucket, []).append(p)
    events, running = [], 0
    for bucket in sorted(buckets):
        langs = sorted(buckets[bucket], key=lambda p: p["published_at"])
        running += len(langs)
        events.append(
            {
                "t": bucket,
                "count_after": running,
                "added": [
                    {
                        "code": p["code"],
                        "name": p["name"],
                        "at": p["published_at"],
                        "source": p["published_at_source"],
                    }
                    for p in langs
                ],
            }
        )
    return events


def build_stats(count, target, release, published):
    now = datetime.datetime.now(datetime.timezone.utc)
    stats = {
        "published_count": count,
        "target": target,
        "pending_count": max(target - count, 0) if target else None,
        "percent": round(100.0 * count / target, 1) if target else None,
    }

    released = parse_iso(release)
    elapsed = None
    if released:
        elapsed = (now - released).total_seconds() / 86400.0
        stats["days_since_release"] = round(max(elapsed, 0), 2)

    stamps = [parse_iso(p["published_at"]) for p in published]
    stamps = sorted(st for st in stamps if st)

    for label, hours in (("added_1h", 1), ("added_4h", 4), ("added_24h", 24)):
        cutoff = now - datetime.timedelta(hours=hours)
        stats[label] = sum(1 for st in stamps if st >= cutoff)

    return stats


def write(rel, payload):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    main()
