#!/usr/bin/env python3
"""Reconstruct a finished Governing Body Update's rollout as a static archive.

The live tracker (scripts/track.py) watches a rollout as it happens and banks
each language's time the moment it first sees it. That is the only way to get
trustworthy times *while* a rollout is in progress -- but it means an update
that finished before the tracker existed has no page at all.

This script builds one anyway, from a timestamp the jw.org APIs expose without
advertising it. Every mediator record carries a `guid` that is a MongoDB
ObjectId, and an ObjectId's first four bytes are the second at which the record
was created:

    datetime.fromtimestamp(int(guid[:8], 16), timezone.utc)

That single field survives both corruptions that make the obvious sources
useless on a finished item:

  * the **bulk firstPublished rewrite**. Once an item is complete the mediator
    stamps every language with the item's own firstPublished. 297 of Update
    #5's 449 languages (66%) report an identical 2026-07-31T13:24:54Z. Every
    one of them still has a distinct guid.

  * **file re-transcoding**, which moves pub-media's modifiedDatetime. 113 of
    Update #5's languages (25%) have been re-transcoded, French three times:
    its files claim 6 August, eight days after it actually went out. The guid
    still says 30 July.

Validated three ways before being trusted. Where firstPublished is *not* the
bulk value it is genuine, and the guid matches it to the second. Where a
language's files have never been replaced the guid sits 10-32 seconds before
the first file write, which is the expected order: the record is created, then
its files are written. And against Update #6 -- which the live tracker watched
in real time -- no guid postdates the tracker's own first sighting, in any of
the languages checked.

WHAT THE GUID IS NOT is a public-availability time. Records are created as each
vernacular is *ingested*, which on a scheduled release runs days ahead of
publication: 11 of Update #5's languages were ingested before English, one of
them 12 hours before. So this script does not pretend the series is "languages
watchable" and does not clamp it to the release. It reports preparation times
as what they are and marks the publication moment on the chart instead, leaving
the reader to see that most of the roster was ready and waiting when the video
went live.

Output is data/report-<docid>.json, in the same schema the live tracker writes,
plus an `archive` block carrying the wording and caveats specific to a
reconstruction. Nothing here touches data/report.json, data/baseline.json or
config.json, so the live tracker is unaffected.

Usage:
    python3 scripts/archive_doc.py --docid 1112024059 \
        --baseline-docid 1112024061 \
        --label "2026 Governing Body Update #5" --short "Update #5" \
        --release 2026-07-31T13:24:54Z
"""

import argparse
import datetime
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jw  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Pause between per-language mediator reads. The roster is fetched in one
# request but each language's guid needs its own, so this is ~450 calls.
FETCH_PAUSE_SECONDS = 0.1

# `progressiveDownloadURL` looks like https://.../a/<hash>/<rev>/o/<file>.mp4,
# where <rev> counts how many times the files have been rewritten. rev=1 means
# pub-media's timestamps are still the originals; anything higher means they
# are not, which is worth stating rather than hiding.
REV_RE = re.compile(r"/a/[0-9a-f]+/(\d+)/o/")


def guid_time(guid):
    """The creation second encoded in an ObjectId's first four bytes."""
    if not guid or len(guid) < 8:
        return None
    try:
        seconds = int(guid[:8], 16)
    except ValueError:
        return None
    # Sanity-bound it. A guid that is not an ObjectId would decode to some
    # absurd year, and a silently absurd date is worse than no date.
    if not 1_400_000_000 < seconds < 2_500_000_000:
        return None
    return jw.normalise_ts(
        datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).isoformat()
    )


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def load(rel, default=None):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write(rel, payload):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("wrote %s" % rel)


def language_index():
    """Reuse the tracker's cached MEPS index; fetch only if it is absent."""
    cached = load("data/languages.json")
    if cached and cached.get("languages"):
        return cached["languages"]
    index = jw.fetch_language_index()
    if len(index) < 500:
        raise SystemExit("refusing to continue: language index looked truncated")
    return index


