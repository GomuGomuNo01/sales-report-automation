/* ==========================================================================
   GRAPHIQUES (SVG et HTML natifs, sans bibliothèque)
   Règles : une série = une couleur (--viz-series), marques fines, grille en
   filet, texte en couleurs de texte, étiquettes sélectives, infobulle au
   survol ET au clavier, équivalent tableau pour chaque graphique.
   Les libellés viennent des données : toujours insérés avec textContent.
   ========================================================================== */

import { playWhenVisible } from './motion.js';

const SVG_NS = 'http://www.w3.org/2000/svg';

function svgEl(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

function h(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text != null) el.textContent = text;
  return el;
}

/** Pas « propre » (1, 2, 2.5, 5 × 10^n) pour des graduations lisibles. */
function niceStep(raw) {
  const power = 10 ** Math.floor(Math.log10(raw || 1));
  const n = raw / power;
  const nice = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
  return nice * power;
}

/* ---------- Barres horizontales ---------- */
export function renderBars(container, rows, { format, share = false, label }) {
  container.replaceChildren();
  const max = Math.max(...rows.map((r) => r.value), 0) || 1;
  const list = h('ol', 'bars');
  list.setAttribute('aria-label', label);
  rows.forEach((row, i) => {
    const item = h('li', 'bar-row');
    item.style.setProperty('--i', i);
    const name = h('span', 'bar-row__label', row.label);
    name.title = row.label;
    const plot = h('span', 'bar-row__plot');
    const bar = h('span', 'bar-row__bar');
    bar.setAttribute('aria-hidden', 'true');
    bar.style.width = `calc(${(row.value / max).toFixed(4)} * (100% - 7.5rem))`;
    const value = h('span', 'bar-row__value', format(row.value));
    if (share && row.share != null) {
      value.append(' ');
      value.append(h('span', 'bar-row__share', `· ${row.shareLabel}`));
    }
    plot.append(bar, value);
    item.append(name, plot);
    list.append(item);
  });
  container.append(list);
  playWhenVisible(list);
}

/* ---------- Courbe (évolution) ---------- */
export function renderLine(container, points, { format, formatAxis, label }) {
  container.replaceChildren();
  container.classList.add('line-chart');
  if (container.dataset.played) { container.classList.remove('is-animating'); container.classList.add('is-drawn'); }
  container.tabIndex = 0;
  container.setAttribute('role', 'group');
  container.setAttribute('aria-label', `${label}. Graphique interactif : utilisez les flèches gauche et droite pour lire chaque mois.`);

  const live = h('p', 'visually-hidden');
  live.setAttribute('aria-live', 'polite');
  const tip = h('div', 'chart-tip');
  tip.setAttribute('aria-hidden', 'true');
  const tipValue = h('span', 'chart-tip__value');
  const tipLabel = h('span', 'chart-tip__label');
  tipLabel.append(h('span', 'chart-tip__key'), h('span', ''));
  tip.append(tipValue, tipLabel);

  const width = Math.max(280, container.clientWidth || 640);
  const compact = width < 520;
  const height = compact ? 220 : 280;
  const m = { top: 28, right: compact ? 16 : 72, bottom: 30, left: compact ? 44 : 56 };
  const innerW = width - m.left - m.right;
  const innerH = height - m.top - m.bottom;

  const max = Math.max(...points.map((p) => p.value), 0);
  const step = niceStep(max / 4);
  const top = Math.max(step, Math.ceil(max / step) * step);
  const x = (i) => m.left + (points.length === 1 ? innerW / 2 : (i * innerW) / (points.length - 1));
  const y = (v) => m.top + innerH - (v / top) * innerH;

  const svg = svgEl('svg', { viewBox: `0 0 ${width} ${height}`, width, height, 'aria-hidden': 'true' });

  for (let v = 0; v <= top + 1e-9; v += step) {
    const yy = Math.round(y(v)) + 0.5;
    svg.append(svgEl('line', { class: v === 0 ? 'lc-axis' : 'lc-grid', x1: m.left, x2: width - m.right, y1: yy, y2: yy }));
    const tick = svgEl('text', { class: 'lc-tick', x: m.left - 8, y: yy + 4, 'text-anchor': 'end' });
    tick.textContent = formatAxis(v);
    svg.append(tick);
  }
  const every = compact ? Math.ceil(points.length / 6) : 1;
  points.forEach((p, i) => {
    if (i % every) return;
    const t = svgEl('text', { class: 'lc-tick', x: x(i), y: height - 8, 'text-anchor': 'middle' });
    t.textContent = p.short;
    svg.append(t);
  });

  const linePath = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  svg.append(svgEl('path', { class: 'lc-area', d: `${linePath} L${x(points.length - 1).toFixed(1)},${y(0)} L${x(0).toFixed(1)},${y(0)} Z` }));
  svg.append(svgEl('path', { class: 'lc-line', d: linePath, pathLength: 1 }));

  // Étiquettes sélectives : le dernier point et le maximum
  const last = points.length - 1;
  const peak = points.reduce((best, p, i) => (p.value > points[best].value ? i : best), 0);
  const annotate = (i, text, muted) => {
    const anchor = i === last && !compact ? 'start' : 'middle';
    const tx = i === last && !compact ? x(i) + 10 : x(i);
    const ty = i === last && !compact ? y(points[i].value) + 4 : y(points[i].value) - 12;
    const t = svgEl('text', { class: `lc-label${muted ? ' lc-label--muted' : ''}`, x: tx, y: ty, 'text-anchor': anchor });
    t.textContent = text;
    svg.append(t);
  };
  if (peak !== last) annotate(peak, `Pic : ${formatAxis(points[peak].value)}`, true);
  svg.append(svgEl('circle', { class: 'lc-dot', cx: x(last), cy: y(points[last].value), r: 4 }));
  if (!compact) annotate(last, formatAxis(points[last].value));

  const cross = svgEl('line', { class: 'lc-cross', y1: m.top, y2: m.top + innerH });
  const hoverDot = svgEl('circle', { class: 'lc-hover-dot', r: 5 });
  const hit = svgEl('rect', { x: m.left - 12, y: 0, width: innerW + 24, height, fill: 'transparent' });
  svg.append(cross, hoverDot, hit);
  container.append(svg, tip, live);

  let active = -1;
  function show(i) {
    active = Math.max(0, Math.min(last, i));
    const p = points[active];
    const cx = x(active);
    const cy = y(p.value);
    cross.setAttribute('x1', cx); cross.setAttribute('x2', cx);
    hoverDot.setAttribute('cx', cx); hoverDot.setAttribute('cy', cy);
    tipValue.textContent = format(p.value);
    tipLabel.lastChild.textContent = p.label;
    container.classList.add('is-hover');
    const scale = container.clientWidth / width;
    const tipW = tip.offsetWidth || 140;
    let left = cx * scale + 12;
    if (left + tipW > container.clientWidth) left = cx * scale - tipW - 12;
    tip.style.setProperty('--tx', `${Math.max(0, left)}px`);
    tip.style.setProperty('--ty', `${Math.max(0, cy * scale - 56)}px`);
    live.textContent = `${p.label} : ${format(p.value)}`;
  }
  const hide = () => { container.classList.remove('is-hover'); };

  hit.addEventListener('pointermove', (event) => {
    const rect = svg.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * width;
    const i = Math.round(((px - m.left) / innerW) * last);
    show(i);
  });
  hit.addEventListener('pointerleave', hide);
  container.addEventListener('focus', () => show(active < 0 ? last : active));
  container.addEventListener('blur', hide);
  container.addEventListener('keydown', (event) => {
    const moves = { ArrowLeft: -1, ArrowRight: 1, Home: -Infinity, End: Infinity };
    if (event.key === 'Escape') { hide(); return; }
    if (!(event.key in moves)) return;
    event.preventDefault();
    const next = moves[event.key] === -Infinity ? 0 : moves[event.key] === Infinity ? last : (active < 0 ? last : active) + moves[event.key];
    show(next);
  });

  playWhenVisible(container);
}

