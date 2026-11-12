// Just enough Markdown for the grading guidelines: headings, paragraphs, bullets and tables. Bold and code marks are
// stripped rather than styled.

const clean = (text) => text.replace(/\*\*(.+?)\*\*/g, '$1').replace(/`(.+?)`/g, '$1').trim();

export function markdownBlocks(source) {
  const blocks = [];
  let paragraph = [];
  let table = null;
  const endParagraph = () => {
    if (paragraph.length) blocks.push({ type: 'p', text: clean(paragraph.join(' ')) });
    paragraph = [];
  };
  const endTable = () => {
    if (table) blocks.push({ type: 'table', rows: table });
    table = null;
  };
  for (const raw of source.split(/\r?\n/)) {
    const line = raw.trim();
    if (line.startsWith('|')) {
      endParagraph();
      if (/^\|[\s:|-]+\|$/.test(line)) continue;  // the |---|---| separator
      table = table || [];
      table.push(line.slice(1, -1).split('|').map(clean));
      continue;
    }
    endTable();
    const heading = line.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      endParagraph();
      blocks.push({ type: `h${heading[1].length}`, text: clean(heading[2]) });
    } else if (/^[-*]\s+/.test(line)) {
      endParagraph();
      blocks.push({ type: 'li', text: clean(line.replace(/^[-*]\s+/, '')) });
    } else if (!line) {
      endParagraph();
    } else if (blocks.length && blocks[blocks.length - 1].type === 'li' && !paragraph.length && raw.startsWith('  ')) {
      blocks[blocks.length - 1].text += ` ${clean(line)}`;  // a bullet's wrapped second line
    } else {
      paragraph.push(line);
    }
  }
  endParagraph();
  endTable();
  return blocks;
}
