// The trail team's on-site captures: photos are copied into the app's own folder (the camera's cache can be
// cleared), queued with the draft, and uploaded when there's signal. See captureQueue.js.
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Directory, File, Paths } from 'expo-file-system';
import { sendForm, sendJson } from '../api';
import { createCaptureQueue } from './captureQueue';

export const captures = createCaptureQueue(AsyncStorage);

const capturesDir = () => {
  const dir = new Directory(Paths.document, 'captures');
  dir.create({ idempotent: true, intermediates: true });
  return dir;
};

// Copy a photo from the camera into the app's folder. Returns the new uri.
export function keepPhoto(uri, clientId) {
  const dest = new File(capturesDir(), `${clientId}.jpg`);
  if (dest.exists) dest.delete();
  new File(uri).copy(dest);
  return dest.uri;
}

export function discardPhotos(photos) {
  for (const p of photos) {
    try {
      const f = new File(p.uri);
      if (f.exists) f.delete();
    } catch {
      // Already gone.
    }
  }
}

export function uploadPhoto(featureId, photo, logout) {
  const form = new FormData();
  form.append('kind', photo.kind);
  form.append('client_id', photo.client_id);
  if (photo.caption) form.append('caption', photo.caption);
  form.append('file', { uri: photo.uri, name: `${photo.kind}.jpg`, type: 'image/jpeg' });
  return sendForm(`/api/team/features/${featureId}/media/`, form, logout, 120000);
}

export function captureApi(logout) {
  return {
    createFeature: (body) => sendJson('/api/team/features/', 'POST', body, logout, 30000),
    uploadPhoto: (featureId, photo) => uploadPhoto(featureId, photo, logout),
    discard: async (capture) => discardPhotos(capture.photos),
  };
}

export function uploadCaptures(logout) {
  return captures.flush(captureApi(logout));
}
