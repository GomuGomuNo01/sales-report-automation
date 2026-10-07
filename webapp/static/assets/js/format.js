/* Formats français partagés par toute l'interface. */

const euros = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });
const eurosCompact = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', notation: 'compact', maximumSignificantDigits: 3 });
const entier = new Intl.NumberFormat('fr-FR');
const decimal1 = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const decimal2 = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 });

export const fmt = {
  eur: (v) => euros.format(v ?? 0),
  eurCompact: (v) => eurosCompact.format(v ?? 0),
  int: (v) => entier.format(v ?? 0),
  dec: (v) => decimal2.format(v ?? 0),
  pct: (v) => `${decimal1.format(v ?? 0)} %`,
  seconds: (v) => `${decimal1.format(v ?? 0)} s`,
  kb: (bytes) => `${entier.format(Math.round((bytes ?? 0) / 1024))} Ko`,
  plural: (n, one, many) => `${entier.format(n)} ${n > 1 ? many : one}`,
};
