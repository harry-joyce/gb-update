#!/usr/bin/env python3
"""Turn the confidential language/publisher spreadsheet into audience weights.

Each language in the spreadsheet carries a publisher count. Weighting the
rollout by those counts answers a different question from the language count:
not "how many languages", but "how much of the worldwide audience can already
watch this".

Run this once per spreadsheet revision:

    python3 scripts/build_weights.py ~/Downloads/Languages.xlsx

The output, data/weights.json, holds publisher counts and is therefore
CONFIDENTIAL. It is gitignored, and nothing derived from it beyond a rounded
aggregate percentage reaches data/report.json. This script itself contains no
data and is safe to commit.

Reads .xlsx with the standard library only — an .xlsx is a zip of XML — so no
dependency has to be installed on whatever machine holds the spreadsheet.
"""

import datetime
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DEFAULT_XLSX = os.path.expanduser("~/Downloads/Languages.xlsx")

# Script variants the media API publishes separately but the spreadsheet counts
# once, under the counterpart listed here. Serbian (Roman) and Serbian
# (Cyrillic) are read by one population of publishers; crediting the variant
# with its own weight would count those publishers twice. Each variant
# therefore carries zero *additional* audience.
ALIASES = {
    "AZA": "AZ",    # Kazakh (Arabic)                 -> Kazakh
    "CNS": "CHC",   # Chinese Cantonese (Simplified)  -> Chinese Cantonese (Traditional)
    "RM": "RMC",    # Romany (Macedonia)              -> Romany (Macedonia) Cyrillic
    "SBO": "SB",    # Serbian (Roman)                 -> Serbian (Cyrillic)
}

COLUMNS = ("name", "code", "branch", "type", "status", "jworg", "wol", "publishers")


def column_number(ref):
    letters = re.match(r"([A-Z]+)", ref or "A1").group(1)
    number = 0
    for char in letters:
        number = number * 26 + ord(char) - 64
    return number


def read_rows(path):
    """Every row of the first worksheet, as lists of strings."""
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(NS + "si"):
                shared.append("".join(t.text or "" for t in item.iter(NS + "t")))
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    rows = []
    for row in sheet.iter(NS + "row"):
        cells = {}
        for cell in row.findall(NS + "c"):
            kind = cell.get("t")
            value = cell.find(NS + "v")
            inline = cell.find(NS + "is")
            if kind == "s" and value is not None:
                text = shared[int(value.text)]
            elif kind == "inlineStr" and inline is not None:
                text = "".join(t.text or "" for t in inline.iter(NS + "t"))
            elif value is not None:
                text = value.text
            else:
                text = ""
            cells[column_number(cell.get("r"))] = (text or "").strip()
        if cells:
            rows.append([cells.get(i, "") for i in range(1, len(COLUMNS) + 1)])
    return rows


def parse(path):
    rows = read_rows(path)
    if not rows:
        raise SystemExit("error: %s has no rows" % path)

    header = [h.lower() for h in rows[0]]
    if "language symbol" not in header or "publishers" not in header:
        raise SystemExit(
            "error: unexpected columns in %s\n  got: %s" % (path, rows[0])
        )

    languages = {}
    for row in rows[1:]:
        record = dict(zip(COLUMNS, row))
        code = record["code"]
        if not code:
            continue
        try:
            count = int(float(record["publishers"] or 0))
        except ValueError:
            count = 0
        if code in languages:
            raise SystemExit("error: duplicate language symbol %r in %s" % (code, path))
        languages[code] = {"name": record["name"], "publishers": count}
    return languages


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GB_LANGUAGES_XLSX", DEFAULT_XLSX)
    if not os.path.exists(path):
        raise SystemExit(
            "error: spreadsheet not found: %s\n"
            "usage: python3 scripts/build_weights.py [path/to/Languages.xlsx]" % path
        )

    languages = parse(path)
    publishers = {code: entry["publishers"] for code, entry in languages.items()}

    # The expected set — the languages the previous update ultimately reached —
    # is what the site measures progress against.
    with open(os.path.join(ROOT, "data/baseline.json"), encoding="utf-8") as fh:
        expected = list(json.load(fh)["codes"])

    def weight(code):
        return 0 if code in ALIASES else publishers.get(code, 0)

    unknown = sorted(c for c in expected if c not in publishers and c not in ALIASES)
    zero = sorted(c for c in expected if weight(c) == 0 and c not in ALIASES)

    payload = {
        "generated": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "source": os.path.basename(path),
        "confidential": "Publisher counts. Never commit this file.",
        "language_count": len(publishers),
        "global_publishers": sum(publishers.values()),
        "expected_publishers": sum(weight(c) for c in expected),
        "expected_matched": sum(1 for c in expected if c in publishers or c in ALIASES),
        "expected_unmatched": unknown,
        "expected_zero": zero,
        "aliases": ALIASES,
        "publishers": publishers,
    }

    out = os.path.join(ROOT, "data/weights.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("wrote data/weights.json  (confidential, gitignored)")
    print("  languages in spreadsheet : %d" % payload["language_count"])
    print("  worldwide publishers     : %d" % payload["global_publishers"])
    print(
        "  expected-set publishers  : %d  (%.2f%% of worldwide, across %d/%d languages)"
        % (
            payload["expected_publishers"],
            100.0 * payload["expected_publishers"] / payload["global_publishers"],
            payload["expected_matched"],
            len(expected),
        )
    )
    if unknown:
        print("  no spreadsheet row       : %s" % ", ".join(unknown))
    if zero:
        print("  zero publishers          : %s" % ", ".join(zero))


if __name__ == "__main__":
    main()
