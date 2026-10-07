/* ==========================================================================
   POINT D'ENTRÉE : initialisation et navigation entre les vues
   Deux vues dans la même page : « accueil » et « rapport ». La navigation
   passe par l'historique du navigateur (bouton Retour compris) et par une
   transition de vue courte qui ne bloque jamais l'interaction.
   ========================================================================== */

import { initMotion, transitionView, afterMotion } from './motion.js';
import { initHeader, initMobileMenu, initScrollSpy, initTabs, initTooltips, initDialogs } from './ui.js';
import { initDashboard, hasReport, isShowingReport, restoreLastReport, redrawWhenVisible } from './dashboard.js';
import { initDemo, runDemo, retry, cancelGeneration } from './demo.js';

const views = {
  accueil: document.getElementById('vue-accueil'),
  rapport: document.getElementById('vue-rapport'),
};
const header = document.getElementById('site-header');
let currentView = 'accueil';
let landingScroll = 0;
let returnFocus = null;  // élément qui a ouvert la vue rapport
let pendingView = null;  // vue visée pendant une transition en cours

function focusWithoutScroll(el) {
  if (!el) return;
  if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1');
  el.focus({ preventScroll: true });
}

/**
 * Affiche une vue. `section` (id) fait défiler l'accueil jusqu'à une section.
 */
function go(view, { push = true, section = null } = {}) {
  const from = pendingView ?? currentView;
  const changing = view !== from;
  if (!changing) {
    if (section) scrollToSection(section);
    return;
  }
  pendingView = view;
  if (from === 'accueil' && currentView === 'accueil') {
    landingScroll = window.scrollY;
    const active = document.activeElement;
    returnFocus = active && active !== document.body && views.accueil.contains(active) ? active : null;
  }
  if (view === 'accueil' && from === 'rapport') cancelGeneration();

  const update = () => {
    Object.entries(views).forEach(([name, el]) => { el.hidden = name !== view; });
    currentView = view;
    if (pendingView === view) pendingView = null;
    header.dataset.solid = String(view === 'rapport');
    // Défilement instantané : la vue entrante doit apparaître en place, sans glisser
    if (view === 'rapport') {
      window.scrollTo({ top: 0, behavior: 'instant' });
    } else if (section) {
      scrollToSection(section, { instant: true });
    } else {
      window.scrollTo({ top: landingScroll, behavior: 'instant' });
    }
  };

  const startViewTransition = Boolean(document.startViewTransition);
  transitionView(update).then(() => {
    if (!startViewTransition) {
      views[view].classList.add('is-entering');
      afterMotion(views[view], '--dur-transition').then(() => views[view].classList.remove('is-entering'));
    }
    if (view === 'rapport') {
      focusWithoutScroll(document.getElementById('rapport-titre'));
      redrawWhenVisible();
    } else if (section) {
      focusWithoutScroll(document.getElementById(`${section}-titre`) ?? document.getElementById(section));
    } else if (returnFocus?.isConnected && returnFocus.offsetParent !== null) {
      returnFocus.focus({ preventScroll: true });
    } else {
      focusWithoutScroll(document.getElementById('hero-titre'));
    }
  });

  if (push) {
    const url = view === 'rapport' ? '#rapport' : (section ? `#${section}` : window.location.pathname);
    history.pushState({ view, section }, '', url);
  }
}

function scrollToSection(id, { instant = false } = {}) {
  const target = document.getElementById(id);
  if (!target) return;
  target.scrollIntoView({ behavior: instant ? 'instant' : 'smooth', block: 'start' });
}

function onNavigate(target) {
  if (target === 'rapport') {
    if (!isShowingReport()) restoreLastReport();
    go('rapport');
  }
  else if (target === 'demo') go('accueil', { section: 'demo' });
  else go('accueil');
}

