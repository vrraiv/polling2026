/* Charts for the Election data pages (site/history/): hand-drawn SVG from the JSON specs each page carries in
   window.CHARTS, styled like the forecast page. Types: xy (lines and/or points, fit lines, reference lines),
   bars (grouped, vertical or horizontal, optional error bars), heatmap. Built by src/site/history.py. */
(function () {
  "use strict";
  const root = getComputedStyle(document.documentElement);
  const css = (v) => root.getPropertyValue("--" + v).trim();
  const col = (c) => (!c ? css("tint") : c.startsWith("#") ? c : css(c) || c);
  const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));

  // ---------- tooltip ----------
  const tip = document.createElement("div");
  tip.className = "tip"; tip.setAttribute("role", "status");
  document.body.appendChild(tip);
  function showTip(e, html) {
    tip.innerHTML = html; tip.style.opacity = 1;
    const r = tip.getBoundingClientRect(), vw = document.documentElement.clientWidth;
    let x = e.pageX + 12, y = e.pageY + 14;
    if (x + r.width > window.scrollX + vw - 8) x = Math.max(window.scrollX + 8, e.pageX - r.width - 12);
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  const hideTip = () => { tip.style.opacity = 0; };
  function bindTips(svgEl, tips) {
    svgEl.querySelectorAll("[data-tip]").forEach((n) => {
      const html = tips[+n.dataset.tip];
      n.addEventListener("mousemove", (e) => showTip(e, html));
      n.addEventListener("mouseleave", hideTip);
      n.addEventListener("click", (e) => showTip(e, html));
    });
  }

  // ---------- numbers ----------
  function fmt(v, f) {
    if (v == null || Number.isNaN(v)) return "–";
    const a = Math.abs(v);
    switch (f) {
      case "dr1": return v > 0.05 ? "D+" + a.toFixed(1) : v < -0.05 ? "R+" + a.toFixed(1) : "Even";
      case "dr0": return Math.round(v) > 0 ? "D+" + Math.round(a) : Math.round(v) < 0 ? "R+" + Math.round(a) : "Even";
      case "signed0": return (Math.round(v) > 0 ? "+" : Math.round(v) < 0 ? "−" : "") + Math.round(a);
      case "signed1": return (v > 0 ? "+" : v < 0 ? "−" : "") + a.toFixed(1);
      case "signed2": return (v > 0 ? "+" : v < 0 ? "−" : "") + a.toFixed(2);
      case "int": case "year": return String(Math.round(v));
      case "dec1": return v.toFixed(1);
      case "dec2": return v.toFixed(2);
      case "pct": return Math.round(v * 100) + "%";
      default: return String(+v.toFixed(1));
    }
  }
  function niceTicks(lo, hi, n) {
    const span = hi - lo || 1, raw = span / (n || 5), mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw * 0.999);
    const out = [];
    for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }
  function domain(vals, ax) {
    let lo = ax && ax.min != null ? ax.min : Math.min(...vals), hi = ax && ax.max != null ? ax.max : Math.max(...vals);
    if (ax && ax.zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    if (lo === hi) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.06;
    if (!(ax && ax.min != null)) lo -= pad;
    if (!(ax && ax.max != null)) hi += pad;
    return [lo, hi];
  }
  const T = (x, y, s, o = {}) => `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-size="${o.size || 11}" fill="${o.fill || css("text-3")}"` +
    `${o.anchor ? ` text-anchor="${o.anchor}"` : ""}${o.rot ? ` transform="rotate(${o.rot} ${x.toFixed(1)} ${y.toFixed(1)})"` : ""}${o.weight ? ` font-weight="${o.weight}"` : ""}>${esc(s)}</text>`;

  function legendHTML(items) {
    if (!items || !items.length) return "";
    return `<div class="legend">` + items.map((it) => {
      const c = col(it.color);
      const mark = it.line ? `<i style="background:${c}"></i>`
        : it.hollow ? `<i class="sq" style="border:2px solid ${c};background:transparent;border-radius:50%;width:9px;height:9px"></i>`
        : `<i class="sq" style="background:${c};${it.dot ? "border-radius:50%" : ""}"></i>`;
      return `<span>${mark}${esc(it.name)}</span>`;
    }).join("") + `</div>`;
  }

  // ---------- xy: lines and points ----------
  function xy(el, s) {
    const W = drawWidth(el, s), H = s.height || 280, m = { l: 52, r: 14, t: 16, b: s.x.label ? 42 : 28 };
    const all = s.series.flatMap((se) => se.pts);
    const xs = all.map((p) => p.x).concat((s.vrefs || []).map((r) => r.x));
    const ys = all.map((p) => p.y).concat((s.refs || []).map((r) => r.y));
    const [x0, x1] = domain(xs, s.x), [y0, y1] = domain(ys, s.y);
    const X = (v) => m.l + (v - x0) / (x1 - x0) * (W - m.l - m.r), Y = (v) => m.t + (1 - (v - y0) / (y1 - y0)) * (H - m.t - m.b);
    const bd = css("border"), t3 = css("text-3"), t2 = css("text-2"), bg = css("bg");
    let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(s.title || "")}">`;
    const yt = s.y.ticks || niceTicks(y0, y1, s.y.n || 5);
    yt.forEach((v) => { g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="${bd}" stroke-width="${v === 0 ? 1.2 : 0.6}" opacity="${v === 0 ? 1 : 0.6}"/>` + T(m.l - 6, Y(v) + 4, fmt(v, s.y.fmt), { anchor: "end" }); });
    const xt = s.x.ticks || niceTicks(x0, x1, s.x.n || 6);
    xt.forEach((v) => { g += T(X(v), H - m.b + 16, fmt(v, s.x.fmt), { anchor: "middle" }); });
    if (s.x.label) g += T((m.l + W - m.r) / 2, H - 6, s.x.label, { anchor: "middle", fill: t2 });
    if (s.y.label) g += T(12, (m.t + H - m.b) / 2, s.y.label, { anchor: "middle", rot: -90, fill: t2 });
    (s.refs || []).forEach((r) => { g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(r.y)}" y2="${Y(r.y)}" stroke="${col(r.color || "text-3")}" stroke-dasharray="4 4"/>` + (r.label ? T(W - m.r - 2, Y(r.y) - 4, r.label, { anchor: "end", fill: col(r.color || "text-3") }) : ""); });
    (s.vrefs || []).forEach((r) => { g += `<line x1="${X(r.x)}" x2="${X(r.x)}" y1="${m.t}" y2="${H - m.b}" stroke="${col(r.color || "text-3")}" stroke-dasharray="4 4"/>` + (r.label ? T(X(r.x) + 4, m.t + 10, r.label, { fill: col(r.color || "text-3") }) : ""); });
    (s.fits || []).forEach((f) => {
      const a = f.x0 != null ? f.x0 : x0, b = f.x1 != null ? f.x1 : x1, c = col(f.color);
      g += `<line x1="${X(a)}" x2="${X(b)}" y1="${Y(f.a + f.b * a)}" y2="${Y(f.a + f.b * b)}" stroke="${c}" stroke-width="1.6" stroke-dasharray="${f.dash || "6 4"}" opacity=".9"/>`;
      if (f.label) g += T(X(b) - 2, Y(f.a + f.b * b) - 6, f.label, { anchor: "end", fill: c });
    });
    const tips = [];
    s.series.forEach((se) => {
      const c = col(se.color);
      if (se.line) {
        const pts = se.pts.filter((p) => p.y != null).sort((a, b) => a.x - b.x);
        g += `<path d="${pts.map((p, i) => `${i ? "L" : "M"}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join("")}" fill="none" stroke="${c}" stroke-width="${se.width || 2}"${se.dash ? ` stroke-dasharray="${se.dash}"` : ""} opacity="${se.opacity || 1}"/>`;
      }
      if (se.markers !== false) se.pts.forEach((p) => {
        const pc = col(p.color || se.color), r = p.r || se.r || 3.6, hollow = p.hollow != null ? p.hollow : se.hollow;
        g += `<circle cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="${r}" fill="${hollow ? bg : pc}" stroke="${pc}" stroke-width="${hollow ? 1.6 : 0.6}" opacity="${p.opacity || se.opacity || 1}"/>`;
        if (p.label) g += T(X(p.x) + (p.ldx != null ? p.ldx : 5), Y(p.y) + (p.ldy != null ? p.ldy : -5), p.label, { size: 10, fill: t2 });
        if (p.tip) { tips.push(p.tip); g += `<circle cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="${Math.max(r + 4, 7)}" fill="transparent" data-tip="${tips.length - 1}"/>`; }
      });
    });
    g += `</svg>`;
    el.innerHTML = g + legendHTML(s.legend);
    bindTips(el, tips);
  }

  // ---------- bars ----------
  function bars(el, s) {
    if (s.horizontal) return hbars(el, s);
    const n = s.cats.length, k = s.series.length, W = drawWidth(el, s);
    // angle the category labels when they don't fit side by side (about 6 units per character at size 11)
    const rot = s.rotate || s.cats.some((c) => c.length * 6 > (W - 66) / n);
    // angled labels drop about 3.2 units per character (size 10 at 40 degrees): the bottom margin grows to fit the
    // longest, and the chart grows with it so the plot keeps its height
    const longest = Math.max(...s.cats.map((c) => c.length));
    const mb = rot ? Math.max(70, Math.round(16 + longest * 3.2)) : 34;
    const H = (s.height || 260) + (rot ? mb - 70 : 0), m = { l: 52, r: 14, t: 16, b: mb };
    const vals = s.series.flatMap((se) => se.values.map((v, j) => [v, v + ((se.err || [])[j] || 0), v - ((se.err || [])[j] || 0)]).flat()).filter((v) => v != null);
    const [y0, y1] = domain(vals.concat((s.refs || []).map((r) => r.y)), Object.assign({ zero: true }, s.y));
    const bw = (W - m.l - m.r) / n, Y = (v) => m.t + (1 - (v - y0) / (y1 - y0)) * (H - m.t - m.b);
    const bd = css("border"), t2 = css("text-2");
    let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(s.title || "")}">`;
    niceTicks(y0, y1, s.y.n || 5).forEach((v) => { g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="${bd}" stroke-width="${v === 0 ? 1.2 : 0.6}" opacity="${v === 0 ? 1 : 0.6}"/>` + T(m.l - 6, Y(v) + 4, fmt(v, s.y.fmt), { anchor: "end" }); });
    if (s.y.label) g += T(12, (m.t + H - m.b) / 2, s.y.label, { anchor: "middle", rot: -90, fill: t2 });
    const tips = [], inner = bw * 0.78, sub = inner / k;
    s.cats.forEach((c, j) => {
      const cx = m.l + bw * j + bw / 2;
      s.series.forEach((se, i) => {
        const v = se.values[j];
        if (v == null) return;
        const x = cx - inner / 2 + sub * i, yv = Y(v), yz = Y(0), fill = col((se.colors || [])[j] || se.color);
        const op = (se.opacity || [])[j] != null ? se.opacity[j] : 1;
        tips.push((se.tips || [])[j] || `${esc(c)}${k > 1 ? " · " + esc(se.name) : ""}: <b>${fmt(v, s.y.fmt)}</b>`);
        g += `<rect x="${(x + 1).toFixed(1)}" y="${Math.min(yv, yz).toFixed(1)}" width="${Math.max(sub - 2, 1).toFixed(1)}" height="${Math.max(Math.abs(yz - yv), 0.8).toFixed(1)}" fill="${fill}" opacity="${op}" data-tip="${tips.length - 1}"/>`;
        const e = (se.err || [])[j];
        if (e) { const xm = x + sub / 2; g += `<line x1="${xm}" x2="${xm}" y1="${Y(v - e)}" y2="${Y(v + e)}" stroke="${css("text")}" stroke-width="1.2"/>`; }
        if (s.values) g += T(x + sub / 2, (v >= 0 ? yv - 4 : yv + 12), fmt(v, s.y.fmt), { anchor: "middle", size: 10, fill: t2 });
      });
      const ly = H - m.b + 14;
      g += rot ? T(cx + 3, ly - 4, c, { anchor: "end", rot: -40, size: 10 }) : T(cx, ly, c, { anchor: "middle", size: n > 12 ? 9 : 11 });
    });
    (s.refs || []).forEach((r) => { g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(r.y)}" y2="${Y(r.y)}" stroke="${col(r.color || "ochre")}" stroke-dasharray="4 4"/>` + (r.label ? T(W - m.r - 2, Y(r.y) - 4, r.label, { anchor: "end", fill: col(r.color || "ochre") }) : ""); });
    g += `</svg>`;
    el.innerHTML = g + legendHTML(s.legend);
    bindTips(el, tips);
  }
  function hbars(el, s) {
    const n = s.cats.length, row = 17, W = drawWidth(el, s), m = { l: Math.min(210, Math.round(W * 0.42)), r: 24, t: 8, b: 30 }, H = m.t + m.b + row * n;
    const se = s.series[0];
    const [x0, x1] = domain(se.values.concat([0]), Object.assign({ zero: true }, s.x || {}));
    const X = (v) => m.l + (v - x0) / (x1 - x0) * (W - m.l - m.r);
    const bd = css("border"), t2 = css("text-2");
    let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(s.title || "")}">`;
    niceTicks(x0, x1, 6).forEach((v) => { g += `<line x1="${X(v)}" x2="${X(v)}" y1="${m.t}" y2="${H - m.b}" stroke="${bd}" stroke-width="${v === 0 ? 1.2 : 0.6}" opacity="${v === 0 ? 1 : 0.6}"/>` + T(X(v), H - m.b + 14, fmt(v, (s.x || {}).fmt), { anchor: "middle" }); });
    if ((s.x || {}).label) g += T((m.l + W - m.r) / 2, H - 2, s.x.label, { anchor: "middle", fill: t2 });
    const tips = [], maxChars = Math.floor((m.l - 10) / 5.6);   // labels that don't fit are shortened; the tip has the full name
    s.cats.forEach((c, j) => {
      const v = se.values[j], y = m.t + row * j, fill = col((se.colors || [])[j] || se.color);
      tips.push((se.tips || [])[j] || `${esc(c)}: <b>${fmt(v, (s.x || {}).fmt)}</b>`);
      const lab = c.length > maxChars ? c.slice(0, maxChars - 1).trimEnd() + "…" : c;
      g += T(m.l - 6, y + row * 0.7, lab, { anchor: "end", size: 10.5, fill: t2 });
      g += `<rect x="${Math.min(X(v), X(0)).toFixed(1)}" y="${(y + 3).toFixed(1)}" width="${Math.max(Math.abs(X(v) - X(0)), 0.8).toFixed(1)}" height="${row - 6}" fill="${fill}" data-tip="${tips.length - 1}"/>`;
    });
    g += `</svg>`;
    el.innerHTML = g + legendHTML(s.legend);
    bindTips(el, tips);
  }

  // ---------- heatmap ----------
  function hex2rgb(h) { const x = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(x.slice(i, i + 2), 16)); }
  function mix(a, b, t) { const A = hex2rgb(a), B = hex2rgb(b); return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * t)).join(",")})`; }
  function heatmap(el, s) {
    const n = s.labels.length, cell = s.cell || 64, m = { l: s.margin || 110, t: s.margin || 110 }, W = m.l + cell * n + 10, H = m.t + cell * n + 10;
    const lo = s.vmin != null ? s.vmin : -1, hi = s.vmax != null ? s.vmax : 1, mid = css("surface-2");
    const colr = (v) => v >= 0 ? mix(mid, css(s.pos || "teal"), Math.min(v / hi, 1)) : mix(mid, css(s.neg || "ochre"), Math.min(v / lo, 1));
    let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(s.title || "")}" style="max-width:${W}px">`;
    const tips = [];
    s.labels.forEach((lab, i) => {
      g += T(m.l - 8, m.t + cell * i + cell / 2 + 4, lab, { anchor: "end", size: 12, fill: css("text-2") });
      g += T(m.l + cell * i + cell / 2, m.t - 8, lab, { anchor: "start", size: 12, fill: css("text-2"), rot: -40 });
      s.labels.forEach((lab2, j) => {
        const v = s.matrix[i][j];
        tips.push(`${esc(lab)} × ${esc(lab2)}: <b>${fmt(v, s.fmt || "dec2")}</b>` + (s.tipNote ? `<br>${s.tipNote}` : ""));
        g += `<rect x="${m.l + cell * j}" y="${m.t + cell * i}" width="${cell - 2}" height="${cell - 2}" rx="4" fill="${colr(v)}" data-tip="${tips.length - 1}"/>`;
        g += T(m.l + cell * j + cell / 2 - 1, m.t + cell * i + cell / 2 + 4, fmt(v, s.fmt || "dec2"), { anchor: "middle", size: 12, fill: css("text"), weight: 600 });
      });
    });
    g += `</svg>`;
    el.innerHTML = g;
    bindTips(el, tips);
  }

  // drawing width in SVG units: the spec's width on wide screens; on narrow ones the container's own width, so text
  // drawn at 11 units shows at about 11px instead of shrinking with the chart
  function drawWidth(el, s) {
    const cw = el.clientWidth || 640;
    return cw < 560 ? Math.max(300, Math.round(cw)) : (s.width || 640);
  }

  const DRAW = { xy, bars, heatmap };
  function renderAll() {
    const specs = window.CHARTS || {};
    document.querySelectorAll("[data-chart]").forEach((el) => {
      const s = specs[el.dataset.chart];
      if (s && DRAW[s.type]) DRAW[s.type](el, s);
    });
  }
  document.addEventListener("click", (e) => { if (!e.target.closest || !e.target.closest("[data-tip]")) hideTip(); });
  let lastW = document.documentElement.clientWidth, timer = null;
  window.addEventListener("resize", () => {
    clearTimeout(timer);
    timer = setTimeout(() => { const w = document.documentElement.clientWidth; if (w !== lastW) { lastW = w; renderAll(); } }, 150);
  });
  renderAll();
})();