def fetch_records(docid, codes, cache_path):
    """Per-language mediator records, cached on disk so reruns are free.

    ~450 requests, so a rerun after a wording change should not repeat them.
    The cache is keyed by language code and is pure upstream data.
    """
    cache = {}
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            cache = json.load(fh)
        print("cache: %d language(s) already read" % len(cache))

    todo = [c for c in codes if c not in cache]
    print("reading %d language record(s) from the mediator" % len(todo))
    for n, code in enumerate(todo, 1):
        url = "%s/media-items/%s/docid-%s_1_VIDEO" % (jw.MEDIATOR, code, docid)
        try:
            payload = jw.fetch_json(url, allow_missing=True)
        except RuntimeError as exc:
            cache[code] = {"error": str(exc)[:200]}
            continue
        media = (payload or {}).get("media") or []
        if not media:
            cache[code] = {"error": "no mediator record"}
        else:
            item = media[0]
            files = item.get("files") or []
            stamps = [jw.normalise_ts(f.get("modifiedDatetime")) for f in files]
            stamps = [s for s in stamps if s]
            url0 = (files[0].get("progressiveDownloadURL") if files else "") or ""
            match = REV_RE.search(url0)
            cache[code] = {
                "guid": item.get("guid") or "",
                "guid_at": guid_time(item.get("guid")),
                "first_published": jw.normalise_ts(item.get("firstPublished")),
                "file_min": min(stamps) if stamps else None,
                "file_max": max(stamps) if stamps else None,
                "rev": int(match.group(1)) if match else None,
                "title": (item.get("title") or "").strip(),
                "duration": item.get("durationFormattedMinSec") or "",
            }
        if cache_path and (n % 25 == 0 or n == len(todo)):
            with open(cache_path, "w", encoding="utf-8") as fh:
                json.dump(cache, fh, ensure_ascii=False, sort_keys=True)
            print("  %d/%d" % (n, len(todo)))
        time.sleep(FETCH_PAUSE_SECONDS)

    if cache_path:
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False, sort_keys=True)
    return cache


def build_history(entries, key):
    """Cumulative count keyed on each language's own time.

    Deliberately identical in shape to track.py's build_history, so the same
    renderer draws both. It differs in one way: the live tracker seeds the
    series at the release, because for a rollout the release *is* the start.
    Here preparation begins before publication, so the series starts at the
    first language and the publication moment is drawn as a marker instead.
    """
    stamps = sorted(e[key] for e in entries if e.get(key))
    points, count = [], 0
    for stamp in stamps:
        count += 1
        if points and points[-1]["t"] == stamp:
            points[-1]["count"] = count
        else:
            points.append({"t": stamp, "count": count})
    return points


def build_events(published, key="files_at"):
    """Publishes grouped into UTC hour buckets, oldest first."""
    buckets = {}
    for entry in published:
        stamp = entry.get(key)
        if not stamp:
            continue
        buckets.setdefault(stamp[:13] + ":00:00Z", []).append(entry)
    events, running = [], 0
    for bucket in sorted(buckets):
        langs = sorted(buckets[bucket], key=lambda e: e[key])
        running += len(langs)
        events.append({
            "t": bucket,
            "count_after": running,
            "added": [
                {
                    "code": e["code"],
                    "name": e["name"],
                    "at": e[key],
                    "source": e["files_at_source"],
                    "in_catalog": e["in_catalog"],
                }
                for e in langs
            ],
        })
    return events


def publisher_reach(published, weights):
    """Share of the worldwide publisher audience the finished update reaches.

    Same contract as track.py: only the rounded percentage is returned, never
    the underlying counts, which are confidential.
    """
    if not weights:
        return {}
    publishers = weights.get("publishers") or {}
    aliases = weights.get("aliases") or {}
    total = weights.get("global_publishers") or sum(publishers.values())
    if not total:
        return {}
    reached = sum(
        0 if e["code"] in aliases else publishers.get(e["code"], 0) for e in published
    )
    return {
        "publisher_percent": round(100.0 * reached / total, 1),
        "publisher_percent_ceiling": round(
            100.0 * (weights.get("expected_publishers") or total) / total, 1
        ),
    }


