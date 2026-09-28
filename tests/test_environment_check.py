"""First-run regression: empty workspace, honest readiness and stable voice selection."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'runtime/workbench/scripts'))
import environment_check as envcheck
from init_workbench import initialize
from workbench_config import validate, resolve_font, select_audio_backend


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'new workspace'

    def test_new_workspace_has_valid_config_and_no_fake_personal_assets(self):
        initialize(self.root)
        report = validate(root=self.root)
        self.assertEqual(report['status'], 'passed', report)
        self.assertEqual(report['backend_profile']['default_audio'], 'edge_tts_local')
        self.assertEqual(report['author_profile']['assets'], [])
        self.assertTrue((self.root / 'package-lock.json').is_file())

    def test_existing_workspace_never_overwritten(self):
        initialize(self.root)
        config = self.root / 'workbench.yaml'
        before = config.read_bytes()
        with self.assertRaisesRegex(ValueError, '空目录'):
            initialize(self.root)
        self.assertEqual(config.read_bytes(), before)

    def test_relative_font_uses_workspace_not_cwd(self):
        initialize(self.root)
        font = self.root / 'font.ttf'
        font.write_bytes(b'path fixture, not real font')
        with patch.dict(os.environ, WORKBENCH_FONT='font.ttf'):
            self.assertEqual(resolve_font(root=self.root), font.resolve())
        with patch.dict(os.environ, WORKBENCH_FONT='missing.ttf'):
            with self.assertRaises(ValueError): resolve_font(root=self.root)

    def test_missing_tools_and_browser_have_actionable_fix(self):
        with patch('environment_check.shutil.which', return_value=None):
            self.assertEqual(envcheck.command('missing')['state'], 'missing')
            self.assertIn('fix', envcheck.node_playwright(self.root))
        with patch('environment_check.shutil.which', return_value='/node'), patch('environment_check.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"state":"missing","error":"no browser"}')):
            self.assertEqual(envcheck.node_playwright(self.root)['state'], 'missing')

    def test_optional_models_do_not_block_core_but_pillow_does(self):
        initialize(self.root)
        def cmd(name, args=None): return {'state':'ready', 'version':'v22.0.0'}
        with patch('environment_check.command', side_effect=cmd), patch('environment_check.node_playwright', return_value={'state':'ready'}), patch('workbench_config.resolve_font', return_value=self.root/'font'), patch('environment_check.importlib.util.find_spec', return_value=object()):
            report = envcheck.check(self.root)
            self.assertEqual(report['status'], 'ready')
            self.assertFalse(report['production_ready'])
            self.assertEqual(report['optional_media']['index_tts_local']['state'], 'not_probed')
        actual = importlib.util.find_spec
        with patch('environment_check.command', side_effect=cmd), patch('environment_check.node_playwright', return_value={'state':'ready'}), patch('workbench_config.resolve_font', return_value=self.root/'font'), patch('environment_check.importlib.util.find_spec', side_effect=lambda n: None if n=='PIL' else actual(n)):
            self.assertEqual(envcheck.check(self.root)['status'], 'needs_setup')

    def test_invalid_yaml_is_reported_not_a_traceback(self):
        initialize(self.root)
        (self.root/'workbench.yaml').write_text('active_profiles: [broken')
        with patch('environment_check.command', return_value={'state':'missing'}), patch('environment_check.node_playwright', return_value={'state':'missing'}), patch.dict(os.environ, WORKBENCH_FONT=''):
            report = envcheck.check(self.root)
        self.assertEqual(report['status'], 'needs_setup')
        self.assertTrue(report['configuration']['errors'])

    def test_selected_edge_dependency_is_required_without_blocking_js_core(self):
        initialize(self.root)
        with patch('environment_check.command', return_value={'state':'ready', 'version':'v22.0.0'}), patch('environment_check.node_playwright', return_value={'state':'ready'}), patch('workbench_config.resolve_font', return_value=self.root/'font'), patch('environment_check.importlib.util.find_spec', side_effect=lambda n: None if n=='edge_tts' else object()):
            report = envcheck.check(self.root)
        self.assertTrue(report['core_ready'])
        self.assertEqual(report['status'], 'needs_setup')
        self.assertEqual(report['selected_narration']['state'], 'missing')
        self.assertTrue(report['selected_narration']['network_required'])
        self.assertFalse(report['selected_narration']['synthesis_verified'])

    def test_reference_diagnostic_checks_runtime_without_silent_edge_fallback(self):
        import yaml
        initialize(self.root)
        path = self.root/'profiles/authors/example_author.yaml'
        author = yaml.safe_load(path.read_text())
        author['voice'].update(reference_audio='reference.wav', mode='reference', preferred_backend_definition='indextts_2_5')
        path.write_text(yaml.safe_dump(author))
        with patch.dict(os.environ, INDEXTTS_ROOT=str(self.root/'absent-runtime'), INDEXTTS_PYTHON=str(self.root/'absent-python'), INDEXTTS_MODEL_ROOT=str(self.root/'absent-model')):
            report = envcheck.narration_dependencies(self.root, {'edge_tts':{'state':'ready'}})
        self.assertEqual(report['definition'], 'indextts_2_5')
        self.assertEqual(report['state'], 'missing')
        self.assertFalse(report['synthesis_verified'])

    def test_reference_voice_never_silently_falls_back(self):
        backends={'audio':{'edge':{'definition':'edge_tts'}, 'local':{'definition':'indextts_2_5'}}, 'policy':{'default_audio':'edge'}}
        author={'voice':{'reference_audio':'ref.wav','preferred_backend_definition':'indextts_2_5'}}
        self.assertEqual(select_audio_backend(author, backends), 'local')
        self.assertEqual(select_audio_backend({'voice':{}}, backends), 'edge')
        with self.assertRaisesRegex(ValueError, 'Edge'):
            select_audio_backend(author, backends, 'edge')
        del backends['audio']['local']
        with self.assertRaisesRegex(ValueError, '声线'):
            select_audio_backend(author, backends)

    def test_explicit_skip_preserves_reference_and_revokes_voice_review(self):
        import yaml
        from configure_voice import configure
        initialize(self.root)
        path = self.root/'profiles/authors/example_author.yaml'
        author = yaml.safe_load(path.read_text())
        author['voice'].update(reference_audio='saved-reference.wav', mode='reference', preferred_backend_definition='indextts_2_5')
        author['baseline']['review']['voice'] = 'passed'
        path.write_text(yaml.safe_dump(author))
        report = configure(self.root, 'edge')
        updated = yaml.safe_load(path.read_text())
        self.assertEqual(report['selected_backend'], 'edge_tts_local')
        self.assertEqual(updated['voice']['reference_audio'], 'saved-reference.wav')
        self.assertEqual(updated['baseline']['review']['voice'], 'pending')
        self.assertEqual(validate(root=self.root)['status'], 'passed')
        with self.assertRaisesRegex(ValueError, '不存在'): configure(self.root, 'reference')
        self.assertEqual(yaml.safe_load(path.read_text())['voice']['mode'], 'edge')

    def test_initialized_author_builds_js_plan_without_h3_or_index_path(self):
        import yaml
        from build_episode_timelines import build_plan
        initialize(self.root)
        author = yaml.safe_load((self.root/'profiles/authors/example_author.yaml').read_text())
        manifest = {'duration':4, 'audio_source':'audio/edge.wav', 'beats':[{'id':'B01','start':0,'title':'intro'}]}
        plan = build_plan('01_test',manifest,[],False,author,'local_custom','edge_tts_local',True)
        self.assertEqual(plan['format']['width'],1280)
        self.assertEqual(plan['animation']['renderer'],'javascript')
        self.assertEqual(plan['delivery']['minimum_generative_duration_ratio'],0)
        self.assertEqual(plan['audio']['source'],'audio/edge.wav')
        self.assertEqual(plan['visual_timeline'][0]['source_end'],4)

    def test_shared_runtime_bridge_is_real_esm_without_node_path(self):
        if not __import__('shutil').which('node'): self.skipTest('Node absent')
        initialize(self.root)
        fake = self.root / 'node_modules/playwright'
        fake.mkdir(parents=True)
        (fake/'index.js').write_text('exports.chromium = {marker:"fixture"};')
        bridge = (self.root/'scripts/playwright_runtime.mjs').as_uri()
        code = f'const m = await import({json.dumps(bridge)}); console.log(m.chromium.marker);'
        result = subprocess.run(['node','--input-type=module','-e',code], env={**os.environ,'MED_AUTOCAST_WORKSPACE_ROOT':str(self.root)}, check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), 'fixture')


if __name__ == '__main__': unittest.main()
