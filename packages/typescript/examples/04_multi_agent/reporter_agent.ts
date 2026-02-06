/**
 * Reporter Agent - Part of multi-agent example.
 *
 * Run: npx ts-node examples/04_multi_agent/reporter_agent.ts
 */
import { Agent } from '../../src';

const agent = new Agent({ name: 'ReporterAgent', description: 'Generates reports' });

agent.skill('generate_summary', { description: 'Generate summary report', tags: ['reporting'] }, async ({ data, format = 'text' }: { data: Record<string, unknown>; format?: string }) => {
  const lines: string[] = [];
  if (format === 'markdown') {
    lines.push('# Summary Report\n');
    for (const [key, value] of Object.entries(data)) {
      lines.push('- **' + key + '**: ' + JSON.stringify(value));
    }
  } else {
    lines.push('Summary Report');
    lines.push('='.repeat(40));
    for (const [key, value] of Object.entries(data)) {
      lines.push(key + ': ' + JSON.stringify(value));
    }
  }
  return { report: lines.join('\n'), format };
});

agent.skill('format_table', { description: 'Format as table', tags: ['reporting'] }, async ({ headers, rows }: { headers: string[]; rows: unknown[][] }) => {
  const widths = headers.map((h, i) => Math.max(h.length, ...rows.map(r => String(r[i] ?? '').length)));
  const sep = '+' + widths.map(w => '-'.repeat(w + 2)).join('+') + '+';
  const headerRow = '| ' + headers.map((h, i) => h.padEnd(widths[i])).join(' | ') + ' |';
  const dataRows = rows.map(row => '| ' + row.map((cell, i) => String(cell ?? '').padEnd(widths[i])).join(' | ') + ' |');
  return { table: [sep, headerRow, sep, ...dataRows, sep].join('\n') };
});

agent.run({ port: 8789 });
