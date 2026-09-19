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

### availableLanguages is cached per edge, so discovery is not left to it

The listing is served from a cache that varies by location and lags. Observed
directly: the same request returned 9 languages from a GitHub runner and 10
from a local machine 30 seconds apart, and Kannada disappeared from the listing
for a while and then came back. Amharic's own record was fetchable at
10:26 UTC while the listing still omitted it.

So the listing is a fast hint, not the source of truth. Every run also probes a
rotating slice of **60 still-pending languages directly** (`SWEEP_SIZE` in
`scripts/track.py`), which is authoritative. At 60 per run, twice an hour, the ~440
pending languages are covered about every 3.5 hours, at roughly two requests a
minute.
Anything the sweep finds is added with its real publish time and tagged
`"discovered_by": "sweep"`.

The effect is that a lagging listing costs discovery *latency* only, bounded by
the sweep cycle — never a missed language, and never a wrong timestamp, since
times come from each language's own record.

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

## Percentage of publishers reached

The language count treats every language alike: English and Abaknon each move
it by one. The fifth tile under **Languages available now** answers the other
question — how much of the worldwide audience can already watch the video —
by weighting each language by the number of publishers who read it.

The weights come from a confidential language/publisher spreadsheet that is
**deliberately not in this repository**. `scripts/build_weights.py` reads it
once per revision and writes `data/weights.json`:

```sh
python3 scripts/build_weights.py ~/Downloads/Languages.xlsx
```

`data/weights.json` holds publisher counts, so it is gitignored, as are
`*.xlsx`. The script itself contains no data and is committed. `track.py` picks
the file up if it exists and skips the figure silently if it does not — so a
runner without the spreadsheet still produces a valid report, just without that
tile.

Three details decide what the number means:

- **Matching.** Languages join by MEPS code, which is the spreadsheet's
  *Language Symbol* column. 445 of the 449 expected codes match a row directly.
- **Script variants carry no weight of their own.** The four that don't match —
  Kazakh (Arabic), Chinese Cantonese (Simplified), Romany (Macedonia) and
  Serbian (Roman) — are second scripts for populations the spreadsheet counts
  once, under `AZ`, `CHC`, `RMC` and `SB`, all four of which are themselves in
  the expected set. Crediting the variant separately would count those
  publishers twice, so the `ALIASES` map in `build_weights.py` pins them to
  zero. Three further languages (Arabic (Lebanon), Banda (Mid-Southern),
  Portuguese (Angola)) match a row that genuinely reads zero.
- **The denominator is worldwide, not the expected set.** The percentage is
  measured against every publisher in the spreadsheet, so it is the literal
  share of the audience reached. The expected 449 languages cover 99.2% of
  that total, which is why the figure tops out just short of 100 — the
  ceiling is reported as `publisher_percent_ceiling` in `stats`.

Because the largest languages publish first, this figure runs far ahead of the
language count: 10 of 449 languages was already most of the audience.

Only the rounded percentage reaches `data/report.json` — never a count, and
never a per-language weight. One decimal place is a privacy decision as much as
a display one: 0.1% is coarser than every language below roughly 9,300
publishers, so differencing successive reports against the languages that
appeared between them cannot recover an individual language's count. The
largest languages are inferable from the aggregate, but their figures are
already published in the annual report.

## Layout

| Path | Purpose |
|---|---|
| `index.html`, `assets/` | The site. Static, dependency-free, reads `data/report.json`. |
| `scripts/track.py` | The half-hourly check. Writes `data/report.json`. |
| `scripts/jw.py` | Shared media-API fetching and parsing. |
| `scripts/verify_times.py` | Daily: re-reads every publish time and reports drift. Never overwrites. |
| `scripts/build_baseline.py` | One-off: snapshots the baseline update and the language index. |
| `scripts/build_weights.py` | One-off per spreadsheet revision: turns publisher counts into `data/weights.json`. |
| `config.json` | Which video is tracked, its release time, and the baseline. |
| `data/overrides.json` | Confirmed publish times. Hand-edited. |
| `data/report.json` | Current state **and** accumulated history — the site's only data source. |
| `data/baseline.json` | The 449 languages Update #5 reached. |
| `data/languages.json` | Cached MEPS language metadata. |
| `data/weights.json` | Publisher counts per language. **Confidential, gitignored**, optional. |

## Automation

Everything runs on **GitHub-hosted Actions runners** (`ubuntu-latest`, a fresh
ephemeral VM per run) — nothing runs on a local machine, so the report keeps
updating with no laptop involved.

`.github/workflows/track.yml` runs every 30 minutes, at **:17 and :47 UTC**;
`.github/workflows/verify.yml` runs daily at **03:41 UTC**. GitHub cron is
always UTC and has no timezone setting. Both share one concurrency group, since
both write `data/report.json`.

Scheduled workflows only run from the **default branch**, and a workflow's
schedule is read from the copy of the file on that branch.

Each run commits when the language list
changes, when a resolved publish time changes (so editing `overrides.json` takes
effect), or when the record is more than `min_commit_interval_hours` (1) old —
so the history stays readable instead of gaining 24 no-op commits a day.

If the API returns no languages, the script **exits non-zero without writing**
rather than recording a false drop to zero, so a change in the API shows up as a
failed workflow run instead of corrupted data.

Two things worth knowing:

- GitHub disables scheduled workflows in repositories with no activity for 60
  days. Commits made by the bot don't reset that timer, so if the rollout runs
  long, push any commit (or hit **Run workflow**) to keep the schedule alive.
- Scheduled runs are queued, not exact, and GitHub sheds them under load: this
  repository's schedule delivered nothing for its first three slots after being
  registered, despite correct configuration and no platform incident. Running
  twice an hour limits what one dropped slot costs. A missed slot never loses
  data -- publish times come from each language's own record, so whenever a run
  lands it reconciles the full current state.

## Local trigger (stopgap while GitHub's scheduler is broken)

GitHub has never delivered a scheduled event to this repository. A minimal
probe workflow — `*/10 * * * *`, one `echo`, `state: active` — never fired
either, so the fault is repository/account level, not in these workflow files.
Everything inspectable was ruled out: correct cron on the default branch,
workflows active, re-registered twice (cron edit and disable/enable), 0 of
2,000 Actions minutes used, no spending limit, no Actions-tab banner, account
created in 2020, and no platform incident.

So a launchd agent on the local Mac dispatches the workflow every 30 minutes
instead:

```sh
tools/install-local-trigger.sh     # install and load
tools/uninstall-local-trigger.sh   # remove when no longer needed
tail -f ~/Library/Logs/gb-update-tracker.log
```

The Mac only *triggers* the run — the checking, committing and pushing stay in
GitHub Actions, which works fine via `push` and `workflow_dispatch`. That avoids
a second, divergent local code path.

Two consequences worth knowing:

- **It only runs while the Mac is awake and logged in.** `StartInterval` is used
  rather than `StartCalendarInterval`, so a sleeping Mac coalesces to one run on
  wake instead of replaying every missed slot. A gap costs freshness only —
  publish times come from each language's own record, so the next run reconciles
  the full state no matter how long the gap.
- **`schedule-probe.yml` is deliberately left in place.** It is the cleanest
  signal that GitHub's scheduling has recovered: the moment it starts appearing
  in the Actions tab, the local agent can be uninstalled. Delete the probe then
  too. Duplicate runs in the meantime are harmless — the tracker is idempotent
  and throttled.

## Running it manually



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
