#!/usr/bin/env python3
"""Re-read every available language's timestamps and report any drift.

The tracker pins each language's upstream timestamps the first time it sees
them, so a later rewrite cannot corrupt banked data. The cost of that safety is
that a rewrite would otherwise go unnoticed for languages already recorded.
This script closes that gap for both signals:

  * the media catalogue's firstPublished, which is rewritten to one bulk value
    once an item is finished (all 449 of Update #5's languages report
    2026-07-31T13:24:54);
  * pub-media's file timestamps, which move every time a file is re-encoded
    and replaced -- English's files already report 22:46 on release day
    against a 14:00 release.

It never changes a resolved time -- it only writes the `integrity` block.
Fixing a genuinely wrong time is a human decision, made by adding an entry to
data/overrides.json.
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

    drifted, file_drifted, missing, uncatalogued, checked = [], [], [], [], 0
    for entry in published:
        code = entry["code"]

        # --- the primary signal: are the files still there, unchanged? --- #
        try:
            pub = jw.pub_media_item(docid, code)
        except RuntimeError as exc:
            print("warning: could not check files for %s (%s)" % (code, exc))
            pub = False  # unknown, not absent
        if pub is None:
            missing.append({"code": code, "name": entry.get("name")})
        elif pub:
            checked += 1
            pinned_file = entry.get("file_modified")
            live_file = pub.get("modified")
            if pinned_file and live_file and live_file != pinned_file:
                file_drifted.append(
                    {
                        "code": code,
                        "name": entry.get("name"),
                        "pinned": pinned_file,
                        "live": live_file,
                        "in_use": entry.get("files_at"),
                        "in_use_source": entry.get("files_at_source"),
                    }
                )

        # --- the second series: only meaningful once catalogued --------- #
        # A language with files but no catalogue entry is the normal state for
        # hours after release, so it is reported as awaiting the catalogue
        # rather than as a missing record.
        if not entry.get("in_catalog"):
            uncatalogued.append({"code": code, "name": entry.get("name")})
            time.sleep(PAUSE_SECONDS)
            continue

        pinned = entry.get("api_published_at")
        try:
            item = jw.media_item(docid, code)
        except RuntimeError as exc:
            print("warning: could not check the catalogue for %s (%s)" % (code, exc))
            time.sleep(PAUSE_SECONDS)
            continue
        if item is None:
            missing.append(
                {"code": code, "name": entry.get("name"), "signal": "catalogue"}
            )
        else:
            live = jw.normalise_ts(item.get("firstPublished"))
            if pinned and live and live != pinned:
                drifted.append(
                    {
                        "code": code,
                        "name": entry.get("name"),
                        "pinned": pinned,
                        "live": live,
                        "in_use": entry.get("catalog_at"),
                        "in_use_source": entry.get("catalog_at_source"),
                    }
                )
        time.sleep(PAUSE_SECONDS)

    # A rewrite hits every language at once, so a near-total drift with one
    # shared new value is the signature of the bulk reset seen on Update #5.
    catalogued = sum(1 for e in published if e.get("in_catalog"))
    distinct_live = {d["live"] for d in drifted}
    bulk = (
        bool(drifted)
        and len(drifted) >= max(3, int(0.8 * max(catalogued, 1)))
        and len(distinct_live) == 1
    )

    integrity = dict(report.get("integrity") or {})
    integrity.update(
        last_full_verification=now,
        verified_count=checked,
        drift_count=len(drifted),
        drifted=drifted,
        file_drift_count=len(file_drifted),
        file_drifted=file_drifted,
        missing_items=missing,
        awaiting_catalogue=len(uncatalogued),
        bulk_rewrite_suspected=bulk,
    )
    report["integrity"] = integrity
    report["generated"] = now

    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print(
        "checked %d language(s): %d catalogue time(s) drifted, %d file time(s) "
        "drifted, %d with no files, %d awaiting the catalogue"
        % (checked, len(drifted), len(file_drifted), len(missing), len(uncatalogued))
    )
    for d in drifted[:20]:
        print("  catalogue %-5s %-22s pinned %s -> live %s (using %s)"
              % (d["code"], d["name"], d["pinned"], d["live"], d["in_use"]))
    for d in file_drifted[:20]:
        print("  files     %-5s %-22s pinned %s -> live %s (using %s)"
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
            fh.write("file_drift=%d\n" % len(file_drifted))
            fh.write("should_commit=true\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Timestamp verification\n\nChecked %d language(s): %d "
                     "catalogue drift, %d file drift, %d with no files.\n"
                     % (checked, len(drifted), len(file_drifted), len(missing)))
            if bulk:
                fh.write("\n**Bulk rewrite suspected** - banked times kept.\n")


if __name__ == "__main__":
    main()
