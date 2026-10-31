import AsyncStorage from '@react-native-async-storage/async-storage';
import { API_URL } from '@env';

const REQUEST_TIMEOUT_MS = 20000;
export const TIMEOUT_MESSAGE = "Couldn't reach the server. Check your connection and try again.";

// fetch with a time limit, so a wrong server address or dead connection shows an error instead of spinning forever.
export async function timedFetch(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (err) {
    if (controller.signal.aborted) throw new Error(TIMEOUT_MESSAGE);
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function refreshToken() {
  const refresh = await AsyncStorage.getItem('refresh');
  if (!refresh) throw new Error('No refresh token available');
  const res = await timedFetch(`${API_URL}/api/auth/jwt/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) throw new Error('Failed to refresh token');
  const data = await res.json();
  await AsyncStorage.setItem('access', data.access);
  // Refresh tokens rotate; keep the new one.
  if (data.refresh) await AsyncStorage.setItem('refresh', data.refresh);
  return data.access;
}

export async function authorizedFetch(url, options = {}, logout, timeoutMs) {
  const send = (access) => timedFetch(`${API_URL}${url}`, {
    ...options,
    headers: { ...options.headers, Authorization: `Bearer ${access}` },
  }, timeoutMs);

  const res = await send(await AsyncStorage.getItem('access'));
  if (res.status !== 401) return res;
  let access;
  try {
    access = await refreshToken();
  } catch {
    if (logout) await logout();
    throw new Error('Your session expired. Please log in again.');
  }
  return send(access);
}

// The first readable error message in a DRF error response ({"error": ...}, {"detail": ...} or {"field": [...]}).
export function errorMessage(data, fallback = 'Something went wrong. Please try again.') {
  if (!data || typeof data !== 'object') return fallback;
  const first = (value) => (Array.isArray(value) ? first(value[0]) : value);
  for (const key of ['error', 'detail', 'non_field_errors']) {
    if (data[key]) return String(first(data[key]));
  }
  const field = Object.keys(data)[0];
  return field ? String(first(data[field])) : fallback;
}

// Fetch JSON as the logged-in rider, or throw an Error with the server's message.
export async function fetchJson(url, { logout, timeoutMs, ...options } = {}) {
  const res = await authorizedFetch(url, options, logout, timeoutMs);
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(errorMessage(data));
    err.status = res.status;
    throw err;
  }
  return data;
}

export function sendJson(url, method, body, logout, timeoutMs) {
  return fetchJson(url, {
    logout,
    method,
    timeoutMs,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

// Logged-out requests (log in, sign up).
export async function publicPost(url, body) {
  const res = await timedFetch(`${API_URL}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(errorMessage(data));
    err.status = res.status;
    throw err;
  }
  return data;
}
