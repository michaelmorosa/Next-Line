import { shortFeet } from './format.js';

// Feature helpers with no React Native imports, so `npm test` can run them in Node.

// The three one-tap outcomes, in the order they're shown. Walking it is a normal, judgment-free choice.
export const OUTCOMES = [
  { key: 'cleaned', label: 'Cleaned it', short: 'Cleaned', icon: 'checkmark-circle' },
  { key: 'sketchy', label: 'Rode it, sketchy', short: 'Sketchy', icon: 'alert-circle' },
  { key: 'walked', label: 'Walked it', short: 'Walked', icon: 'walk' },
];

export const STATUS_LABELS = {
  cleaned: 'Cleaned',
  sketchy: 'Rode it sketchy',
  walked: 'Walked it',
  not_yet: 'Not yet',
};

export function outcomeLabel(key) {
  return (OUTCOMES.find((o) => o.key === key) || {}).label || key;
}

export function gradeLabel(grade) {
  return grade == null ? 'Ungraded' : `Grade ${grade}`;
}

// "Drop · Grade 4"
export function featureMeta(f) {
  return `${f.type_label} · ${gradeLabel(f.grade)}`;
}

// "Cleaned 7 of 12 features"
export function progressLine(cleaned, total) {
  if (!total) return 'No graded features yet';
  return `Cleaned ${cleaned} of ${total} feature${total === 1 ? '' : 's'}`;
}

// "+60 pts", "−5 pts"
export function points(amount) {
  return `${amount < 0 ? '−' : '+'}${Math.abs(amount).toLocaleString()} pts`;
}

const MEASUREMENTS = [
  ['drop_height_m', 'Drop', shortFeet],
  ['gap_length_m', 'Gap', shortFeet],
  ['steepness_deg', 'Steepness', (v) => `${v}°`],
];

// [{ label: 'Drop', value: '3 ft' }] for the measurements a feature has.
export function measurementList(measurements = {}) {
  return MEASUREMENTS.filter(([key]) => measurements[key] != null)
    .map(([key, label, format]) => ({ label, value: format(measurements[key]) }));
}

// The body for POST /api/logs/batch/ from the outcomes picked on "Log this trail". Features left unpicked are
// skipped, and the order follows `features` (riding order). Each log gets its own client_id so retries are safe.
export function batchBody(features, picked, { riddenOn, rideId, makeId }) {
  const logs = features
    .filter((f) => picked[f.id])
    .map((f) => ({ feature: f.id, outcome: picked[f.id], client_id: makeId() }));
  return { ridden_on: riddenOn, ...(rideId ? { ride: rideId } : {}), logs };
}

// Counts for the "Log this trail" button: { picked, cleaned }.
export function pickedSummary(picked) {
  const values = Object.values(picked).filter(Boolean);
  return { picked: values.length, cleaned: values.filter((v) => v === 'cleaned').length };
}

// Today's date where the rider is, "2026-11-04".
export function localDay(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// A random UUID v4 for client_ids. Uses crypto.randomUUID where the runtime has it.
export function uuid() {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.floor(Math.random() * 16);
    return (c === 'x' ? r : (r % 4) + 8).toString(16);
  });
}
