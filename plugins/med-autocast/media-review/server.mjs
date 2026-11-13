import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { getUiCapability, registerAppResource, registerAppTool, RESOURCE_MIME_TYPE } from '@modelcontextprotocol/ext-apps/server';
import { z } from 'zod';
import { execFile } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const root = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(root, '..');
const adapter = resolve(packageRoot, 'skills/med-autocast/runtime/native_helpers/app_contribution.py');
const html = await readFile(resolve(root, 'index.html'), 'utf8');
const resourceUri = 'ui://med-autocast/media-review.html';
const inputSchema = z.object({
  series_id: z.string().min(1).optional(),
  episode_id: z.string().min(1).optional(),
  shot_id: z.string().min(1).optional(),
  request_id: z.string().min(1).optional(),
}).strict();
const noteSchema = z.object({
  series_id: z.string().min(1),
  episode_id: z.string().min(1),
  shot_id: z.string().min(1).optional(),
  revision: z.string().startsWith('sha256:'),
  request_id: z.string().regex(/^[A-Za-z0-9_-]{1,100}$/),
  note: z.string().min(1).max(20000),
}).strict();

function supportsUi(server) {
  return getUiCapability(server.server.getClientCapabilities())?.mimeTypes?.includes(RESOURCE_MIME_TYPE) === true;
}
function invoke(operation, input) {
  return new Promise((resolvePromise, reject) => {
    const child = execFile('python3', [adapter, operation], { cwd: packageRoot, env: process.env, timeout: 120000, maxBuffer: 32 * 1024 * 1024 }, (error, stdout) => {
      try {
        const result = JSON.parse(stdout || '{}');
        if (error || result.ok === false || result.state === 'unavailable') {
          const message = result.error?.message || result.reason || 'Med Auto Cast 工作区读取未完成';
          reject(Object.assign(new Error(message), { result }));
          return;
        }
        resolvePromise(result);
      } catch {
        reject(new Error('Med Auto Cast owner 返回不可解析结果，请重新读取当前工作区。'));
      }
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify(input));
  });
}
function errorResult(error) {
  return { isError: true, structuredContent: { error: { code: 'med_autocast_media_review_failed', message: error.message } }, content: [{ type: 'text', text: error.message }] };
}

export function createMcpServer() {
  const server = new McpServer({ name: 'med-autocast-media-review', version: '0.1.1' }, { instructions: 'Use this MiniApp for dense media and shot review. Notes are human review material only; they never approve quality or publish a candidate.' });
  registerAppResource(server, 'Med Auto Cast media review', resourceUri, { _meta: { ui: { prefersBorder: true, csp: { connectDomains: [], resourceDomains: [] } } } }, async () => ({ contents: [{ uri: resourceUri, mimeType: RESOURCE_MIME_TYPE, text: html, _meta: { ui: { prefersBorder: true, csp: { connectDomains: [], resourceDomains: [] } } } }] }));
  registerAppTool(server, 'open_media_review', { title: 'Med Auto Cast · 媒体审看', description: '查看当前视频候选，按镜头定位并记录审看意见。打开后选择单集，再选择要核对的镜头。', inputSchema, annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false }, _meta: { ui: { resourceUri, 'openai/outputTemplate': resourceUri } } }, async input => {
    try {
      const focus = inputSchema.parse(input);
      const data = await invoke('media', focus);
      if (supportsUi(server)) return { content: [{ type: 'text', text: 'Med Auto Cast 媒体审看已准备就绪。' }], structuredContent: { data, focus, presentation: { mode: 'mcp-app', resource_uri: resourceUri } } };
      return { content: [{ type: 'text', text: JSON.stringify(data) }], structuredContent: { data, focus, presentation: { mode: 'structured-data' } } };
    } catch (error) {
      if (supportsUi(server)) return { content: [{ type: 'text', text: error.message }], structuredContent: { data: { state: 'unavailable', reason: error.message }, focus: input, presentation: { mode: 'mcp-app', resource_uri: resourceUri } } };
      return errorResult(error);
    }
  });
  registerAppTool(server, 'media_review_note', { title: '记录媒体审看意见', description: '把当前版本的人工审看意见写入 Med Auto Cast 工作区；意见不是质量批准。', inputSchema: noteSchema, annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false }, _meta: { ui: { resourceUri, visibility: ['app'] } } }, async input => {
    if (!supportsUi(server)) return errorResult(new Error('该意见操作需要媒体审看 UI。'));
    try { return { content: [{ type: 'text', text: '审看意见已记录，正在回读当前版本。' }], structuredContent: await invoke('note', noteSchema.parse(input)) }; }
    catch (error) { return errorResult(error); }
  });
  return server;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await createMcpServer().connect(new StdioServerTransport());
}
