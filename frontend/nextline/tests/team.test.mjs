// Run with: npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import { betterFix, captureBody, captureProblems, measurementFor, parseMeasurement } from '../utils/team.js';

const position = { latitude: 45.1, longitude: -122.2, accuracy: 6 };

test('a capture needs GPS, a type and a grade', () => {
  assert.deepEqual(captureProblems({ position: null, type: null, grade: null, measurementText: '' }),
    ['Waiting for GPS.', 'Pick a type.', 'Pick a grade.']);
  assert.deepEqual(captureProblems({ position, type: 'drop', grade: 3, measurementText: '' }), []);
  assert.match(captureProblems({ position: { ...position, accuracy: 48 }, type: 'drop', grade: 3 })[0], /±157 ft\. Wait for ±100 ft/);
  assert.deepEqual(captureProblems({ position, type: 'drop', grade: 3, measurementText: 'tall' }),
    ['The measurement should be a number.']);
});

test('measurements parse commas and blanks', () => {
  assert.equal(parseMeasurement('1,2'), 1.2);
  assert.equal(parseMeasurement(' '), null);
  assert.equal(parseMeasurement('-3'), undefined);
  assert.equal(measurementFor('drop').field, 'drop_height_m');
  assert.equal(measurementFor('corner'), null);
});

test('capture body', () => {
  assert.deepEqual(captureBody({ clientId: 'c1', position, type: 'drop', grade: 4, name: '  Big step ', trailId: 9,
    measurementText: '3' }), {
    client_id: 'c1', type: 'drop', grade: 4, lat: 45.1, lng: -122.2, name: 'Big step', trail: 9, drop_height_m: 0.914,
  });
  // No trail picked: the server uses the nearest. No name: it makes one. Corners have no measurement.
  assert.deepEqual(captureBody({ clientId: 'c2', position, type: 'corner', grade: 2, name: '', measurementText: '3' }), {
    client_id: 'c2', type: 'corner', grade: 2, lat: 45.1, lng: -122.2,
  });
});

test('keeps the most accurate GPS fix', () => {
  const a = { accuracy: 12 };
  const b = { accuracy: 5 };
  const c = { accuracy: 20 };
  assert.equal(betterFix(null, a), a);
  assert.equal(betterFix(a, b), b);
  assert.equal(betterFix(b, c), b);
  assert.equal(betterFix(b, { accuracy: null }), b);
});
