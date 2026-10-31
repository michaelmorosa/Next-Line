// The ride recorder. One per app, outside React, because GPS points arrive from a background task whether or not
// any screen is showing. Screens read it with useRecorder().
//
// While recording: GPS builds the track and live stats; the accelerometer feeds the jump and crash detectors.
// The ride is saved to a file every few seconds, and on Finish it joins the upload queue, so nothing is lost to a
// dead battery or a trail with no signal.
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants, { ExecutionEnvironment } from 'expo-constants';
import * as Location from 'expo-location';
import { Accelerometer } from 'expo-sensors';
import { createCrashDetector, createJumpDetector, magnitude } from './detectors';
import { clearActive, loadActive, saveActive, savePending } from './storage';
import { haversine, uuidv4 } from '../utils/geo';

export const LOCATION_TASK = 'nextline-ride-location';
const SETTINGS_KEY = 'recording.settings';

const SAMPLE_INTERVAL_MS = 20; // 50 Hz: enough to time airtime to a few hundredths of a second
const CHECKPOINT_MS = 15000;
const MAX_ACCURACY_M = 35; // fixes worse than this are skipped
// Same as the server's auto-pause: slower than this is stopped.
const MOVING_SPEED = 1.0;
const MAX_GAP_S = 30;
const ALTITUDE_NOISE_M = 3;
// Jumps only count while riding, so a phone dropped at the trailhead isn't one.
const JUMP_MIN_SPEED = 1.5;
const FIX_STALE_MS = 10000;
// If background GPS hasn't delivered a point by then, start foreground GPS as well.
const BACKGROUND_FALLBACK_MS = 20000;

// Expo Go can't run background location tasks: recording there uses foreground GPS, so keep the app open.
export const IN_EXPO_GO = Constants.executionEnvironment === ExecutionEnvironment.StoreClient;

export const DEFAULT_SETTINGS = { detectJumps: true, detectCrashes: true };

const blank = () => ({
  status: 'idle', // idle | recording | paused | interrupted
  clientId: null,
  startedAt: null,
  pausedMs: 0,
  pausedAt: null,
  points: [],
  jumps: [],
  distanceM: 0,
  climbM: 0,
  descentM: 0,
  movingS: 0,
  speed: 0,
  autoPaused: false,
  gpsAccuracy: null,
  lastFixAt: null,
  background: false,
  crash: null, // { at, lat, lng } when crash detection fired and the rider hasn't answered yet
  settings: DEFAULT_SETTINGS,
});

let state = blank();
let altSmooth = null;
let altRef = null;
let accelSub = null;
let watchSub = null;
let checkpointTimer = null;
let fallbackTimer = null;
let jumpDetector = createJumpDetector();
let crashDetector = createCrashDetector();
const listeners = new Set();

function emit() {
  const snapshot = { ...state };
  listeners.forEach((fn) => fn(snapshot));
}

export function subscribe(fn) {
  listeners.add(fn);
  fn({ ...state });
  return () => listeners.delete(fn);
}

export function getState() {
  return state;
}

