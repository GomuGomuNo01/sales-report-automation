/* ==========================================================================
   POINT D'ENTRÉE : initialisation et navigation entre les vues
   Trois vues dans la même page : « accueil », « rapport » et « presentation »
   (la vidéo de 40 s, ouverte depuis l'onglet « Présentation »). La navigation
   passe par l'historique du navigateur (bouton Retour compris) et par une
   transition de vue courte qui ne bloque jamais l'interaction.
   ========================================================================== */

import { initMotion, transitionView, afterMotion, motionAllowed } from './motion.js';
import { initTheme, initHeader, initMobileMenu, initScrollSpy, initTabs, initTooltips, initDialogs } from './ui.js';
import { initDashboard, hasReport, isShowingReport, restoreLastReport, redrawWhenVisible } from './dashboard.js';
import { initDemo, runDemo, retry, cancelGeneration } from './demo.js';

const views = {
  accueil: document.getElementById('vue-accueil'),
  rapport: document.getElementById('vue-rapport'),
  presentation: document.getElementById('vue-presentation'),
};
// Vues ouvertes par une adresse propre (#rapport, #presentation)
const HASH_VIEWS = ['rapport', 'presentation'];
const video = document.getElementById('presentation-video');
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
  if (view !== 'rapport' && from === 'rapport') cancelGeneration();
  if (from === 'presentation') video?.pause();

  const update = () => {
    Object.entries(views).forEach(([name, el]) => { el.hidden = name !== view; });
    currentView = view;
    if (pendingView === view) pendingView = null;
    header.dataset.solid = String(view !== 'accueil');
    document.querySelectorAll('[data-nav="presentation"]').forEach((link) => {
      if (view === 'presentation') link.setAttribute('aria-current', 'true');
      else link.removeAttribute('aria-current');
    });
    // Défilement instantané : la vue entrante doit apparaître en place, sans glisser
    if (view !== 'accueil') {
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
    } else if (view === 'presentation') {
      focusWithoutScroll(document.getElementById('presentation-titre'));
      playPresentation();
    } else if (section) {
      focusWithoutScroll(document.getElementById(`${section}-titre`) ?? document.getElementById(section));
    } else if (returnFocus?.isConnected && returnFocus.offsetParent !== null) {
      returnFocus.focus({ preventScroll: true });
    } else {
      focusWithoutScroll(document.getElementById('hero-titre'));
    }
  });

  if (push) {
    const url = HASH_VIEWS.includes(view) ? `#${view}` : (section ? `#${section}` : window.location.pathname);
    history.pushState({ view, section }, '', url);
  }
}

/* ---------- Vidéo de présentation ---------- */
// Lecture automatique sans le son (condition des navigateurs), sauf si le système
// demande de limiter les animations : la vidéo attend alors un clic sur « lecture ».
function playPresentation() {
  if (!video || !motionAllowed()) return;
  video.muted = true;
  video.play().catch(() => {});
}

function initChapters() {
  document.querySelectorAll('[data-chapitre]').forEach((button) => {
    button.addEventListener('click', () => {
      if (!video) return;
      video.currentTime = Number(button.dataset.chapitre);
      video.muted = false;  // un clic autorise le son
      video.play().catch(() => {
        // Lecture refusée par le navigateur : la vidéo reste positionnée sur le chapitre
      });
    });
  });
}

function scrollToSection(id, { instant = false } = {}) {
  const target = document.getElementById(id);
  if (!target) return;
  target.scrollIntoView({ behavior: instant ? 'instant' : 'smooth', block: 'start' });
}

function onNavigate(target, { restore = false } = {}) {
  if (target === 'rapport') {
    // Seul un clic explicite sur « Revoir le rapport » restaure le dernier rapport réussi ;
    // une nouvelle génération ouvre la vue rapport sur son propre état de progression.
    if (restore && !isShowingReport()) restoreLastReport();
    go('rapport');
  }
  else if (target === 'presentation') go('presentation');
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
      onNavigate(target, { restore: target === 'rapport' });
      return;
    }
    // Ancres de l'accueil cliquées depuis la vue rapport ou la vue présentation
    const anchor = event.target.closest('a[href^="#"]');
    if (anchor && currentView !== 'accueil') {
      const id = anchor.getAttribute('href').slice(1);
      if (id && !HASH_VIEWS.includes(id) && id !== 'contenu') {
        event.preventDefault();
        go('accueil', { section: id });
      }
    }
    const action = event.target.closest('[data-action]');
    if (action?.dataset.action === 'run-demo') runDemo();
    if (action?.dataset.action === 'retry') retry();
  });

  window.addEventListener('popstate', (event) => {
    const fromHash = window.location.hash.slice(1);
    const view = event.state?.view ?? (HASH_VIEWS.includes(fromHash) ? fromHash : 'accueil');
    if (view === 'rapport' && !hasReport()) { history.replaceState({ view: 'accueil' }, '', window.location.pathname); go('accueil', { push: false }); return; }
    go(view, { push: false, section: event.state?.section ?? null });
  });

  // Un lien direct vers #rapport sans rapport en mémoire revient à l'accueil ;
  // un lien direct vers #presentation ouvre la vidéo
  if (window.location.hash === '#rapport') history.replaceState({ view: 'accueil' }, '', window.location.pathname);
  else if (window.location.hash === '#presentation') {
    history.replaceState({ view: 'accueil' }, '', window.location.pathname);
    go('presentation');
  }
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
      next.srcset = `assets/img/rapport-p${page}-400.webp 400w, assets/img/rapport-p${page}-800.webp 800w`;
      next.src = `assets/img/rapport-p${page}-800.webp`;
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
// Streamlit Community Cloud affiche l'appli dans une iframe (/~/+/), masquée tant
// qu'elle n'a pas signalé être prête : on envoie le message qu'attend la page hôte.
if (window.parent !== window) {
  window.parent.postMessage({ stCommVersion: 1, type: 'GUEST_READY' }, '*');
}

initTheme();
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
initChapters();
initNavigation();
