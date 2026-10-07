/* ==========================================================================
   COMPOSANTS D'INTERFACE
   Header · Menu mobile · Suivi de section · Tabs · Tooltip · Toast ·
   Dialog · États des boutons
   ========================================================================== */

import { afterMotion, duration, finePointer } from './motion.js';

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

/* ---------- Thème jour/nuit ----------
   Le script en tête de index.html pose data-theme avant le premier affichage.
   Le bouton bascule et mémorise le choix ; sans choix enregistré, la page suit
   le thème du système, y compris s'il change pendant la visite. */
const THEME_KEY = 'theme';
const THEME_COLOR = { light: '#f8fafc', dark: '#090d16' };

export const isDarkTheme = () => document.documentElement.dataset.theme === 'dark';

function syncThemeToggles() {
  const label = isDarkTheme() ? 'Activer le thème clair' : 'Activer le thème sombre';
  document.querySelectorAll('[data-action="toggle-theme"]').forEach((btn) => btn.setAttribute('aria-label', label));
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLOR[theme]);
  syncThemeToggles();
  document.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
}

function savedTheme() {
  try { return localStorage.getItem(THEME_KEY); } catch { return null; }
}

export function initTheme() {
  syncThemeToggles();
  document.querySelectorAll('[data-action="toggle-theme"]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const theme = isDarkTheme() ? 'light' : 'dark';
      try { localStorage.setItem(THEME_KEY, theme); } catch { /* stockage indisponible : choix valable pour cette visite */ }
      applyTheme(theme);
    });
  });
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (!savedTheme()) applyTheme(e.matches ? 'dark' : 'light');
  });
}

/* ---------- Header : compact et flouté après le défilement ---------- */
export function initHeader() {
  const header = document.getElementById('site-header');
  const sentinel = document.createElement('div');
  sentinel.setAttribute('aria-hidden', 'true');
  sentinel.style.cssText = 'position:absolute;top:0;left:0;width:1px;height:24px;pointer-events:none';
  document.body.prepend(sentinel);
  new IntersectionObserver(([entry]) => {
    header.dataset.scrolled = String(!entry.isIntersecting);
  }).observe(sentinel);
}

/* ---------- Menu mobile ---------- */
export function initMobileMenu() {
  const toggle = document.querySelector('.menu-toggle');
  const menu = document.getElementById('mobile-menu');
  const backdrop = document.querySelector('.mobile-menu-backdrop');
  if (!toggle || !menu) return;
  let open = false;

  const focusables = () => [toggle, ...menu.querySelectorAll(FOCUSABLE)];

  function setOpen(next, { restoreFocus = true } = {}) {
    if (next === open) return;
    open = next;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Fermer le menu' : 'Ouvrir le menu');
    document.body.classList.toggle('is-locked', open);
    // Le reste de la page devient inerte : ni focus ni lecteur d'écran derrière le menu
    document.querySelectorAll('main, .site-footer, .brand, .site-header__actions > a').forEach((el) => { el.inert = open; });
    if (open) {
      menu.hidden = false;
      backdrop.hidden = false;
      requestAnimationFrame(() => {
        menu.classList.add('is-open');
        backdrop.classList.add('is-open');
        menu.querySelector(FOCUSABLE)?.focus({ preventScroll: true });
      });
    } else {
      menu.classList.remove('is-open');
      backdrop.classList.remove('is-open');
      afterMotion(menu).then(() => { if (!open) { menu.hidden = true; backdrop.hidden = true; } });
      if (restoreFocus) toggle.focus({ preventScroll: true });
    }
  }

  toggle.addEventListener('click', () => setOpen(!open));
  backdrop.addEventListener('click', () => setOpen(false));
  menu.addEventListener('click', (event) => {
    if (event.target.closest('a, [data-action]')) setOpen(false, { restoreFocus: false });
  });
  document.addEventListener('keydown', (event) => {
    if (!open) return;
    if (event.key === 'Escape') { setOpen(false); return; }
    if (event.key !== 'Tab') return;
    const items = focusables();
    const index = items.indexOf(document.activeElement);
    const next = event.shiftKey ? (index <= 0 ? items.length - 1 : index - 1) : (index === items.length - 1 ? 0 : index + 1);
    event.preventDefault();
    items[next].focus();
  });
  window.matchMedia('(min-width: 48em)').addEventListener('change', (e) => { if (e.matches) setOpen(false, { restoreFocus: false }); });
  return { close: () => setOpen(false, { restoreFocus: false }) };
}

