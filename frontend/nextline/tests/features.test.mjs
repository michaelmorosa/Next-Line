// Run with: npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  batchBody, featureMeta, measurementList, outcomeLabel, pickedSummary, points, progressLine, uuid,
} from '../utils/features.js';
import { createLogQueue, isPermanent } from '../utils/logQueue.js';

test('labels', () => {
  assert.equal(featureMeta({ type_label: 'Drop', grade: 4 }), 'Drop · Grade 4');
  assert.equal(featureMeta({ type_label: 'Jump', grade: null }), 'Jump · Ungraded');
  assert.equal(progressLine(7, 12), 'Cleaned 7 of 12 features');
  assert.equal(progressLine(1, 1), 'Cleaned 1 of 1 feature');
  assert.equal(progressLine(0, 0), 'No graded features yet');
  assert.equal(points(60), '+60 pts');
  assert.equal(points(-5), '−5 pts');
  assert.equal(outcomeLabel('walked'), 'Walked it');
});

test('measurements show only what a feature has', () => {
  assert.deepEqual(measurementList({ drop_height_m: 0.9 }), [{ label: 'Drop', value: '0.9 m' }]);
  assert.deepEqual(measurementList({ gap_length_m: 4, steepness_deg: 30 }).map((m) => m.value), ['4 m', '30°']);
  assert.deepEqual(measurementList(), []);
});

test('batch body keeps riding order and skips unpicked features', () => {
  const features = [{ id: 3 }, { id: 1 }, { id: 2 }];
  let n = 0;
  const body = batchBody(features, { 1: 'walked', 3: 'cleaned', 2: null }, {
    riddenOn: '2026-11-10', rideId: 9, makeId: () => `id${(n += 1)}`,
  });
  assert.deepEqual(body, {
    ridden_on: '2026-11-10',
    ride: 9,
    logs: [
      { feature: 3, outcome: 'cleaned', client_id: 'id1' },
      { feature: 1, outcome: 'walked', client_id: 'id2' },
    ],
  });
  assert.equal('ride' in batchBody(features, {}, { riddenOn: 'x', makeId: uuid }), false);
  assert.deepEqual(pickedSummary({ 1: 'cleaned', 2: 'sketchy', 3: null }), { picked: 2, cleaned: 1 });
});

test('uuids look like v4 and differ', () => {
  const a = uuid();
  assert.match(a, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.notEqual(a, uuid());
});

function memoryStorage() {
  const map = new Map();
  return { getItem: async (k) => map.get(k) ?? null, setItem: async (k, v) => { map.set(k, v); } };
}

const entry = (id, feature = 1) => ({ client_id: id, feature, outcome: 'cleaned', ridden_on: '2026-11-10' });

test('queue keeps logs until they send, without duplicates', async () => {
  const queue = createLogQueue(memoryStorage());
  await queue.add([entry('a'), entry('b')]);
  await queue.add([entry('a')]);  // retried add of the same log
  assert.equal(await queue.count(), 2);
  const sent = [];
  const result = await queue.flush(async (e) => { sent.push(e.client_id); });
  assert.deepEqual(sent, ['a', 'b']);
  assert.deepEqual(result, { sent: 2, dropped: [], left: 0 });
  assert.equal(await queue.count(), 0);
});

test('queue stops at the first network failure and keeps the rest in order', async () => {
  const queue = createLogQueue(memoryStorage());
  await queue.add([entry('a'), entry('b'), entry('c')]);
  let calls = 0;
  const result = await queue.flush(async () => {
    calls += 1;
    if (calls === 2) throw new Error("Couldn't reach the server.");
  });
  assert.deepEqual(result, { sent: 1, dropped: [], left: 2 });
  assert.deepEqual((await queue.read()).map((e) => e.client_id), ['b', 'c']);
});

test('queue drops logs the server rejects for good, and reports them', async () => {
  const queue = createLogQueue(memoryStorage());
  await queue.add([entry('closed', 7), entry('ok')]);
  const result = await queue.flush(async (e) => {
    if (e.feature === 7) {
      const err = new Error("That feature isn't open for logging.");
      err.status = 404;
      throw err;
    }
  });
  assert.equal(result.sent, 1);
  assert.equal(result.dropped[0].message, "That feature isn't open for logging.");
  assert.equal(result.left, 0);
});

test('expired logins and rate limits are retried, not dropped', () => {
  assert.equal(isPermanent({ status: 400 }), true);
  assert.equal(isPermanent({ status: 401 }), false);
  assert.equal(isPermanent({ status: 429 }), false);
  assert.equal(isPermanent({ status: 500 }), false);
  assert.equal(isPermanent(new Error('offline')), false);
});

test('logs queued during a flush are kept', async () => {
  const queue = createLogQueue(memoryStorage());
  await queue.add([entry('a')]);
  await queue.flush(async () => { await queue.add([entry('late')]); });
  assert.deepEqual((await queue.read()).map((e) => e.client_id), ['late']);
});

test('a corrupt queue reads as empty', async () => {
  const storage = memoryStorage();
  await storage.setItem('pendingFeatureLogs', '{not json');
  assert.deepEqual(await createLogQueue(storage).read(), []);
});
