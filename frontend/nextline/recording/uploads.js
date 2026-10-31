import { sendJson } from '../api';
import { listPending, removePending } from './storage';

// Long tracks on a weak trailhead connection take a while.
const UPLOAD_TIMEOUT_MS = 90000;

// Upload one finished ride. The server ignores repeats of the same client_id, so retrying is always safe.
export async function uploadRide(ride, logout) {
  const saved = await sendJson('/api/rides/', 'POST', ride, logout, UPLOAD_TIMEOUT_MS);
  removePending(ride.client_id);
  return saved;
}

// Try every waiting ride. Returns { uploaded, failed }.
export async function uploadPending(logout) {
  let uploaded = 0;
  let failed = 0;
  for (const ride of listPending()) {
    try {
      await uploadRide(ride, logout);
      uploaded += 1;
    } catch {
      failed += 1;
    }
  }
  return { uploaded, failed };
}