/* ---------- Suivi de section dans la navigation ---------- */
export function initScrollSpy() {
  const links = [...document.querySelectorAll('[data-spy]')];
  const sections = links.map((link) => document.getElementById(link.dataset.spy)).filter(Boolean);
  const visible = new Set();
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => (e.isIntersecting ? visible.add(e.target.id) : visible.delete(e.target.id)));
    const current = sections.find((s) => visible.has(s.id))?.id;
    links.forEach((link) => {
      if (link.dataset.spy === current) link.setAttribute('aria-current', 'true');
      else link.removeAttribute('aria-current');
    });
  }, { rootMargin: '-45% 0px -50% 0px' });
  sections.forEach((s) => io.observe(s));
}

/* ---------- Tabs (ARIA, clavier, indicateur glissant) ---------- */
export function initTabs(tablist, { onChange, sharedPanel = false } = {}) {
  const tabs = [...tablist.querySelectorAll('[role="tab"]')];
  const indicator = tablist.querySelector('.tablist__indicator');
  const vertical = tablist.getAttribute('aria-orientation') === 'vertical';

  const placeIndicator = () => {
    if (!indicator) return;
    const tab = tabs.find((t) => t.getAttribute('aria-selected') === 'true');
    if (!tab || !tab.offsetWidth) return;
    tablist.style.setProperty('--tab-x', `${tab.offsetLeft}px`);
    tablist.style.setProperty('--tab-w', `${tab.offsetWidth}px`);
  };

  function select(tab, { focus = false } = {}) {
    tabs.forEach((t) => {
      const selected = t === tab;
      t.setAttribute('aria-selected', String(selected));
      t.tabIndex = selected ? 0 : -1;
      if (!sharedPanel) {
        const panel = document.getElementById(t.getAttribute('aria-controls'));
        if (panel) { panel.hidden = !selected; panel.classList.toggle('is-active', selected); }
      }
    });
    if (focus) tab.focus();
    placeIndicator();
    onChange?.(tab);
  }

  tablist.addEventListener('click', (event) => {
    const tab = event.target.closest('[role="tab"]');
    if (tab && tab.getAttribute('aria-selected') !== 'true') select(tab);
  });
  tablist.addEventListener('keydown', (event) => {
    const index = tabs.indexOf(document.activeElement);
    if (index < 0) return;
    const prev = vertical ? ['ArrowUp', 'ArrowLeft'] : ['ArrowLeft'];
    const next = vertical ? ['ArrowDown', 'ArrowRight'] : ['ArrowRight'];
    let target = null;
    if (prev.includes(event.key)) target = tabs[(index - 1 + tabs.length) % tabs.length];
    else if (next.includes(event.key)) target = tabs[(index + 1) % tabs.length];
    else if (event.key === 'Home') target = tabs[0];
    else if (event.key === 'End') target = tabs[tabs.length - 1];
    if (!target) return;
    event.preventDefault();
    select(target, { focus: true });
  });

  if ('ResizeObserver' in window) new ResizeObserver(placeIndicator).observe(tablist);
  placeIndicator();
  return { select: (id) => { const tab = tabs.find((t) => t.id === id); if (tab) select(tab); }, refresh: placeIndicator };
}

/* ---------- Tooltip (survol, focus clavier, toucher) ---------- */
export function initTooltips() {
  const tip = document.getElementById('tooltip');
  let owner = null;
  let showTimer = null;

  function position(trigger) {
    const r = trigger.getBoundingClientRect();
    const t = tip.getBoundingClientRect();
    const margin = 8;
    let top = r.top - t.height - margin;
    if (top < margin) top = r.bottom + margin;
    const left = Math.min(Math.max(margin, r.left + r.width / 2 - t.width / 2), window.innerWidth - t.width - margin);
    tip.style.top = `${Math.round(top)}px`;
    tip.style.left = `${Math.round(left)}px`;
  }

  function show(trigger) {
    clearTimeout(showTimer);
    owner?.setAttribute('aria-expanded', 'false');
    owner = trigger;
    tip.textContent = trigger.dataset.tip;
    tip.hidden = false;
    trigger.setAttribute('aria-describedby', 'tooltip');
    trigger.setAttribute('aria-expanded', 'true');
    position(trigger);
    requestAnimationFrame(() => tip.classList.add('is-visible'));
  }

  function hide() {
    clearTimeout(showTimer);
    if (!owner) return;
    owner.removeAttribute('aria-describedby');
    owner.setAttribute('aria-expanded', 'false');
    owner = null;
    tip.classList.remove('is-visible');
    afterMotion(tip, '--dur-micro').then(() => { if (!owner) tip.hidden = true; });
  }

  document.addEventListener('pointerover', (e) => {
    const trigger = e.target.closest?.('[data-tip]');
    if (!trigger || !finePointer.matches || trigger === owner) return;
    clearTimeout(showTimer);
    showTimer = setTimeout(() => show(trigger), 120);
  });
  document.addEventListener('pointerout', (e) => {
    const trigger = e.target.closest?.('[data-tip]');
    if (trigger && !trigger.contains(e.relatedTarget) && finePointer.matches) hide();
  });
  document.addEventListener('focusin', (e) => { const t = e.target.closest?.('[data-tip]'); if (t) show(t); });
  document.addEventListener('focusout', (e) => { if (e.target.closest?.('[data-tip]')) hide(); });
  document.addEventListener('click', (e) => {
    const trigger = e.target.closest?.('[data-tip]');
    if (trigger) { if (owner === trigger && !finePointer.matches) hide(); else show(trigger); }
    else hide();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hide(); });
  window.addEventListener('scroll', () => {
    if (owner && owner === document.activeElement) position(owner);
    else hide();
  }, { passive: true });
}