/* ---------- Heatmap (tableau HTML, échelle séquentielle bleue) ---------- */
const RAMP_LIGHT = ['#f1f6fd', '#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab', '#184f95', '#104281'];
const RAMP_DARK = ['#141c2a', '#13284a', '#15335f', '#184f95', '#1c5cab', '#256abf', '#2a78d6', '#3987e5', '#5598e7', '#6da7ec', '#86b6ef', '#9ec5f4', '#b7d3f6'];

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function renderHeatmap(container, data, { format, formatCompact, label }) {
  container.replaceChildren();
  const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const ramp = dark ? RAMP_DARK : RAMP_LIGHT;
  const all = data.valeurs.flat();
  const max = Math.max(...all, 0) || 1;
  const colorFor = (v) => ramp[Math.min(ramp.length - 1, Math.round((v / max) * (ramp.length - 1)))];

  const wrap = h('div', 'heatmap-wrap');
  wrap.tabIndex = 0;
  wrap.setAttribute('role', 'region');
  wrap.setAttribute('aria-label', `${label} (défilement horizontal possible)`);
  const table = h('table', 'heatmap');
  table.append(h('caption', 'visually-hidden', label));
  const thead = h('thead');
  const headRow = h('tr');
  const corner = h('th');
  corner.append(h('span', 'visually-hidden', 'Vendeur'));
  headRow.append(corner);
  data.regions.forEach((r) => { const th = h('th', '', r); th.scope = 'col'; headRow.append(th); });
  thead.append(headRow);
  const tbody = h('tbody');
  data.vendeurs.forEach((v, i) => {
    const tr = h('tr');
    const th = h('th', '', v);
    th.scope = 'row';
    tr.append(th);
    data.regions.forEach((region, j) => {
      const value = data.valeurs[i][j] ?? 0;
      const bg = colorFor(value);
      const td = h('td', '', value ? formatCompact(value) : '–');
      td.style.background = bg;
      td.style.color = luminance(bg) > 0.4 ? '#0b1220' : '#ffffff';
      td.title = `${v} · ${region} : ${format(value)}`;
      tr.append(td);
    });
    tbody.append(tr);
  });
  table.append(thead, tbody);
  wrap.append(table);

  const legend = h('div', 'heat-legend');
  const scale = h('span', 'heat-legend__scale');
  scale.style.background = `linear-gradient(90deg, ${ramp.join(', ')})`;
  scale.setAttribute('aria-hidden', 'true');
  legend.append(h('span', '', formatCompact(0)), scale, h('span', '', formatCompact(max)));
  container.append(wrap, legend);
}

/* ---------- Tableau équivalent (accessibilité) ---------- */
export function renderTable(container, columns, rows) {
  container.replaceChildren();
  const wrap = h('div', 'table-wrap');
  const table = h('table', 'table');
  const thead = h('thead');
  const tr = h('tr');
  columns.forEach((c) => { const th = h('th', c.num ? 'is-num' : '', c.label); th.scope = 'col'; tr.append(th); });
  thead.append(tr);
  const tbody = h('tbody');
  rows.forEach((row) => {
    const r = h('tr');
    row.forEach((cell, i) => r.append(h('td', columns[i].num ? 'is-num' : '', cell)));
    tbody.append(r);
  });
  table.append(thead, tbody);
  wrap.append(table);
  container.append(wrap);
}
