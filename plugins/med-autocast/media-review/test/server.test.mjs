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
