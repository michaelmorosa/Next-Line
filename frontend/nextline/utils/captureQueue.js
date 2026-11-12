// Features captured on site by the trail team, waiting to upload. Signal at a trail is often poor, so a capture is
// saved on the phone first and sent in steps: create the draft, then each photo. Each step is safe to repeat (the
// draft and every photo carry a client_id), so after a dropped connection the queue just carries on where it was.
//
// Pure logic: `storage` has async getItem/setItem, and `api` has
//   createFeature(body) -> { id }        (POST /api/team/features/)
//   uploadPhoto(featureId, photo)        (POST /api/team/features/<id>/media/)
//   discard(capture)                      (delete the capture's local photo files once uploaded)
// Errors with `.status` came from the server; anything else is treated as "no signal".

const KEY = 'pendingFeatureCaptures';

const permanent = (err) => Boolean(err && err.status && err.status >= 400 && err.status < 500
  && err.status !== 401 && err.status !== 429);

export function createCaptureQueue(storage, key = KEY) {
  const read = async () => {
    try {
      const raw = await storage.getItem(key);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  };
  const write = (captures) => storage.setItem(key, JSON.stringify(captures));

  // Save one capture's progress without losing captures added meanwhile.
  const update = async (clientId, changes) => {
    const all = await read();
    await write(all.map((c) => (c.client_id === clientId ? { ...c, ...changes } : c)));
  };
  const remove = async (clientId) => {
    await write((await read()).filter((c) => c.client_id !== clientId));
  };

  return {
    read,

    // capture: { client_id, body: {...feature fields, client_id}, photos: [{ kind, uri, client_id }], created_at }
    async add(capture) {
      const all = await read();
      if (all.some((c) => c.client_id === capture.client_id)) return all.length;
      const fresh = { ...capture, feature_id: null, error: null, photos: capture.photos.map((p) => ({ ...p, uploaded: false })) };
      await write([...all, fresh]);
      return all.length + 1;
    },

    async count() {
      return (await read()).length;
    },

    // Remove a capture the team doesn't want (e.g. one the server rejected), deleting its local files.
    async drop(clientId, api) {
      const capture = (await read()).find((c) => c.client_id === clientId);
      if (capture && api?.discard) await api.discard(capture);
      await remove(clientId);
    },

    // Upload what's waiting, oldest first. Stops at the first network failure.
    // Returns { uploaded: [feature ids], failed: [{ client_id, message }], left }.
    async flush(api) {
      const uploaded = [];
      const failed = [];
      for (const capture of await read()) {
        if (capture.error) {  // rejected earlier: left for the team to fix or drop
          failed.push({ client_id: capture.client_id, message: capture.error });
          continue;
        }
        let featureId = capture.feature_id;
        try {
          if (!featureId) {
            featureId = (await api.createFeature(capture.body)).id;
            await update(capture.client_id, { feature_id: featureId });
          }
          const photos = [...capture.photos];
          for (let i = 0; i < photos.length; i += 1) {
            if (photos[i].uploaded) continue;
            try {
              await api.uploadPhoto(featureId, photos[i]);
            } catch (err) {
              if (!permanent(err)) throw err;
              // A photo the server can't read shouldn't hold up the rest. Note it and move on.
              photos[i] = { ...photos[i], rejected: err.message };
            }
            photos[i] = { ...photos[i], uploaded: true };
            await update(capture.client_id, { photos });
          }
          if (api.discard) await api.discard(capture);
          await remove(capture.client_id);
          uploaded.push(featureId);
        } catch (err) {
          if (permanent(err)) {
            await update(capture.client_id, { error: err.message });
            failed.push({ client_id: capture.client_id, message: err.message });
            continue;
          }
          break;  // no signal: try again later
        }
      }
      return { uploaded, failed, left: (await read()).length };
    },
  };
}
