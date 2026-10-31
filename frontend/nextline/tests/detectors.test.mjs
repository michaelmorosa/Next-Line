// Run with: npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import { createCrashDetector, createJumpDetector } from '../recording/detectors.js';

const HZ = 50;
const STEP = 1000 / HZ;

// Feed [g, durationMs] segments at 50 Hz; returns everything the detector emitted.
function run(detector, segments, extra) {
  const events = [];
  let t = 0;
  for (const [g, ms] of segments) {
    for (let i = 0; i < ms / STEP; i++) {
      const e = detector.push(t, g, extra);
      if (e) events.push(e);
      t += STEP;
    }
  }
  return events;
}

test('a jump: free fall then landing spike', () => {
  const jumps = run(createJumpDetector(), [[1, 1000], [0.1, 500], [2.5, 60], [1, 500]]);
  assert.equal(jumps.length, 1);
  assert.equal(jumps[0].tMs, 1000);
  assert.equal(jumps[0].airtimeS, 0.5);
});

test('a soft landing a moment after free fall still counts', () => {
  const jumps = run(createJumpDetector(), [[1, 500], [0.2, 300], [0.9, 100], [2.0, 40], [1, 300]]);
  assert.equal(jumps.length, 1);
});

test('a brief dip from pedaling is not a jump', () => {
  assert.equal(run(createJumpDetector(), [[1, 500], [0.3, 80], [2.0, 40], [1, 500]]).length, 0);
});

test('free fall without a landing is not a jump', () => {
  assert.equal(run(createJumpDetector(), [[1, 500], [0.1, 400], [1.0, 1000]]).length, 0);
});

test('no jumps while stopped', () => {
  assert.equal(run(createJumpDetector(), [[1, 500], [0.1, 400], [3, 40], [1, 500]], false).length, 0);
});

test('two jumps in a row', () => {
  const jumps = run(createJumpDetector(), [[1, 500], [0.1, 300], [2.2, 40], [1, 800], [0.15, 620], [3, 40], [1, 200]]);
  assert.deepEqual(jumps.map((j) => j.airtimeS), [0.3, 0.62]);
});

test('crash: big impact, then the phone lies still', () => {
  const crashes = run(createCrashDetector(), [[1, 1000], [6, 60], [1.5, 1500], [1.0, 9000]], 0);
  assert.equal(crashes.length, 1);
  assert.equal(crashes[0].tMs, 1040);
});

test('hard landing and riding on is not a crash', () => {
  const wobble = Array.from({ length: 40 }, (_, i) => [i % 2 ? 0.7 : 1.4, 250]);
  assert.equal(run(createCrashDetector(), [[1, 1000], [5, 40], ...wobble], 0).length, 0);
});

test('getting back on the bike cancels', () => {
  assert.equal(run(createCrashDetector(), [[1, 1000], [6, 40], [1, 4000], [1, 6000]], 5).length, 0);
});
