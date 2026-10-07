/* ==========================================================================
   SYSTÈME DE MOTION
   Toutes les animations de l'interface passent par ce module et par les
   tokens CSS (--dur-*, --ease-*, --move-*, --stagger). Règles communes :
   - transform et opacity uniquement ;
   - mouvement réduit : rien ne bouge, le contenu s'affiche directement ;
   - interactions curseur réservées aux pointeurs fins (souris, trackpad) ;
   - parallaxe réservée aux grands écrans.
   ========================================================================== */

const root = document.documentElement;
const media = (query) => window.matchMedia(query);

export const prefersReducedMotion = media('(prefers-reduced-motion: reduce)');
export const finePointer = media('(hover: hover) and (pointer: fine)');
export const largeScreen = media('(min-width: 64em)');

export const motionAllowed = () => !prefersReducedMotion.matches;
export const pointerEffectsAllowed = () => finePointer.matches && motionAllowed();

/** Lit une durée de token CSS (ex. "--dur-component") en millisecondes. */
export function duration(token) {
  const raw = getComputedStyle(root).getPropertyValue(token).trim();
  if (!raw) return 0;
  return raw.endsWith('ms') ? parseFloat(raw) : parseFloat(raw) * 1000;
}

/** Attend la fin d'une transition/animation, avec un délai maximum de sécurité. */
export function afterMotion(el, token = '--dur-component') {
  return new Promise((resolve) => {
    const limit = duration(token) + 60;
    let done = false;
    const finish = () => { if (!done) { done = true; resolve(); } };
    el.addEventListener('transitionend', finish, { once: true });
    el.addEventListener('animationend', finish, { once: true });
    setTimeout(finish, limit);
  });
}

/* ---------- Apparition au défilement (fade-up, scale, slide, stagger) ---------- */

let revealObserver = null;

function reveal(el) {
  el.classList.add('is-revealed');
  afterMotion(el, '--dur-complex').then(() => el.classList.add('is-settled'));
}

/* Un élément atteint au clavier (ou contenant le focus) apparaît sans attendre */
function revealOnFocus(event) {
  for (let el = event.target.closest?.('[data-reveal]'); el; el = el.parentElement?.closest('[data-reveal]')) {
    if (el.classList.contains('is-revealed')) continue;
    el.style.setProperty('--reveal-delay', '0ms');
    reveal(el);
    revealObserver?.unobserve(el);
  }
}

export function initReveal(scope = document) {
  // Hiérarchie temporelle : chaque enfant d'un groupe décale son entrée d'un pas de --stagger
  scope.querySelectorAll('[data-reveal-group]').forEach((group) => {
    group.querySelectorAll(':scope > [data-reveal]').forEach((el, i) => {
      el.style.setProperty('--reveal-delay', `calc(${i} * var(--stagger))`);
    });
  });
  scope.querySelectorAll('[data-reveal-delay]').forEach((el) => {
    el.style.setProperty('--reveal-delay', `calc(${Number(el.dataset.revealDelay) || 0} * var(--stagger))`);
  });

  const targets = scope.querySelectorAll('[data-reveal]:not(.is-revealed)');
  if (!root.classList.contains('has-motion') || !('IntersectionObserver' in window)) {
    targets.forEach((el) => el.classList.add('is-revealed'));
    return;
  }
  revealObserver ??= new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      reveal(entry.target);
      revealObserver.unobserve(entry.target);
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });
  targets.forEach((el) => revealObserver.observe(el));
}

/** Rejoue une animation CSS déclenchée par une classe (une seule fois par élément). */
export function playOnce(el, className = 'is-animating') {
  if (!motionAllowed() || el.dataset.played) return;
  el.dataset.played = 'true';
  el.classList.add(className);
}

/** Déclenche playOnce quand l'élément entre dans la vue. */
export function playWhenVisible(el, className = 'is-animating') {
  if (!motionAllowed() || !('IntersectionObserver' in window)) return;
  const io = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) { playOnce(el, className); io.disconnect(); }
  }, { threshold: 0.2 });
  io.observe(el);
}

/* ---------- Transitions de vue ---------- */

export function transitionView(update) {
  if (document.startViewTransition && motionAllowed()) {
    const transition = document.startViewTransition(update);
    return transition.updateCallbackDone.catch(() => {});
  }
  update();
  return Promise.resolve();
}

/* ---------- Curseur : parallaxe du visuel, lueurs, CTA magnétiques ---------- */

