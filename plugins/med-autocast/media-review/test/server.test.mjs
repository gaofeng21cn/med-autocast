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

test('standalone launcher selects the active Framework workspace and preserves explicit focus', async () => {
  const { resolveMediaFocus } = await import('../server.mjs');
  const calls = [];
  const run = async (...args) => {
    calls.push(args);
    return { workspace_catalog: { projects: [
      { project: 'unrelated', active_binding: { status: 'active', workspace_path: '/other' } },
      { project: 'med-autocast', active_binding: { status: 'active', workspace_path: '/production' } },
    ] } };
  };
  assert.deepEqual(await resolveMediaFocus({ series_id: 'series' }, {}, run), { workspace_path: '/production', series_id: 'series' });
  assert.deepEqual(calls[0].slice(0, 2), ['opl', ['workspace', 'list', '--json']]);
  assert.deepEqual(await resolveMediaFocus({ workspace_path: '/selected', episode_id: 'ep2' }, {}, run), { workspace_path: '/selected', episode_id: 'ep2' });
  assert.equal(calls.length, 1, 'explicit navigation must not follow a changed active workspace');
  await assert.rejects(resolveMediaFocus({}, {}, async () => ({ workspace_catalog: { projects: [] } })), /登记制作工作区/);
});

test('standalone reads and notes use the authoritative contribution broker with the exact workspace', async () => {
  const { invoke } = await import('../server.mjs');
  const focus = { workspace_path: '/production', series_id: 'series', episode_id: 'ep2' };
  const calls = [];
  const data = { state: 'ready', data: { items: [{ episode_id: 'ep2' }] } };
  const run = async (...args) => { calls.push(args); return { opl_app_contribution: { response: { result: data } } }; };
  assert.deepEqual(await invoke('media', focus, { OPL_BIN: '/framework/bin/opl' }, run), data);
  assert.deepEqual(calls[0].slice(0, 3), ['/framework/bin/opl', [
    'app', 'contribution', 'read', '--package-id', 'med-autocast', '--ref', 'med-autocast.workspace.v1#media', '--input-stdin', '--json',
  ], focus]);
  const note = { ...focus, revision: 'sha256:current', request_id: 'review-1', note: 'Check framing' };
  await invoke('note', note, {}, run);
  assert.equal(calls[1][1][2], 'execute');
  assert.ok(calls[1][1].includes('--confirm'));
  assert.deepEqual(calls[1][2], note);
  await assert.rejects(invoke('media', focus, {}, async () => ({ opl_app_contribution: { response: { result: { state: 'unavailable', reason: 'Workspace was archived' } } } })), /Workspace was archived/);
});
