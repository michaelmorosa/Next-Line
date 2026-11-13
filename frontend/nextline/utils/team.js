import { shortFeet } from './format.js';

// Trail team helpers with no React Native imports (tested in Node).

export const FEATURE_TYPES = [
  { key: 'drop', label: 'Drop' },
  { key: 'jump', label: 'Jump' },
  { key: 'corner', label: 'Corner' },
  { key: 'rock_garden', label: 'Rock garden' },
  { key: 'roots', label: 'Roots' },
  { key: 'steep', label: 'Steep' },
  { key: 'skinny', label: 'Skinny' },
  { key: 'climb', label: 'Climb' },
  { key: 'other', label: 'Other' },
];

export const GRADES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

export const PHOTO_SLOTS = [
  { kind: 'approach', label: 'Approach' },
  { kind: 'feature', label: 'Feature' },
  { kind: 'exit', label: 'Landing / exit' },
];

// The measurement worth taking on site for each type, if any. Lengths are typed in feet and stored in metres.
const FT_PER_M = 3.28084;
const MEASUREMENT = {
  drop: { field: 'drop_height_m', label: 'Drop height (ft)', feet: true },
  jump: { field: 'gap_length_m', label: 'Gap length (ft)', feet: true },
  steep: { field: 'steepness_deg', label: 'Steepness (°)' },
};

export function measurementFor(type) {
  return MEASUREMENT[type] || null;
}

// What the team typed (feet for lengths) -> the API value (metres).
export function measurementToApi(m, n) {
  return m.feet && n != null ? Math.round((n / FT_PER_M) * 1000) / 1000 : n;
}

// The API value -> what the team sees in the input, to a tenth of a foot.
export function measurementFromApi(m, v) {
  return m.feet && v != null ? Number((v * FT_PER_M).toFixed(1)) : v;
}

// "4.5" -> 4.5, "" -> null, "abc" -> undefined (invalid).
export function parseMeasurement(text) {
  const t = String(text ?? '').trim().replace(',', '.');
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 && n < 1000 ? n : undefined;
}

// What's still missing before a capture can be saved. GPS within 100 ft and a type and grade are enough; photos are
// strongly encouraged but a capture without one can be saved and photographed later.
export const MAX_ACCURACY_M = 30.48;

export function captureProblems({ position, type, grade, measurementText }) {
  const problems = [];
  if (!position) problems.push('Waiting for GPS.');
  else if (position.accuracy != null && position.accuracy > MAX_ACCURACY_M) {
    problems.push(`GPS is ±${shortFeet(position.accuracy)}. Wait for ±${shortFeet(MAX_ACCURACY_M)} or better.`);
  }
  if (!type) problems.push('Pick a type.');
  if (!grade) problems.push('Pick a grade.');
  if (parseMeasurement(measurementText) === undefined) problems.push('The measurement should be a number.');
  return problems;
}

// The draft body sent to POST /api/team/features/.
export function captureBody({ clientId, position, type, grade, name, trailId, measurementText }) {
  const body = {
    client_id: clientId, type, grade, lat: position.latitude, lng: position.longitude,
    ...(name?.trim() ? { name: name.trim() } : {}),
    ...(trailId ? { trail: trailId } : {}),
  };
  const m = measurementFor(type);
  const value = parseMeasurement(measurementText);
  if (m && value != null) body[m.field] = measurementToApi(m, value);
  return body;
}

// The best GPS fix so far: the most accurate, preferring newer ones of equal accuracy.
export function betterFix(current, next) {
  if (!current) return next;
  if (next.accuracy == null) return current;
  return current.accuracy == null || next.accuracy <= current.accuracy ? next : current;
}
