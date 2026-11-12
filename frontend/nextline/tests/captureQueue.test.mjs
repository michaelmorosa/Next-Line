// Run with: npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import { createCaptureQueue } from '../utils/captureQueue.js';

function memoryStorage() {
  const map = new Map();
  return { getItem: async (k) => map.get(k) ?? null, setItem: async (k, v) => { map.set(k, v); } };
}

const capture = (id, kinds = ['approach', 'feature']) => ({
  client_id: id,
  body: { client_id: id, type: 'drop', grade: 3, lat: 45, lng: -122 },
  photos: kinds.map((kind) => ({ kind, uri: `file:///${id}-${kind}.jpg`, client_id: `${id}-${kind}` })),
  created_at: '2026-11-10T10:00:00Z',
});

// A fake server that remembers what it got, so retries can be checked for duplicates.
function fakeApi({ failFeature, failPhoto } = {}) {
  const server = { features: new Map(), photos: new Map(), discarded: [] };
  let nextId = 1;
  return {
    server,
    async createFeature(body) {
      if (failFeature) failFeature(body);
      if (!server.features.has(body.client_id)) server.features.set(body.client_id, nextId++);
      return { id: server.features.get(body.client_id) };
    },
    async uploadPhoto(featureId, photo) {
      if (failPhoto) failPhoto(photo);
      server.photos.set(photo.client_id, featureId);
    },
    async discard(c) { server.discarded.push(c.client_id); },
  };
}

const offline = () => { throw new Error("Couldn't reach the server."); };
const rejected = (message, status = 400) => () => {
  const err = new Error(message);
  err.status = status;
  throw err;
};

test('uploads the draft then each photo, then forgets it', async () => {
  const queue = createCaptureQueue(memoryStorage());
  await queue.add(capture('a'));
  const api = fakeApi();
  const result = await queue.flush(api);
  assert.deepEqual(result, { uploaded: [1], failed: [], left: 0 });
  assert.deepEqual([...api.server.photos.keys()], ['a-approach', 'a-feature']);
  assert.deepEqual(api.server.discarded, ['a']);
});

test('no signal: nothing is lost, and the next try carries on', async () => {
  const queue = createCaptureQueue(memoryStorage());
  await queue.add(capture('a'));
  assert.deepEqual(await queue.flush(fakeApi({ failFeature: offline })), { uploaded: [], failed: [], left: 1 });
  assert.equal(await queue.count(), 1);
  const api = fakeApi();
  assert.equal((await queue.flush(api)).left, 0);
  assert.equal(api.server.features.size, 1);
});

test('a dropped connection mid-photos resumes without duplicates', async () => {
  const queue = createCaptureQueue(memoryStorage());
  await queue.add(capture('a', ['approach', 'feature', 'exit']));
  const api = fakeApi({ failPhoto: (p) => { if (p.kind === 'feature') offline(); } });
  assert.equal((await queue.flush(api)).left, 1);
  const saved = (await queue.read())[0];
  assert.equal(saved.feature_id, 1);  // the draft exists; it isn't created again
  assert.deepEqual(saved.photos.map((p) => p.uploaded), [true, false, false]);

  const calls = [];
  const retry = fakeApi();
  retry.server.features.set('a', 1);
  const upload = retry.uploadPhoto;
  retry.uploadPhoto = async (id, p) => { calls.push(p.kind); return upload(id, p); };
  retry.createFeature = async () => { throw new Error('should not create the draft again'); };
  assert.equal((await queue.flush(retry)).left, 0);
  assert.deepEqual(calls, ['feature', 'exit']);
});

test('the draft rejected by the server is kept with the reason, and the rest still upload', async () => {
  const queue = createCaptureQueue(memoryStorage());
  await queue.add(capture('bad'));
  await queue.add(capture('good'));
  const api = fakeApi({ failFeature: (body) => { if (body.client_id === 'bad') rejected('No trail within reach.')(); } });
  const result = await queue.flush(api);
  assert.deepEqual(result.failed, [{ client_id: 'bad', message: 'No trail within reach.' }]);
  assert.equal(result.uploaded.length, 1);
  assert.equal(result.left, 1);
  // It isn't retried blindly; the team fixes or drops it.
  const again = await queue.flush(fakeApi());
  assert.equal(again.failed.length, 1);
  await queue.drop('bad', api);
  assert.equal(await queue.count(), 0);
  assert.ok(api.server.discarded.includes('bad'));
});

test('a photo the server cannot read does not block the capture', async () => {
  const queue = createCaptureQueue(memoryStorage());
  await queue.add(capture('a', ['approach', 'feature']));
  const api = fakeApi({ failPhoto: (p) => { if (p.kind === 'approach') rejected("That file isn't a photo we can read.")(); } });
  const result = await queue.flush(api);
  assert.deepEqual(result, { uploaded: [1], failed: [], left: 0 });
  assert.deepEqual([...api.server.photos.keys()], ['a-feature']);
});

test('an expired login is retried later, not treated as a rejection', async () => {
  const queue = createCaptureQueue(memoryStorage());
  await queue.add(capture('a'));
  const result = await queue.flush(fakeApi({ failFeature: rejected('Session expired', 401) }));
  assert.deepEqual(result, { uploaded: [], failed: [], left: 1 });
  assert.equal((await queue.read())[0].error, null);
});

test('adding the same capture twice keeps one', async () => {
  const queue = createCaptureQueue(memoryStorage());
  await queue.add(capture('a'));
  await queue.add(capture('a'));
  assert.equal(await queue.count(), 1);
});

test('captures added during an upload are kept', async () => {
  const queue = createCaptureQueue(memoryStorage());
  await queue.add(capture('a'));
  const api = fakeApi();
  const create = api.createFeature;
  api.createFeature = async (body) => {
    await queue.add(capture('late'));
    return create(body);
  };
  await queue.flush(api);
  assert.deepEqual((await queue.read()).map((c) => c.client_id), ['late']);
});
