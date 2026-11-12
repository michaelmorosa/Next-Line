// Run with: npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import { markdownBlocks } from '../utils/markdown.js';

test('headings, paragraphs, wrapped bullets and tables', () => {
  const doc = [
    '# Guidelines',
    '',
    'Every feature gets a grade',
    'from **1 to 10**.',
    '',
    '- Steps are small.',
    '  Say so if not.',
    '- Consequence counts.',
    '',
    '## Drops',
    '',
    '| Grade | What it looks like |',
    '|---|---|',
    '| 1 | Roll-down |',
    '| 2 | `30 cm` roll-off |',
  ].join('\n');
  assert.deepEqual(markdownBlocks(doc), [
    { type: 'h1', text: 'Guidelines' },
    { type: 'p', text: 'Every feature gets a grade from 1 to 10.' },
    { type: 'li', text: 'Steps are small. Say so if not.' },
    { type: 'li', text: 'Consequence counts.' },
    { type: 'h2', text: 'Drops' },
    { type: 'table', rows: [['Grade', 'What it looks like'], ['1', 'Roll-down'], ['2', '30 cm roll-off']] },
  ]);
});