function initPointerParallax() {
  document.querySelectorAll('[data-pointer-parallax]').forEach((container) => {
    const host = container.closest('.hero') ?? container;
    const layers = [...container.querySelectorAll('[data-depth]')];
    const amplitude = 10; // px pour une profondeur de 1, sous --move-md
    let target = { x: 0, y: 0 };
    const current = { x: 0, y: 0 };
    let frame = null;

    const tick = () => {
      current.x += (target.x - current.x) * 0.12;
      current.y += (target.y - current.y) * 0.12;
      for (const layer of layers) {
        const depth = parseFloat(layer.dataset.depth) || 0;
        layer.style.transform = `translate3d(${(-current.x * amplitude * depth).toFixed(2)}px, ${(-current.y * amplitude * depth).toFixed(2)}px, 0)`;
      }
      const moving = Math.abs(target.x - current.x) > 0.002 || Math.abs(target.y - current.y) > 0.002;
      frame = moving ? requestAnimationFrame(tick) : null;
    };

    host.addEventListener('pointermove', (event) => {
      if (!pointerEffectsAllowed() || event.pointerType !== 'mouse') return;
      const rect = host.getBoundingClientRect();
      target = {
        x: ((event.clientX - rect.left) / rect.width - 0.5) * 2,
        y: ((event.clientY - rect.top) / rect.height - 0.5) * 2,
      };
      host.style.setProperty('--hx', `${event.clientX - rect.left}px`);
      host.style.setProperty('--hy', `${event.clientY - rect.top}px`);
      host.classList.add('is-pointer');
      frame ??= requestAnimationFrame(tick);
    }, { passive: true });

    host.addEventListener('pointerleave', () => {
      if (!host.classList.contains('is-pointer')) return;
      target = { x: 0, y: 0 };
      host.classList.remove('is-pointer');
      frame ??= requestAnimationFrame(tick);
    });
  });
}

function initGlow() {
  document.addEventListener('pointermove', (event) => {
    if (!pointerEffectsAllowed()) return;
    const card = event.target.closest?.('[data-glow]');
    if (!card) return;
    const rect = card.getBoundingClientRect();
    card.style.setProperty('--mx', `${event.clientX - rect.left}px`);
    card.style.setProperty('--my', `${event.clientY - rect.top}px`);
  }, { passive: true });
}

function initMagnetic() {
  const strength = 0.16;
  const limit = 6; // px, au plus --move-sm + 2
  document.querySelectorAll('[data-magnetic]').forEach((el) => {
    el.addEventListener('pointermove', (event) => {
      if (!pointerEffectsAllowed() || event.pointerType !== 'mouse') return;
      const rect = el.getBoundingClientRect();
      const dx = Math.max(-limit, Math.min(limit, (event.clientX - rect.left - rect.width / 2) * strength));
      const dy = Math.max(-limit, Math.min(limit, (event.clientY - rect.top - rect.height / 2) * strength));
      el.style.setProperty('--mag-x', `${dx.toFixed(1)}px`);
      el.style.setProperty('--mag-y', `${dy.toFixed(1)}px`);
    }, { passive: true });
    el.addEventListener('pointerleave', () => {
      el.style.removeProperty('--mag-x');
      el.style.removeProperty('--mag-y');
    });
  });
}

/* ---------- Parallaxe au défilement (grands écrans avec souris uniquement) ----------
   Réservée aux calques de fond : décalage plafonné à 2 × --move-lg (48px). */

function initScrollParallax() {
  const items = [...document.querySelectorAll('[data-parallax]')];
  if (!items.length) return;
  let frame = null;
  const update = () => {
    frame = null;
    const active = largeScreen.matches && finePointer.matches && motionAllowed();
    for (const el of items) {
      const factor = active ? parseFloat(el.dataset.parallax) || 0 : 0;
      const offset = Math.min(48, Math.min(window.scrollY, window.innerHeight) * factor);
      el.style.transform = offset ? `translate3d(0, ${offset.toFixed(1)}px, 0)` : '';
    }
  };
  window.addEventListener('scroll', () => { frame ??= requestAnimationFrame(update); }, { passive: true });
  largeScreen.addEventListener('change', update);
  prefersReducedMotion.addEventListener('change', update);
  update();
}

export function initMotion() {
  clearTimeout(window.__motionGuard);
  if (!motionAllowed()) root.classList.remove('has-motion');
  prefersReducedMotion.addEventListener('change', () => {
    root.classList.toggle('has-motion', motionAllowed());
    document.querySelectorAll('[data-reveal]').forEach((el) => el.classList.add('is-revealed'));
  });
  initReveal();
  document.addEventListener('focusin', revealOnFocus);
  initPointerParallax();
  initGlow();
  initMagnetic();
  initScrollParallax();
}
