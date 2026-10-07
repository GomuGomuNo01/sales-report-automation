/* ==========================================================================
   DÉMO : formulaire, validation, envoi et lecture du flux de progression
   ========================================================================== */

import { fmt } from './format.js';
import { afterMotion } from './motion.js';
import { setLoading, flashSuccess, toast } from './ui.js';
import { resetReport, setStep, showError, renderReport } from './dashboard.js';

const MAX_FILES = 30;
const MAX_TOTAL = 20 * 1024 * 1024;
const MAX_PERIODE = 60;

const $ = (id) => document.getElementById(id);
const form = () => $('demo-form');
const state = { files: [], running: false, lastRequest: null, controller: null };
let navigate = () => {};

/* ---------- Erreurs de champ (affichées sous le champ concerné) ---------- */

function setFieldError(name, message) {
  const field = $(`field-${name}`);
  const error = $(`${name}-error`);
  const input = name === 'fichiers' ? $('fichiers') : $(name);
  if (!field || !error) return;
  error.textContent = message || '';
  field.classList.toggle('is-invalid', Boolean(message));
  if (input) {
    if (message) input.setAttribute('aria-invalid', 'true');
    else input.removeAttribute('aria-invalid');
  }
  if (name === 'fichiers') $('dropzone').classList.toggle('is-invalid', Boolean(message));
  if (message) field.classList.remove('is-valid');
}

function clearErrors() {
  ['fichiers', 'periode'].forEach((n) => setFieldError(n, ''));
  $('form-error').textContent = '';
}

/* ---------- Période ---------- */

function validatePeriode({ quiet = false } = {}) {
  const input = $('periode');
  const value = input.value.trim();
  const field = $('field-periode');
  if (value.length > MAX_PERIODE) {
    setFieldError('periode', `${MAX_PERIODE} caractères maximum (actuellement ${value.length}).`);
    return false;
  }
  setFieldError('periode', '');
  field.classList.toggle('is-valid', !quiet && value.length > 0);
  return true;
}

/* ---------- Fichiers ---------- */

function validateFiles() {
  const files = state.files;
  if (!files.length) return 'Ajoutez au moins un fichier CSV.';
  if (files.length > MAX_FILES) return `${MAX_FILES} fichiers maximum (vous en avez ajouté ${files.length}).`;
  const wrong = files.find((f) => !/\.csv$/i.test(f.name));
  if (wrong) return `« ${wrong.name} » n'est pas un fichier .csv.`;
  const empty = files.find((f) => f.size === 0);
  if (empty) return `« ${empty.name} » est vide.`;
  const total = files.reduce((sum, f) => sum + f.size, 0);
  if (total > MAX_TOTAL) return `Taille totale trop importante : ${fmt.dec(total / 1048576)} Mo pour 20 Mo maximum.`;
  return '';
}

function renderFiles() {
  const list = $('file-list');
  list.replaceChildren();
  state.files.forEach((file, index) => {
    const item = document.createElement('li');
    item.className = 'file-item';
    item.innerHTML = '<svg class="icon file-item__icon" aria-hidden="true"><use href="#i-file"/></svg><span class="file-item__name"></span><span class="file-item__size"></span><button class="btn btn--ghost btn--icon btn--sm" type="button"><svg class="icon icon--sm" aria-hidden="true"><use href="#i-x"/></svg></button>';
    item.querySelector('.file-item__name').textContent = file.name;
    item.querySelector('.file-item__size').textContent = file.size < 1024 ? `${file.size} o` : fmt.kb(file.size);
    const remove = item.querySelector('button');
    remove.setAttribute('aria-label', `Retirer ${file.name}`);
    remove.addEventListener('click', () => {
      state.files.splice(index, 1);
      renderFiles();
      if ($('fichiers-error').textContent) setFieldError('fichiers', state.files.length ? validateFiles() : '');
      const next = $('file-list').querySelectorAll('button')[Math.min(index, state.files.length - 1)];
      (next ?? $('fichiers')).focus();
    });
    list.append(item);
  });
}

function addFiles(fileList) {
  const known = new Set(state.files.map((f) => `${f.name}:${f.size}`));
  for (const file of fileList) {
    const key = `${file.name}:${file.size}`;
    if (!known.has(key)) { state.files.push(file); known.add(key); }
  }
  renderFiles();
  setFieldError('fichiers', validateFiles());
}

function initDropzone() {
  const zone = $('dropzone');
  const input = $('fichiers');
  let depth = 0;
  zone.addEventListener('dragenter', (e) => { e.preventDefault(); depth += 1; zone.classList.add('is-dragover'); });
  zone.addEventListener('dragover', (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
  zone.addEventListener('dragleave', () => { depth = Math.max(0, depth - 1); if (!depth) zone.classList.remove('is-dragover'); });
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    depth = 0;
    zone.classList.remove('is-dragover');
    if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files);
  });
  input.addEventListener('change', () => { addFiles(input.files); input.value = ''; });
}

