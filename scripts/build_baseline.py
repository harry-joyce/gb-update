#!/usr/bin/env python3
"""Snapshot the baseline update's language list and the MEPS language index.

Run once (or again when the baseline in config.json changes). The baseline is
the report's target: how many languages the previous Governing Body Update
video ultimately reached.

Note the baseline deliberately stores only the language *list*, not publish
times. The media API reports a single bulk `firstPublished` for every language
of a completed item (Update #5 shows 2026-07-31T13:24:54 for all 449), so its
historical rollout cannot be reconstructed -- only its final total is usable.
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

    codes, item = jw.available_languages(baseline["docid"])
    if len(codes) < 100:
        raise SystemExit(
            "refusing to write baseline: only %d languages found, expected ~450" % len(codes)
        )

    index = jw.fetch_language_index()
    if len(index) < 500:
        raise SystemExit("refusing to write language index: only %d entries" % len(index))

    unresolved = [c for c in codes if c not in index]
    if unresolved:
        print("warning: %d codes have no metadata: %s" % (len(unresolved), unresolved[:10]))

    signs = sum(1 for c in codes if index.get(c, {}).get("sign"))

    write("data/languages.json", {"fetched": jw.utcnow(), "count": len(index), "languages": index})
    write(
        "data/baseline.json",
        {
            "label": baseline["label"],
            "short": baseline["short"],
            "docid": baseline["docid"],
            "url": jw.english_video_page(
                baseline["docid"], config["tracked"].get("category", "StudioNewsReports")
            ),
            "fetched": jw.utcnow(),
            "count": len(codes),
            "sign_language_count": signs,
            "codes": codes,
        },
    )
    print("baseline: %d languages (%d sign) / index: %d" % (len(codes), signs, len(index)))


def write(rel, payload):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("wrote %s" % rel)


if __name__ == "__main__":
    main()
