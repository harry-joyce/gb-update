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

### If the API rewrites its timestamps

It already does, on a schedule we can't control: once an item is finished the
media API replaces every language's `firstPublished` with one bulk value — all
449 of Update #5's languages now report `2026-07-31T13:24:54`. If that happened
to Update #6 naively, the whole rollout history would collapse to a single
instant. Four things prevent that:

1. **Pinning.** Each language's API timestamp is read exactly once, when the
   language first appears, and then never refetched. A later rewrite cannot
   reach data already banked. This is the load-bearing protection.
2. **Detection.** The English record is refetched every run anyway (it is what
   lists the languages), so comparing it against its pinned value detects a
   rewrite for free. Without this, pinning would protect old rows silently
   while new languages kept trusting a poisoned API.
3. **Degradation.** Once a rewrite is detected, languages appearing afterwards
   stop trusting the API and fall back to the time the tracker first saw them,
   marked `‡`. The site shows a banner explaining what happened.
4. **Daily full verification.** `scripts/verify_times.py` re-reads every
   published language once a day and records any drift in the `integrity`
   block. It never changes a resolved time — it only reports. If ≥80% of
   languages drift to one shared value, it flags `bulk_rewrite_suspected`.

Correcting a time is always a human decision: add an entry to
`data/overrides.json`, which outranks everything above.

A related guard: an API time *earlier than the release* is clamped up to the
release time and marked `api_clamped`, since a file can sit in the CDN before it
goes public. English demonstrates this — the API says `11:39:09Z`, and the clamp
independently produces the confirmed `14:00Z`.

### availableLanguages is discovery, not proof of removal

The English record's `availableLanguages` array is how new languages are
found, but it is not treated as authoritative for *removal*. Kannada was
observed dropping out of that array while its own media item stayed live, with
its Kannada title and a valid publish time. Trusting the listing would have
deleted a genuinely published language and its banked timestamp.

So a language that disappears from the listing is verified directly, and only a
missing per-language media item counts as removal. Removed languages are moved
to a `removed` archive in `report.json` rather than deleted, and are restored
with their original timestamp if they come back. Languages in this state are
listed in `integrity.listing_lag` and noted on the site.

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

## The chart's view options

Against a 449-language target, early progress is a flat line, so the chart has
two controls:

- **Scale** — *Fit to data* (the default) scales the axis to the visible counts,
  making the rollout's step pattern legible from day one; *Full target* pins the
  axis to 0–449 for progress-against-goal context. The target line is drawn only
  when it falls inside the visible scale.
- **Range** — 6h / 24h / 3d / 7d / All. A narrowed range carries the running
  total into the window rather than restarting at zero, and tick marks switch
  from dates to hours automatically.

Both selections persist in `localStorage`.

## Layout

| Path | Purpose |
|---|---|
| `index.html`, `assets/` | The site. Static, dependency-free, reads `data/report.json`. |
| `scripts/track.py` | The hourly check. Writes `data/report.json`. |
| `scripts/jw.py` | Shared media-API fetching and parsing. |
| `scripts/verify_times.py` | Daily: re-reads every publish time and reports drift. Never overwrites. |
| `scripts/build_baseline.py` | One-off: snapshots the baseline update and the language index. |
| `config.json` | Which video is tracked, its release time, and the baseline. |
| `data/overrides.json` | Confirmed publish times. Hand-edited. |
| `data/report.json` | Current state **and** accumulated history — the site's only data source. |
| `data/baseline.json` | The 449 languages Update #5 reached. |
| `data/languages.json` | Cached MEPS language metadata. |

## Automation

Everything runs on **GitHub-hosted Actions runners** (`ubuntu-latest`, a fresh
ephemeral VM per run) — nothing runs on a local machine, so the report keeps
updating with no laptop involved.

`.github/workflows/track.yml` runs hourly at **:17 UTC**;
`.github/workflows/verify.yml` runs daily at **03:41 UTC**. GitHub cron is
always UTC and has no timezone setting. Both share one concurrency group, since
both write `data/report.json`.

Scheduled workflows only run from the **default branch**, and a workflow's
schedule is read from the copy of the file on that branch.

The hourly job commits when the language list
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
