#!/usr/bin/env python3
"""Re-read every published language's publish time and report any drift.

The hourly tracker pins each language's API timestamp the first time it sees
it, so a later bulk rewrite cannot corrupt banked data. The cost of that safety
is that a rewrite would otherwise go unnoticed for languages already recorded.
This script closes that gap: it refetches every published language, compares
the API's current value against the pinned one, and records the difference.

It never changes a resolved publish time -- it only writes the `integrity`
block. Fixing a genuinely wrong time is a human decision, made by adding an
entry to data/overrides.json.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jw  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "data", "report.json")
PAUSE_SECONDS = 0.15


def main():
    if not os.path.exists(REPORT):
        raise SystemExit("no data/report.json yet -- run scripts/track.py first")

    report = json.load(open(REPORT, encoding="utf-8"))
    config = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    docid = config["tracked"]["docid"]
    published = report.get("published") or []
    now = jw.utcnow()

    drifted, missing, checked = [], [], 0
    for entry in published:
        code = entry["code"]
        pinned = entry.get("api_published_at")
        try:
            item = jw.media_item(docid, code)
        except RuntimeError as exc:
            print("warning: could not check %s (%s)" % (code, exc))
            continue
        checked += 1
        if item is None:
            missing.append({"code": code, "name": entry.get("name")})
            continue
        live = jw.normalise_ts(item.get("firstPublished"))
        if pinned and live and live != pinned:
            drifted.append(
                {
                    "code": code,
                    "name": entry.get("name"),
                    "pinned": pinned,
                    "live": live,
                    "in_use": entry.get("published_at"),
                    "in_use_source": entry.get("published_at_source"),
                }
            )
        time.sleep(PAUSE_SECONDS)

    # A rewrite hits every language at once, so a near-total drift with one
    # shared new value is the signature of the bulk reset seen on Update #5.
    distinct_live = {d["live"] for d in drifted}
    bulk = bool(drifted) and len(drifted) >= max(3, int(0.8 * checked)) and len(distinct_live) == 1

    integrity = dict(report.get("integrity") or {})
    integrity.update(
        last_full_verification=now,
        verified_count=checked,
        drift_count=len(drifted),
        drifted=drifted,
        missing_items=missing,
        bulk_rewrite_suspected=bulk,
    )
    report["integrity"] = integrity
    report["generated"] = now

    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("checked %d language(s): %d drifted, %d with no media item"
          % (checked, len(drifted), len(missing)))
    for d in drifted[:20]:
        print("  %-5s %-22s pinned %s -> live %s (using %s)"
              % (d["code"], d["name"], d["pinned"], d["live"], d["in_use"]))
    if bulk:
        print(
            "BULK REWRITE SUSPECTED: %d languages now share the single value %s. "
            "Banked times are unchanged and remain the record of this rollout."
            % (len(drifted), list(distinct_live)[0])
        )

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("drift=%d\n" % len(drifted))
            fh.write("should_commit=true\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Publish-time verification\n\nChecked %d language(s): "
                     "%d drifted, %d missing.\n" % (checked, len(drifted), len(missing)))
            if bulk:
                fh.write("\n**Bulk rewrite suspected** - banked times kept.\n")


if __name__ == "__main__":
    main()
