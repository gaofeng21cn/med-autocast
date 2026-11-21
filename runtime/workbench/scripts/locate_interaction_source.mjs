#!/usr/bin/env node
// Locate source patterns worth checking at their actual shot times.
import {createHash} from 'node:crypto';
import {existsSync, readFileSync, readdirSync, writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {join, relative, resolve} from 'node:path';

const readJson = path => JSON.parse(readFileSync(path, 'utf8'));
const require = createRequire(import.meta.url);
const [input, output, parserPath] = process.argv.slice(2);
if (!input || !output) {
  throw Error('usage: locate_interaction_source.mjs --project <project> [typescript.js] | <queue.json> <output.json> [typescript.js]');
}

const single = input === '--project';
const episodes = single ? [{project: resolve(output)}] : readJson(input).episodes;
const bundledParser = episodes
  .filter(row => row.project)
  .map(row => join(resolve(row.project), 'node_modules/typescript/lib/typescript.js'))
  .find(path => existsSync(path));
const parser = parserPath ? resolve(parserPath) : bundledParser;
const sharedModules = process.env.MED_AUTOCAST_SHARED_NODE_MODULES;
const sharedParser = sharedModules && join(sharedModules, 'typescript/lib/typescript.js');
const availableParser = [parser, sharedParser].find(candidate => candidate && existsSync(candidate));
const ts = availableParser ? require(availableParser) : null;

function* descend(node) {
  yield node;
  const children = [];
  ts.forEachChild(node, child => { children.push(child); });
  for (const child of children) {
    yield* descend(child);
  }
}

const string = node => node && ts.isStringLiteralLike(node) ? node.text : null;
const callName = call => ts.isIdentifier(call.expression) ? call.expression.text : null;
const ancestor = (node, test) => {
  for (let parent = node.parent; parent; parent = parent.parent) {
    if (test(parent)) return parent;
  }
  return null;
};

function hasTransition(expression, scope, seen = new Set()) {
  if (!expression || seen.has(expression)) return false;
  seen.add(expression);
  for (const node of descend(expression)) {
    if (ts.isCallExpression(node) && ['lerp', 'mix', 'phase', 'act'].includes(callName(node))) {
      const [from, to] = node.arguments;
      if (!['lerp', 'mix'].includes(callName(node)) || from?.getText() !== to?.getText()) return true;
    }
    if (ts.isIdentifier(node)) {
      const declaration = [...descend(scope)].find(part =>
        ts.isVariableDeclaration(part) && ts.isIdentifier(part.name) &&
        part.name.text === node.text && part.pos < node.pos);
      if (hasTransition(declaration?.initializer, scope, seen)) return true;
    }
  }
  return false;
}

function mentionsPose(expression, pose) {
  return expression && [...descend(expression)].some(node => string(node) === pose);
}

function locate(project, score) {
  const root = join(project, 'src');
  if (!existsSync(root)) return {status:'missing_sources', files:[], findings:[]};
  if (!ts) return {status:'parser_unavailable', files:[], findings:[]};
  const files = readdirSync(root, {withFileTypes:true})
    .filter(file => file.isFile() && /\.[cm]?[jt]sx?$/.test(file.name))
    .sort((left, right) => left.name.localeCompare(right.name));
  const sources = files.map(file => {
    const path = join(root, file.name);
    return ts.createSourceFile(path, readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true);
  });
  const parseErrors = sources.flatMap(ast => (ast.parseDiagnostics || []).map(error => ({
    source: relative(project, ast.fileName),
    line: ast.getLineAndCharacterOfPosition(error.start ?? 0).line + 1,
    message: ts.flattenDiagnosticMessageText(error.messageText, ' '),
  })));
  const functions = new Map();
  const uses = new Map();
  const shots = new Map();
  for (const ast of sources) {
    for (const node of descend(ast)) {
      if (ts.isFunctionDeclaration(node) && node.name) functions.set(node.name.text, node);
      if (ts.isCallExpression(node) && callName(node)) {
        const name = callName(node);
        if (!uses.has(name)) uses.set(name, []);
        uses.get(name).push(node);
      }
      if (!ts.isObjectLiteralExpression(node)) continue;
      const id = node.properties.find(p => ts.isPropertyAssignment(p) && p.name.getText() === 'id');
      const render = node.properties.find(p => p.name?.getText() === 'render');
      if (id && render) shots.set(node, string(id.initializer));
      const target = render?.initializer || (render && ts.isShorthandPropertyAssignment(render) ? render.name : null);
      if (id && target && ts.isIdentifier(target)) shots.set(target.text, string(id.initializer));
    }
  }

  function shotIds(node, seen = new Set()) {
    const inline = ancestor(node, parent => shots.has(parent));
    if (inline) return [shots.get(inline)];
    const owner = ancestor(node, parent => ts.isFunctionDeclaration(parent) || ts.isVariableDeclaration(parent));
    const name = owner?.name?.getText();
    if (!name || seen.has(name)) return [];
    if (shots.has(name)) return [shots.get(name)];
    return [...new Set((uses.get(name) || []).flatMap(call => shotIds(call, new Set([...seen,name]))))];
  }

  const findings = [];
  function record(kind, call, detail) {
    const ast = call.getSourceFile();
    const ids = shotIds(call);
    findings.push({
      kind, source:relative(project,ast.fileName),
      line:ast.getLineAndCharacterOfPosition(call.getStart()).line+1,
      shots:ids.flatMap(id => {
        const shot = score.shots?.find(item => item.id === id);
        return shot ? [{id,start:shot.start,end:shot.end}] : [];
      }),
      detail,
      blocks_stage_progress: false,
    });
  }

  const person = functions.get('person');
  const fixedPoseLibrary = person && [...descend(person)].some(node =>
    ['manwalk','womanwalk','doctor_walk','reserve_person_walk_v1'].includes(string(node)));
  if (fixedPoseLibrary) {
    for (const call of uses.get('person') || []) {
      const scope = ancestor(call, ts.isFunctionLike);
      if (scope && mentionsPose(call.arguments[5], 'walk') && hasTransition(call.arguments[2], scope)) {
        record('fixed_pose_translation',call,'位置随时间变化，行走分支使用固定迈步素材');
      }
    }
  }
  for (const actor of ['woman','person']) {
    const helper = functions.get(actor);
    if (!helper || ![...descend(helper)].some(node => string(node) === 'reserve_person_walk_v1')) continue;
    for (const call of uses.get(actor) || []) {
      const scope = ancestor(call, ts.isFunctionLike);
      if (scope && hasTransition(call.arguments[1],scope)) {
        record('pose_library_translation',call,'角色位置插值，姿态实现包含单张迈步图，核对落脚和重心');
      }
    }
  }
  for (const call of uses.get('sprite') || []) {
    if (string(call.arguments[1]) !== 'chair' || call.arguments.length > 6) continue;
    const scope = ancestor(call,ts.isFunctionLike);
    if (!scope) continue;
    const others = [...descend(scope)].filter(ts.isCallExpression);
    const chairs = others.filter(node => callName(node) === 'sprite' &&
      string(node.arguments[1]) === 'chair' && node.arguments.length <= 6);
    const sitters = others.filter(node => callName(node) === 'person' && mentionsPose(node.arguments[5],'sit'));
    if (chairs.length >= 2 && call === chairs[0] && sitters.length >= 2) {
      record('same_orientation_chairs',call,'两张同方向椅图配两个坐姿，核对椅背、座面与人物朝向');
    }
  }

  return {
    status: parseErrors.length ? 'partial_parse' : sources.length ? 'scanned' : 'missing_sources',
    parse_errors: parseErrors,
    files:sources.map(ast => ({
      path:relative(project,ast.fileName),
      sha256:createHash('sha256').update(ast.text).digest('hex'),
    })),
    findings,
  };
}

function reviewEpisode({series_id, episode_id, project, evidence}) {
  if (!project) {
    return {series_id, episode_id, project, status:'missing_project', files:[], findings:[]};
  }
  project = resolve(project);
  try {
    const configPath = join(project, 'project.json');
    const config = existsSync(configPath) ? readJson(configPath) : {};
    const scorePath = evidence?.score ?? join(project, config.score || 'score.json');
    const score = scorePath.endsWith('.json') && existsSync(scorePath) ? readJson(scorePath) : {};
    const currentPath = join(project, 'out/current.json');
    const current = existsSync(currentPath) ? readJson(currentPath) : {};
    return {
      series_id: series_id ?? config.series_id,
      episode_id: episode_id ?? config.episode_id,
      project,
      registered_video_sha256: current.sha256 || null,
      ...locate(project, score),
    };
  } catch (error) {
    return {series_id, episode_id, project, status:'source_read_error', error:error.message, files:[], findings:[]};
  }
}
const rows = episodes.map(reviewEpisode);
if (single) {
  console.log(JSON.stringify(rows[0]));
} else {
  const summary = {
    episodes: rows.length,
    scanned: rows.filter(row => row.status === 'scanned').length,
    flagged_episodes: rows.filter(row => row.findings.length).length,
    findings: rows.reduce((sum,row) => sum + row.findings.length, 0),
  };
  writeFileSync(output, JSON.stringify({summary, episodes:rows}, null, 2) + '\n');
  console.log(JSON.stringify(summary));
}