/* ---------- Toast ---------- */
export function toast(title, { text = '', type = 'success', timeout = 5000 } = {}) {
  const region = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = `toast toast--${type}`;
  if (type === 'error') el.setAttribute('role', 'alert');
  const icon = type === 'error' ? 'i-alert' : 'i-check-circle';
  el.innerHTML = `<svg class="icon toast__icon" aria-hidden="true"><use href="#${icon}"/></svg><div class="toast__body"><span class="toast__title"></span><span class="toast__text"></span></div><button class="btn btn--ghost btn--icon" type="button" aria-label="Fermer la notification"><svg class="icon icon--sm" aria-hidden="true"><use href="#i-x"/></svg></button>`;
  el.querySelector('.toast__title').textContent = title;
  const body = el.querySelector('.toast__text');
  if (text) body.textContent = text; else body.remove();

  let timer = null;
  const remove = () => {
    clearTimeout(timer);
    el.classList.add('is-leaving');
    afterMotion(el, '--dur-micro').then(() => el.remove());
  };
  const arm = () => { clearTimeout(timer); timer = setTimeout(remove, timeout); };
  el.querySelector('button').addEventListener('click', remove);
  el.addEventListener('pointerenter', () => clearTimeout(timer));
  el.addEventListener('pointerleave', arm);
  el.addEventListener('focusin', () => clearTimeout(timer));
  el.addEventListener('focusout', arm);
  region.append(el);
  arm();
}

/* ---------- Dialog (natif, ouverture et fermeture animées) ---------- */
export function initDialogs() {
  function close(dialog) {
    if (!dialog.open || dialog.classList.contains('is-closing')) return;
    dialog.classList.add('is-closing');
    afterMotion(dialog, '--dur-micro').then(() => {
      dialog.classList.remove('is-closing');
      dialog.close();
    });
  }
  document.addEventListener('click', (event) => {
    const opener = event.target.closest('[data-dialog-open]');
    if (opener) {
      const dialog = document.getElementById(opener.dataset.dialogOpen);
      dialog?.showModal();
      return;
    }
    const closer = event.target.closest('[data-dialog-close]');
    if (closer) close(closer.closest('dialog'));
  });
  document.querySelectorAll('dialog').forEach((dialog) => {
    dialog.addEventListener('cancel', (event) => { event.preventDefault(); close(dialog); });
    dialog.addEventListener('click', (event) => { if (event.target === dialog) close(dialog); });
  });
}

/* ---------- États des boutons ---------- */
export function setLoading(buttons, loading) {
  for (const btn of buttons) {
    btn.classList.toggle('is-loading', loading);
    btn.classList.remove('is-success');
    if (loading) btn.setAttribute('aria-busy', 'true'); else btn.removeAttribute('aria-busy');
  }
}

export function flashSuccess(btn, label = 'Rapport prêt') {
  if (!btn) return;
  let state = btn.querySelector('.btn__state--success');
  if (!state) {
    state = document.createElement('span');
    state.className = 'btn__state btn__state--success';
    state.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-check"/></svg><span></span>';
    btn.append(state);
  }
  state.querySelector('span').textContent = label;
  btn.classList.add('is-success');
  setTimeout(() => btn.classList.remove('is-success'), Math.max(1400, duration('--dur-complex') * 2));
}
