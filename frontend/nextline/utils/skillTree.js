// Where to draw each skill in the tree, and the prerequisite lines between them. Pure, so it's tested with npm test.
//
// Columns are depth (the longest prerequisite chain, from the server), so lines always run left to right. Rows are
// branches: each branch gets a lane, tall enough for its busiest column, with its name above it.

export const NODE_W = 136;
export const NODE_H = 66;
export const COL_GAP = 34;
export const ROW_GAP = 12;
export const LANE_GAP = 18;
export const LABEL_H = 22;
export const PAD = 16;

export function layoutTree(branches, skills) {
  const nodes = {};
  const lanes = [];
  let top = PAD;
  for (const branch of branches) {
    const members = skills.filter((s) => s.branch === branch.id);
    if (!members.length) continue;
    const perDepth = {};
    for (const s of members) {
      const row = perDepth[s.depth] || 0;
      perDepth[s.depth] = row + 1;
      nodes[s.id] = {
        id: s.id,
        x: PAD + s.depth * (NODE_W + COL_GAP),
        y: top + LABEL_H + row * (NODE_H + ROW_GAP),
      };
    }
    const rows = Math.max(...Object.values(perDepth));
    const height = LABEL_H + rows * NODE_H + (rows - 1) * ROW_GAP;
    lanes.push({ id: branch.id, name: branch.name, color: branch.color, y: top, height });
    top += height + LANE_GAP;
  }
  const maxDepth = Math.max(0, ...skills.map((s) => s.depth));
  const states = Object.fromEntries(skills.map((s) => [s.id, s.state]));
  const edges = [];
  for (const s of skills) {
    for (const p of s.prerequisites) {
      if (!nodes[p] || !nodes[s.id]) continue;
      edges.push({ from: p, to: s.id, met: states[p] === 'mastered', path: edgePath(nodes[p], nodes[s.id]) });
    }
  }
  return {
    nodes,
    edges,
    lanes,
    width: PAD * 2 + (maxDepth + 1) * NODE_W + maxDepth * COL_GAP,
    height: top - LANE_GAP + PAD,
  };
}

// A smooth S-curve from the right edge of `from` to the left edge of `to`.
export function edgePath(from, to) {
  const x1 = from.x + NODE_W;
  const y1 = from.y + NODE_H / 2;
  const x2 = to.x;
  const y2 = to.y + NODE_H / 2;
  const mid = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`;
}

// What to show under a skill's name in the tree.
export function nodeCaption(skill) {
  if (skill.capstone && skill.state === 'mastered') return 'You conquered the tree';
  if (skill.capstone && skill.state === 'locked') return 'Master every branch';
  if (skill.state === 'mastered') return skill.coach_verified ? 'Mastered · coach ✓' : 'Mastered';
  if (skill.state === 'in_progress') {
    return skill.eligible ? 'Ready to test' : `${skill.sessions} session${skill.sessions === 1 ? '' : 's'}`;
  }
  if (skill.state === 'ready') return `Tier ${skill.tier} · ready`;
  return `Tier ${skill.tier}`;
}

// The point to scroll to so a node sits in the middle of a viewport `viewWidth` wide.
export function scrollTargetFor(node, viewWidth) {
  return Math.max(0, node.x + NODE_W / 2 - viewWidth / 2);
}
