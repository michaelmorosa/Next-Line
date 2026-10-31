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

export function km(metres) {
  return (metres / 1000).toFixed(metres < 10000 ? 2 : 1);
}

export function metres(m) {
  return Math.round(m || 0).toLocaleString();
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

// Climb rate in vertical metres per hour: "890 m/h".
export function climbRate(v) {
  return v == null ? '—' : `${Math.round(v).toLocaleString()} m/h`;
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
