/* ==========================================================================
   VUE RAPPORT : progression, tableau de bord, qualité, données, journal
   ========================================================================== */

import { fmt } from './format.js';
import { renderBars, renderLine, renderHeatmap, renderTable } from './charts.js';
import { initTabs } from './ui.js';

const STEP_ORDER = ['extraction', 'nettoyage', 'transformation', 'visualisation', 'rapport'];
const STEP_LABELS = {
  extraction: 'Extraction', nettoyage: 'Nettoyage', transformation: 'Transformation',
  visualisation: 'Visualisation', rapport: 'Rapport PDF',
};
const STEP_DONE = {
  extraction: 'terminée', nettoyage: 'terminé', transformation: 'terminée',
  visualisation: 'terminée', rapport: 'terminé',
};
const COLUMN_LABELS = {
  date: 'Date', vendeur: 'Vendeur', region: 'Région', produit: 'Produit', categorie: 'Catégorie',
  quantite: 'Quantité', prix_unitaire: 'Prix unitaire', remise: 'Remise', statut: 'Statut',
  ca_net: 'CA net', ca_comptabilise: 'CA comptabilisé',
};
const NUMERIC = new Set(['quantite', 'prix_unitaire', 'remise', 'ca_net', 'ca_comptabilise']);

const $ = (id) => document.getElementById(id);
let tabs = null;
let current = null;
let lastGood = null;   // dernier rapport réussi, conservé même si une génération suivante échoue
let runSteps = {};     // détails des étapes de l'exécution en cours
let resizeFrame = null;

/** Les URL de l'API commencent par « / » : on les rend relatives à la page (préfixe de chemin éventuel). */
const relative = (url) => String(url).replace(/^\//, '');

function h(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text != null) el.textContent = text;
  return el;
}

function icon(name, extra = '') {
  return `<svg class="icon ${extra}" aria-hidden="true"><use href="#${name}"/></svg>`;
}

/* ---------- États ---------- */

export function resetReport() {
  current = null;
  runSteps = {};
  $('rapport-titre').textContent = 'Génération du rapport…';
  $('rapport-meta').replaceChildren();
  const pdf = $('pdf-link');
  pdf.removeAttribute('href');
  pdf.classList.add('is-pending');
  pdf.setAttribute('aria-disabled', 'true');
  pdf.setAttribute('aria-label', 'Télécharger le PDF (disponible à la fin de la génération)');
  $('rapport-progression').hidden = false;
  $('rapport-chargement').hidden = false;
  $('rapport-erreur').hidden = true;
  $('rapport-onglets').hidden = true;
  $('rapport-corps').setAttribute('aria-busy', 'true');
  $('progress-fill').style.setProperty('--progress', 0);
  $('progress-live').textContent = 'Génération du rapport démarrée.';
  document.querySelectorAll('#steps .step').forEach((step, i) => {
    step.dataset.state = 'pending';
    step.querySelector('.step__icon').textContent = String(i + 1);
    step.querySelector('.step__detail').textContent = 'En attente';
  });
}

export function setStep(name, status, detail) {
  const step = document.querySelector(`#steps [data-step="${name}"]`);
  if (!step) return;
  if (status === 'en_cours') {
    step.dataset.state = 'active';
    step.querySelector('.step__icon').innerHTML = '<span class="spinner" aria-hidden="true"></span>';
    step.querySelector('.step__detail').textContent = 'En cours…';
    $('progress-live').textContent = `${STEP_LABELS[name]} en cours.`;
  } else if (status === 'termine') {
    if (detail) runSteps[name] = detail;
    step.dataset.state = 'done';
    step.querySelector('.step__icon').innerHTML = icon('i-check', 'icon--sm');
    step.querySelector('.step__detail').textContent = detail || 'Terminé';
    $('progress-live').textContent = `${STEP_LABELS[name]} ${STEP_DONE[name]}${detail ? ` : ${detail}` : ''}.`;
  }
  const done = document.querySelectorAll('#steps .step[data-state="done"]').length;
  const active = status === 'en_cours' ? 0.5 : 0;
  $('progress-fill').style.setProperty('--progress', ((done + active) / STEP_ORDER.length).toFixed(3));
}

