import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const testRoot = dirname(fileURLToPath(import.meta.url));

test('media review bundle declares a standard MCP App resource and its two owner paths', async () => {
  const server = await readFile(resolve(testRoot, '..', 'server.mjs'), 'utf8');
  const template = await readFile(resolve(testRoot, '..', 'index.html'), 'utf8');
  assert.match(server, /ui:\/\/med-autocast\/media-review\.html/);
  assert.match(server, /registerAppResource/);
  assert.match(server, /open_media_review/);
  assert.match(server, /media_review_note/);
  assert.match(server, /invoke\('media'/);
  assert.match(server, /invoke\('note'/);
  assert.match(template, /data-fullscreen|review-rail|timeline/);
});


test('real stdio launcher forwards navigation input to the Python owner', { timeout: 20000 }, async () => {
  const { mkdtemp, writeFile, rm } = await import('node:fs/promises');
  const { tmpdir } = await import('node:os');
  const { Client } = await import('@modelcontextprotocol/sdk/client/index.js');
  const { StdioClientTransport, getDefaultEnvironment } = await import('@modelcontextprotocol/sdk/client/stdio.js');
  const profile = await mkdtemp(resolve(tmpdir(), 'mac-navigation-'));
  await writeFile(resolve(profile, 'workbench.yaml'), 'series: {}\n');
  const client = new Client({ name: 'navigation-test', version: '1' });
  const transport = new StdioClientTransport({ command: process.execPath, args: [resolve(testRoot, '..', 'server.mjs')], env: { ...getDefaultEnvironment(), OPL_PROFILE_WORKSPACE: profile }, stderr: 'pipe' });
  try {
    await client.connect(transport);
    const empty = await client.callTool({ name: 'open_media_review', arguments: {} }, undefined, { timeout: 8000 });
    assert.equal(empty.isError, undefined);
    assert.deepEqual(empty.structuredContent.data.data.items, []);
    const missing = await client.callTool({ name: 'open_media_review', arguments: { series_id: 'missing' } }, undefined, { timeout: 8000 });
    assert.equal(missing.isError, true);
    assert.match(missing.content[0].text, /所选系列未登记/);
  } finally { await client.close(); await rm(profile, { recursive: true, force: true }); }
});