def plural(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


def fmt_day(stamp):
    dt = parse_iso(stamp)
    return dt.strftime("%-d %B %Y") if dt else str(stamp)


def fmt_moment(stamp):
    dt = parse_iso(stamp)
    return dt.strftime("%-d %B %Y, %H:%M UTC") if dt else str(stamp)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--docid", required=True, help="the update to archive")
    ap.add_argument("--baseline-docid", required=True,
                    help="the previous update, whose final roster is the target")
    ap.add_argument("--label", required=True)
    ap.add_argument("--short", required=True)
    ap.add_argument("--baseline-label", default=None)
    ap.add_argument("--baseline-short", default=None)
    ap.add_argument("--release", default=None,
                    help="the scheduled jw.org publication moment, ISO-8601. "
                         "Drawn as a marker on the chart; never used to clamp.")
    ap.add_argument("--marker", action="append", default=[], metavar="TIME=LABEL",
                    help="an extra dotted marker on the chart, e.g. "
                         "--marker '2026-07-28T12:24:43Z=Translation materials sent'. "
                         "Repeatable. Markers earlier than the first language "
                         "stretch the chart back to reach them.")
    ap.add_argument("--category", default="StudioNewsReports")
    ap.add_argument("--cache", default=None,
                    help="path for the per-language read cache "
                         "(default data/.archive-cache-<docid>.json)")
    ap.add_argument("--out", default=None,
                    help="default data/report-<docid>.json")
    args = ap.parse_args()

    docid = args.docid
    release = jw.normalise_ts(args.release) if args.release else None

    extra_markers = []
    for raw in args.marker:
        if "=" not in raw:
            raise SystemExit(
                "--marker needs TIME=LABEL, got %r" % raw
            )
        when, _, label = raw.partition("=")
        stamp = jw.normalise_ts(when.strip())
        if not parse_iso(stamp):
            raise SystemExit("--marker time %r is not a valid ISO-8601 instant" % when)
        if not label.strip():
            raise SystemExit("--marker %r has no label" % raw)
        extra_markers.append({"t": stamp, "label": label.strip()})
    cache_path = args.cache or os.path.join(ROOT, "data", ".archive-cache-%s.json" % docid)
    out_rel = args.out or "data/report-%s.json" % docid
    now = jw.utcnow()

    # ---- the two rosters, one request each -------------------------------- #
    files_codes, pub_meta = jw.pub_media_languages(docid)
    listed, english_item = jw.available_languages(docid)
    print("pub-media %d language(s) | catalogue %d" % (len(files_codes), len(listed)))
    if len(files_codes) < 100:
        raise SystemExit(
            "refusing to write an archive: pub-media returned only %d languages "
            "for docid %s, which is too few for a finished update"
            % (len(files_codes), docid)
        )

    # ---- the baseline: the previous update's final roster ------------------ #
    baseline_codes, baseline_item = jw.available_languages(args.baseline_docid)
    print("baseline %s: %d language(s)" % (args.baseline_docid, len(baseline_codes)))

    index = language_index()
    weights = load("data/weights.json")

    files_set, listed_set = set(files_codes), set(listed)
    codes = sorted(files_set | listed_set)
    records = fetch_records(docid, codes, cache_path)

    failed = sorted(c for c in codes if records.get(c, {}).get("error"))
    no_time = sorted(
        c for c in codes
        if not records.get(c, {}).get("error") and not records[c].get("guid_at")
    )
    if failed:
        print("warning: %d language(s) had no readable record: %s"
              % (len(failed), ", ".join(failed[:12])))
    if no_time:
        print("warning: %d language(s) had an unusable guid: %s"
              % (len(no_time), ", ".join(no_time[:12])))

    # ---- one entry per language ------------------------------------------- #
    published = []
    for code in codes:
        rec = records.get(code) or {}
        meta = jw.describe(code, index)
        if meta["name"] == code and code in pub_meta:
            fallback = pub_meta[code]
            meta.update(
                name=fallback.get("name") or code,
                vernacular=fallback.get("name") or code,
                locale=fallback.get("locale") or meta["locale"],
                script=fallback.get("script") or meta["script"],
                direction=fallback.get("direction") or meta["direction"],
            )

        at = rec.get("guid_at")
        source = "record"
        note = None
        if not at:
            # No usable guid: fall back to the file timestamps and say so. This
            # is a genuinely weaker value -- it moves on re-transcode -- so it
            # gets its own provenance class rather than being passed off as one.
            at = rec.get("file_min")
            source = "file_estimated" if at else None
            note = (
                "no usable record identifier for this language; estimated from "
                "pub-media's file timestamps, which record the last time a file "
                "was written rather than when it was first published"
            ) if at else "no time could be recovered for this language"

        rev = rec.get("rev")
        meta.update(
            title=rec.get("title") or (pub_meta.get(code, {}) or {}).get("name") or meta["name"],
            url=jw.watch_url(code, docid),
            in_files=code in files_set,
            in_catalog=code in listed_set,
            files_at=at,
            files_at_source=source,
            files_at_note=note,
            # The catalogue cannot be separated from the primary signal
            # retroactively: both resolve from the same record. Carried so the
            # table is complete, and flagged in the archive notices.
            catalog_at=at if code in listed_set else None,
            catalog_at_source=source if code in listed_set else None,
            catalog_at_note=note,
            published_at=at,
            published_at_source=source,
            published_at_note=note,
            api_published_at=rec.get("first_published"),
            file_modified=rec.get("file_min"),
            file_modified_latest=rec.get("file_max"),
            file_revision=rev,
            retranscoded=bool(rev and rev > 1),
            record_guid=rec.get("guid"),
            beyond_baseline=code not in baseline_codes,
        )
        published.append(meta)

    published.sort(key=lambda e: (e["files_at"] or "", e["name"].lower()))

    with_files = [e for e in published if e["in_files"]]
    catalogued = [e for e in published if e["in_catalog"]]
    timed = [e for e in published if e["files_at"]]

    pending_codes = sorted(set(baseline_codes) - files_set)
    pending = sorted(
        (jw.describe(c, index) for c in pending_codes), key=lambda e: e["name"].lower()
    )

    history = build_history(timed, "files_at")
    events = build_events(timed)
    target = len(baseline_codes)

    # ---- the shape of the rollout, for the page's own prose --------------- #
    stamps = sorted(e["files_at"] for e in timed)
    first_at, last_at = (stamps[0], stamps[-1]) if stamps else (None, None)
    ready_at_release = sum(1 for s in stamps if release and s < release)
    after_release = len(stamps) - ready_at_release
    retranscoded = sum(1 for e in published if e["retranscoded"])
    beyond = [e for e in with_files if e["beyond_baseline"]]
    beyond_baseline = len(beyond)
    beyond_names = sorted(e["name"] for e in beyond)
    bulk_rewritten = sum(
        1 for e in published
        if e["api_published_at"]
        and e["api_published_at"] == jw.normalise_ts(
            (english_item or {}).get("firstPublished")
        )
    )
    span_days = None
    if first_at and last_at:
        span_days = round(
            (parse_iso(last_at) - parse_iso(first_at)).total_seconds() / 86400.0, 1
        )
    tail_days = None
    if release and last_at:
        tail_days = round(
            (parse_iso(last_at) - parse_iso(release)).total_seconds() / 86400.0, 1
        )
    lead_days = None
    if release and first_at:
        lead_days = round(
            (parse_iso(release) - parse_iso(first_at)).total_seconds() / 86400.0, 1
        )

    stats = {
        "published_count": len(with_files),
        "catalog_count": len(catalogued),
        "catalog_lag": max(len(with_files) - len(catalogued), 0),
        "target": target,
        "pending_count": len(pending),
        "percent": round(100.0 * len(with_files) / target, 1) if target else None,
        "catalog_percent": round(100.0 * len(catalogued) / target, 1) if target else None,
        "ready_at_release": ready_at_release,
        "after_release": after_release,
        "retranscoded_count": retranscoded,
        "bulk_rewritten_count": bulk_rewritten,
        "rollout_span_days": span_days,
        "tail_days": tail_days,
        "lead_days": lead_days,
    }
    stats.update(publisher_reach(with_files, weights))

    duration = (english_item or {}).get("durationFormattedMinSec") or ""

    markers = list(extra_markers)
    if release:
        markers.append({"t": release, "label": "Published on jw.org"})
    markers.sort(key=lambda m: m["t"])


    # ---- wording that only makes sense for a reconstruction --------------- #
    meta_bits = []
    if release:
        meta_bits.append("Published on jw.org " + fmt_moment(release))
    if span_days is not None:
        meta_bits.append("rollout complete in %s days" % span_days)
    if duration:
        meta_bits.append(duration)

    tiles = []
    if release:
        tiles.append({
            "label": "Ready when it published",
            "value": str(ready_at_release),
        })
        tiles.append({
            "label": "Arrived after publication",
            "value": str(after_release),
        })
    if tail_days is not None:
        tiles.append({"label": "Days to the last language", "value": str(tail_days)})
    tiles.append({
        "label": "Never received it" if pending else "Left behind",
        "value": str(len(pending)),
    })
    if stats.get("publisher_percent") is not None:
        tiles.append({
            "label": "Percentage of publishers reached",
            "value": "%s%%" % stats["publisher_percent"],
        })

    notices = [
        "<strong>This page is a reconstruction, not a recording.</strong> "
        "The tracker was not running when " + args.short + " rolled out, so "
        "every time here was recovered afterwards from jw.org rather than "
        "observed as it happened. What that means in practice is set out below."
    ]
    notices.append(
        "<strong>The times are preparation times, not the moments each language "
        "became watchable.</strong> Each one is when jw.org created that "
        "language&rsquo;s record, which is when the vernacular version was taken "
        "in — and materials are normally prepared days ahead of a scheduled "
        "release. " + (
            "%d of the %d languages were already in hand when the video published, "
            "so they became watchable together at the moment marked on the chart, "
            "not on the dates shown against them. The remaining %d arrived "
            "afterwards, and for those the two are close." % (
                ready_at_release, len(timed), after_release
            ) if release and ready_at_release else
            "Where a language arrived after publication the two are close."
        )
    )
    notices.append(
        "<strong>The times are recovered from a record identifier, because "
        "jw.org&rsquo;s own publish times no longer survive.</strong> "
        "Once an update is finished the media API replaces each language&rsquo;s "
        "<code>firstPublished</code> with one shared value" + (
            " — %d of the %d languages here report an identical time" % (
                bulk_rewritten, len(published)
            ) if bulk_rewritten else ""
        ) + ", and re-encoding moves the file timestamps" + (
            " — %d language%s had files rewritten after release" % (
                retranscoded, "" if retranscoded == 1 else "s"
            ) if retranscoded else ""
        ) + ". Each record&rsquo;s identifier encodes the second it was created, "
        "which neither of those rewrites touches, and it matches jw.org&rsquo;s "
        "own publish time exactly wherever that time is still intact."
    )
    notices.append(
        "<strong>There is only one series, where a live page has two.</strong> "
        "The tracker normally shows the media files running ahead of the "
        "catalogue listing, because it watches them diverge. Both signals "
        "finished complete here and both now resolve from the same record, so "
        "the gap between them cannot be recovered."
    )

    report = {
        "generated": now,
        "last_checked": now,
        "update": {
            "docid": docid,
            "label": args.label,
            "short": args.short,
            "release": release,
            "release_source": "confirmed" if release else None,
            "duration": duration,
            "url": jw.english_video_page(docid, args.category),
            "api_first_published": jw.normalise_ts(
                (english_item or {}).get("firstPublished")
            ),
        },
        "baseline": {
            "docid": args.baseline_docid,
            "label": args.baseline_label or ("the previous update"),
            "short": args.baseline_short or "the previous update",
            "count": target,
            "sign_language_count": sum(
                1 for c in baseline_codes if index.get(c, {}).get("sign")
            ),
            "url": jw.english_video_page(args.baseline_docid, args.category),
        },
        "source": {
            "api": "%s/media-items/E/docid-%s_1_VIDEO" % (jw.MEDIATOR, docid),
            "files_api": jw.download_api(docid),
            "page": jw.english_video_page(docid, args.category),
        },
        "stats": stats,
        "published": published,
        "pending": pending,
        "removed": [],
        "history": history,
        "catalog_history": [],
        "events": events,
        "counts": {
            "record_times": sum(1 for e in published if e["files_at_source"] == "record"),
            "file_times": sum(
                1 for e in published if e["files_at_source"] == "file_estimated"
            ),
            "no_time": sum(1 for e in published if not e["files_at"]),
            "retranscoded": retranscoded,
            "bulk_rewritten": bulk_rewritten,
            "sign_languages": sum(1 for e in with_files if e.get("sign")),
        },
        "integrity": {
            "drift_count": 0,
            "drifted": [],
            "file_drift_count": 0,
            "file_drifted": [],
            "awaiting_catalogue": 0,
            "api_reset_detected": False,
            "api_reset_detected_at": None,
            "bulk_rewrite_suspected": False,
        },
        "archive": {
            "is_archive": True,
            "built": now,
            "series_label": "Languages prepared",
            "meta": meta_bits,
            "release_marker": ({
                "t": release,
                "label": "Published on jw.org",
            } if release else None),
            "markers": markers,
            "tiles": tiles,
            "hero_of": "of the %d %s reached" % (
                target, args.baseline_short or "the previous update"
            ),
            "target_label": args.baseline_short or "previous",
            "pending_note": (
                "Languages that received %s but never received %s."
                % (args.baseline_short or "the previous update", args.short)
            ),
            # More useful than restating the headline: which way the roster
            # moved against the update before it.
            "hero_caption": (
                "Finished. %s went beyond the %s roster%s; %s."
                % (
                    plural(beyond_baseline, "language", "languages"),
                    args.baseline_short or "previous",
                    " (" + ", ".join(beyond_names[:6]) + ")" if beyond_names else "",
                    ("%s that had %s never received this one (%s)" % (
                        plural(len(pending), "language", "languages"),
                        args.baseline_short or "the previous update",
                        ", ".join(p["name"] for p in pending[:6]),
                    )) if pending else "none were left behind",
                )
            ),
            "method_note": (
                "Reconstructed from jw.org after the fact. Each language&rsquo;s time "
                "is the second jw.org created its media record, recovered from the "
                "record&rsquo;s own identifier because the media API overwrites its "
                "publish times once an update is complete. The language list itself "
                "is read live from the same media service the live tracker uses."
            ),
            "checked_note": (
                "%s finished rolling out on %s. This page is a fixed archive built "
                "on %s — it is not polled and does not change."
                % (args.short, fmt_day(last_at) if last_at else "an unknown date",
                   fmt_day(now))
            ),
            "notices": notices,
            # The second line is only true if some language actually fell
            # back to its file timestamps. Usually none does, and a legend
            # entry for a mark that appears nowhere on the page is just noise.
            "legend": [
                "¶ — the second jw.org created the language’s record, "
                "which is when the vernacular was taken in rather than when it "
                "became watchable."
            ] + ([
                "§ — approximate: no record identifier was usable, so the "
                "time comes from the video file itself."
            ] if any(e["files_at_source"] == "file_estimated" for e in published) else []),
        },
    }

    write(out_rel, report)
    print()
    print("%s: %d language(s) of %d (%.1f%%), %d pending"
          % (args.short, len(with_files), target, stats["percent"] or 0, len(pending)))
    if release:
        print("  %d ready at publication, %d arrived after" % (ready_at_release, after_release))
    print("  preparation %s -> %s (%s days)" % (first_at, last_at, span_days))
    print("  %d bulk-rewritten firstPublished recovered, %d re-transcoded"
          % (bulk_rewritten, retranscoded))


if __name__ == "__main__":
    main()
