// Logging how a feature went, with a fallback queue for no signal. See logQueue.js.
import AsyncStorage from '@react-native-async-storage/async-storage';
import { sendJson } from '../api';
import { localDay, uuid } from './features';
import { createLogQueue, isPermanent } from './logQueue';

export const pendingLogs = createLogQueue(AsyncStorage);

// The server answered (with an error): don't queue, show the message.
const answered = (err) => Boolean(err && err.status);

// Log one feature. Returns the server's result, or { queued: true } when there's no signal.
export async function logFeature(featureId, outcome, { note = '', riddenOn = localDay(), rideId } = {}, logout) {
  const entry = { feature: featureId, outcome, note, ridden_on: riddenOn, client_id: uuid(), ...(rideId ? { ride: rideId } : {}) };
  try {
    return await sendJson(`/api/features/${featureId}/log/`, 'POST', entry, logout);
  } catch (err) {
    if (answered(err)) throw err;
    await pendingLogs.add([entry]);
    return { queued: true };
  }
}

// "Log this trail": a batch body from utils/features.batchBody. Queued log by log when there's no signal.
export async function logBatch(body, logout) {
  try {
    return await sendJson('/api/logs/batch/', 'POST', body, logout, 60000);
  } catch (err) {
    if (answered(err)) throw err;
    await pendingLogs.add(body.logs.map((l) => ({
      ...l, ridden_on: body.ridden_on, ...(body.ride ? { ride: body.ride } : {}),
    })));
    return { queued: true };
  }
}

// Send whatever is waiting. Safe to call often (screens call it when they open).
export async function syncPendingLogs(logout) {
  if (!(await pendingLogs.count())) return { sent: 0, dropped: [], left: 0 };
  return pendingLogs.flush((e) => sendJson(`/api/features/${e.feature}/log/`, 'POST', e, logout));
}

export { isPermanent };
