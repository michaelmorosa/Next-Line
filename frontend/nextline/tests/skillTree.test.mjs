// Run with: npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import { NODE_H, NODE_W, edgePath, layoutTree, nodeCaption, scrollTargetFor } from '../utils/skillTree.js';

const branches = [
  { id: 'foundations', name: 'Foundations', color: '#7FD1C1' },
  { id: 'wheel_lifts', name: 'Wheel lifts', color: '#E6D36A' },
  { id: 'drops', name: 'Drops', color: '#E5636B' },
  { id: 'empty', name: 'Nothing here', color: '#000' },
];

const skill = (id, branch, depth, prerequisites = [], state = 'locked', extra = {}) => (
  { id, branch, depth, prerequisites, state, tier: depth + 1, sessions: 0, ...extra }
);

const skills = [
  skill('attack', 'foundations', 0, [], 'mastered'),
  skill('braking', 'foundations', 0, [], 'ready'),
  skill('wheel_lift', 'wheel_lifts', 1, ['attack'], 'mastered'),
  skill('manual', 'wheel_lifts', 2, ['wheel_lift'], 'in_progress', { sessions: 2 }),
  skill('roll_offs', 'drops', 1, ['attack', 'braking']),
  skill('small_drops', 'drops', 3, ['roll_offs', 'manual']),
];

test('prerequisites sit to the left of what they unlock', () => {
  const { nodes } = layoutTree(branches, skills);
  for (const s of skills) {
    for (const p of s.prerequisites) assert.ok(nodes[p].x + NODE_W < nodes[s.id].x, `${p} before ${s.id}`);
  }
});

test('one lane per branch with skills, stacked without overlap', () => {
  const { nodes, lanes, height } = layoutTree(branches, skills);
  assert.deepEqual(lanes.map((l) => l.id), ['foundations', 'wheel_lifts', 'drops']);
  // Two skills at depth 0 in Foundations stack vertically.
  assert.equal(nodes.attack.x, nodes.braking.x);
  assert.ok(nodes.braking.y >= nodes.attack.y + NODE_H);
  // Lanes don't overlap, and every node is inside its lane.
  for (let i = 1; i < lanes.length; i++) assert.ok(lanes[i].y >= lanes[i - 1].y + lanes[i - 1].height);
  for (const s of skills) {
    const lane = lanes.find((l) => l.id === s.branch);
    assert.ok(nodes[s.id].y >= lane.y && nodes[s.id].y + NODE_H <= lane.y + lane.height);
  }
  assert.ok(height >= lanes.at(-1).y + lanes.at(-1).height);
});

test('an edge for every prerequisite, including across branches', () => {
  const { edges } = layoutTree(branches, skills);
  assert.equal(edges.length, 6);
  const small = edges.filter((e) => e.to === 'small_drops').map((e) => e.from).sort();
  assert.deepEqual(small, ['manual', 'roll_offs']);
  assert.equal(edges.find((e) => e.from === 'attack' && e.to === 'wheel_lift').met, true);
  assert.equal(edges.find((e) => e.from === 'manual').met, false);
});

test('width fits the deepest column', () => {
  const { nodes, width } = layoutTree(branches, skills);
  assert.ok(width >= nodes.small_drops.x + NODE_W);
});

test('edge path runs from right edge to left edge', () => {
  assert.equal(edgePath({ x: 0, y: 0 }, { x: 200, y: 100 }),
    `M ${NODE_W} ${NODE_H / 2} C ${(NODE_W + 200) / 2} ${NODE_H / 2}, ${(NODE_W + 200) / 2} ${100 + NODE_H / 2}, 200 ${100 + NODE_H / 2}`);
});

test('captions', () => {
  assert.equal(nodeCaption({ state: 'mastered' }), 'Mastered');
  assert.equal(nodeCaption({ state: 'mastered', coach_verified: true }), 'Mastered · coach ✓');
  assert.equal(nodeCaption({ state: 'in_progress', sessions: 1 }), '1 session');
  assert.equal(nodeCaption({ state: 'in_progress', sessions: 4, eligible: true }), 'Ready to test');
  assert.equal(nodeCaption({ state: 'ready', tier: 2 }), 'Tier 2 · ready');
});

test('scroll target centres a node and never goes negative', () => {
  assert.equal(scrollTargetFor({ x: 0 }, 400), 0);
  assert.equal(scrollTargetFor({ x: 500 }, 400), 500 + NODE_W / 2 - 200);
});