/* ---------- Source de données ---------- */

function currentSource() {
  return form().querySelector('input[name="source"]:checked').value;
}

function syncPanels({ animate = true } = {}) {
  const source = currentSource();
  form().querySelectorAll('[data-panel]').forEach((panel) => {
    const show = panel.dataset.panel === source;
    if (show && panel.hidden) {
      panel.hidden = false;
      if (animate) {
        panel.classList.add('panel-in');
        afterMotion(panel).then(() => panel.classList.remove('panel-in'));
      }
    } else if (!show) {
      panel.hidden = true;
    }
  });
  if (source === 'demo') setFieldError('fichiers', '');
}

/* ---------- Requête ---------- */

function buildRequest({ forceDemo = false } = {}) {
  const data = new FormData();
  const source = forceDemo ? 'demo' : currentSource();
  data.append('source', source);
  data.append('anomalies', forceDemo ? 'true' : String($('demo-form').elements.anomalies.checked));
  data.append('periode', forceDemo ? '' : $('periode').value.trim());
  if (source === 'fichiers') state.files.forEach((f) => data.append('fichiers', f, f.name));
  return data;
}

function triggers() {
  return [...document.querySelectorAll('[data-action="run-demo"]'), $('submit-btn')];
}

async function readStream(response, onLine) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index;
    while ((index = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, index).trim();
      buffer = buffer.slice(index + 1);
      if (line) onLine(JSON.parse(line));
    }
  }
  if (buffer.trim()) onLine(JSON.parse(buffer));
}

async function generate(request, { origin } = {}) {
  if (state.running) return;
  state.running = true;
  state.lastRequest = request;
  state.controller = new AbortController();
  const buttons = triggers();
  setLoading(buttons, true);
  resetReport();
  navigate('rapport');

  let finished = false;
  try {
    const response = await fetch('/api/rapports', { method: 'POST', body: request, signal: state.controller.signal });
    if (response.status === 422) {
      const body = await response.json().catch(() => ({}));
      finished = true;
      showError('Le formulaire contient des erreurs. Corrigez-les puis relancez la génération.');
      navigate('demo');
      const errors = body.erreurs ?? {};
      Object.entries(errors).forEach(([field, message]) => {
        if (field === 'fichiers' || field === 'periode') setFieldError(field, message);
        else $('form-error').textContent = message;
      });
      toast('Vérifiez le formulaire', { type: 'error', text: Object.values(errors)[0] ?? '' });
      return;
    }
    if (!response.ok || !response.body) {
      throw new Error(`Le serveur a répondu avec une erreur (${response.status}). Réessayez dans un instant.`);
    }
    await readStream(response, (event) => {
      if (event.type === 'etape') setStep(event.etape, event.statut, event.detail);
      else if (event.type === 'resultat') {
        finished = true;
        renderReport(event.rapport);
        $('last-report').hidden = false;
        flashSuccess(origin === 'form' ? $('submit-btn') : null);
        toast('Rapport prêt', { text: `Généré en ${fmt.seconds(event.rapport.duree)} à partir de ${fmt.int(event.rapport.nb_lignes_brutes)} lignes.` });
      } else if (event.type === 'erreur') {
        finished = true;
        showError(event.message);
      }
    });
    if (!finished) throw new Error('La génération s\'est interrompue avant la fin. Réessayez.');
  } catch (error) {
    if (error.name === 'AbortError') return;
    const message = error instanceof TypeError
      ? 'Connexion au serveur impossible. Vérifiez votre connexion puis réessayez.'
      : error.message;
    showError(message);
    toast('Échec de la génération', { type: 'error', text: message });
  } finally {
    state.running = false;
    state.controller = null;
    setLoading(buttons, false);
  }
}

export function cancelGeneration() {
  state.controller?.abort();
}

export function retry() {
  if (state.lastRequest) generate(state.lastRequest, { origin: 'retry' });
}

export function runDemo() {
  generate(buildRequest({ forceDemo: true }), { origin: 'cta' });
}

export function initDemo({ onNavigate }) {
  navigate = onNavigate;
  const f = form();
  f.querySelectorAll('input[name="source"]').forEach((radio) => radio.addEventListener('change', () => syncPanels()));
  syncPanels({ animate: false });
  initDropzone();
  $('periode').addEventListener('input', () => validatePeriode());
  $('periode').addEventListener('blur', () => validatePeriode());

  f.addEventListener('submit', (event) => {
    event.preventDefault();
    clearErrors();
    const okPeriode = validatePeriode({ quiet: true });
    let firstInvalid = okPeriode ? null : $('periode');
    if (currentSource() === 'fichiers') {
      const message = validateFiles();
      if (message) { setFieldError('fichiers', message); firstInvalid ??= $('fichiers'); }
    }
    if (firstInvalid) { firstInvalid.focus(); return; }
    generate(buildRequest(), { origin: 'form' });
  });
}
