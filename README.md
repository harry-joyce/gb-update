# Language availability tracker — 2026 Governing Body Update #6

A self-updating report of how many languages [2026 Governing Body Update
#6](https://www.jw.org/en/news/region/global/2026-Governing-Body-Update-6/) has
been published in on jw.org, and how that number has grown since release.

**Site:** https://harry-joyce.github.io/gb-update/

## How availability is determined

jw.org emits one `<link rel="alternate" hreflang="…">` tag on the English
article for every language that article has actually been published in. That
tag set *is* the availability list, and it carries each language's translated
title and URL, so the report can link straight to every version.

Language names, native names, scripts and text direction come from
`https://www.jw.org/en/languages/`, cached in `data/languages.json` and
refreshed weekly.

### What the dates mean

`first_seen` is when **this tracker** first observed a language — not an
official publication time. jw.org shows only the update's release date on the
article, identical in every language, so there is no per-language publication
timestamp to read. Languages that were already present on the tracker's first
run are credited to the release date and flagged `"first_seen_exact": false`.

For the same reason the chart cannot show Update #5's historical rollout curve;
it shows Update #5's **final total** (193 languages) as a target line instead.

## Layout

| Path | Purpose |
|---|---|
| `index.html`, `assets/` | The site. Static, dependency-free, reads `data/report.json`. |
| `scripts/track.py` | The hourly check. Writes `data/report.json`. |
| `scripts/jw.py` | Shared jw.org fetching and parsing. |
| `scripts/build_baseline.py` | One-off: snapshots the baseline update and the language index. |
| `config.json` | Which update is tracked, and which is the baseline. |
| `data/report.json` | Current state **and** accumulated history — the site's only data source. |
| `data/baseline.json` | The 193 languages Update #5 reached. |
| `data/languages.json` | Cached jw.org language metadata. |

## Automation

`.github/workflows/track.yml` runs hourly. It commits only when the language
list changes or the record is more than `min_commit_interval_hours` (6) old, so
the history stays readable instead of gaining 24 no-op commits a day.

If jw.org returns a page with no `rel="alternate"` links, the script **exits
non-zero without writing** rather than recording a false drop to zero — so a
markup change or a blocked fetch shows up as a failed workflow run instead of
corrupted data.

Two things worth knowing:

- GitHub disables scheduled workflows in repositories with no activity for 60
  days. Commits made by the bot don't reset that timer, so if the rollout runs
  long, push any commit (or hit **Run workflow**) to keep the schedule alive.
- Scheduled runs are queued, not exact; an hourly job often lands a few minutes
  late.

## Running it locally

```sh
python3 scripts/track.py          # check jw.org and update data/report.json
python3 scripts/build_baseline.py # re-snapshot the baseline + language index
python3 -m http.server 8000       # then open http://localhost:8000
```

No third-party packages are required. (On macOS python.org builds without a CA
bundle, `certifi` is used automatically if it is installed.)

## Tracking a different update

Edit `config.json` — point `tracked` at the new update and `baseline` at the one
before it — then run `python3 scripts/build_baseline.py` and delete
`data/report.json` so history restarts cleanly.
