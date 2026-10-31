// Rides are kept as files on the phone until the server has them: the ride being recorded (saved every few
// seconds, so a dead battery or a killed app doesn't lose it) and finished rides waiting for signal to upload.
// Files rather than AsyncStorage, which on Android can't hold one value bigger than about 2 MB.
import { Directory, File, Paths } from 'expo-file-system';

const ridesDir = () => {
  const dir = new Directory(Paths.document, 'rides');
  dir.create({ idempotent: true, intermediates: true });
  return dir;
};

const activeFile = () => new File(ridesDir(), 'active.json');
const pendingFile = (clientId) => new File(ridesDir(), `pending-${clientId}.json`);

function readJson(file) {
  try {
    return file.exists ? JSON.parse(file.textSync()) : null;
  } catch {
    return null;
  }
}

export function saveActive(ride) {
  activeFile().write(JSON.stringify(ride));
}

export function loadActive() {
  return readJson(activeFile());
}

export function clearActive() {
  const file = activeFile();
  if (file.exists) file.delete();
}

export function savePending(ride) {
  pendingFile(ride.client_id).write(JSON.stringify(ride));
}

export function removePending(clientId) {
  const file = pendingFile(clientId);
  if (file.exists) file.delete();
}

// Finished rides not uploaded yet, oldest first.
export function listPending() {
  return ridesDir().list()
    .filter((f) => f instanceof File && f.name.startsWith('pending-'))
    .map(readJson)
    .filter(Boolean)
    .sort((a, b) => a.started_at.localeCompare(b.started_at));
}
