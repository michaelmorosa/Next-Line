// Feature logs waiting for signal. Logging at the trail often happens with none, so a log that can't be sent is
// kept and sent later. Every log carries a client_id, so sending one twice is harmless: the server keeps one.
//
// `storage` is anything with async getItem/setItem (AsyncStorage in the app, a Map-backed fake in tests), and
// `send(entry)` posts one log, throwing an Error with `.status` when the server answered.

const KEY = 'pendingFeatureLogs';

// Errors the server answered with that won't change on retry (the feature closed, a bad date). Dropped from the
// queue and reported, rather than retried forever.
export function isPermanent(err) {
  return Boolean(err && err.status && err.status >= 400 && err.status < 500 && err.status !== 401 && err.status !== 429);
}

export function createLogQueue(storage, key = KEY) {
  const read = async () => {
    try {
      const raw = await storage.getItem(key);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  };
  const write = (entries) => storage.setItem(key, JSON.stringify(entries));

  return {
    read,

    // Queue logs ({ feature, outcome, ridden_on, client_id, note?, ride? }). Ones already queued are skipped.
    async add(entries) {
      const current = await read();
      const known = new Set(current.map((e) => e.client_id));
      const added = entries.filter((e) => e.client_id && !known.has(e.client_id));
      await write([...current, ...added]);
      return current.length + added.length;
    },

    async count() {
      return (await read()).length;
    },

    // Send everything waiting, oldest first. Stops at the first network failure (no signal yet).
    // Returns { sent, dropped: [{ entry, message }], left }.
    async flush(send) {
      const entries = await read();
      const done = new Set();
      const dropped = [];
      for (const entry of entries) {
        try {
          await send(entry);
          done.add(entry.client_id);
        } catch (err) {
          if (isPermanent(err)) {
            done.add(entry.client_id);
            dropped.push({ entry, message: err.message });
          } else {
            break;
          }
        }
      }
      // Re-read, so logs queued while this was sending aren't lost.
      const left = (await read()).filter((e) => !done.has(e.client_id));
      await write(left);
      return { sent: done.size - dropped.length, dropped, left: left.length };
    },
  };
}
