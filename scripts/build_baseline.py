#!/usr/bin/env python3
"""Snapshot the baseline update's language list and the jw.org language index.

Run this once (or again if the baseline update in config.json changes). The
baseline gives the report a realistic target: the number of languages the
previous Governing Body Update ultimately reached.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jw  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    config = json.load(open(os.path.join(ROOT, "config.json")))
    baseline = config["baseline"]

    page = jw.fetch(baseline["url"])
    alternates = jw.parse_alternates(page)
    if len(alternates) < 50:
        raise SystemExit(
            "refusing to write baseline: only %d languages found, expected ~190"
            % len(alternates)
        )

    index = jw.fetch_language_index()
    if len(index) < 500:
        raise SystemExit("refusing to write language index: only %d entries" % len(index))

    write(
        "data/languages.json",
        {"fetched": jw.utcnow(), "count": len(index), "languages": index},
    )
    write(
        "data/baseline.json",
        {
            "label": baseline["label"],
            "short": baseline["short"],
            "url": baseline["url"],
            "release_date": jw.parse_release_date(page),
            "doc_id": jw.parse_doc_id(page),
            "fetched": jw.utcnow(),
            "count": len(alternates),
            "codes": sorted(alternates),
        },
    )
    print("baseline: %d languages / index: %d languages" % (len(alternates), len(index)))


def write(rel, payload):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("wrote %s" % rel)


if __name__ == "__main__":
    main()
