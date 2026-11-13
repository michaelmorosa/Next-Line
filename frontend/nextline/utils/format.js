// "1:07:42" for an hour or more, otherwise "4:52".
export function duration(seconds) {
  if (seconds == null) return '—';
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

// "2h 14m" or "48m".
export function shortDuration(seconds) {
  const m = Math.round((seconds || 0) / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`;
}

// The API works in metres; riders see US units.
const M_PER_MILE = 1609.344;
const FT_PER_M = 3.28084;

// Miles from metres, as a number string: "1.24", or "12.4" from 10 miles up.
export function miles(m) {
  const mi = (m || 0) / M_PER_MILE;
  return mi.toFixed(mi < 10 ? 2 : 1);
}

// Whole feet from metres, as a number string: "1,234".
export function feet(m) {
  return Math.round((m || 0) * FT_PER_M).toLocaleString();
}

// A short length in feet with its unit: "3 ft", "4.9 ft", "23 ft". Tenths only below 10 ft.
export function shortFeet(m) {
  const ft = (m || 0) * FT_PER_M;
  return `${ft < 10 ? Number(ft.toFixed(1)) : Math.round(ft)} ft`;
}

// Metres per second to whole miles per hour.
export function mph(metresPerSecond) {
  return Math.round((metresPerSecond || 0) * 2.23694);
}

export function seconds(s) {
  return `${(s || 0).toFixed(2)} s`;
}

// "−49 s" / "+12 s" for a time difference.
export function delta(s) {
  const n = Math.round(s);
  return `${n < 0 ? '−' : '+'}${Math.abs(n)} s`;
}

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// "Sat · Oct 4".
export function day(iso) {
  const d = new Date(iso);
  return `${DAYS[d.getDay()]} · ${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

// "Oct 4".
export function shortDate(iso) {
  const d = new Date(iso);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

// Climb rate, given in vertical metres per hour, shown in feet: "2,920 ft/h".
export function climbRate(v) {
  return v == null ? '—' : `${feet(v)} ft/h`;
}

// Arrow for a trail's direction.
export function directionLabel(direction) {
  return direction === 'climb' ? '↑ Climb' : '↓ Descent';
}

// Touchdowns (feet put down): "clean", "1 foot down", "3 feet down".
export function feetDown(n) {
  if (!n) return 'clean';
  return `${n} ${n === 1 ? 'foot' : 'feet'} down`;
}

// Today's date where the rider is, "2026-11-04". Practice is logged against it, so an evening session counts today.
export function localDay(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// "Oct 4" for a date-only "2026-10-04", read as a local date (new Date() would read it as UTC midnight).
export function dateOnly(ymd) {
  const [y, m, d] = ymd.split('-').map(Number);
  return shortDate(new Date(y, m - 1, d).toISOString());
}

// "+10 pts", "−5 pts". (Named xp from when points were called XP.)
export function xp(amount) {
  return `${amount < 0 ? '−' : '+'}${Math.abs(amount).toLocaleString()} pts`;
}
