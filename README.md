# Language availability tracker — 2026 Governing Body Update #6

A self-updating report of how many languages the [2026 Governing Body Update #6
video](https://www.jw.org/en/library/videos/#en/mediaitems/StudioNewsReports/docid-1112024060_1_VIDEO)
has been published in, and how that number has grown since release.

**Site:** https://harry-joyce.github.io/gb-update/

Released **18 September 2026, 14:00 UTC**. Target: the **449 languages**
(including 72 sign languages) that Update #5 ultimately reached.

## How availability is determined

The JW media ("mediator") API, not the web page:

```
https://b.jw-cdn.org/apis/mediator/v1/media-items/E/docid-1112024060_1_VIDEO
```

The English record's `availableLanguages` array lists every language the video
is currently published in — the whole list in one request. A request for an
individual language returns that language's own `firstPublished` timestamp and
translated title, so the timeline reflects **actual publication times** rather
than when the tracker happened to look. Each language's detail is fetched once,
when it first appears.

Language names, native names, scripts and text direction come from
`https://www.jw.org/en/languages/`, keyed by `langcode` — which *is* the MEPS
code the media API uses (English `E`, German `X`, Basque `BQ`). All 449 baseline
codes resolve.

### Publish times and `data/overrides.json`

`firstPublished` records when a file entered the CDN, which can precede public
availability: English reports `2026-09-18T11:39:09Z` but was actually published
at **14:00 UTC**. So confirmed times live in `data/overrides.json`, keyed by MEPS
code, and take precedence:

```json
{ "times": { "E": "2026-09-18T14:00:00Z" } }
```

The site marks each time with its provenance — unmarked for a confirmed time,
`†` for an API time, `‡` if no publish time was available and the tracker's own
first sighting had to be used. Add entries as confirmed times become known;
remove one to fall back to the API value.

### Why Update #5 has no rollout curve

The media API reports a single bulk `firstPublished` for every language of a
finished item — all 449 of Update #5's languages report
`2026-07-31T13:24:54`. Only its final total is meaningful, so it appears as a
target line rather than a comparison curve.

### Per-language links

Links go through `jw.org/finder?lank=…&wtlocale=<MEPS>`. Every language
localises its URL segments (German `/bibliothek/videos/`, Basque
`/liburutegia/bideoak/`), so a hand-built `/<locale>/library/videos/` path 404s
for everything except English.

## Layout

| Path | Purpose |
|---|---|
| `index.html`, `assets/` | The site. Static, dependency-free, reads `data/report.json`. |
| `scripts/track.py` | The hourly check. Writes `data/report.json`. |
| `scripts/jw.py` | Shared media-API fetching and parsing. |
| `scripts/build_baseline.py` | One-off: snapshots the baseline update and the language index. |
| `config.json` | Which video is tracked, its release time, and the baseline. |
| `data/overrides.json` | Confirmed publish times. Hand-edited. |
| `data/report.json` | Current state **and** accumulated history — the site's only data source. |
| `data/baseline.json` | The 449 languages Update #5 reached. |
| `data/languages.json` | Cached MEPS language metadata. |

## Automation

`.github/workflows/track.yml` runs hourly. It commits when the language list
changes, when a resolved publish time changes (so editing `overrides.json` takes
effect), or when the record is more than `min_commit_interval_hours` (6) old —
so the history stays readable instead of gaining 24 no-op commits a day.

If the API returns no languages, the script **exits non-zero without writing**
rather than recording a false drop to zero, so a change in the API shows up as a
failed workflow run instead of corrupted data.

Two things worth knowing:

- GitHub disables scheduled workflows in repositories with no activity for 60
  days. Commits made by the bot don't reset that timer, so if the rollout runs
  long, push any commit (or hit **Run workflow**) to keep the schedule alive.
- Scheduled runs are queued, not exact; an hourly job often lands a few minutes
  late.

## Running it locally

```sh
python3 scripts/track.py          # check the API and update data/report.json
python3 scripts/build_baseline.py # re-snapshot the baseline + language index
python3 -m http.server 8000       # then open http://localhost:8000
```

No third-party packages are required. (On macOS python.org builds without a CA
bundle, `certifi` is used automatically if it is installed.)

## Tracking a different update

Edit `config.json` — point `tracked` at the new video's `docid` and `release`
time, and `baseline` at the previous update — then run
`python3 scripts/build_baseline.py`, clear `data/overrides.json`, and delete
`data/report.json` so history restarts cleanly.
