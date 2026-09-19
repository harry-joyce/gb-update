#!/usr/bin/env python3
"""Check how many languages the tracked Governing Body Update is available in.

Reads the English article's rel=alternate links -- jw.org publishes one per
language the article actually exists in -- and folds the result into
data/report.json, which is the payload the website renders.

Writes a `should_commit` flag to $GITHUB_OUTPUT so CI only records a commit
when something actually changed (or the report has gone stale).
"""

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jw  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "data", "report.json")
INDEX_MAX_AGE_DAYS = 7

MONTHS = {
    m: i + 1
    for i, m in enumerate(
        "january february march april may june july august september "
        "october november december".split()
    )
}


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
    except ValueError:
        return None


def release_to_iso(text):
    """'SEPTEMBER 18, 2026' -> '2026-09-18'. Returns None if unrecognised."""
    if not text:
        return None
    cleaned = text.replace(",", " ").split()
    month = day = year = None
    for token in cleaned:
        key = token.lower()
        if key in MONTHS:
            month = MONTHS[key]
        elif token.isdigit():
            if len(token) == 4:
                year = int(token)
            elif day is None:
                day = int(token)
    if not (month and day and year):
        return None
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


def language_index():
    """Cached jw.org language metadata, refreshed at most weekly."""
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
    baseline = load("data/baseline.json") or {}
    previous = load("data/report.json")
    now = jw.utcnow()

    page = jw.fetch(tracked["url"])
    alternates = jw.parse_alternates(page)
    if not alternates:
        raise SystemExit(
            "refusing to write report: no rel=alternate links found at %s. The page "
            "markup may have changed, or the fetch was blocked." % tracked["url"]
        )

    index, refreshed = language_index()

    # first_seen is sticky: it records when *we* first observed a language,
    # because jw.org does not expose per-language publish timestamps.
    seen = dict((previous or {}).get("ever_seen") or {})
    current = set(alternates)
    added = sorted(c for c in current if c not in seen)
    removed = sorted(c for c in seen if c not in current)

    # On the very first run we cannot know when the languages already present
    # appeared, only that they predate this tracker -- so credit them to the
    # release date and mark the timestamp inexact.
    seeding = previous is None
    release_raw = jw.parse_release_date(page)
    release_iso = release_to_iso(release_raw)
    stamp = (release_iso + "T00:00:00Z") if (seeding and release_iso) else now
    for code in added:
        seen[code] = {"t": stamp, "exact": not seeding}

    baseline_codes = set(baseline.get("codes") or [])
    target = baseline.get("count") or len(baseline_codes) or None

    published = []
    for code in sorted(current, key=lambda c: (index.get(c, {}).get("name") or c).lower()):
        meta = jw.describe(code, index)
        meta.update(
            title=alternates[code]["title"],
            url=alternates[code]["url"],
            first_seen=seen.get(code, {}).get("t", now),
            first_seen_exact=seen.get(code, {}).get("exact", True),
            beyond_baseline=bool(baseline_codes) and code not in baseline_codes,
        )
        published.append(meta)

    pending = [
        jw.describe(code, index)
        for code in sorted(
            baseline_codes - current, key=lambda c: (index.get(c, {}).get("name") or c).lower()
        )
    ]

    history = list((previous or {}).get("history") or [])
    if not history or history[-1]["count"] != len(current):
        history.append({"t": stamp if seeding else now, "count": len(current)})

    events = list((previous or {}).get("events") or [])
    if added or removed:
        events.append(
            {
                "t": stamp if seeding else now,
                "seed": seeding,
                "count_after": len(current),
                "added": [
                    {"code": c, "name": jw.describe(c, index)["name"]} for c in added
                ],
                "removed": [
                    {"code": c, "name": jw.describe(c, index)["name"]} for c in removed
                ],
            }
        )

    report = {
        "generated": now,
        "last_checked": now,
        "source": tracked["url"],
        "update": {
            "label": jw.parse_title(page) or tracked["label"],
            "short": tracked["short"],
            "url": tracked["url"],
            "doc_id": jw.parse_doc_id(page),
            "release_date_text": release_raw,
            "release_date": release_iso,
        },
        "baseline": {
            "label": baseline.get("label"),
            "short": baseline.get("short"),
            "url": baseline.get("url"),
            "count": target,
        },
        "stats": build_stats(len(current), target, release_iso, history, events),
        "published": published,
        "pending": pending,
        "history": history,
        "events": events,
        "ever_seen": seen,
    }

    if refreshed:
        write("data/languages.json", {"fetched": now, "count": len(index), "languages": index})
    write("data/report.json", report)

    should_commit = bool(added or removed) or previous is None or refreshed
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
        summary += " | +%d: %s" % (len(added), ", ".join(added))
    if removed:
        summary += " | -%d: %s" % (len(removed), ", ".join(removed))
    print(summary)
    print("should_commit=%s" % ("true" if should_commit else "false"))

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("should_commit=%s\n" % ("true" if should_commit else "false"))
            fh.write("count=%d\n" % len(current))
            fh.write("added=%d\n" % len(added))
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write("### %s\n\n%s\n" % (report["update"]["label"], summary))


def build_stats(count, target, release_iso, history, events):
    now = datetime.datetime.now(datetime.timezone.utc)
    stats = {
        "published_count": count,
        "target": target,
        "pending_count": max(target - count, 0) if target else None,
        "percent": round(100.0 * count / target, 1) if target else None,
    }

    # Only quote a pace once we have actually watched a language arrive --
    # dividing the seeded count by elapsed days invents a trend from nothing.
    observed_any = any(not e.get("seed") and e.get("added") for e in events)

    if release_iso:
        released = datetime.datetime.fromisoformat(release_iso + "T00:00:00+00:00")
        elapsed = (now - released).total_seconds() / 86400.0
        stats["days_since_release"] = round(max(elapsed, 0), 2)
        if elapsed >= 0.5 and observed_any:
            stats["per_day_overall"] = round(count / elapsed, 1)

    for label, hours in (("added_24h", 24), ("added_7d", 24 * 7)):
        cutoff = now - datetime.timedelta(hours=hours)
        stats[label] = sum(
            len(e.get("added") or [])
            for e in events
            if not e.get("seed") and (parse_iso(e.get("t")) or now) >= cutoff
        )

    # Rough ETA from the trailing week's rate. Clearly a projection, not a promise.
    remaining = stats.get("pending_count")
    if remaining and stats.get("added_7d"):
        rate = stats["added_7d"] / 7.0
        if rate > 0:
            days = remaining / rate
            if days <= 400:
                stats["projected_days_remaining"] = round(days, 1)
                stats["projected_completion"] = (
                    now + datetime.timedelta(days=days)
                ).date().isoformat()
    return stats


def write(rel, payload):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    main()