function initNavigation() {
  // Liens et boutons de navigation internes
  document.addEventListener('click', (event) => {
    const nav = event.target.closest('[data-nav]');
    if (nav) {
      event.preventDefault();
      const target = nav.dataset.nav;
      if (target === 'accueil' && currentView === 'accueil') {
        window.scrollTo({ top: 0, behavior: 'smooth' });
        history.pushState({ view: 'accueil' }, '', window.location.pathname);
        return;
      }
      if (target === 'rapport' && !hasReport()) return;
      onNavigate(target);
      return;
    }
    // Ancres de l'accueil cliquées depuis la vue rapport
    const anchor = event.target.closest('a[href^="#"]');
    if (anchor && currentView === 'rapport') {
      const id = anchor.getAttribute('href').slice(1);
      if (id && id !== 'rapport' && id !== 'contenu') {
        event.preventDefault();
        go('accueil', { section: id });
      }
    }
    const action = event.target.closest('[data-action]');
    if (action?.dataset.action === 'run-demo') runDemo();
    if (action?.dataset.action === 'retry') retry();
  });

  window.addEventListener('popstate', (event) => {
    const view = event.state?.view ?? (window.location.hash === '#rapport' ? 'rapport' : 'accueil');
    if (view === 'rapport' && !hasReport()) { history.replaceState({ view: 'accueil' }, '', window.location.pathname); go('accueil', { push: false }); return; }
    go(view, { push: false, section: event.state?.section ?? null });
  });

  // Un lien direct vers #rapport sans rapport en mémoire revient à l'accueil
  if (window.location.hash === '#rapport') history.replaceState({ view: 'accueil' }, '', window.location.pathname);
  else history.replaceState({ view: 'accueil' }, '', window.location.href);
}

/* ---------- Aperçu des pages du rapport ---------- */
function initShowcase() {
  const tablist = document.querySelector('[data-tabs="pages"]');
  const figure = document.getElementById('page-preview');
  if (!tablist || !figure) return;
  let img = figure.querySelector('img');
  let token = 0;

  initTabs(tablist, {
    sharedPanel: true,
    onChange: (tab) => {
      const page = tab.dataset.page;
      const mine = ++token;
      figure.setAttribute('aria-busy', 'true');
      figure.classList.add('is-loading');
      const next = new Image();
      next.className = 'paper__img is-entering';
      next.width = 800;
      next.height = 1131;
      next.decoding = 'async';
      next.alt = tab.dataset.alt;
      next.sizes = '(min-width: 64em) 30rem, 90vw';
      next.srcset = `/assets/img/rapport-p${page}-400.webp 400w, /assets/img/rapport-p${page}-800.webp 800w`;
      next.src = `/assets/img/rapport-p${page}-800.webp`;
      const swap = () => {
        if (mine !== token) return;
        figure.removeAttribute('aria-busy');
        figure.classList.remove('is-loading');
        figure.setAttribute('aria-labelledby', tab.id);
        const previous = img;
        previous.classList.add('is-leaving');
        figure.append(next);
        requestAnimationFrame(() => requestAnimationFrame(() => next.classList.remove('is-entering')));
        img = next;
        afterMotion(previous).then(() => previous.remove());
      };
      (next.decode ? next.decode() : Promise.resolve()).then(swap, swap);
    },
  });
}

/* ---------- Narration « Fonctionnement » : l'illustration suit l'étape lue ---------- */
function initStory() {
  const story = document.querySelector('[data-story]');
  if (!story) return;
  const steps = [...story.querySelectorAll('.story-step')];
  const visuals = [...story.querySelectorAll('.story-visual')];
  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const index = Number(entry.target.dataset.step);
      steps.forEach((s, i) => s.classList.toggle('is-active', i === index));
      visuals.forEach((v, i) => v.classList.toggle('is-active', i === index));
    });
  }, { rootMargin: '-45% 0px -45% 0px' });
  steps.forEach((s) => io.observe(s));
}

/* ---------- Démarrage ---------- */
initMotion();
initHeader();
initMobileMenu();
initScrollSpy();
initTooltips();
initDialogs();
initShowcase();
initStory();
initDashboard();
initDemo({ onNavigate });
initNavigation();