export function showError(message, { source = 'demo' } = {}) {
  current = null;
  const back = document.querySelector('#rapport-erreur [data-nav="demo"]');
  if (back) back.textContent = source === 'fichiers' ? 'Modifier mes fichiers' : 'Modifier les paramètres';
  // Aucun reste d'un rapport précédent sous le message d'erreur
  $('rapport-onglets').hidden = true;
  const pdf = $('pdf-link');
  pdf.removeAttribute('href');
  pdf.classList.add('is-pending');
  pdf.setAttribute('aria-disabled', 'true');
  // Refus avant toute étape (fichier rejeté d'emblée) : la première étape porte l'échec
  const active = document.querySelector('#steps .step[data-state="active"]')
    ?? document.querySelector('#steps .step[data-state="pending"]');
  if (active) {
    active.dataset.state = 'error';
    active.querySelector('.step__icon').innerHTML = icon('i-x', 'icon--sm');
    active.querySelector('.step__detail').textContent = 'Échec';
  }
  $('rapport-titre').textContent = 'Le rapport n\'a pas pu être généré';
  $('rapport-erreur-message').textContent = message;
  $('rapport-chargement').hidden = true;
  $('rapport-erreur').hidden = false;
  $('rapport-corps').setAttribute('aria-busy', 'false');
  $('progress-live').textContent = `Échec : ${message}`;
  const errorCard = $('rapport-erreur');
  if (errorCard.getBoundingClientRect().top > window.innerHeight * 0.6) {
    errorCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

/* ---------- Rendu du rapport ---------- */

function kpiCard({ label, value, sub, tip, hero = false }) {
  const card = h('div', `card kpi${hero ? ' kpi--hero' : ''}`);
  const head = h('div', 'kpi__head');
  head.append(h('span', '', label));
  if (tip) {
    const btn = h('button', 'tip-trigger');
    btn.type = 'button';
    btn.dataset.tip = tip;
    btn.setAttribute('aria-label', `Comment est calculé : ${label}`);
    btn.setAttribute('aria-expanded', 'false');
    btn.innerHTML = icon('i-info', 'icon--sm');
    head.append(btn);
  }
  card.append(head, h('span', 'kpi__value', value));
  if (sub) card.append(h('span', 'kpi__sub', sub));
  return card;
}

function chartCard({ title, sub, wide = false }) {
  const card = h('section', `card chart-card${wide ? ' chart-card--wide' : ''}`);
  const head = h('div', 'chart-card__head');
  const titles = h('div');
  const heading = h('h2', 'chart-card__title', title);
  titles.append(heading);
  if (sub) titles.append(h('p', 'chart-card__sub', sub));
  head.append(titles);
  const body = h('div', 'chart-card__body');
  card.append(head, body);
  return { card, body };
}

function tableToggle(card, columns, rows) {
  const foot = h('div', 'chart-card__foot');
  const btn = h('button', 'link-btn');
  btn.type = 'button';
  btn.innerHTML = `${icon('i-table', 'icon--sm')}<span>Afficher les données</span>`;
  const holder = h('div', 'chart-card__table');
  holder.hidden = true;
  holder.id = `table-${Math.random().toString(36).slice(2, 9)}`;
  btn.setAttribute('aria-expanded', 'false');
  btn.setAttribute('aria-controls', holder.id);
  btn.addEventListener('click', () => {
    const open = holder.hidden;
    if (open && !holder.childElementCount) renderTable(holder, columns, rows);
    holder.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
    btn.lastChild.textContent = open ? 'Masquer les données' : 'Afficher les données';
  });
  foot.append(btn);
  card.append(foot, holder);
}

function renderOverview(panel, r) {
  panel.replaceChildren();
  const k = r.kpis;
  const primary = h('div', 'kpis');
  primary.append(
    kpiCard({ label: 'CA comptabilisé', value: fmt.eur(k.ca_total), sub: `sur ${r.periode.replace(/ - /g, '\u00a0– ')}`, hero: true,
      tip: 'Chiffre d\'affaires net (après remise) des commandes livrées ou en cours. Annulations et retours sont exclus.' }),
    kpiCard({ label: 'Commandes actives', value: fmt.int(k.nb_commandes), sub: `${fmt.plural(k.nb_annulations, 'annulée ou retournée', 'annulées ou retournées')}` }),
    kpiCard({ label: 'Panier moyen', value: fmt.eur(k.panier_moyen), tip: 'CA comptabilisé divisé par le nombre de commandes actives.' }),
    kpiCard({ label: 'Taux d\'annulation', value: fmt.pct(k.taux_annulation), tip: 'Part des lignes de commande annulées ou retournées.' }),
  );
  const secondary = h('div', 'kpis kpis--secondary');
  secondary.append(
    kpiCard({ label: 'Remises accordées', value: fmt.eur(k.remise_totale) }),
    kpiCard({ label: 'Vendeurs', value: fmt.int(k.nb_vendeurs) }),
    kpiCard({ label: 'Produits', value: fmt.int(k.nb_produits) }),
    kpiCard({ label: 'Lignes analysées', value: fmt.int(r.nb_lignes_propres), sub: `sur ${fmt.int(r.nb_lignes_brutes)} lignes brutes` }),
  );

  const charts = h('div', 'charts');
  const s = r.series;

  const months = s.mois.map((m) => ({
    label: `${m.mois_nom} ${m.annee}`,
    short: m.mois_nom.slice(0, 3) === 'Jui' ? m.mois_nom.slice(0, 4) : m.mois_nom.slice(0, 3),
    value: m.ca,
  }));
  const evo = chartCard({ title: 'Évolution mensuelle du CA', sub: 'CA comptabilisé par mois', wide: true });
  charts.append(evo.card);
  tableToggle(evo.card, [{ label: 'Mois' }, { label: 'CA comptabilisé', num: true }], months.map((m) => [m.label, fmt.eur(m.value)]));

  const sellers = chartCard({ title: 'Top vendeurs', sub: `Les ${s.vendeurs.length} meilleurs, par CA comptabilisé` });
  renderBars(sellers.body, s.vendeurs.map((v) => ({ label: v.nom, value: v.ca })), { format: fmt.eurCompact, label: 'Top vendeurs par chiffre d\'affaires' });
  charts.append(sellers.card);

  const cats = chartCard({ title: 'Répartition par catégorie', sub: 'CA et part du total' });
  renderBars(cats.body, s.categories.map((c) => ({ label: c.nom, value: c.ca, share: c.part, shareLabel: fmt.pct(c.part) })), { format: fmt.eurCompact, share: true, label: 'Chiffre d\'affaires par catégorie' });
  charts.append(cats.card);

  const heat = chartCard({ title: 'Vendeurs × régions', sub: 'CA de chaque vendeur dans chaque région · l\'échelle sous le tableau indique les montants', wide: true });
  renderHeatmap(heat.body, s.heatmap, { format: fmt.eur, formatCompact: fmt.eurCompact, label: 'Chiffre d\'affaires par vendeur et par région' });
  charts.append(heat.card);

  const products = chartCard({ title: 'Top produits', sub: 'Les références qui portent le CA' });
  renderBars(products.body, s.produits.map((p) => ({ label: p.nom, value: p.ca })), { format: fmt.eurCompact, label: 'Top produits par chiffre d\'affaires' });
  charts.append(products.card);

  const regions = chartCard({ title: 'CA par région', sub: 'CA et part du total' });
  renderBars(regions.body, s.regions.map((x) => ({ label: x.nom, value: x.ca, share: x.part, shareLabel: fmt.pct(x.part) })), { format: fmt.eurCompact, share: true, label: 'Chiffre d\'affaires par région' });
  charts.append(regions.card);

  panel.append(primary, secondary, charts);
  // La courbe se dimensionne sur la largeur réelle : on la dessine une fois insérée
  renderLine(evo.body, months, { format: fmt.eur, formatAxis: fmt.eurCompact, label: 'Évolution mensuelle du chiffre d\'affaires comptabilisé' });
  evo.body.dataset.chart = 'line';
  current.lineHost = evo.body;
  current.lineData = months;
}

function renderQuality(panel, r, source) {
  panel.replaceChildren();
  const total = r.qualite.reduce((sum, q) => sum + q.lignes, 0);
  const max = Math.max(...r.qualite.map((q) => q.lignes), 1);
  const summary = h('div', 'quality-summary');
  summary.append(h('strong', '', fmt.int(total)), h('span', 'ink-2', `anomalie${total > 1 ? 's' : ''} détectée${total > 1 ? 's' : ''} et corrigée${total > 1 ? 's' : ''} dans ${fmt.int(r.nb_lignes_brutes)} lignes brutes`));
  const intro = h('p', 'ink-2 small', 'Les exports ERP sont rarement propres. Voici ce que le nettoyage a trouvé dans les fichiers bruts, et ce qu\'il en a fait.');
  intro.style.marginBottom = 'var(--space-5)';
  const list = h('ul', 'quality-list');
  r.qualite.forEach((q) => {
    const row = h('li', `quality-row${q.lignes ? '' : ' is-zero'}`);
    const count = h('span', 'quality-row__count');
    const meter = h('span', 'quality-row__meter');
    meter.setAttribute('aria-hidden', 'true');
    const fill = h('span');
    fill.style.setProperty('--w', (q.lignes / max).toFixed(3));
    meter.append(fill);
    count.append(meter, h('span', '', q.lignes ? fmt.plural(q.lignes, 'ligne', 'lignes') : 'Aucune'));
    const fix = h('span', 'quality-row__fix');
    fix.innerHTML = icon(q.lignes ? 'i-check-circle' : 'i-check', 'icon--sm');
    fix.append(q.correction);
    row.append(h('span', 'quality-row__name', q.anomalie), count, fix);
    list.append(row);
  });
  panel.append(summary, intro, list);
  if (!total) {
    const tipBox = h('p', 'callout');
    tipBox.style.marginTop = 'var(--space-4)';
    tipBox.innerHTML = icon('i-info');
    tipBox.append(source === 'demo'
      ? ' Ces données étaient déjà propres. Activez « Ajouter des anomalies » dans le formulaire pour voir le nettoyage à l\'œuvre.'
      : ' Aucune anomalie détectée : vos fichiers étaient déjà propres.');
    panel.append(tipBox);
  }
  $('qualite-count').textContent = fmt.int(total);
}

function renderData(panel, r) {
  panel.replaceChildren();
  const head = h('div', 'data-head');
  const text = h('p', 'ink-2 small');
  text.append(h('strong', '', `${fmt.int(r.nb_lignes_donnees)} lignes`), ` nettoyées et enrichies. Aperçu des ${fmt.int(r.apercu.lignes.length)} premières.`);
  const dl = h('a', 'btn btn--secondary btn--sm');
  dl.href = relative(r.csv.url);
  dl.download = r.csv.nom;
  dl.innerHTML = `${icon('i-download', 'btn__icon btn__icon--down')}<span>Télécharger le CSV complet</span>`;
  head.append(text, dl);
  const holder = h('div');
  const columns = r.apercu.colonnes.map((c) => ({ label: COLUMN_LABELS[c] ?? c, num: NUMERIC.has(c) }));
  const rows = r.apercu.lignes.map((line) => line.map((cell, i) => {
    const col = r.apercu.colonnes[i];
    if (cell == null) return '–';
    if (col === 'remise') return fmt.pct(cell * 100);
    if (col === 'quantite') return fmt.int(cell);
    if (NUMERIC.has(col)) return fmt.eur(cell);
    return String(cell);
  }));
  renderTable(holder, columns, rows);
  holder.firstChild.classList.add('data-table-wrap');
  holder.firstChild.tabIndex = 0;
  holder.firstChild.setAttribute('role', 'region');
  holder.firstChild.setAttribute('aria-label', 'Aperçu des données nettoyées (défilement possible)');
  panel.append(head, holder);
}

function renderJournal(panel, r) {
  panel.replaceChildren();
  panel.append(h('p', 'ink-2 small', 'Les messages réellement produits par le pipeline pendant cette exécution.'));
  panel.lastChild.style.marginBottom = 'var(--space-4)';
  const pre = h('pre', 'log');
  pre.tabIndex = 0;
  pre.setAttribute('aria-label', 'Journal d\'exécution');
  r.journal.forEach((line) => {
    const span = h('span', /WARNING|ERROR/.test(line) ? 'log__warn' : '', `${line}\n`);
    pre.append(span);
  });
  panel.append(pre);
}

export function renderReport(r, { source = 'demo' } = {}) {
  current = { report: r, source };
  lastGood = { report: r, source, steps: { ...(lastGood?.report === r ? lastGood.steps : runSteps) } };
  // Tiret demi-cadratin collé au premier mois et espaces insécables : pas de tiret orphelin en fin de ligne
  const periode = r.periode.replace(/ - /g, '\u00a0– ');
  $('rapport-titre').textContent = `Rapport «\u00a0${periode}\u00a0»`;
  const meta = $('rapport-meta');
  meta.replaceChildren();
  [
    ['i-clock', `Généré en ${fmt.seconds(r.duree)}`],
    ['i-layers', fmt.plural(r.nb_fichiers, 'fichier', 'fichiers')],
    ['i-table', `${fmt.int(r.nb_lignes_brutes)} lignes brutes`],
  ].forEach(([name, text]) => {
    const chip = h('span', 'meta-chip');
    chip.innerHTML = icon(name, 'icon--sm');
    chip.append(text);
    meta.append(chip);
  });
  const pdf = $('pdf-link');
  pdf.classList.remove('is-pending');
  pdf.removeAttribute('aria-disabled');
  pdf.href = relative(r.pdf.url);
  pdf.download = r.pdf.nom;
  pdf.setAttribute('aria-label', `Télécharger le PDF (${fmt.kb(r.pdf.taille)})`);

  $('rapport-chargement').hidden = true;
  $('rapport-erreur').hidden = true;
  $('rapport-onglets').hidden = false;
  $('progress-fill').style.setProperty('--progress', 1);

  tabs ??= initTabs(document.querySelector('[data-tabs="rapport"]'), {
    onChange: () => { if (current?.lineHost) redrawLine(); },
  });
  tabs.select('tab-synthese');
  renderOverview($('panel-synthese'), r);
  renderQuality($('panel-qualite'), r, source);
  renderData($('panel-donnees'), r);
  renderJournal($('panel-journal'), r);
  tabs.refresh();
  $('rapport-corps').setAttribute('aria-busy', 'false');
  $('progress-live').textContent = `Rapport prêt, généré en ${fmt.seconds(r.duree)}.`;
}

/* La courbe se redessine à la bonne largeur (redimensionnement, thème) */
function redrawLine() {
  if (!current?.lineHost || !current.lineHost.isConnected || !current.lineHost.clientWidth) return;
  renderLine(current.lineHost, current.lineData, { format: fmt.eur, formatAxis: fmt.eurCompact, label: 'Évolution mensuelle du chiffre d\'affaires comptabilisé' });
}

export function initDashboard() {
  window.addEventListener('resize', () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => { redrawLine(); tabs?.refresh(); });
  }, { passive: true });
  document.addEventListener('themechange', () => {
    if (current?.report) renderOverview($('panel-synthese'), current.report);
  });
}

export const hasReport = () => Boolean(current?.report || lastGood);
export const isShowingReport = () => Boolean(current?.report);
export function restoreLastReport() {
  if (!lastGood) return false;
  $('rapport-progression').hidden = false;
  const saved = lastGood;
  STEP_ORDER.forEach((name) => setStep(name, 'termine', saved.steps?.[name]));
  renderReport(saved.report, { source: saved.source });
  return true;
}
export const redrawWhenVisible = () => requestAnimationFrame(() => { redrawLine(); tabs?.refresh(); });
