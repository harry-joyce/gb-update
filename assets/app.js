/* Language availability tracker — renders data/report.json. No dependencies. */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };

  /* ---- state ---------------------------------------------------------- */
  var state = {
    report: null,
    sort: { published: { key: "published_at", dir: -1 }, pending: { key: "name", dir: 1 } },
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
    var tiles = [];
    tiles.push(["New in last 24 hours", s.added_24h == null ? "—" : "+" + s.added_24h]);
    tiles.push(["New in last 7 days", s.added_7d == null ? "—" : "+" + s.added_7d]);
    if (s.per_day_overall != null) {
      tiles.push(["Average pace", s.per_day_overall + " <small>/ day</small>"]);
    }
    if (s.projected_completion) {
      tiles.push([
        "Projected to finish",
        fmtDate(s.projected_completion) + " <small>at current pace</small>"
      ]);
    } else if (s.pending_count != null) {
      tiles.push(["Still pending", String(s.pending_count)]);
    }
    $("tiles").innerHTML = tiles.map(function (t) {
      return '<div class="tile"><p class="tile-label">' + esc(t[0]) +
        '</p><p class="tile-value">' + t[1] + "</p></div>";
    }).join("");

    /* chart */
    var noteBits = [
      "Cumulative count of languages, plotted on each language's own publish time."
    ];
    if (base.count) {
      noteBits.push("The dashed line marks the " + base.count + " languages " +
        (base.short || "the previous update") + " reached. Its rollout curve cannot be " +
        "drawn: the media API reports one bulk publish time for every language of a " +
        "finished video, so only its final total is meaningful.");
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

    var counts = report.counts || {};
    var legend = [];
    if (counts.confirmed_times) {
      legend.push(plural(counts.confirmed_times, "time is", "times are") + " confirmed.");
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
      " take precedence over the API value.";
    $("footer-checked").textContent =
      "Last checked " + fmtUTC(report.last_checked) +
      " (" + relative(report.last_checked) + "). Checks run hourly; the report is " +
      "only rewritten when the language list changes or the record goes stale.";
  }

  /* ---- chart ---------------------------------------------------------- */
  function drawChart(report) {
    var svg = $("chart");
    var history = (report.history || []).slice();
    var target = (report.baseline || {}).count || null;
    var W = 880, H = 300;
    var pad = { t: 22, r: 66, b: 34, l: 46 };

    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    while (svg.lastChild && svg.lastChild.id !== "chart-desc") { svg.removeChild(svg.lastChild); }
    var desc = $("chart-desc");

    if (!history.length) {
      desc.textContent = "No history recorded yet.";
      return;
    }

    /* Extend the series to "now" so a flat stretch reads as flat, not missing. */
    var points = history.map(function (h) {
      return { t: new Date(h.t).getTime(), count: h.count };
    }).filter(function (p) { return !isNaN(p.t); });
    if (!points.length) { desc.textContent = "No history recorded yet."; return; }

    var lastChecked = new Date(report.last_checked).getTime();
    if (!isNaN(lastChecked) && lastChecked > points[points.length - 1].t) {
      points.push({ t: lastChecked, count: points[points.length - 1].count, synthetic: true });
    }

    var t0 = points[0].t;
    var t1 = points[points.length - 1].t;
    if (t1 - t0 < 36e5) { t1 = t0 + 36e5; }           // keep a minimum span
    var maxCount = Math.max.apply(null, points.map(function (p) { return p.count; }));
    var rawMax = Math.max(maxCount, target || 0, 1);
    var step = niceStep(rawMax, 4);
    var yMax = Math.max(Math.ceil(rawMax / step) * step, step);

    var x = function (t) { return pad.l + (t - t0) / (t1 - t0) * (W - pad.l - pad.r); };
    var y = function (v) { return H - pad.b - (v / yMax) * (H - pad.t - pad.b); };

    var ns = "http://www.w3.org/2000/svg";
    function add(tag, attrs, parent) {
      var el = document.createElementNS(ns, tag);
      for (var k in attrs) { if (attrs[k] != null) { el.setAttribute(k, attrs[k]); } }
      (parent || svg).appendChild(el);
      return el;
    }

    /* y gridlines + ticks */
    var ticks = yTicks(yMax, step);
    ticks.forEach(function (v) {
      add("line", { class: "grid-line", x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v) });
      add("text", {
        class: "axis-text", x: pad.l - 9, y: y(v) + 4, "text-anchor": "end"
      }).textContent = v;
    });

    /* x ticks */
    xTicks(t0, t1).forEach(function (tick) {
      add("text", {
        class: "axis-text", x: x(tick), y: H - pad.b + 18, "text-anchor": "middle"
      }).textContent = tick === t0 ? "release" : shortDate(tick);
    });

    /* target reference line */
    if (target && target <= yMax) {
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

    /* step series: a language appears at a moment, so hold the value between checks */
    var d = "", area = "";
    points.forEach(function (p, i) {
      if (i === 0) { d += "M" + x(p.t) + "," + y(p.count); }
      else {
        d += "L" + x(p.t) + "," + y(points[i - 1].count);
        d += "L" + x(p.t) + "," + y(p.count);
      }
    });
    area = d + "L" + x(points[points.length - 1].t) + "," + y(0) + "L" + x(t0) + "," + y(0) + "Z";

    add("path", { class: "series-area", d: area });
    add("path", { class: "series-line", d: d });

    var last = points[points.length - 1];
    add("circle", { class: "end-dot", cx: x(last.t), cy: y(last.count), r: 4.5 });
    add("text", {
      class: "end-label", x: x(last.t) + 10, y: y(last.count) + 4
    }).textContent = last.count;

    desc.textContent =
      "Line chart: 0 languages at release on " +
      fmtUTC(report.update.release || history[0].t, true) + ", rising to " +
      last.count + " by " + fmtUTC(report.last_checked) +
      (target ? ", against an expected total of " + target + "." : ".");

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
      var tAt = t0 + (px - pad.l) / (W - pad.l - pad.r) * (t1 - t0);
      var best = points[0];
      for (var i = 0; i < points.length; i++) {
        if (points[i].t <= tAt) { best = points[i]; }
      }
      cross.setAttribute("x1", x(best.t));
      cross.setAttribute("x2", x(best.t));
      cross.setAttribute("opacity", 1);
      hoverDot.setAttribute("cx", x(best.t));
      hoverDot.setAttribute("cy", y(best.count));
      hoverDot.setAttribute("opacity", 1);
      tip.innerHTML = "<strong>" + best.count + " languages</strong>" +
        '<span class="tt-date">' +
        (best.synthetic ? "as of last check • " : "") + fmtUTC(new Date(best.t).toISOString()) +
        "</span>";
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

  function yTicks(max, step) {
    var out = [];
    for (var v = 0; v <= max + 1e-6; v += step) { out.push(Math.round(v)); }
    return out;
  }

  /* Day-aligned ticks: rollouts are read in days, not arbitrary fractions. */
  function xTicks(t0, t1) {
    var DAY = 864e5, span = t1 - t0, out = [t0];
    if (span > DAY * 1.5) {
      var stepDays = Math.max(1, Math.ceil(span / DAY / 5));
      var midnight = new Date(t0);
      midnight.setHours(0, 0, 0, 0);
      var t = midnight.getTime() + stepDays * DAY;
      while (t < t1 - span * 0.06) {
        if (t > t0 + span * 0.06) { out.push(t); }
        t += stepDays * DAY;
      }
    }
    out.push(t1);
    return out;
  }

  function shortDate(t) {
    return new Date(t).toLocaleDateString(undefined, { day: "numeric", month: "short" });
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
      var mark = "";
      if (r.published_at_source === "api") {
        mark = '<abbr class="ts-mark" title="From the media API\u2019s firstPublished; ' +
          'may precede public availability">\u2020</abbr>';
      } else if (r.published_at_source === "observed") {
        mark = '<abbr class="ts-mark" title="No publish time available; this is when the ' +
          'tracker first saw it">\u2021</abbr>';
      }
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
        var mark = a.source === "api" ? '<abbr class="ts-mark" title="Time from the media API">\u2020</abbr>'
          : a.source === "observed" ? '<abbr class="ts-mark" title="First observed by the tracker">\u2021</abbr>'
          : "";
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
