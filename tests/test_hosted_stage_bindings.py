"""Exercise the real Framework compiler, beyond local reference existence checks."""
import json
import os
from pathlib import Path
import subprocess
import unittest


class HostedStageBindingsTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('OPL_FRAMEWORK_ROOT'), 'requires explicit Framework source checkout')
    def test_every_stage_compiles_against_framework_runtime(self):
        root = Path(__file__).resolve().parents[1]
        script = r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const [framework, repo] = process.argv.slice(1);
const api = await import(pathToFileURL(path.join(framework, 'src/authority/packages/standard-agent-stage-manifest.ts')).href);
const manifest = JSON.parse(fs.readFileSync(path.join(repo, 'agent/stages/manifest.json'), 'utf8'));
const compiled = manifest.stages.map(stage => {
  const binding = api.resolveStandardAgentStageQualityRuntimeBinding(repo, stage.stage_id);
  assert.ok(binding);
  assert.equal(binding.stage_id, stage.stage_id);
  assert.ok(binding.route_budget.max_route_back_rounds >= 0);
  return binding.stage_id;
});
console.log(JSON.stringify({ compiled }));
'''
        result = subprocess.run(['node', '--conditions=opl-source', '--experimental-strip-types',
            '--input-type=module', '-e', script, os.environ['OPL_FRAMEWORK_ROOT'], str(root)],
            text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        manifest = json.loads((root / 'agent/stages/manifest.json').read_text())
        self.assertEqual(set(json.loads(result.stdout)['compiled']), {stage['stage_id'] for stage in manifest['stages']})
