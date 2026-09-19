#!/usr/bin/env python3
"""Check which languages the tracked Governing Body Update video is available in.

Two signals are read, because jw.org publishes a video to two places at
different times and the gap between them is large:

  * pub-media (PRIMARY) -- every language with a media file on the CDN. One
    request returns the whole roster, so discovery costs a single call no
    matter how many languages exist. This is the number that answers "can a
    publisher watch it", and it is what the playback/download selector on the
    news article offers.

  * the media catalogue (SECOND SERIES) -- the mediator's availableLanguages,
    which is what the /library/videos/ page lists. It trails pub-media, so it
    is recorded alongside rather than instead: the lag between the two lines is
    itself worth seeing.

Per-language detail is fetched once, when a language first appears, and then
pinned. Results accumulate in data/report.json, the site's only data source.

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

# Languages probed against the *catalogue* per run, and the pause between
# probes. This is no longer discovery -- pub-media discovers everything in one
# request -- so the probe only exists to beat the availableLanguages listing's
# edge cache, and its domain is just the languages that have files but are not
# yet listed. That set is small (the lag is usually minutes), so the whole of
# it is normally covered every run rather than rotated through.
CATALOG_PROBE_SIZE = 40
PROBE_PAUSE_SECONDS = 0.1


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
    override_block = load("data/overrides.json") or {}
    overrides = override_block.get("times") or {}
    catalog_overrides = override_block.get("catalog_times") or {}
    # Confidential publisher counts, built by scripts/build_weights.py from the
    # language spreadsheet. Absent on any machine without it; the site simply
    # omits the audience figure in that case.
    weights = load("data/weights.json")
    previous = load("data/report.json")
    now = jw.utcnow()

    # ---- the primary signal: which languages have files -------------- #
    files_codes, pub_meta = [], {}
    pub_media_failed = None
    try:
        files_codes, pub_meta = jw.pub_media_languages(docid)
    except (RuntimeError, ValueError) as exc:
        pub_media_failed = str(exc)
        print("warning: pub-media roster unavailable (%s)" % exc)

    # ---- the second series: which languages the catalogue lists ------ #
    listed, english_item = [], None
    catalog_failed = None
    try:
        listed, english_item = jw.available_languages(docid)
    except (RuntimeError, ValueError) as exc:
        catalog_failed = str(exc)
        print("warning: media catalogue unavailable (%s)" % exc)

    if not files_codes and not listed:
        raise SystemExit(
            "refusing to write report: neither pub-media nor the media catalogue "
            "returned any language for docid %s. Both APIs may have changed." % docid
        )
    if pub_media_failed:
        # Without the roster the catalogue is all there is; say so in the report
        # rather than letting the headline count silently drop by half.
        print("note: falling back to the catalogue listing for this run")

    index, refreshed = language_index()

    # Each language's detail is fetched exactly once, and the timestamps it
    # returned are then PINNED forever. That is deliberate: the media API
    # rewrites firstPublished to a single bulk value once an item is finished
    # (all 449 of Update #5's languages report 2026-07-31T13:24:54), and
    # pub-media's modifiedDatetime moves every time a file is re-encoded.
    # Pinning means neither rewrite can reach data already banked.
    baseline_codes = set(baseline.get("codes") or [])
    known = {e["code"]: e for e in (previous or {}).get("published", [])}
    archive = {e["code"]: e for e in (previous or {}).get("removed", [])}

    release = tracked.get("release") or jw.normalise_ts(
        (english_item or {}).get("firstPublished")
    )

    # The English catalogue record is refetched every run as a side effect of
    # listing the languages, so comparing it against its pinned value detects a
    # bulk rewrite for free -- without which a pin would protect old data
    # silently while new languages kept trusting a poisoned API.
    prior_integrity = (previous or {}).get("integrity") or {}
    english_api_now = jw.normalise_ts((english_item or {}).get("firstPublished"))
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

    files_set = set(files_codes)
    listed_set = set(listed)

    # Neither roster is treated as authoritative for *removal*. Kannada once
    # vanished from availableLanguages while its own media item stayed live, so
    # trusting a roster to un-publish would delete a real language and its
    # banked time. A language that drops out is verified directly against both
    # APIs, and only losing its files *and* its catalogue item counts.
    candidates = files_set | listed_set | set(known)

    # The catalogue probe: languages with files that the listing does not
    # mention yet. Bounded per run, rotating if it ever exceeds the cap.
    unlisted = sorted((files_set | set(known)) - listed_set)
    probe_prior = (previous or {}).get("catalog_probe") or {}
    offset = int(probe_prior.get("offset") or 0)
    probe_set = set()
    if unlisted and not catalog_failed:
        if offset >= len(unlisted):
            offset = 0
        slice_codes = unlisted[offset:offset + CATALOG_PROBE_SIZE]
        if len(slice_codes) < CATALOG_PROBE_SIZE:
            slice_codes += unlisted[:CATALOG_PROBE_SIZE - len(slice_codes)]
        probe_set = set(slice_codes)
        offset = (offset + CATALOG_PROBE_SIZE) % len(unlisted)

    published, removed_entries, lagging, newly_catalogued = [], [], [], []

    def build_entry(code, pub, item, prior, in_files, in_catalog):
        """Assemble one language's record across both signals."""
        meta = jw.describe(code, index)
        if meta["name"] == code and code in pub_meta:
            # Unknown to jw.org's language index; pub-media states its own
            # name, locale and script, so use those rather than showing a code.
            fallback = pub_meta[code]
            meta.update(
                name=fallback.get("name") or code,
                vernacular=fallback.get("name") or code,
                locale=fallback.get("locale") or meta["locale"],
                script=fallback.get("script") or meta["script"],
                direction=fallback.get("direction") or meta["direction"],
            )

        prior = prior or {}
        first_observed = prior.get("first_observed") or now

        # Pinned upstream values, read once and never refetched.
        if prior.get("api_published_at") is not None:
            api_ts = prior["api_published_at"]
        else:
            api_ts = jw.normalise_ts((item or {}).get("firstPublished"))
        if prior.get("file_modified") is not None:
            file_ts = prior["file_modified"]
        else:
            file_ts = (pub or {}).get("modified")

        # The catalogue's title is authoritative; pub-media's is the fallback,
        # and is a real localised title for every language except English,
        # whose pub-media entry is the generic "Video".
        title = (
            prior.get("title")
            or ((item or {}).get("title") or "").strip()
            or ((pub or {}).get("title") or "").strip()
            or meta["name"]
        )

        files_at, files_src, files_note = resolve_file_time(
            code, overrides, api_ts, file_ts, first_observed, release, api_reset, prior
        )
        catalog_at, catalog_src, catalog_note = (None, None, None)
        if in_catalog:
            catalog_at, catalog_src, catalog_note = resolve_catalog_time(
                code, catalog_overrides or overrides, api_ts,
                prior.get("catalog_observed") or now, release, api_reset, prior
            )

        meta.update(
            title=title,
            url=jw.watch_url(code, docid),
            in_files=in_files,
            in_catalog=in_catalog,
            files_at=files_at,
            files_at_source=files_src,
            files_at_note=files_note,
            catalog_at=catalog_at,
            catalog_at_source=catalog_src,
            catalog_at_note=catalog_note,
            # `published_at` stays the primary series, so every consumer that
            # asks when a language became available keeps getting an answer.
            published_at=files_at,
            published_at_source=files_src,
            published_at_note=files_note,
            api_published_at=api_ts,
            file_modified=file_ts,
            file_formats=(pub or {}).get("formats") or prior.get("file_formats") or [],
            first_observed=first_observed,
            catalog_observed=(
                prior.get("catalog_observed") or (now if in_catalog else None)
            ),
            listed_by_api=code in listed_set,
            discovered_by=prior.get("discovered_by") or (
                "pub-media" if code in files_set else "catalogue"
            ),
            beyond_baseline=bool(baseline_codes) and code not in baseline_codes,
        )
        return meta

    for code in sorted(candidates):
        prior = known.get(code) or archive.get(code)
        in_files = code in files_set
        in_catalog = code in listed_set
        pub = item = None

        # --- files: the primary signal --- #
        if in_files:
            if not (prior and prior.get("file_modified") is not None):
                pub = jw.pub_media_item(docid, code)
                # A roster entry whose files cannot be fetched is not yet real.
                if pub is None and not prior:
                    continue
        elif prior and prior.get("in_files"):
            # Dropped out of the roster: verify directly before believing it.
            pub = jw.pub_media_item(docid, code)
            in_files = pub is not None

        # --- catalogue: the second series --- #
        if in_catalog:
            if not (prior and prior.get("api_published_at") is not None):
                item = jw.media_item(docid, code)
                if item is None:
                    in_catalog = False
        elif code in probe_set or (prior and prior.get("in_catalog")):
            item = jw.media_item(docid, code)
            in_catalog = item is not None
            if in_catalog:
                if prior and prior.get("in_catalog"):
                    # Live record, absent from the listing: the Kannada case.
                    lagging.append(code)
                else:
                    newly_catalogued.append(code)
            time.sleep(PROBE_PAUSE_SECONDS)

        if not in_files and not in_catalog:
            if prior:
                removed_entries.append(
                    dict(prior, removed_at=now, removed_reason="no files and no catalogue item")
                )
            continue

        published.append(build_entry(code, pub, item, prior, in_files, in_catalog))

    current = {p["code"] for p in published}
    added = sorted(c for c in current if c not in known)
    removed = sorted(e["code"] for e in removed_entries)

    # Keep anything previously archived that has not come back.
    for code, entry in archive.items():
        if code not in current and code not in removed:
            removed_entries.append(entry)

    published.sort(key=lambda p: (p["files_at"] or "", p["name"].lower()))

    catalogued = [p for p in published if p["in_catalog"]]
    with_files = [p for p in published if p["in_files"]]
    pending_codes = sorted(baseline_codes - {p["code"] for p in with_files})
    pending = sorted(
        (jw.describe(c, index) for c in pending_codes),
        key=lambda p: p["name"].lower(),
    )

    history = build_history(with_files, "files_at", release)
    catalog_history = build_history(catalogued, "catalog_at", release)
    events = build_events(with_files)
    target = baseline.get("count") or len(baseline_codes) or None
    stats = build_stats(len(with_files), len(catalogued), target, release, with_files, weights)

    report = {
        "generated": now,
        "last_checked": now,
        "source": {
            "page": jw.english_video_page(docid, category),
            "files_api": jw.download_api(docid),
            "api": "%s/media-items/E/docid-%s_1_VIDEO" % (jw.MEDIATOR, docid),
        },
        "update": {
            "label": tracked["label"],
            "short": tracked["short"],
            "docid": docid,
            "url": jw.english_video_page(docid, category),
            "release": release,
            "release_source": "confirmed" if tracked.get("release") else "api",
            "api_first_published": jw.normalise_ts((english_item or {}).get("firstPublished")),
            "duration": (english_item or {}).get("durationFormattedMinSec"),
        },
        "baseline": {
            "label": baseline.get("label"),
            "short": baseline.get("short"),
            "url": baseline.get("url"),
            "count": target,
            "sign_language_count": baseline.get("sign_language_count"),
        },
        "catalog_probe": {
            "offset": offset,
            "size": CATALOG_PROBE_SIZE,
            "last_checked_count": len(probe_set),
            "unlisted_total": len(unlisted),
            "newly_catalogued": sorted(newly_catalogued),
        },
        "integrity": {
            "api_reset_detected": api_reset,
            "listing_lag": sorted(lagging),
            "listing_count": len(listed),
            "files_count": len(files_codes),
            "pub_media_unavailable": pub_media_failed,
            "catalogue_unavailable": catalog_failed,
            "api_reset_detected_at": reset_detected_at,
            "english_api_first_published": {
                "pinned": english_api_pinned,
                "latest": english_api_now,
            },
            "last_full_verification": prior_integrity.get("last_full_verification"),
            "drift_count": prior_integrity.get("drift_count"),
            "drifted": prior_integrity.get("drifted") or [],
            "file_drift_count": prior_integrity.get("file_drift_count"),
        },
        "counts": {
            "confirmed_times": sum(1 for p in with_files if p["files_at_source"] == "confirmed"),
            "api_times": sum(1 for p in with_files if p["files_at_source"] == "api"),
            "clamped_times": sum(1 for p in with_files if p["files_at_source"] == "api_clamped"),
            "file_times": sum(1 for p in with_files if p["files_at_source"] == "file_estimated"),
            "observed_times": sum(1 for p in with_files if p["files_at_source"] == "observed"),
            "sign_languages": sum(1 for p in with_files if p["sign"]),
            "catalogued": len(catalogued),
            "awaiting_catalogue": len(with_files) - len(catalogued),
        },
        "stats": stats,
        "published": published,
        "removed": sorted(removed_entries, key=lambda e: e.get("removed_at") or ""),
        "pending": pending,
        "history": history,
        "catalog_history": catalog_history,
        "events": events,
    }

    if refreshed:
        write("data/languages.json", {"fetched": now, "count": len(index), "languages": index})
    write("data/report.json", report)

    should_commit = bool(added or removed or newly_catalogued) or previous is None or refreshed
    if not should_commit:
        # Any change to a resolved time (e.g. a new override) counts too.
        old_times = {
            e["code"]: (e.get("published_at"), e.get("catalog_at"))
            for e in (previous or {}).get("published", [])
        }
        new_times = {p["code"]: (p["files_at"], p["catalog_at"]) for p in published}
        prev_stats = (previous or {}).get("stats") or {}
        should_commit = (
            sorted(prior_integrity.get("listing_lag") or []) != sorted(lagging)
        ) or old_times != new_times or (
            api_reset and not prior_integrity.get("api_reset_detected")
        ) or (
            stats.get("catalog_count") != prev_stats.get("catalog_count")
        ) or (
            # The audience figure moves without any language changing: weights
            # arriving for the first time, or a rebuilt spreadsheet. Without
            # this the new value sits in an uncommitted file until something
            # else happens to be worth a commit.
            stats.get("publisher_percent") != prev_stats.get("publisher_percent")
        )
    if not should_commit:
        last = parse_iso((previous or {}).get("last_checked"))
        max_age = datetime.timedelta(hours=config.get("min_commit_interval_hours", 6))
        should_commit = not last or (
            datetime.datetime.now(datetime.timezone.utc) - last
        ) >= max_age

    summary = "%d languages" % len(with_files)
    if target:
        summary += " of %d (%.1f%%)" % (target, 100.0 * len(with_files) / target)
    summary += " | %d in the catalogue" % len(catalogued)
    if added:
        names = ", ".join(jw.describe(c, index)["name"] for c in added)
        summary += " | +%d: %s" % (len(added), names)
    if removed:
        summary += " | -%d: %s" % (len(removed), ", ".join(removed))
    if newly_catalogued:
        print(
            "catalogue caught up on %d language(s): %s"
            % (len(newly_catalogued), ", ".join(sorted(newly_catalogued)))
        )
    if lagging:
        print(
            "note: %d language(s) missing from availableLanguages but still live, "
            "kept catalogued: %s" % (len(lagging), ", ".join(sorted(lagging)))
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
            fh.write("count=%d\n" % len(with_files))
            fh.write("catalog_count=%d\n" % len(catalogued))
            fh.write("added=%d\n" % len(added))
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("### %s\n\n%s\n" % (tracked["label"], summary))


def resolve_file_time(code, overrides, api_ts, file_ts, first_observed, release,
                      api_reset, prior):
    """Decide when a language's video became available, and say where that came from.

    Precedence: a hand-confirmed time; then the catalogue's own firstPublished,
    which records the file's arrival on the CDN and is the earliest trustworthy
    upstream value; then an estimate from pub-media's file timestamps; then the
    moment the tracker first saw the language.

    The pub-media estimate needs clamping in both directions, because
    modifiedDatetime is a *last written* time, not a first published one: it
    moves whenever a file is re-encoded and replaced. English is the worked
    example -- released at 14:00, its files report 22:46 the same evening, 8
    hours late. So the estimate is confined to the window between the release
    and the moment the tracker first saw the language, which makes it never
    worse than the first-sighting fallback it replaces, and usually much
    sharper.
    """
    override = overrides.get(code)
    if override:
        return jw.normalise_ts(override), "confirmed", None

    # A value banked from a trustworthy reading stays put.
    if prior and prior.get("files_at_source") in ("api", "api_clamped", "file_estimated"):
        return (
            prior.get("files_at") or prior.get("published_at"),
            prior["files_at_source"],
            prior.get("files_at_note") or prior.get("published_at_note"),
        )
    # Reports written before this file carried a single `published_at`, taken
    # from the catalogue. Those are exactly the values this series wants.
    if prior and prior.get("files_at_source") is None and prior.get("published_at_source") in (
        "api", "api_clamped"
    ):
        return prior["published_at"], prior["published_at_source"], prior.get("published_at_note")

    if api_ts and not api_reset:
        if release and api_ts < release:
            return (
                release,
                "api_clamped",
                "the catalogue reported %s, before the release; clamped to the "
                "release time" % api_ts,
            )
        return api_ts, "api", None

    if file_ts:
        lower = max(release or file_ts, file_ts)
        estimate = min(lower, first_observed) if first_observed else lower
        if release and estimate < release:
            estimate = release
        note = (
            "estimated from pub-media's file timestamps (%s), which record the "
            "last time a file was written rather than when it was first "
            "published; bounded by the release and by when the tracker first "
            "saw the language" % file_ts
        )
        return estimate, "file_estimated", note

    if api_reset:
        return (
            first_observed,
            "observed",
            "the catalogue's timestamps were rewritten, so its value is not "
            "trustworthy; this is when the tracker first saw the language",
        )
    return first_observed, "observed", "no publish time was available"


def resolve_catalog_time(code, overrides, api_ts, catalog_observed, release,
                         api_reset, prior):
    """Decide when a language entered the media catalogue.

    The mediator states no "catalogued at" field, so the best available value
    is its firstPublished -- pinned, and clamped up to the release for the same
    reason as the primary series. Where that is unusable, the time the tracker
    first saw the language in the catalogue is used instead; with checks every
    30 minutes that is bounded, unlike a rewritten upstream timestamp.
    """
    override = overrides.get(code)
    if override:
        return jw.normalise_ts(override), "confirmed", None

    if prior and prior.get("catalog_at_source") in ("api", "api_clamped"):
        return prior["catalog_at"], prior["catalog_at_source"], prior.get("catalog_at_note")

    if api_ts and not api_reset:
        if release and api_ts < release:
            return (
                release,
                "api_clamped",
                "the catalogue reported %s, before the release; clamped to the "
                "release time" % api_ts,
            )
        return api_ts, "api", None

    return (
        catalog_observed,
        "observed",
        "no usable catalogue timestamp; this is when the tracker first saw the "
        "language listed",
    )


def build_history(entries, key, release):
    """Cumulative count keyed on real times, not on when we polled."""
    stamps = sorted(e[key] for e in entries if e.get(key))
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
        stamp = p["files_at"]
        if not stamp:
            continue
        bucket = stamp[:13] + ":00:00Z"
        buckets.setdefault(bucket, []).append(p)
    events, running = [], 0
    for bucket in sorted(buckets):
        langs = sorted(buckets[bucket], key=lambda p: p["files_at"])
        running += len(langs)
        events.append(
            {
                "t": bucket,
                "count_after": running,
                "added": [
                    {
                        "code": p["code"],
                        "name": p["name"],
                        "at": p["files_at"],
                        "source": p["files_at_source"],
                        "in_catalog": p["in_catalog"],
                    }
                    for p in langs
                ],
            }
        )
    return events


def publisher_reach(published, weights):
    """How much of the worldwide publisher audience the video already reaches.

    The language count treats Dutch and Abaknon alike; this weights each
    language by its publishers, so the figure tracks audience rather than
    breadth. Only the rounded percentage is returned -- the underlying counts
    are confidential and must not reach data/report.json.
    """
    if not weights:
        return {}
    publishers = weights.get("publishers") or {}
    aliases = weights.get("aliases") or {}
    total = weights.get("global_publishers") or sum(publishers.values())
    if not total:
        return {}

    # A script variant's readers are already counted under its counterpart, so
    # it adds no audience of its own.
    reached = sum(
        0 if entry["code"] in aliases else publishers.get(entry["code"], 0)
        for entry in published
    )
    return {
        # One decimal place is deliberate: it is coarser than every language
        # below ~9,300 publishers, so successive reports cannot be differenced
        # to recover an individual language's count.
        "publisher_percent": round(100.0 * reached / total, 1),
        "publisher_percent_ceiling": round(
            100.0 * (weights.get("expected_publishers") or total) / total, 1
        ),
    }


def build_stats(count, catalog_count, target, release, published, weights=None):
    now = datetime.datetime.now(datetime.timezone.utc)
    stats = {
        "published_count": count,
        "catalog_count": catalog_count,
        "catalog_lag": max(count - catalog_count, 0),
        "target": target,
        "pending_count": max(target - count, 0) if target else None,
        "percent": round(100.0 * count / target, 1) if target else None,
        "catalog_percent": round(100.0 * catalog_count / target, 1) if target else None,
    }
    stats.update(publisher_reach(published, weights))

    released = parse_iso(release)
    if released:
        stats["days_since_release"] = round(max((now - released).total_seconds() / 86400.0, 0), 2)

    stamps = sorted(st for st in (parse_iso(p["files_at"]) for p in published) if st)

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
