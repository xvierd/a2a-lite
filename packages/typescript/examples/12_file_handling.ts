/**
 * Multi-modal file handling.
 *
 * Run: npx ts-node examples/12_file_handling.ts
 */
import { Agent, FilePart, Artifact } from '../src';

const agent = new Agent({ name: 'FileProcessor', description: 'Processes files' });

agent.skill('summarize_doc', { description: 'Summarize a document' }, async ({ document }: { document: { name: string; data: string; mimeType?: string } }) => {
  const file = new FilePart({ name: document.name, data: Buffer.from(document.data, 'base64'), mimeType: document.mimeType });
  const content = file.data?.toString('utf-8') || '';
  const words = content.split(/\s+/);
  const summary = words.slice(0, 50).join(' ') + '...';
  return 'Summary of ' + file.name + ': ' + summary;
});

agent.skill('process_data', { description: 'Process JSON data' }, async ({ data }: { data: { items?: Array<{ value?: number }> } }) => {
  const items = data.items || [];
  return { processed: items.length, total: items.reduce((sum, item) => sum + (item.value || 0), 0) };
});

agent.skill('generate_report', { description: 'Generate a report' }, async ({ title }: { title: string }) => {
  const artifact = new Artifact({ name: 'report.json', description: 'Report: ' + title });
  artifact.addText('# Report: ' + title + '\n\nThis is the summary...');
  artifact.addData({ title, generated: new Date().toISOString().split('T')[0], metrics: { users: 100, revenue: 5000 } });
  return artifact.toA2A();
});

agent.skill('analyze_image', { description: 'Analyze an image' }, async ({ image }: { image: { name: string; data: string; mimeType: string } }) => {
  if (!image.mimeType.startsWith('image/')) return { error: 'Expected image, got ' + image.mimeType };
  const data = Buffer.from(image.data, 'base64');
  return { filename: image.name, mime_type: image.mimeType, size_bytes: data.length };
});

agent.run({ port: 8787 });