export async function loadSettings() {
  try {
    const raw = await AsyncStorage.getItem(SETTINGS_KEY);
    return { ...DEFAULT_SETTINGS, ...(raw ? JSON.parse(raw) : {}) };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export async function saveSettings(settings) {
  await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  if (state.status !== 'idle') {
    state = { ...state, settings };
    emit();
  }
}

// { ok, background, canAskAgain, approximate }. Background ("Always") permission is what lets recording continue
// with the screen off; without it, recording only works while the app is open. Precise location is required:
// approximate location is off by kilometres, and every fix would be dropped.
export async function requestPermissions() {
  const fg = await Location.requestForegroundPermissionsAsync();
  if (fg.status !== 'granted') return { ok: false, background: false, canAskAgain: fg.canAskAgain };
  if (fg.android?.accuracy === 'coarse' || fg.ios?.accuracy === 'reduced') {
    return { ok: false, background: false, canAskAgain: false, approximate: true };
  }
  let background = false;
  try {
    background = (await Location.requestBackgroundPermissionsAsync()).status === 'granted';
  } catch {
    // Expo Go on iOS can't do background location; fall back to foreground.
  }
  return { ok: true, background };
}

async function watchInForeground() {
  if (watchSub) return;
  watchSub = await Location.watchPositionAsync(
    { accuracy: Location.Accuracy.High, timeInterval: 1000, distanceInterval: 0 },
    (location) => handleLocations([location]),
  );
}

async function startSensors(allowBackground) {
  let background = false;
  if (allowBackground && !IN_EXPO_GO) {
    try {
      await Location.startLocationUpdatesAsync(LOCATION_TASK, {
        accuracy: Location.Accuracy.High,
        timeInterval: 1000,
        distanceInterval: 2,
        activityType: Location.ActivityType.Fitness,
        pausesUpdatesAutomatically: false,
        showsBackgroundLocationIndicator: true,
        foregroundService: {
          notificationTitle: 'Next Line is recording',
          notificationBody: 'Your ride is being recorded. Open the app to finish.',
          notificationColor: '#F2994A',
        },
      });
      background = true;
    } catch {
      background = false;
    }
  }
  if (background) {
    // Starting background updates can succeed without points ever arriving; don't record nothing.
    fallbackTimer = setTimeout(() => {
      if (!state.lastFixAt && ['recording', 'paused'].includes(state.status)) watchInForeground();
    }, BACKGROUND_FALLBACK_MS);
  } else {
    await watchInForeground();
  }
  Accelerometer.setUpdateInterval(SAMPLE_INTERVAL_MS);
  accelSub = Accelerometer.addListener(onAccel);
  checkpointTimer = setInterval(checkpoint, CHECKPOINT_MS);
  state = { ...state, background };
}

async function stopSensors() {
  accelSub?.remove();
  accelSub = null;
  watchSub?.remove();
  watchSub = null;
  clearInterval(checkpointTimer);
  checkpointTimer = null;
  clearTimeout(fallbackTimer);
  fallbackTimer = null;
  try {
    if (await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK)) {
      await Location.stopLocationUpdatesAsync(LOCATION_TASK);
    }
  } catch {
    // Not running.
  }
}

function resetDetectors() {
  jumpDetector = createJumpDetector();
  crashDetector = createCrashDetector();
}

function permissionError(permission) {
  const err = new Error(permission.approximate
    ? 'Next Line needs your precise location: approximate location is off by kilometres. In Settings, open '
      + 'Location and turn on "Use precise location" (iPhone: "Precise Location").'
    : 'Location permission is needed to record a ride.');
  err.canAskAgain = permission.canAskAgain;
  return err;
}

export async function start() {
  if (state.status !== 'idle') return;
  const permission = await requestPermissions();
  if (!permission.ok) throw permissionError(permission);
  const settings = await loadSettings();
  state = { ...blank(), status: 'recording', clientId: uuidv4(), startedAt: Date.now(), settings };
  altSmooth = null;
  altRef = null;
  resetDetectors();
  await startSensors(permission.background);
  checkpoint();
  emit();
}

export function pause() {
  if (state.status !== 'recording') return;
  state = { ...state, status: 'paused', pausedAt: Date.now(), autoPaused: false };
  emit();
}

export function resume() {
  if (state.status !== 'paused') return;
  state = { ...state, status: 'recording', pausedMs: state.pausedMs + (Date.now() - state.pausedAt), pausedAt: null };
  resetDetectors();
  emit();
}

function onAccel({ x, y, z }) {
  if (state.status !== 'recording') return;
  const now = Date.now();
  const g = magnitude(x, y, z);
  const fresh = state.lastFixAt && now - state.lastFixAt < FIX_STALE_MS;
  const speed = fresh ? state.speed : 0;

  if (state.settings.detectJumps) {
    const jump = jumpDetector.push(now, g, speed >= JUMP_MIN_SPEED);
    if (jump) {
      const t = Math.round((jump.tMs - state.startedAt) / 100) / 10;
      state = { ...state, jumps: [...state.jumps, { t, airtime_s: jump.airtimeS }] };
      emit();
    }
  }
  if (state.settings.detectCrashes && !state.crash) {
    const crash = crashDetector.push(now, g, speed);
    if (crash) {
      const last = state.points[state.points.length - 1];
      state = { ...state, crash: { at: crash.tMs, lat: last?.[1] ?? null, lng: last?.[2] ?? null } };
      emit();
    }
  }
}

// GPS points, from the background task or the foreground watcher.
export function handleLocations(locations) {
  if (state.status !== 'recording') return;
  let { distanceM, climbM, descentM, movingS, speed, gpsAccuracy, lastFixAt } = state;
  const points = state.points;
  for (const location of locations) {
    const { latitude, longitude, altitude, accuracy, speed: gpsSpeed } = location.coords;
    gpsAccuracy = accuracy;
    lastFixAt = location.timestamp;
    if (accuracy != null && accuracy > MAX_ACCURACY_M) continue;
    const t = (location.timestamp - state.startedAt) / 1000;
    const prev = points[points.length - 1];
    if (t < 0 || (prev && t <= prev[0])) continue;

    const step = prev ? haversine(prev[1], prev[2], latitude, longitude) : 0;
    const dt = prev ? t - prev[0] : 0;
    speed = gpsSpeed != null && gpsSpeed >= 0 ? gpsSpeed : (dt > 0 ? step / dt : 0);
    // Only moving counts, so GPS drift while standing around doesn't add distance.
    if (prev && dt <= MAX_GAP_S && speed >= MOVING_SPEED) {
      movingS += dt;
      distanceM += step;
    }
    if (altitude != null) {
      altSmooth = altSmooth == null ? altitude : altSmooth * 0.8 + altitude * 0.2;
      if (altRef == null) {
        altRef = altSmooth;
      } else if (altSmooth - altRef >= ALTITUDE_NOISE_M) {
        climbM += altSmooth - altRef;
        altRef = altSmooth;
      } else if (altRef - altSmooth >= ALTITUDE_NOISE_M) {
        descentM += altRef - altSmooth;
        altRef = altSmooth;
      }
    }
    points.push([
      Math.round(t * 10) / 10,
      Math.round(latitude * 1e6) / 1e6,
      Math.round(longitude * 1e6) / 1e6,
      altitude == null ? null : Math.round(altitude * 10) / 10,
      Math.round(speed * 100) / 100,
    ]);
  }
  state = { ...state, distanceM, climbM, descentM, movingS, speed, gpsAccuracy, lastFixAt, autoPaused: speed < MOVING_SPEED };
  emit();
}

function checkpoint() {
  if (!['recording', 'paused'].includes(state.status)) return;
  try {
    const { status, crash, background, ...saved } = state;
    saveActive(saved);
  } catch {
    // Disk full or similar; the next checkpoint tries again.
  }
}

function rideFromState(s) {
  const pausedMs = s.pausedMs + (s.pausedAt ? Date.now() - s.pausedAt : 0);
  return {
    client_id: s.clientId,
    started_at: new Date(s.startedAt).toISOString(),
    elapsed_s: Math.max(0, Math.round((Date.now() - s.startedAt - pausedMs) / 1000)),
    track: s.points,
    jumps: s.jumps,
  };
}

// Stop recording and queue the ride for upload. Returns the queued ride.
export async function finish() {
  if (state.status === 'idle') return null;
  await stopSensors();
  const ride = rideFromState(state);
  // An interrupted ride's elapsed time stops at its last saved point, not now.
  if (state.status === 'interrupted') {
    const last = state.points[state.points.length - 1];
    ride.elapsed_s = Math.round(last ? last[0] : 0);
  }
  savePending(ride);
  clearActive();
  state = blank();
  emit();
  return ride;
}

export async function discard() {
  await stopSensors();
  clearActive();
  state = blank();
  emit();
}

export function dismissCrash() {
  crashDetector.reset();
  state = { ...state, crash: null };
  emit();
}

// On app start: a ride that was recording when the app was killed comes back as "interrupted".
export async function restore() {
  if (state.status !== 'idle') return;
  const saved = loadActive();
  if (!saved?.clientId) return;
  await stopSensors();
  state = { ...blank(), ...saved, status: 'interrupted', pausedAt: null };
  emit();
}

export async function resumeInterrupted() {
  if (state.status !== 'interrupted') return;
  const permission = await requestPermissions();
  if (!permission.ok) throw permissionError(permission);
  // The time the app was dead counts as paused.
  const last = state.points[state.points.length - 1];
  const lastAt = state.startedAt + (last ? last[0] * 1000 : 0);
  state = { ...state, status: 'recording', pausedMs: state.pausedMs + Math.max(0, Date.now() - lastAt) };
  altSmooth = null;
  altRef = null;
  resetDetectors();
  await startSensors(permission.background);
  emit();
}
