/* Language availability tracker — renders data/report.json. No dependencies. */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };

  /* ---- state ---------------------------------------------------------- */
  var state = {
    report: null,
    sort: { published: { key: "published_at", dir: -1 }, pending: { key: "name", dir: 1 } },
    chart: { y: "fit", range: "all" },
    activity: { group: "hour" },
    query: { published: "", pending: "" }
  };

  /* ---- theme: light / dark / system, system being the default --------- */
  var THEMES = ["light", "dark", "system"];

  function storedTheme() {
    try {
      var value = localStorage.getItem("theme");
      return THEMES.indexOf(value) === -1 ? "system" : value;
    } catch (e) {
      return "system";
    }
  }

  function applyTheme(choice) {
    if (choice === "system") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", choice);
    }
    var buttons = document.querySelectorAll("[data-theme-choice]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].setAttribute(
        "aria-pressed", String(buttons[i].dataset.themeChoice === choice)
      );
    }
    if (state.report) { drawChart(state.report); }
  }

  (function initTheme() {
    var buttons = document.querySelectorAll("[data-theme-choice]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function (ev) {
        var choice = ev.currentTarget.dataset.themeChoice;
        try {
          if (choice === "system") { localStorage.removeItem("theme"); }
          else { localStorage.setItem("theme", choice); }
        } catch (e) {}
        applyTheme(choice);
      });
    }
    applyTheme(storedTheme());

    // Follow the OS while "system" is selected.
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var onChange = function () {
      if (storedTheme() === "system" && state.report) { drawChart(state.report); }
    };
    if (mq.addEventListener) { mq.addEventListener("change", onChange); }
    else if (mq.addListener) { mq.addListener(onChange); }
  })();

  /* ---- formatting ----------------------------------------------------- */
  function fmtDate(iso) {
    var d = new Date(iso);
    if (isNaN(d)) { return iso || "—"; }
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  }

  function fmtDateTime(iso) {
    var d = new Date(iso);
    if (isNaN(d)) { return iso || "—"; }
    return d.toLocaleString(undefined, {
      day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"
    });
  }

  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function pad(n) { return (n < 10 ? "0" : "") + n; }

  /* Publish times are quoted in UTC, so render them in UTC -- converting to
     the viewer's zone would make them impossible to reconcile with the times
     recorded in overrides.json. */
  function fmtUTC(iso, withYear) {
    var d = new Date(iso);
    if (isNaN(d)) { return iso || "—"; }
    return d.getUTCDate() + " " + MONTHS[d.getUTCMonth()] +
      (withYear ? " " + d.getUTCFullYear() : "") + ", " +
      pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()) + " UTC";
  }

  function fmtUTCDate(iso) {
    var d = new Date(iso);
    if (isNaN(d)) { return iso || "—"; }
    return d.getUTCDate() + " " + MONTHS[d.getUTCMonth()] + " " + d.getUTCFullYear();
  }

  function relative(iso) {
    var d = new Date(iso);
    if (isNaN(d)) { return ""; }
    var secs = (Date.now() - d.getTime()) / 1000;
    if (secs < 90) { return "just now"; }
    var mins = Math.round(secs / 60);
    if (mins < 60) { return mins + " min ago"; }
    var hrs = Math.round(mins / 60);
    if (hrs < 24) { return hrs + (hrs === 1 ? " hour ago" : " hours ago"); }
    var days = Math.round(hrs / 24);
    return days + (days === 1 ? " day ago" : " days ago");
  }

  function plural(n, one, many) { return n + " " + (n === 1 ? one : many); }

  /* Pages may omit elements they have no use for -- an archive has no chart
     note and no vertical-scale switch -- so a missing target is a no-op
     rather than a crash. */
  function text(el, value) { if (el) { el.textContent = value; } }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ---- update rail ----------------------------------------------------- */
  /* Every page this site publishes, newest first. This list is the single
     place to add an entry when a new update starts being tracked or a finished
     one is archived: both pages build the rail from it, so neither HTML file
     carries a copy of the menu that could drift out of step with the other. */
  var UPDATES = [
    { file: "index.html", badge: "#6", short: "Update #6", note: "Tracking now" },
    { file: "update-5.html", badge: "#5", short: "Update #5", note: "Archive" }
  ];

  /* The page being served. A directory URL is index.html -- which is how
     GitHub Pages serves the site root at /gb-update/ -- so this cannot simply
     take the last path segment or the root would match nothing. */
  function currentFile() {
    var path = location.pathname;
    if (!path || path.charAt(path.length - 1) === "/") { return "index.html"; }
    return path.slice(path.lastIndexOf("/") + 1);
  }

  (function initRail() {
    var here = currentFile();
    var root = document.documentElement;
    var NARROW = "(max-width: 860px)";

    /* The rail has no single source of truth for "is it open": an explicit
       class wins, and with neither the stylesheet decides from the viewport.
       So ask the same question CSS is answering rather than keeping a flag
       that could disagree with what is on screen. */
    function isCollapsed() {
      if (root.classList.contains("rail-collapsed")) { return true; }
      if (root.classList.contains("rail-open")) { return false; }
      return window.matchMedia(NARROW).matches;
    }

    var nav = document.createElement("nav");
    nav.className = "rail";
    nav.setAttribute("aria-label", "Governing Body Updates");

    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "rail-toggle";
    toggle.setAttribute("aria-expanded", String(!isCollapsed()));
    toggle.setAttribute("aria-controls", "rail-list");
    toggle.innerHTML =
      '<span class="rail-bars" aria-hidden="true"></span>' +
      '<span class="rail-toggle-text">Updates</span>';

    var list = document.createElement("ul");
    list.className = "rail-list";
    list.id = "rail-list";
    list.innerHTML = UPDATES.map(function (u) {
      var active = u.file === here;
      return '<li><a href="' + esc(u.file) + '"' +
        (active ? ' aria-current="page"' : "") +
        /* The title carries the full name for the collapsed strip, where only
           the badge is showing. */
        ' title="' + esc(u.short + " \u2014 " + u.note) + '">' +
        '<span class="rail-badge" aria-hidden="true">' + esc(u.badge) + '</span>' +
        '<span class="rail-text">' +
        '<span class="rail-short">' + esc(u.short) + '</span>' +
        '<span class="rail-note">' + esc(u.note) + '</span>' +
        '</span></a></li>';
    }).join("");

    /* Only ever visible on a narrow screen, where the rail overlays the page
       rather than displacing it -- tapping off it should close it. */
    var backdrop = document.createElement("div");
    backdrop.className = "rail-backdrop";
    backdrop.addEventListener("click", function () { setCollapsed(true); });

    /* Sets exactly one explicit class, so the choice survives a resize across
       the breakpoint instead of being taken back by the media query. */
    function setCollapsed(next) {
      root.classList.toggle("rail-collapsed", next);
      root.classList.toggle("rail-open", !next);
      toggle.setAttribute("aria-expanded", String(!next));
      try { localStorage.setItem("rail", next ? "collapsed" : "open"); } catch (e) {}
    }

    toggle.addEventListener("click", function () { setCollapsed(!isCollapsed()); });

    /* Before any choice is made the default flips at the breakpoint, so the
       button's state has to follow it or a screen reader would be told the
       menu is open while it is a strip. */
    var mq = window.matchMedia(NARROW);
    var onNarrowChange = function () {
      toggle.setAttribute("aria-expanded", String(!isCollapsed()));
    };
    if (mq.addEventListener) { mq.addEventListener("change", onNarrowChange); }
    else if (mq.addListener) { mq.addListener(onNarrowChange); }

    nav.appendChild(toggle);
    nav.appendChild(list);
    document.body.appendChild(nav);
    document.body.appendChild(backdrop);
  })();

  /* ---- load ----------------------------------------------------------- */
  /* Which report to draw. The live tracker's page says nothing and gets
     data/report.json; an archive page names its own file on <body>, so one
     renderer serves both without a second copy of it. */
  var SOURCE = document.body.getAttribute("data-report") || "data/report.json";

  fetch(SOURCE, { cache: "no-store" })
    .then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status); }
      return r.json();
    })
    .then(render)
    .catch(function (err) {
      var box = $("error");
      box.hidden = false;
      box.textContent =
        "Could not load " + SOURCE + " (" + err.message + "). " +
        "If this site was just published, the first tracking run may not have completed yet.";
    });

  /* ---- render --------------------------------------------------------- */
  function render(report) {
    state.report = report;
    $("main").hidden = false;

    var s = report.stats || {};
    var upd = report.update || {};
    var base = report.baseline || {};
    /* An archive is a reconstruction of a finished rollout rather than a live
       recording of one in progress, so several lines of copy here would be
       wrong for it ("day 54 of the rollout", "new in the last hour"). Rather
       than grow a second set of hardcoded strings, the archive supplies its
       own wording in the report and this renderer prefers it where present.
       With no archive block every branch below behaves exactly as before. */
    var arc = report.archive || {};

    document.title = "Language availability — " + (upd.label || "Governing Body Update");
    text($("update-title"), upd.label || "Governing Body Update");

    var meta = [];
    if (arc.meta && arc.meta.length) {
      meta = arc.meta.slice();
    } else {
      if (upd.release) { meta.push("Released " + fmtUTC(upd.release, true)); }
      if (s.days_since_release != null) {
        meta.push("day " + Math.floor(s.days_since_release + 1) + " of the rollout");
      }
      if (upd.duration) { meta.push(upd.duration); }
    }
    $("update-meta").innerHTML = meta.map(esc).join('<span class="dot">•</span>');

    /* hero */
    text($("hero-value"), String(s.published_count == null ? "—" : s.published_count));
    if (s.target) {
      text($("hero-of"), arc.hero_of || ("of about " + s.target + " expected"));
      text($("hero-pct"), (s.percent == null ? "" : s.percent + "%"));
      var pct = Math.max(0, Math.min(100, s.percent || 0));
      $("meter-fill").style.width = Math.max(pct, pct > 0 ? 0.4 : 0) + "%";
      $("meter-caption").innerHTML = arc.hero_caption ? esc(arc.hero_caption) :
        plural(s.pending_count || 0, "language", "languages") + " still to come, against the " +
        esc(base.count) + " languages " +
        (base.url
          ? '<a href="' + esc(base.url) + '" rel="noopener">' + esc(base.short || "the previous update") + "</a>"
          : esc(base.short || "the previous update")) +
        " reached" +
        (base.sign_language_count
          ? " (including " + esc(base.sign_language_count) + " sign languages)"
          : "") + ".";
    } else {
      $("meter-caption").textContent = "No baseline available for comparison.";
    }

    /* stat tiles */
    function delta(n) { return n == null ? "\u2014" : "+" + n; }
    var tiles;
    if (arc.tiles && arc.tiles.length) {
      /* "New in the last hour" says nothing about a rollout that finished
         weeks ago, so an archive names its own tiles. */
      tiles = arc.tiles.map(function (t) { return [t.label, t.value]; });
    } else {
      tiles = [
        ["New in the last hour", delta(s.added_1h)],
        ["New in the last 4 hours", delta(s.added_4h)],
        ["New in the last 24 hours", delta(s.added_24h)]
      ];
      if (s.pending_count != null) {
        tiles.push(["Still pending", String(s.pending_count)]);
      }
      if (s.publisher_percent != null) {
        // Weighted by how many publishers read each language, so this runs well
        // ahead of the language count: the largest languages publish first.
        tiles.push(["Percentage of publishers reached", s.publisher_percent + "%"]);
      }
    }
    $("tiles").innerHTML = tiles.map(function (t) {
      return '<div class="tile"><p class="tile-label">' + esc(t[0]) +
        '</p><p class="tile-value">' + esc(t[1]) + "</p></div>";
    }).join("");

    /* chart */
    var noteBits = [
      arc.chart_note ||
      "Cumulative count of languages, plotted on each language's own publish time."
    ];
    if (base.count) {
      noteBits.push("The dashed line marks the " + base.count + " languages " +
        (base.short || "the previous update") + " reached.");
    }
    text($("chart-note"), noteBits.join(" "));

    /* The archive pins the chart to its full span, so it has no range control
       and states its two bracketing moments as text instead. Same source as
       the dotted rules on the chart, so the two cannot disagree. */
    var dates = $("chart-dates");
    if (dates) {
      var stamps = (arc.markers || []).filter(function (m) { return m && m.t; });
      dates.innerHTML = stamps.map(function (m) {
        return '<li><span class="chart-date-label">' + esc(m.label) + "</span>" +
          '<span class="chart-date-value">' + esc(fmtUTC(m.t, true)) + "</span></li>";
      }).join("");
      dates.hidden = !stamps.length;
    }

    drawChart(report);

    /* tables */
    text($("count-published"), String((report.published || []).length));
    text($("count-pending"), String((report.pending || []).length));
    text($("count-activity"), String((report.events || []).length));

    $("pending-note").innerHTML = arc.pending_note ? esc(arc.pending_note) :
      "Languages that received " + esc(base.short || "the previous update") +
      " but do not yet have " + esc(upd.short || "this update") + ".";

    renderIntegrity(report);

    $("published-legend").innerHTML = (arc.legend && arc.legend.length ? arc.legend : [
      "\u00a7 \u2014 approximate: the time comes from the video file itself, " +
        "not from jw.org.",
      "\u2020 \u2014 approximate: the time is the media API\u2019s firstPublished, " +
        "which can run earlier than public availability.",
      "\u2021 \u2014 approximate: the time is this tracker\u2019s own first " +
        "sighting of the language."
    ]).map(esc).join("<br>");

    renderPublished();
    renderPending();
    renderFeed(report.events || []);

    /* footer */
    var src = report.source || {};
    $("footer-source").innerHTML = "Source: " +
      '<a href="' + esc(src.page || upd.url) + '" rel="noopener">the video on jw.org</a>' +
      (src.files_api
        ? ' via <a href="' + esc(src.files_api) + '" rel="noopener">its media service</a>'
        : "");
    $("footer-method").innerHTML = arc.method_note ? arc.method_note :
      "The count comes from jw.org\u2019s own media service, which reports every " +
      "language a video is available to watch or download in \u2014 the same list the " +
      "language selector under the video offers. Each language brings its own publish " +
      "time, so the timeline reflects when languages actually went up rather than when " +
      "this tracker happened to look, and a time is recorded once and never rewritten " +
      "afterwards. Times confirmed by hand, in " +
      '<a href="https://github.com/harry-joyce/gb-update/blob/main/data/overrides.json" rel="noopener">overrides.json</a>' +
      ", take precedence. A daily check re-reads every language and reports anything " +
      "that has changed upstream." +
      ((report.integrity || {}).last_full_verification
        ? " Last verified " + fmtUTC(report.integrity.last_full_verification) + "."
        : "");
    $("footer-checked").textContent = arc.checked_note ? arc.checked_note :
      "Last recorded check " + fmtUTC(report.last_checked) +
      " (" + relative(report.last_checked) + "). Checks run every 30 minutes, but the " +
      "report is only rewritten when the language list changes or the record is over " +
      "an hour old \u2014 so this timestamp can trail the newest check. A new language " +
      "is always committed immediately, so the count itself is never behind.";
  }

  /* One symbol per provenance class, with the detail in the tooltip:
     nothing for a confirmed time, dagger for anything derived from the API,
     double dagger when only the tracker's own sighting was available. */
  function provenanceMark(source, note) {
    if (source === "record") {
      /* Archive pages only. The time is when jw.org created the language's
         record, which is the most reliable value recoverable after the fact
         but is an ingestion time, not the moment it became watchable. */
      return '<abbr class="ts-mark" title="' +
        esc(note || "The second jw.org created this language’s media record, " +
          "recovered from the record’s own identifier. That is when the " +
          "vernacular version was taken in, which on a scheduled release runs " +
          "ahead of when it became watchable") +
        '">¶</abbr>';
    }
    if (source === "file_estimated") {
      return '<abbr class="ts-mark" title="' +
        esc(note || "Estimated from pub-media\u2019s file timestamps, which record the " +
          "last time a file was written rather than when it was first published") +
        '">\u00a7</abbr>';
    }
    if (source === "api") {
      return '<abbr class="ts-mark" title="' +
        esc(note || "From the media API\u2019s firstPublished, which records when the " +
          "file entered the CDN and may precede public availability") +
        '">\u2020</abbr>';
    }
    if (source === "api_clamped") {
      return '<abbr class="ts-mark" title="' +
        esc(note || "The API reported a time before the release; clamped to the release time") +
        '">\u2020</abbr>';
    }
    if (source === "observed") {
      return '<abbr class="ts-mark" title="' +
        esc(note || "No publish time was available; this is when the tracker first saw it") +
        '">\u2021</abbr>';
    }
    return "";
  }

  /* Notices are written for a reader who is here for the number, not for the
     plumbing: anything that could make the count wrong gets said plainly, and
     the rest stays in data/report.json for whoever wants it. They sit at the
     foot of the page, just above the footer rule, so the caveats are there for
     anyone who goes looking without greeting everyone else first. */
  function renderIntegrity(report) {
    var box = $("integrity");
    var info = report.integrity || {};
    var items = [];

    /* An archive's caveats are about how the times were recovered rather than
       about a check that just failed, and they are written by the script that
       recovered them, which knows the actual counts. They lead, because on a
       reconstruction the provenance is the first thing a reader needs. */
    var arc = report.archive || {};
    if (arc.notices && arc.notices.length) {
      items = items.concat(arc.notices);
    }

    if (info.pub_media_unavailable) {
      items.push(
        "<strong>jw.org\u2019s media service could not be read on the last check</strong>, " +
        "so the count may be behind. It corrects itself on the next check that " +
        "succeeds."
      );
    }

    if (info.api_reset_detected) {
      items.push(
        "<strong>jw.org has rewritten its publish times for this video.</strong> This is " +
        "what happened to Update #5, where all 449 languages ended up reporting one " +
        "identical time. Every time already recorded here was saved when it was first " +
        "read and is unaffected; languages appearing from now on show the time this " +
        "tracker first saw them, marked \u2021." +
        (info.api_reset_detected_at
          ? " Detected " + esc(fmtUTC(info.api_reset_detected_at)) + "."
          : "")
      );
    }

    if (info.bulk_rewrite_suspected) {
      items.push(
        "<strong>The daily check found that jw.org has replaced its publish times " +
        "with one shared value.</strong> The times shown here are the ones recorded " +
        "as the rollout happened."
      );
    } else {
      var changed = (info.drift_count || 0) + (info.file_drift_count || 0);
      if (changed) {
        items.push(
          "<strong>" + esc(changed) + " publish " +
          (changed === 1 ? "time has" : "times have") +
          " changed on jw.org</strong> since first recorded. The times first " +
          "recorded are still shown."
        );
      }
    }

    var missing = (info.missing_items || []).filter(function (m) {
      return m.signal !== "catalogue";
    });
    if (missing.length) {
      items.push(
        "The video could no longer be found in " +
        esc(missing.map(function (m) { return m.name || m.code; }).join(", ")) +
        " at the last daily check."
      );
    }

    box.hidden = items.length === 0;
    box.innerHTML = items.length === 1
      ? items[0]
      : "<ul>" + items.map(function (i) { return "<li>" + i + "</li>"; }).join("") + "</ul>";
  }

  /* Keyed by report, so the live page and an archive remember their own view
     instead of overwriting each other's. */
  var VIEW_KEY = "chartView:" + SOURCE;

  /* ---- chart ---------------------------------------------------------- */
  var RANGES = { "6h": 6 * 36e5, "24h": 24 * 36e5, "3d": 3 * 864e5, "7d": 7 * 864e5 };

  function seriesFrom(history, lastChecked) {
    var pts = (history || []).map(function (h) {
      return { t: new Date(h.t).getTime(), count: h.count };
    }).filter(function (p) { return !isNaN(p.t); });
    /* Extend to the last check so a flat stretch reads as flat, not missing. */
    if (pts.length && !isNaN(lastChecked) && lastChecked > pts[pts.length - 1].t) {
      pts.push({ t: lastChecked, count: pts[pts.length - 1].count, synthetic: true });
    }
    return pts;
  }

  /* Carry the running total into the window, so a narrowed view does not
     pretend the count restarted at zero. */
  function clipSeries(points, tStart, fromStart) {
    var visible = [], countAtStart = 0;
    for (var i = 0; i < points.length; i++) {
      if (points[i].t <= tStart) { countAtStart = points[i].count; }
      else { visible.push(points[i]); }
    }
    visible.unshift({ t: tStart, count: countAtStart, clipped: !fromStart });
    return visible;
  }

  /* A language appears at a moment, so the value holds between publishes. */
  function stepPath(visible, x, y) {
    var d = "";
    visible.forEach(function (p, i) {
      if (i === 0) { d += "M" + x(p.t) + "," + y(p.count); }
      else {
        d += "L" + x(p.t) + "," + y(visible[i - 1].count);
        d += "L" + x(p.t) + "," + y(p.count);
      }
    });
    return d;
  }

  function pointAt(visible, t) {
    var best = visible.length ? visible[0] : null;
    for (var i = 0; i < visible.length; i++) {
      if (visible[i].t <= t) { best = visible[i]; }
    }
    return best;
  }

  /* Moments worth marking on the time axis, oldest first. `markers` is the
     general form; `release_marker` is the single-marker shape and is still
     honoured. Times that don't parse are dropped rather than drawn at the
     epoch. */
  function markerList(report) {
    var arc = report.archive || {};
    var raw = arc.markers || (arc.release_marker ? [arc.release_marker] : []);
    return raw.map(function (m) {
      return { t: new Date(m.t).getTime(), label: m.label || "" };
    }).filter(function (m) {
      return !isNaN(m.t);
    }).sort(function (a, b) {
      return a.t - b.t;
    });
  }

  function drawChart(report) {
    var svg = $("chart");
    var target = (report.baseline || {}).count || null;
    var W = 880, H = 300;
    var pad = { t: 22, r: 66, b: 38, l: 54 };

    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    while (svg.lastChild && svg.lastChild.id !== "chart-desc") { svg.removeChild(svg.lastChild); }
    var desc = $("chart-desc");

    /* A live report extends its series to the last check, so a quiet stretch
       reads as flat rather than missing. An archive's "last check" is the day
       it was built, which can be months after the final language -- extending
       to it would append a long dead flat run and squash the rollout itself
       into the left edge. So an archive ends at its last real point. */
    var isArchive = !!(report.archive || {}).is_archive;
    var lastChecked = isArchive ? NaN : new Date(report.last_checked).getTime();
    var points = seriesFrom(report.history, lastChecked);
    if (!points.length) { desc.textContent = "No history recorded yet."; return; }

    /* ---- time window ---- */
    var markers = markerList(report);
    var tEnd = points[points.length - 1].t;
    var span = RANGES[state.chart.range];
    var tStart;
    if (span) {
      /* A narrowed range means what it says, so markers outside it just don't
         draw. */
      tStart = Math.max(points[0].t, tEnd - span);
    } else {
      /* Showing everything. A marker can predate the first language --
         translation materials go out before any vernacular comes back -- so
         the domain has to stretch to reach it or the marker falls off the
         chart. A little padding past it keeps its rule off the axis. */
      tStart = points[0].t;
      for (var mi = 0; mi < markers.length; mi++) {
        if (markers[mi].t < tStart) { tStart = markers[mi].t; }
      }
      if (tStart < points[0].t) { tStart -= (tEnd - tStart) * 0.035; }
    }
    if (tEnd - tStart < 36e5) { tStart = tEnd - 36e5; }
    var fromStart = tStart <= points[0].t;

    var visible = clipSeries(points, tStart, fromStart);

    /* ---- vertical scale ---- */
    var counts = visible.map(function (p) { return p.count; });
    var vMin = Math.min.apply(null, counts), vMax = Math.max.apply(null, counts);
    var yMin, yMax, step;

    if (state.chart.y === "target" && target) {
      yMin = 0;
      step = niceStep(Math.max(target, vMax), 4);
      yMax = Math.max(Math.ceil(Math.max(target, vMax) / step) * step, step);
    } else {
      var spread = Math.max(vMax - vMin, 1);
      step = niceStep(spread, 4);
      yMin = Math.floor(vMin / step) * step;
      yMax = Math.ceil((vMax + spread * 0.1) / step) * step;
      if (yMax <= yMin) { yMax = yMin + step; }
      /* Don't truncate the axis for the sake of a sliver. */
      if (yMin > 0 && yMin <= yMax * 0.15) { yMin = 0; }
    }

    var x = function (t) {
      return pad.l + (t - tStart) / (tEnd - tStart) * (W - pad.l - pad.r);
    };
    var y = function (v) {
      return H - pad.b - (v - yMin) / (yMax - yMin) * (H - pad.t - pad.b);
    };

    var ns = "http://www.w3.org/2000/svg";
    function add(tag, attrs, parent) {
      var el = document.createElementNS(ns, tag);
      for (var k in attrs) { if (attrs[k] != null) { el.setAttribute(k, attrs[k]); } }
      (parent || svg).appendChild(el);
      return el;
    }

    /* y gridlines + ticks */
    for (var v = yMin; v <= yMax + 1e-6; v += step) {
      var vy = y(v);
      add("line", { class: "grid-line", x1: pad.l, x2: W - pad.r, y1: vy, y2: vy });
      add("text", {
        class: "axis-text", x: pad.l - 9, y: vy + 4, "text-anchor": "end"
      }).textContent = Math.round(v);
    }

    /* x ticks. xTicks spaces them in time, but labels collide in pixels: at
       some spans the last interior tick lands a few pixels short of the final
       one and the two dates overprint. Pruning is done here because only the
       renderer knows the scale. */
    var ticks = pruneTicks(xTicks(tStart, tEnd), x);
    ticks.forEach(function (tick, idx) {
      add("text", {
        class: "axis-text", x: x(tick.t), y: H - pad.b + 18,
        "text-anchor": idx === 0 ? "start" : idx === ticks.length - 1 ? "end" : "middle"
        /* On a live report the series starts at the release, so naming the
           first tick "release" is accurate. On an archive it starts at the
           first vernacular taken in, days earlier, so the release gets its own
           marker instead and this tick keeps its date. */
      }).textContent = (idx === 0 && fromStart && !isArchive) ? "release" : tick.label;
    });
    if (ticks.length && ticks[0].sub) {
      add("text", {
        class: "axis-note", x: pad.l, y: H - pad.b + 31
      }).textContent = ticks[0].sub;
    }

    /* Dotted vertical rules for the moments that bracket the rollout: when
       translation materials went out, and when the video published. They carry
       the meaning of the curve's shape -- without them the flat run on the
       left reads as nothing happening, when in fact it is the wait between
       materials going out and the first vernacular coming back, and the near-
       vertical jump reads as a sudden burst of publishing rather than a roster
       that was already in hand going live at once.

       Labels are staggered in alternating rows because two markers a few days
       apart sit close enough on a month-long axis for their text to collide. */
    markers.forEach(function (m, i) {
      if (m.t < tStart || m.t > tEnd) { return; }
      var mx = x(m.t);
      add("line", {
        class: "release-line", x1: mx, x2: mx, y1: pad.t, y2: H - pad.b
      });
      /* Anchor the label inward when it would otherwise overflow the plot. */
      var nearRight = mx > W - pad.r - 92;
      add("text", {
        class: "release-text",
        x: mx + (nearRight ? -7 : 7),
        y: pad.t + 11 + (i % 2) * 14,
        "text-anchor": nearRight ? "end" : "start"
      }).textContent = m.label;
    });

    /* target reference line, only when it falls inside the visible scale */
    if (target && target >= yMin && target <= yMax) {
      add("line", {
        class: "target-line", x1: pad.l, x2: W - pad.r, y1: y(target), y2: y(target)
      });
      add("text", {
        class: "target-text", x: W - pad.r + 7, y: y(target) + 4
      }).textContent = target;
      add("text", {
        class: "axis-text", x: W - pad.r + 7, y: y(target) + 18
      }).textContent = (report.archive || {}).target_label || "expected";
    }

    var d = stepPath(visible, x, y);
    var floor = y(yMin);
    add("path", {
      class: "series-area",
      d: d + "L" + x(visible[visible.length - 1].t) + "," + floor +
         "L" + x(tStart) + "," + floor + "Z"
    });
    add("path", { class: "series-line", d: d });

    var last = visible[visible.length - 1];
    add("circle", { class: "end-dot", cx: x(last.t), cy: y(last.count), r: 4.5 });
    /* The running total and the target label share the right-hand gutter, so a
       series that finishes on or near its target prints one over the other --
       which is exactly what a completed rollout does. Lift the total clear of
       the target block when they collide. */
    var endY = y(last.count) + 4;
    if (target && target >= yMin && target <= yMax && Math.abs(endY - (y(target) + 4)) < 16) {
      endY = Math.max(y(target) - 11, pad.t + 4);
    }
    add("text", {
      class: "end-label", x: x(last.t) + 10, y: endY
    }).textContent = last.count;

    desc.textContent =
      "Line chart of cumulative languages" +
      (fromStart
        ? (isArchive
            ? " from " + fmtUTC(report.history[0].t, true)
            : " from release on " +
              fmtUTC(report.update.release || report.history[0].t, true))
        : " over the last " + state.chart.range) +
      ", reaching " + last.count + " by " +
      fmtUTC(isArchive ? points[points.length - 1].t : report.last_checked) +
      ". Vertical axis " + yMin + " to " + yMax +
      (target && target >= yMin && target <= yMax
        ? ", with an expected total of " + target + "." : ".") +
      markers.filter(function (m) {
        return m.t >= tStart && m.t <= tEnd;
      }).map(function (m) {
        return " " + m.label + " is marked at " + fmtUTC(m.t, true) + ".";
      }).join("");

    /* hover layer */
    var cross = add("line", { class: "crosshair", y1: pad.t, y2: H - pad.b, x1: 0, x2: 0, opacity: 0 });
    var hoverDot = add("circle", { class: "hover-dot", r: 4.5, cx: 0, cy: 0, opacity: 0 });
    var tip = $("tooltip");
    var hit = add("rect", {
      x: pad.l, y: pad.t, width: W - pad.l - pad.r, height: H - pad.t - pad.b,
      fill: "transparent", style: "cursor:crosshair"
    });

    function onMove(ev) {
      var box = svg.getBoundingClientRect();
      var px = (ev.clientX - box.left) / box.width * W;
      var tAt = tStart + (px - pad.l) / (W - pad.l - pad.r) * (tEnd - tStart);
      var best = pointAt(visible, tAt);
      cross.setAttribute("x1", x(best.t));
      cross.setAttribute("x2", x(best.t));
      cross.setAttribute("opacity", 1);
      hoverDot.setAttribute("cx", x(best.t));
      hoverDot.setAttribute("cy", y(best.count));
      hoverDot.setAttribute("opacity", 1);
      tip.innerHTML = "<strong>" + plural(best.count, "language", "languages") + "</strong>" +
        '<span class="tt-date">' +
        (best.synthetic ? "as of last check \u2022 " : best.clipped ? "start of view \u2022 " : "") +
        fmtUTC(new Date(best.t).toISOString()) + "</span>";
      tip.style.opacity = 1;
      var left = x(best.t) / W * box.width;
      tip.style.left = Math.min(Math.max(left + 12, 4), box.width - tip.offsetWidth - 4) + "px";
      tip.style.top = Math.max(y(best.count) / H * box.height - 46, 2) + "px";
    }

    function onLeave() {
      cross.setAttribute("opacity", 0);
      hoverDot.setAttribute("opacity", 0);
      tip.style.opacity = 0;
    }

    hit.addEventListener("mousemove", onMove);
    hit.addEventListener("mouseleave", onLeave);
    hit.addEventListener("touchmove", function (ev) {
      if (ev.touches[0]) { onMove(ev.touches[0]); }
    }, { passive: true });
    hit.addEventListener("touchend", onLeave);
  }

  /* A 1-2-5 style step, so ticks land on numbers people read easily. */
  function niceStep(range, count) {
    var raw = range / Math.max(count, 1);
    var mag = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 1e-9))));
    var norm = raw / mag;
    var mult = norm <= 1.5 ? 1 : norm <= 3 ? 2 : norm <= 7 ? 5 : 10;
    return Math.max(1, Math.round(mult * mag));
  }

  /* Tick granularity follows the window: hours for a short view, days for a
     long one, so a 6-hour range doesn't collapse onto a single date label. */
  /* Keep the first and last ticks, since they anchor the axis, and drop any
     interior tick that would crowd a kept neighbour. The gap allows for the
     anchoring: an interior label is centred on its tick and the final one ends
     on it, so the worst case needs half of one label plus all of the other --
     about 62px for a "22 Aug" at this font size. */
  function pruneTicks(ticks, x) {
    if (ticks.length < 3) { return ticks; }
    var MIN_GAP = 62, lastT = ticks[ticks.length - 1].t;
    var kept = [ticks[0]];
    for (var i = 1; i < ticks.length - 1; i++) {
      if (x(ticks[i].t) - x(kept[kept.length - 1].t) >= MIN_GAP &&
          x(lastT) - x(ticks[i].t) >= MIN_GAP) {
        kept.push(ticks[i]);
      }
    }
    kept.push(ticks[ticks.length - 1]);
    return kept;
  }

  function xTicks(t0, t1) {
    var HOUR = 36e5, DAY = 864e5, span = t1 - t0, out = [];
    if (span <= DAY * 1.5) {
      var stepH = span <= 8 * HOUR ? 1 : span <= 14 * HOUR ? 2 : 6;
      var first = Math.ceil(t0 / (stepH * HOUR)) * (stepH * HOUR);
      out.push({ t: t0, label: hhmm(t0), sub: fmtUTCDate(new Date(t0).toISOString()) });
      for (var t = first; t < t1 - span * 0.04; t += stepH * HOUR) {
        if (t > t0 + span * 0.04) { out.push({ t: t, label: hhmm(t) }); }
      }
      out.push({ t: t1, label: hhmm(t1) });
      return out;
    }
    out.push({ t: t0, label: shortDate(t0) });
    var stepDays = Math.max(1, Math.ceil(span / DAY / 5));
    var midnight = new Date(t0);
    midnight.setUTCHours(0, 0, 0, 0);
    var d = midnight.getTime() + stepDays * DAY;
    while (d < t1 - span * 0.06) {
      if (d > t0 + span * 0.06) { out.push({ t: d, label: shortDate(d) }); }
      d += stepDays * DAY;
    }
    out.push({ t: t1, label: shortDate(t1) });
    return out;
  }

  function hhmm(t) {
    var d = new Date(t);
    return pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes());
  }

  function shortDate(t) {
    var d = new Date(t);
    return d.getUTCDate() + " " + MONTHS[d.getUTCMonth()];
  }

  /* ---- published table ------------------------------------------------ */
  function renderPublished() {
    var rows = (state.report.published || []).slice();
    var q = state.query.published.toLowerCase();
    if (q) {
      rows = rows.filter(function (r) {
        return (r.name + " " + r.vernacular + " " + r.code + " " + (r.locale || "") +
          " " + (r.title || "")).toLowerCase().indexOf(q) !== -1;
      });
    }
    var sort = state.sort.published;
    rows.sort(function (a, b) {
      var av = a[sort.key], bv = b[sort.key];
      if (sort.key === "published_at") {
        av = new Date(a.files_at || a.published_at).getTime() || 0;
        bv = new Date(b.files_at || b.published_at).getTime() || 0;
      } else {
        av = String(av).toLowerCase(); bv = String(bv).toLowerCase();
      }
      return (av < bv ? -1 : av > bv ? 1 : 0) * sort.dir;
    });

    var tbody = $("table-published").tBodies[0];
    tbody.innerHTML = rows.map(function (r) {
      var mark = provenanceMark(r.files_at_source || r.published_at_source,
                                r.files_at_note || r.published_at_note);
      var when = '<span class="exact">' + esc(fmtUTC(r.files_at || r.published_at)) +
        "</span>" + mark;
      var name = '<span class="lang-name">' + esc(r.name) + "</span>" +
        (r.beyond_baseline ? '<span class="chip new">new</span>' : "") +
        (r.sign ? '<span class="chip">sign</span>' : "") +
        (r.vernacular && r.vernacular !== r.name
          ? '<br><span class="lang-vern" dir="' + esc(r.direction) + '">' + esc(r.vernacular) + "</span>"
          : "");
      return "<tr><td>" + name +
        '</td><td class="code">' + esc(r.code) +
        '</td><td class="when">' + when +
        '</td><td class="title-cell"><a href="' + esc(r.url) + '" rel="noopener" dir="' +
        esc(r.direction) + '">' + esc(r.title || "Open") + "</a></td></tr>";
    }).join("");

    $("empty-published").hidden = rows.length > 0;
    text($("result-published"),
      rows.length === (state.report.published || []).length
        ? plural(rows.length, "language", "languages")
        : rows.length + " of " + (state.report.published || []).length);
    markSort("table-published", sort);
  }

  /* ---- pending table -------------------------------------------------- */
  function renderPending() {
    var rows = (state.report.pending || []).slice();
    var q = state.query.pending.toLowerCase();
    if (q) {
      rows = rows.filter(function (r) {
        return (r.name + " " + r.vernacular + " " + r.code).toLowerCase().indexOf(q) !== -1;
      });
    }
    var sort = state.sort.pending;
    rows.sort(function (a, b) {
      var av = String(a[sort.key] || "").toLowerCase();
      var bv = String(b[sort.key] || "").toLowerCase();
      return (av < bv ? -1 : av > bv ? 1 : 0) * sort.dir;
    });

    var tbody = $("table-pending").tBodies[0];
    tbody.innerHTML = rows.map(function (r) {
      return '<tr><td><span class="lang-name">' + esc(r.name) + "</span>" +
        (r.sign ? '<span class="chip">sign</span>' : "") +
        '</td><td class="lang-vern" dir="' + esc(r.direction) + '">' + esc(r.vernacular) +
        '</td><td class="code">' + esc(r.code) +
        '</td><td class="lang-vern">' + esc(titleCase(r.script)) + "</td></tr>";
    }).join("");

    $("empty-pending").hidden = rows.length > 0;
    text($("result-pending"),
      rows.length === (state.report.pending || []).length
        ? plural(rows.length, "language", "languages")
        : rows.length + " of " + (state.report.pending || []).length);
    markSort("table-pending", sort);
  }

  function titleCase(v) {
    if (!v) { return "—"; }
    return v.charAt(0) + v.slice(1).toLowerCase();
  }

  function markSort(tableId, sort) {
    var ths = $(tableId).querySelectorAll("th.sortable");
    for (var i = 0; i < ths.length; i++) {
      var th = ths[i];
      if (th.dataset.sort === sort.key) {
        th.setAttribute("aria-sort", sort.dir === 1 ? "ascending" : "descending");
        th.querySelector(".arrow").textContent = sort.dir === 1 ? "↑" : "↓";
      } else {
        th.removeAttribute("aria-sort");
      }
    }
  }

  /* ---- activity feed -------------------------------------------------- */
  /* Events arrive bucketed by the hour they happened. Day grouping folds
     each run of same-date buckets into one row, so the feed stays in the
     same shape and only the granularity changes. */
  function byDay(events) {
    var out = [], index = {};
    events.forEach(function (e) {
      var key = String(e.t).slice(0, 10);
      var row = index[key];
      if (!row) {
        row = index[key] = { t: e.t, added: [], count_after: e.count_after };
        out.push(row);
      }
      row.added = row.added.concat(e.added || []);
      row.count_after = e.count_after;
    });
    out.forEach(function (row) {
      row.added.sort(function (a, b) { return String(a.at) < String(b.at) ? -1 : 1; });
    });
    return out;
  }

  function renderFeed(events) {
    var byHour = state.activity.group === "hour";
    var rows = (byHour ? events.slice() : byDay(events)).reverse();

    text($("activity-note"), byHour
      ? "Publishes grouped by the hour they happened, most recent first."
      : "Publishes grouped by the day they happened, most recent first.");

    $("empty-activity").hidden = rows.length > 0;
    $("feed").innerHTML = rows.map(function (e) {
      var added = e.added || [];
      var names = added.map(function (a) {
        var mark = provenanceMark(a.source, a.note);
        return "<strong>" + esc(a.name) + "</strong> " +
          '<span class="feed-time">' + esc(timeOnly(a.at)) + "</span>" + mark;
      });
      return "<li>" +
        '<span class="feed-when">' + esc(fmtUTCDate(e.t)) + "<br>" +
        esc(byHour ? hourLabel(e.t) : spanLabel(added)) + "</span>" +
        '<span class="feed-delta">+' + added.length + "</span>" +
        '<span class="feed-body"><span class="feed-langs">' + names.join(", ") + "</span>" +
        '<span class="feed-total">Total published: ' + esc(e.count_after) + "</span></span>" +
        "</li>";
    }).join("");
  }

  function hourLabel(iso) {
    var d = new Date(iso);
    if (isNaN(d)) { return ""; }
    return pad(d.getUTCHours()) + ":00 UTC";
  }

  /* In day mode the hour is gone from the heading, so show the window the
     day's publishes actually landed in. */
  function spanLabel(added) {
    if (!added.length) { return ""; }
    var first = timeOnly(added[0].at);
    var last = timeOnly(added[added.length - 1].at);
    if (!first || !last) { return ""; }
    return (first === last ? first : first + "\u2013" + last) + " UTC";
  }

  function timeOnly(iso) {
    var d = new Date(iso);
    if (isNaN(d)) { return ""; }
    return pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes());
  }

  /* ---- interactions --------------------------------------------------- */
  ["published", "pending"].forEach(function (which) {
    $("search-" + which).addEventListener("input", function (ev) {
      state.query[which] = ev.target.value.trim();
      which === "published" ? renderPublished() : renderPending();
    });
    $("table-" + which).querySelectorAll("th.sortable").forEach(function (th) {
      th.addEventListener("click", function () {
        var key = th.dataset.sort, sort = state.sort[which];
        if (sort.key === key) { sort.dir *= -1; } else { sort.key = key; sort.dir = 1; }
        which === "published" ? renderPublished() : renderPending();
      });
    });
  });

  /* ---- chart view options --------------------------------------------- */
  (function initChartOptions() {
    try {
      var saved = JSON.parse(localStorage.getItem(VIEW_KEY) || "null");
      if (saved && saved.y && saved.range) {
        if (["fit", "target"].indexOf(saved.y) !== -1) { state.chart.y = saved.y; }
        if (saved.range === "all" || RANGES[saved.range]) { state.chart.range = saved.range; }
      }
    } catch (e) {}

    /* Not every page offers every control: the archive drops the vertical
       scale and offers a narrower set of ranges. Since the view is remembered,
       a restored value with no button here would be unreachable -- and a "last
       6 hours" window on a rollout that finished in August would draw an empty
       chart with no way out. So discard any choice this page cannot change. */
    if (!document.querySelector('[data-chart-y="' + state.chart.y + '"]')) {
      state.chart.y = "fit";
    }
    if (!document.querySelector('[data-chart-range="' + state.chart.range + '"]')) {
      state.chart.range = "all";
    }

    function sync() {
      var all = document.querySelectorAll("[data-chart-y],[data-chart-range]");
      for (var i = 0; i < all.length; i++) {
        var el = all[i];
        var on = el.dataset.chartY
          ? el.dataset.chartY === state.chart.y
          : el.dataset.chartRange === state.chart.range;
        el.setAttribute("aria-pressed", String(on));
      }
    }

    function choose(ev) {
      var el = ev.currentTarget;
      if (el.dataset.chartY) { state.chart.y = el.dataset.chartY; }
      else { state.chart.range = el.dataset.chartRange; }
      try { localStorage.setItem(VIEW_KEY, JSON.stringify(state.chart)); } catch (e) {}
      sync();
      if (state.report) { drawChart(state.report); }
    }

    var buttons = document.querySelectorAll("[data-chart-y],[data-chart-range]");
    for (var j = 0; j < buttons.length; j++) {
      buttons[j].addEventListener("click", choose);
    }
    sync();
  })();

  /* ---- activity grouping ---------------------------------------------- */
  (function initActivityGroup() {
    try {
      var saved = localStorage.getItem("activityGroup");
      if (saved === "hour" || saved === "day") { state.activity.group = saved; }
    } catch (e) {}

    var buttons = document.querySelectorAll("[data-activity-group]");

    function sync() {
      for (var i = 0; i < buttons.length; i++) {
        buttons[i].setAttribute(
          "aria-pressed",
          String(buttons[i].dataset.activityGroup === state.activity.group)
        );
      }
    }

    for (var j = 0; j < buttons.length; j++) {
      buttons[j].addEventListener("click", function (ev) {
        state.activity.group = ev.currentTarget.dataset.activityGroup;
        try { localStorage.setItem("activityGroup", state.activity.group); } catch (e) {}
        sync();
        if (state.report) { renderFeed(state.report.events || []); }
      });
    }
    sync();
  })();

  var tabs = ["published", "pending", "activity"];
  tabs.forEach(function (name) {
    $("tab-" + name).addEventListener("click", function () {
      tabs.forEach(function (other) {
        var selected = other === name;
        $("tab-" + other).setAttribute("aria-selected", String(selected));
        $("panel-" + other).hidden = !selected;
      });
    });
  });

  window.addEventListener("resize", function () {
    if (state.report) { drawChart(state.report); }
  });
})();
