/* Language availability tracker — renders data/report.json. No dependencies. */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };

  /* ---- state ---------------------------------------------------------- */
  var state = {
    report: null,
    sort: { published: { key: "published_at", dir: -1 }, pending: { key: "name", dir: 1 } },
    chart: { y: "fit", range: "all" },
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

  function text(el, value) { el.textContent = value; }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ---- load ----------------------------------------------------------- */
  fetch("data/report.json", { cache: "no-store" })
    .then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status); }
      return r.json();
    })
    .then(render)
    .catch(function (err) {
      var box = $("error");
      box.hidden = false;
      box.textContent =
        "Could not load data/report.json (" + err.message + "). " +
        "If this site was just published, the first tracking run may not have completed yet.";
    });

  /* ---- render --------------------------------------------------------- */
  function render(report) {
    state.report = report;
    $("main").hidden = false;

    var s = report.stats || {};
    var upd = report.update || {};
    var base = report.baseline || {};

    document.title = "Language availability — " + (upd.label || "Governing Body Update");
    text($("update-title"), upd.label || "Governing Body Update");

    var meta = [];
    if (upd.release) { meta.push("Released " + fmtUTC(upd.release, true)); }
    if (s.days_since_release != null) {
      meta.push("day " + Math.floor(s.days_since_release + 1) + " of the rollout");
    }
    if (upd.duration) { meta.push(upd.duration); }
    $("update-meta").innerHTML = meta.map(esc).join('<span class="dot">•</span>');

    /* hero */
    text($("hero-value"), String(s.published_count == null ? "—" : s.published_count));
    if (s.target) {
      text($("hero-of"), "of about " + s.target + " expected");
      text($("hero-pct"), (s.percent == null ? "" : s.percent + "%"));
      var pct = Math.max(0, Math.min(100, s.percent || 0));
      $("meter-fill").style.width = Math.max(pct, pct > 0 ? 0.4 : 0) + "%";
      $("meter-caption").innerHTML =
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
    var tiles = [
      ["New in the last hour", s.added_1h],
      ["New in the last 4 hours", s.added_4h],
      ["New in the last 24 hours", s.added_24h]
    ];
    if (s.pending_count != null) { tiles.push(["Still pending", s.pending_count]); }
    $("tiles").innerHTML = tiles.map(function (t) {
      var value = t[1] == null ? "\u2014"
        : (t[0] === "Still pending" ? String(t[1]) : "+" + t[1]);
      return '<div class="tile"><p class="tile-label">' + esc(t[0]) +
        '</p><p class="tile-value">' + esc(value) + "</p></div>";
    }).join("");

    /* chart */
    var noteBits = [
      "Cumulative count of languages, plotted on each language's own publish time."
    ];
    if (base.count) {
      noteBits.push("The dashed line marks the " + base.count + " languages " +
        (base.short || "the previous update") + " reached.");
    }
    text($("chart-note"), noteBits.join(" "));
    drawChart(report);

    /* tables */
    text($("count-published"), String((report.published || []).length));
    text($("count-pending"), String((report.pending || []).length));
    text($("count-activity"), String((report.events || []).length));

    $("pending-note").innerHTML =
      "Languages that received " + esc(base.short || "the previous update") +
      " but do not yet have " + esc(upd.short || "this update") + ".";

    renderIntegrity(report);

    var counts = report.counts || {};
    var legend = [];
    if (counts.confirmed_times) {
      legend.push(plural(counts.confirmed_times, "time is", "times are") + " confirmed.");
    }
    if (counts.clamped_times) {
      legend.push(plural(counts.clamped_times, "time was", "times were") +
        " reported by the API as earlier than the release and clamped to the release time.");
    }
    if (counts.observed_times) {
      legend.push(plural(counts.observed_times, "time is", "times are") +
        " marked \u2021 \u2014 no API publish time was usable, so the tracker's own " +
        "first sighting is shown.");
    }
    if (counts.api_times) {
      legend.push(plural(counts.api_times, "time is", "times are") +
        " marked \u2020 \u2014 taken from the media API's firstPublished, which records when " +
        "the file entered the CDN and can run earlier than public availability. " +
        "English reports " +
        (upd.api_first_published ? fmtUTC(upd.api_first_published) : "an earlier time") +
        " but was published at " + (upd.release ? fmtUTC(upd.release) : "14:00 UTC") + ".");
    }
    $("published-legend").innerHTML = legend.join(" ");

    renderPublished();
    renderPending();
    renderFeed(report.events || []);

    /* footer */
    var src = report.source || {};
    $("footer-source").innerHTML = "Source: " +
      '<a href="' + esc(src.page || upd.url) + '" rel="noopener">the video on jw.org</a>' +
      (src.api ? ' via <a href="' + esc(src.api) + '" rel="noopener">the JW media API</a>' : "");
    $("footer-method").innerHTML =
      "The media API lists every language a video is published in, plus each language's own " +
      "publish time, so the timeline reflects actual publication rather than when this " +
      "tracker happened to look. Confirmed times recorded in " +
      '<a href="https://github.com/harry-joyce/gb-update/blob/main/data/overrides.json" rel="noopener">overrides.json</a>' +
      " take precedence over the API value. Each language's API timestamp is pinned the " +
      "first time it is read, so a later upstream rewrite cannot alter the recorded " +
      "rollout; a daily job re-reads every language and reports any drift." +
      ((report.integrity || {}).last_full_verification
        ? " Last verified " + fmtUTC(report.integrity.last_full_verification) + "."
        : "");
    $("footer-checked").textContent =
      "Last checked " + fmtUTC(report.last_checked) +
      " (" + relative(report.last_checked) + "). Checks run hourly; the report is " +
      "only rewritten when the language list changes or the record goes stale.";
  }

  /* One symbol per provenance class, with the detail in the tooltip:
     nothing for a confirmed time, dagger for anything derived from the API,
     double dagger when only the tracker's own sighting was available. */
  function provenanceMark(source, note) {
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

  function renderIntegrity(report) {
    var box = $("integrity");
    var info = report.integrity || {};
    var items = [];

    if (info.api_reset_detected) {
      items.push(
        "<strong>The media API has rewritten its publish timestamps.</strong> This is " +
        "what happened to Update #5, where all 449 languages ended up reporting one " +
        "identical time. Every time already recorded here was pinned when it was first " +
        "read and is unaffected; languages appearing from now on fall back to the time " +
        "the tracker first saw them, marked \u2021." +
        (info.api_reset_detected_at
          ? " Detected " + esc(fmtUTC(info.api_reset_detected_at)) + "."
          : "")
      );
    }

    if (info.bulk_rewrite_suspected) {
      items.push(
        "<strong>Daily verification found a bulk rewrite.</strong> " +
        esc(info.drift_count) + " languages now report a single shared timestamp " +
        "upstream. The times shown here are the ones recorded as the rollout happened."
      );
    } else if (info.drift_count) {
      items.push(
        "<strong>" + esc(info.drift_count) + " publish " +
        (info.drift_count === 1 ? "time has" : "times have") +
        " changed upstream</strong> since first recorded. The originally recorded " +
        "times are still shown."
      );
    }

    if ((info.listing_lag || []).length) {
      var names = (report.published || [])
        .filter(function (p) { return info.listing_lag.indexOf(p.code) !== -1; })
        .map(function (p) { return p.name; });
      items.push(
        (names.length === 1 ? names[0] + " is" : names.join(", ") + " are") +
        " no longer in the API's language list but " +
        (names.length === 1 ? "its own record is" : "their own records are") +
        " still live, so " + (names.length === 1 ? "it is" : "they are") +
        " still counted as published."
      );
    }

    if ((info.missing_items || []).length) {
      items.push(
        "No media record found for " +
        esc(info.missing_items.map(function (m) { return m.name || m.code; }).join(", ")) +
        " at the last verification."
      );
    }

    box.hidden = items.length === 0;
    box.innerHTML = items.length === 1
      ? items[0]
      : "<ul>" + items.map(function (i) { return "<li>" + i + "</li>"; }).join("") + "</ul>";
  }


  /* ---- chart ---------------------------------------------------------- */
  var RANGES = { "6h": 6 * 36e5, "24h": 24 * 36e5, "3d": 3 * 864e5, "7d": 7 * 864e5 };

  function drawChart(report) {
    var svg = $("chart");
    var history = (report.history || []).slice();
    var target = (report.baseline || {}).count || null;
    var W = 880, H = 300;
    var pad = { t: 22, r: 66, b: 38, l: 54 };

    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    while (svg.lastChild && svg.lastChild.id !== "chart-desc") { svg.removeChild(svg.lastChild); }
    var desc = $("chart-desc");

    var points = history.map(function (h) {
      return { t: new Date(h.t).getTime(), count: h.count };
    }).filter(function (p) { return !isNaN(p.t); });
    if (!points.length) { desc.textContent = "No history recorded yet."; return; }

    /* Extend to the last check so a flat stretch reads as flat, not missing. */
    var lastChecked = new Date(report.last_checked).getTime();
    if (!isNaN(lastChecked) && lastChecked > points[points.length - 1].t) {
      points.push({ t: lastChecked, count: points[points.length - 1].count, synthetic: true });
    }

    /* ---- time window ---- */
    var tEnd = points[points.length - 1].t;
    var span = RANGES[state.chart.range];
    var tStart = span ? Math.max(points[0].t, tEnd - span) : points[0].t;
    if (tEnd - tStart < 36e5) { tStart = tEnd - 36e5; }
    var fromStart = tStart <= points[0].t;

    /* Carry the running total into the window, so a narrowed view does not
       pretend the count restarted at zero. */
    var visible = [], countAtStart = 0;
    for (var i = 0; i < points.length; i++) {
      if (points[i].t <= tStart) { countAtStart = points[i].count; }
      else { visible.push(points[i]); }
    }
    visible.unshift({ t: tStart, count: countAtStart, clipped: !fromStart });

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

    /* x ticks */
    var ticks = xTicks(tStart, tEnd);
    ticks.forEach(function (tick, idx) {
      add("text", {
        class: "axis-text", x: x(tick.t), y: H - pad.b + 18,
        "text-anchor": idx === 0 ? "start" : idx === ticks.length - 1 ? "end" : "middle"
      }).textContent = (idx === 0 && fromStart) ? "release" : tick.label;
    });
    if (ticks.length && ticks[0].sub) {
      add("text", {
        class: "axis-note", x: pad.l, y: H - pad.b + 31
      }).textContent = ticks[0].sub;
    }

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
      }).textContent = "expected";
    }

    /* step series: a language appears at a moment, so hold the value between */
    var d = "";
    visible.forEach(function (p, i) {
      if (i === 0) { d += "M" + x(p.t) + "," + y(p.count); }
      else {
        d += "L" + x(p.t) + "," + y(visible[i - 1].count);
        d += "L" + x(p.t) + "," + y(p.count);
      }
    });
    var base = y(yMin);
    var area = d + "L" + x(visible[visible.length - 1].t) + "," + base +
      "L" + x(tStart) + "," + base + "Z";

    add("path", { class: "series-area", d: area });
    add("path", { class: "series-line", d: d });

    var last = visible[visible.length - 1];
    add("circle", { class: "end-dot", cx: x(last.t), cy: y(last.count), r: 4.5 });
    add("text", {
      class: "end-label", x: x(last.t) + 10, y: y(last.count) + 4
    }).textContent = last.count;

    desc.textContent =
      "Line chart of cumulative languages" +
      (fromStart
        ? " from release on " + fmtUTC(report.update.release || history[0].t, true)
        : " over the last " + state.chart.range) +
      ", reaching " + last.count + " by " + fmtUTC(report.last_checked) +
      ". Vertical axis " + yMin + " to " + yMax +
      (target && target >= yMin && target <= yMax
        ? ", with an expected total of " + target + "." : ".");

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
      var best = visible[0];
      for (var j = 0; j < visible.length; j++) {
        if (visible[j].t <= tAt) { best = visible[j]; }
      }
      cross.setAttribute("x1", x(best.t));
      cross.setAttribute("x2", x(best.t));
      cross.setAttribute("opacity", 1);
      hoverDot.setAttribute("cx", x(best.t));
      hoverDot.setAttribute("cy", y(best.count));
      hoverDot.setAttribute("opacity", 1);
      tip.innerHTML = "<strong>" + best.count + " languages</strong>" +
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
        av = new Date(av).getTime() || 0; bv = new Date(bv).getTime() || 0;
      } else {
        av = String(av).toLowerCase(); bv = String(bv).toLowerCase();
      }
      return (av < bv ? -1 : av > bv ? 1 : 0) * sort.dir;
    });

    var tbody = $("table-published").tBodies[0];
    tbody.innerHTML = rows.map(function (r) {
      var mark = provenanceMark(r.published_at_source, r.published_at_note);
      var when = '<span class="exact">' + esc(fmtUTC(r.published_at)) + "</span>" + mark;
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
  function renderFeed(events) {
    var rows = events.slice().reverse();
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
        esc(hourLabel(e.t)) + "</span>" +
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
      var saved = JSON.parse(localStorage.getItem("chartView") || "null");
      if (saved && saved.y && saved.range) {
        if (["fit", "target"].indexOf(saved.y) !== -1) { state.chart.y = saved.y; }
        if (saved.range === "all" || RANGES[saved.range]) { state.chart.range = saved.range; }
      }
    } catch (e) {}

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
      try { localStorage.setItem("chartView", JSON.stringify(state.chart)); } catch (e) {}
      sync();
      if (state.report) { drawChart(state.report); }
    }

    var buttons = document.querySelectorAll("[data-chart-y],[data-chart-range]");
    for (var j = 0; j < buttons.length; j++) {
      buttons[j].addEventListener("click", choose);
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
