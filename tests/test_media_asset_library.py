"""Exercise the real Git/install/query/copy path, including non-blocking misses."""
import importlib.util
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/workbench/scripts'))
import animation_library as local
import media_asset_library as companion
from check_animation_assets import check_assets


class MediaCompanionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / 'workspace'
        self.workspace.mkdir()
        self.repo = self.base / 'remote'
        self.repo.mkdir()
        (self.repo / 'tools').mkdir()
        (self.repo / 'catalog').mkdir()
        (self.repo / 'collections').mkdir()
        (self.repo / 'collections/series.json').write_text('{}')
        (self.repo / 'tools/query_assets.py').write_text("import json;from pathlib import Path;print((Path(__file__).resolve().parents[1]/'catalog/assets.jsonl').read_text().strip() or '[]')")
        (self.repo / 'tools/verify_catalog.py').write_text("print('verified')")
        original = self.base / 'original.png'
        original.write_bytes(b'actual paper bytes')
        archive = local.archive(self.repo, {'id': 'paper', 'kind': 'image', 'entry': 'files/paper.png',
                               'reuse_scope': {'kind': 'general'},
                               'asset': {'asset_id': 'paper', 'path': 'files/paper.png', 'medical': True,
                                         'status': 'approved_direct_use', 'visual_review': {'status': 'passed'}}},
                                [{'source': str(original), 'path': 'files/paper.png'}])
        record = local.read(self.repo / archive['record'])
        self.record = record
        self.row = {'id': 'paper:paper@' + record['revision'], 'source_id': 'paper',
                    'revision': record['revision'], 'kind': 'image', 'portable_record': archive['record'],
                    'reuse_scope': {'kind': 'general'}, 'review_boundary': {'admission': 'review_candidate'},
                    'payload': [{**record['files'][0], 'path': str(Path(archive['record']).parent/'files/paper.png')} ]}
        (self.repo / 'catalog/assets.jsonl').write_text(json.dumps(self.row) + '\n')
        # The fake query still runs through a real subprocess, returning the documented array.
        (self.repo / 'tools/query_assets.py').write_text("import json;from pathlib import Path;print(json.dumps([json.loads(s) for s in (Path(__file__).resolve().parents[1]/'catalog/assets.jsonl').read_text().splitlines() if s]))")
        subprocess.run(['git', 'init', '-b', 'main', str(self.repo)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture'], check=True, capture_output=True)
        self.target = self.base / 'installed'
        (self.workspace / 'workbench.yaml').write_text('asset_library:\n  root: ' + str(self.target) + '\n')
        self.project = self.workspace / 'productions/s/e'
        self.project.mkdir(parents=True)
        local.write(self.project/'project.json', {'series_id':'s','episode_id':'e'})
        local.write(self.project/'asset_manifest.json', {'assets':[]})

    def test_real_install_reuse_copy_review_and_idempotence(self):
        installed = companion.ensure(self.workspace, repository=str(self.repo))
        self.assertEqual(installed['installation'], 'installed_and_verified')
        (self.target/'local-note.md').write_text('preserve this user edit')
        reused = companion.ensure(self.workspace, repository='/not-used')
        self.assertEqual(reused['installation'], 'reused_existing')
        self.assertEqual((self.target/'local-note.md').read_text(), 'preserve this user edit')
        found = companion.query(self.workspace)
        self.assertEqual(found['count'], 1)
        self.assertTrue(Path(found['assets'][0]['resolved_payloads'][0]['path']).is_file())
        result = companion.use(self.workspace, 'productions/s/e', self.row['id'])
        self.assertEqual(result['status'], 'copied_and_verified')
        self.assertEqual(Path(result['entry']).read_bytes(), b'actual paper bytes')
        asset = local.read(self.project/'asset_manifest.json')['assets'][0]
        self.assertEqual(asset['visual_review']['status'], 'pending')
        self.assertEqual(asset['medical_review']['status'], 'pending')
        self.assertEqual(companion.use(self.workspace,'productions/s/e', self.row['id'])['status'], 'copied_and_verified')
        self.assertEqual(len(local.read(self.workspace/'assets/paper-theatre/uses.json')['uses']), 1)

    def test_animation_reference_brief_prioritizes_executable_motion_and_keeps_ceiling_open(self):
        companion.ensure(self.workspace, repository=str(self.repo))
        motion = {
            **self.row,
            'id': 'paper:motion@v1',
            'source_id': 'motion',
            'revision': 'v1',
            'kind': 'motion_recipe',
            'discovery': {'category': 'motion', 'actions': ['坐下']},
        }

        def fake_query(*args, **kwargs):
            kind = kwargs.get('kind')
            if kind == 'motion_recipe':
                return {'status': 'available', 'assets': [motion]}
            return {'status': 'available', 'assets': []}

        with patch.object(companion, 'query', side_effect=fake_query):
            brief = companion.animation_reference(self.workspace, text='坐下', limit=1)
        self.assertEqual(brief['schema'], 'med_autocast_animation_reference/v1')
        self.assertTrue(brief['baseline_only'])
        self.assertEqual(brief['creative_ceiling'], 'open')
        self.assertEqual(brief['candidates'][0]['reference_role'], 'motion_baseline')
        self.assertEqual(brief['candidates'][0]['reference_mode'], 'baseline_reference')

    def test_external_motion_use_records_exact_open_animation_reference(self):
        sequence = self.base / 'sequence.json'
        entry = self.base / 'index.html'
        sequence.write_text('{"frames": [], "events": []}')
        entry.write_text('<canvas></canvas>')
        archived = local.archive(self.repo, {
            'id': 'motion', 'kind': 'motion_recipe', 'entry': 'index.html',
            'title': '可复用坐下动作', 'registration': {'frames_ref': 'sequence.json'},
            'reuse_scope': {'kind': 'general'},
        }, [
            {'source': entry, 'path': 'index.html', 'role': 'source'},
            {'source': sequence, 'path': 'sequence.json', 'role': 'payload'},
        ])
        record = local.read(self.repo / archived['record'])
        row = {'id': 'paper:motion@' + record['revision'], 'source_id': 'motion',
               'revision': record['revision'], 'kind': 'motion_recipe',
               'portable_record': archived['record'],
               'portable_record_sha256': local.digest(self.repo / archived['record']),
               'reuse_scope': {'kind': 'general'},
               'review_boundary': {'admission': 'reusable_candidate'},
               'payload': [{**item, 'path': str(Path(archived['record']).parent / item['path'])}
                           for item in record['files']]}
        (self.repo / 'catalog/assets.jsonl').write_text(json.dumps(row) + '\n')
        imported = companion.use(self.workspace, 'productions/s/e', row['id'], explicit=self.repo)
        self.assertEqual(imported['status'], 'copied_and_verified')
        self.assertEqual(imported['animation_reference']['creative_ceiling'], 'open')
        manifest = local.read(self.project / 'asset_manifest.json')
        self.assertEqual(len(manifest['animation_references']), 1)
        reference = manifest['animation_references'][0]
        self.assertEqual(reference['external_asset_id'], row['id'])
        self.assertTrue((self.project / reference['entry']).is_file())
        manifest.update({'schema': 'medical_animation_assets/v1',
                         'shots': [{'shot_id': 'S01', 'asset_ids': []}]})
        self.project.joinpath('asset_manifest.json').write_text(json.dumps(manifest))
        self.assertEqual(check_assets(self.project / 'asset_manifest.json')['animation_references'], 1)

    def test_framework_headless_install_is_discovered_without_a_second_download(self):
        state = self.base / 'opl-state'
        installed = state / 'internal-package-carrier/plugins/cache/mac-media-assets/mac-media-assets/0.1.5'
        shutil.copytree(self.repo, installed, ignore=shutil.ignore_patterns('.git'))
        skill = installed / 'skills/mac-media-assets/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('# Assets')
        (self.workspace / 'workbench.yaml').write_text('asset_library:\n  root: ../mac-media-assets\n')
        with patch.dict('os.environ', {'OPL_STATE_DIR': str(state)}):
            status = companion.ensure(self.workspace, repository='/must-not-download')
            self.assertEqual(status['installation'], 'reused_existing')
            self.assertEqual(Path(status['repo']), installed.resolve())
            self.assertEqual(companion.query(self.workspace)['count'], 1)

    def test_current_managed_library_wins_over_an_old_native_cache(self):
        state = self.base / 'opl-state'
        old = state / 'internal-package-carrier/plugins/cache/mac-media-assets/mac-media-assets/0.1.5'
        current = state / 'codex-plugin-marketplaces/mac-media-assets/plugins/mac-media-assets'
        for folder in [old, current]:
            shutil.copytree(self.repo, folder, ignore=shutil.ignore_patterns('.git'))
            skill = folder / 'skills/mac-media-assets/SKILL.md'
            skill.parent.mkdir(parents=True)
            skill.write_text('# Assets')
        (self.workspace / 'workbench.yaml').write_text('asset_library:\n  root: ../mac-media-assets\n')
        with patch.dict('os.environ', {'OPL_STATE_DIR': str(state)}):
            found, _ = companion.locate(self.workspace)
            self.assertEqual(found, current.resolve())

    def test_native_local_source_update_wins_over_stale_managed_projection(self):
        state = self.base / 'opl-state'
        old = state / 'codex-plugin-marketplaces/mac-media-assets/plugins/mac-media-assets'
        current = state / 'internal-package-carrier/.tmp/marketplaces/mac-media-assets'
        for folder in [old, current]:
            shutil.copytree(self.repo, folder, ignore=shutil.ignore_patterns('.git'))
        (old / 'catalog/assets.jsonl').write_text('')
        (self.workspace / 'workbench.yaml').write_text('asset_library:\n  root: ../mac-media-assets\n')
        with patch.dict('os.environ', {'OPL_STATE_DIR': str(state)}):
            found, _ = companion.locate(self.workspace)
            self.assertEqual(found, current.resolve())
            self.assertEqual(companion.query(self.workspace)['count'], 1)

    def test_real_native_entry_selects_bundled_tool(self):
        completed = subprocess.run([sys.executable, str(ROOT/'runtime/native_helpers/workbench_tool.py'),
                                    '--workspace',str(self.workspace),'--name','media_asset_library','--','status'],
                                   capture_output=True,text=True,check=True)
        report=json.loads(completed.stdout)
        self.assertEqual(report['status'],'unavailable')
        self.assertFalse(report['blocks_production'])
        self.assertFalse(self.target.exists())

    def test_offline_empty_query_and_existing_directory_continue(self):
        report = companion.ensure(self.workspace, offline=True)
        self.assertFalse(report['blocks_production'])
        self.assertFalse(self.target.exists())
        self.assertEqual(companion.query(self.workspace)['count'], 0)
        self.target.mkdir()
        (self.target/'keep').write_text('keep')
        report = companion.ensure(self.workspace, repository=str(self.repo))
        self.assertEqual(report['installation'], 'preserved_existing')
        self.assertEqual((self.target/'keep').read_text(), 'keep')

    def test_collection_import_preserves_success_when_another_part_is_missing(self):
        companion.ensure(self.workspace, repository=str(self.repo))
        config={'assemblies':[{'id':'example','parts':[
            {'asset_id':self.row['id'],'source_id':'paper'},
            {'asset_id':'paper:missing@none','source_id':'missing'}]}]}
        (self.target/'collections/assemblies.json').write_text(json.dumps(config))
        result=companion.use_collection(self.workspace,'productions/s/e','example')
        self.assertEqual(result['status'],'copied_with_debt')
        self.assertFalse(result['blocks_production'])
        self.assertEqual(result['imports'][0]['status'],'copied_and_verified')
        self.assertTrue(Path(result['receipt']).is_file())
        self.assertEqual(len(local.read(self.project/'asset_manifest.json')['assets']),1)

    def test_empty_collection_provider_does_not_block_production(self):
        result=companion.use_collection(self.workspace,'productions/s/e','missing')
        self.assertEqual(result['status'],'not_imported')
        self.assertFalse(result['blocks_production'])

    def test_standalone_environment_original_enters_render_manifest(self):
        metadata={'id':'plain-door','kind':'environment','entry':'files/paper.png',
                  'reuse_scope':{'kind':'general'},'content_bounds':[1,2,3,4],
                  'medical_review':'not_applicable'}
        archived=local.archive(self.repo,metadata,[{'source':str(self.base/'original.png'),
                                                   'path':'files/paper.png'}])
        result=local.reuse(self.workspace.resolve(),self.repo.resolve(),'productions/s/e','plain-door',archived['revision'])
        self.assertEqual(len(result['imported_assets']),1)
        asset=local.read(self.project/'asset_manifest.json')['assets'][0]
        self.assertEqual(asset['content_bounds'],[1,2,3,4])
        self.assertEqual(asset['visual_review']['status'],'pending')
        original=local.read(self.repo/archived['record'])
        self.assertNotIn('asset',original)
        self.assertEqual(original['revision'],archived['revision'])

    def test_character_use_preserves_contact_anchors_and_resets_current_review(self):
        registration = {
            'pivot': {'x': .5, 'y': .5},
            'anchors': {'head': {'x': .5, 'y': .1},
                        'feet': {'x': .5, 'y': .95},
                        'hand_right': {'x': .7, 'y': .55}},
        }
        for wrapped in (False, True):
            with self.subTest(project_asset_wrapper=wrapped):
                identifier = 'character_wrapped' if wrapped else 'character_standalone'
                metadata = {'id': identifier, 'kind': 'transparent_subject',
                            'title': '完整人物站姿', 'entry': 'files/person.png',
                            'reuse_scope': {'kind': 'general'},
                            'registration': registration,
                            'review': {'static_alpha': 'passed'},
                            'medical_review': 'not_applicable'}
                if wrapped:
                    metadata['asset'] = {
                        'asset_id': identifier, 'path': 'files/person.png',
                        'registration': registration, 'medical': False,
                        'status': 'approved_direct_use',
                        'visual_review': {'status': 'passed'},
                    }
                archived = local.archive(self.repo, metadata, [
                    {'source': str(self.base/'original.png'), 'path': 'files/person.png'},
                ])
                original_path = self.repo / archived['record']
                original_bytes = original_path.read_bytes()
                record = local.read(original_path)
                row = {'id': f"paper:{identifier}@{record['revision']}",
                       'source_id': identifier, 'revision': record['revision'],
                       'kind': record['kind'], 'portable_record': archived['record'],
                       'portable_record_sha256': local.digest(original_path),
                       'reuse_scope': record['reuse_scope'],
                       'payload': [{**item, 'path': str(original_path.parent.relative_to(self.repo)/item['path'])}
                                   for item in record['files']]}
                (self.repo/'catalog/assets.jsonl').write_text(json.dumps(row)+'\n')
                result = companion.use(self.workspace, 'productions/s/e', row['id'],
                                       explicit=self.repo)
                self.assertEqual(result['status'], 'copied_and_verified')
                asset = next(item for item in local.read(self.project/'asset_manifest.json')['assets']
                             if item['asset_id'] == identifier)
                self.assertEqual(asset['registration'], registration)
                self.assertEqual(asset['status'], 'pending_review')
                self.assertEqual(asset['visual_review']['status'], 'pending')
                self.assertEqual((self.project/asset['path']).read_bytes(), b'actual paper bytes')
                self.assertEqual(original_path.read_bytes(), original_bytes)
                lineage = local.read(Path(result['directory'])/'external-source.json')
                self.assertEqual(lineage['asset_id'], row['id'])
                self.assertEqual(lineage['current_shot_review'], 'pending')

    def test_author_scope_filtered_and_not_importable_for_other_author(self):
        companion.ensure(self.workspace, repository=str(self.repo))
        row = dict(self.row, reuse_scope={'kind':'author','id':'another_author'})
        (self.target/'catalog/assets.jsonl').write_text(json.dumps(row)+'\n')
        with patch.object(companion, 'author_id', return_value='current_author'):
            self.assertEqual(companion.query(self.workspace)['count'], 0)
            self.assertEqual(companion.query(self.workspace,include_author_assets=True)['count'],1)
        record = local.read(self.target / row['portable_record'])
        record['reuse_scope'] = row['reuse_scope']
        local.write(self.target/row['portable_record'],record)
        with patch.object(companion, 'author_id', return_value='current_author'):
            result = companion.use(self.workspace,'productions/s/e',row['id'])
        self.assertEqual(result['status'],'not_imported')
        self.assertFalse((self.project/'assets/library').exists())

    def test_current_author_clinician_overrides_gender_alias_and_blocks_generic_import(self):
        profile_dir = self.workspace / 'profiles/authors'
        profile_dir.mkdir(parents=True)
        (profile_dir / 'dr_mie.yaml').write_text(
            'schema: medical_video_author_profile/v1\n'
            'profile_id: dr_mie\n'
            'display_name: Dr.咩\n'
            'visual_identity:\n'
            '  enabled: true\n'
            '  character_reference: assets/authors/dr_mie/reference.png\n'
            '  character_library:\n'
            '    root: assets/authors/dr_mie/library\n'
            '    poses: poses.json\n'
            '    default_for_clinician: true\n'
            '    request_aliases: [医生, 女性医生]\n'
        )
        record_dir = self.workspace / 'assets/authors/dr_mie/library/entries/dr_mie_stand/v1'
        record_dir.mkdir(parents=True)
        (record_dir / 'person.png').write_bytes(b'dr mie bytes')
        local.write(record_dir / 'record.json', {
            'id': 'dr_mie_stand', 'revision': 'v1', 'title': 'Dr.咩站姿',
            'kind': 'transparent_subject', 'reuse_scope': {'kind': 'author', 'id': 'dr_mie'},
            'registration': {'pivot': {'x': .5, 'y': .5}}, 'content_bounds': [1, 2, 30, 80],
            'review': {'identity': 'compared_with_named_master'},
            'files': [{'path': 'person.png', 'role': 'payload'}],
        })
        local.write(self.workspace / 'assets/authors/dr_mie/library/poses.json', {
            'poses': {'stand_explain': {'id': 'dr_mie_stand', 'revision': 'v1',
                                        'record': 'entries/dr_mie_stand/v1/record.json'}}
        })
        (self.workspace / 'assets/authors/dr_mie/reference.png').write_bytes(b'reference')
        (self.workspace / 'workbench.yaml').write_text(
            'active_profiles:\n  author: profiles/authors/dr_mie.yaml\n'
            'series:\n  s:\n    author_profile: profiles/authors/dr_mie.yaml\n'
        )
        queried = companion.query(self.workspace, series='s', character_role='男医生', pose='站立讲解')
        self.assertEqual(queried['library'], 'author_private')
        self.assertEqual(queried['assets'][0]['title'], 'Dr.咩站姿')
        queries = {
            'explicit_generic': companion.query(self.workspace, series='s', character_role='男性医生', pose='站立讲解',
                                                character_context='generic', explicit=self.repo),
            'generic_without_role': companion.query(self.workspace, series='s', character_context='generic', explicit=self.repo),
            'exact_external_id': companion.query(self.workspace, series='s', asset_id='paper:clinician@v1', explicit=self.repo),
            'physician_alias': companion.query(self.workspace, series='s', character_role='physician', explicit=self.repo),
            'include_author_assets': companion.query(self.workspace, series='s', asset_id='paper:clinician@v1',
                                                     include_author_assets=True, explicit=self.repo),
        }
        for name, result in queries.items():
            with self.subTest(query=name):
                self.assertEqual(result['library'], 'author_private')
                self.assertEqual(result['assets'][0]['source_id'], 'dr_mie_stand')

        generic = self.base / 'generic.png'
        generic.write_bytes(b'generic clinician bytes')
        archive = local.archive(self.repo, {
            'id': 'character_clinician_woman_stand_v1', 'kind': 'transparent_subject',
            'title': '女性医生完整讲解站姿', 'entry': 'files/person.png',
            'reuse_scope': {'kind': 'general'},
            'discovery': {'character_role': 'clinician_woman'},
        }, [{'source': str(generic), 'path': 'files/person.png'}])
        record = local.read(self.repo / archive['record'])
        row = {'id': 'paper:portrait_7_stand@v1', 'source_id': record['id'], 'revision': record['revision'],
               'kind': record['kind'], 'portable_record': archive['record'],
               'reuse_scope': record['reuse_scope'],
               'payload': [{**record['files'][0],
                            'path': str(Path(archive['record']).parent / 'files/person.png')}]}
        (self.repo / 'catalog/assets.jsonl').write_text(json.dumps(row) + '\n')
        legacy_woman = companion.query(self.workspace, series='s', asset_id=row['id'],
                                       include_author_assets=True, explicit=self.repo)
        self.assertEqual(legacy_woman['library'], 'author_private')
        self.assertEqual(legacy_woman['assets'][0]['source_id'], 'dr_mie_stand')
        broad_with_author_assets = companion.query(self.workspace, series='s', include_author_assets=True,
                                                   explicit=self.repo)
        self.assertEqual(broad_with_author_assets['count'], 0)
        denied = companion.use(self.workspace, 'productions/s/e', row['id'], explicit=self.repo)
        self.assertEqual(denied['status'], 'not_imported')
        self.assertEqual(denied['replacement']['library'], 'author_private')
        self.assertEqual(local.read(self.project / 'asset_manifest.json')['assets'], [])

        # The private query result is also usable without a public-library path.
        private = self.workspace / 'assets/authors/dr_mie/library'
        human_scale = {'nominal_height_cm': 165, 'pose': 'stand_explain',
                       'calibration': {'status': 'pending'}}
        archived = local.archive(private, {'id':'scaled_author', 'kind':'transparent_subject',
            'entry':'files/person.png', 'reuse_scope':{'kind':'author','id':'dr_mie'},
            'human_scale':human_scale}, [{'source': record_dir / 'person.png', 'path':'files/person.png'}])
        identifier = f"author:dr_mie/scaled_author@{archived['revision']}"
        imported = companion.use(self.workspace, 'productions/s/e', identifier)
        self.assertEqual(imported['library'], 'author_private')
        self.assertEqual(imported['status'], 'copied_and_verified')
        self.assertEqual(local.read(self.project / 'asset_manifest.json')['assets'][0]['human_scale'], human_scale)

    def test_author_motion_aliases_and_copied_sequence_registration(self):
        profile = self.workspace / 'author.yaml'
        profile.write_text('profile_id: example_author\nvisual_identity:\n  enabled: true\n'
                           '  character_reference: reference.png\n  character_library:\n'
                           '    root: private\n    default_for_clinician: true\n')
        (self.workspace / 'workbench.yaml').write_text('active_profiles:\n  author: author.yaml\n'
                                                       'series:\n  s:\n    author_profile: author.yaml\n')
        sequence = self.base / 'sequence.json'
        sequence.write_text('{"frames":[],"events":[]}')
        registration = {'coordinate_space': 'frame_local_pixels', 'frames_ref': 'sequence.json'}
        poses = {}
        for pose in ['walk_cycle', 'sit_cycle', 'handoff_action']:
            archived = local.archive(self.workspace / 'private', {
                'id': pose, 'kind': 'motion_recipe', 'title': pose, 'entry': 'sequence.json',
                'registration': registration, 'reuse_scope': {'kind': 'author', 'id': 'example_author'},
            }, [{'source': sequence, 'path': 'sequence.json'}])
            poses[pose] = {'id': pose, 'revision': archived['revision'], 'record': archived['record']}
        local.write(self.workspace / 'private/poses.json', {'poses': poses})
        for alias, pose in [('走上前', 'walk_cycle'), ('坐站过渡', 'sit_cycle'), ('连续递接报告', 'handoff_action')]:
            result = companion.query(self.workspace, character_role='医生', pose=alias)
            self.assertEqual([a['pose'] for a in result['assets']], [pose])
            inferred = companion.query(self.workspace, text='医生' + alias)
            self.assertEqual([a['pose'] for a in inferred['assets']], [pose])
        imported = companion.use(self.workspace, 'productions/s/e', result['assets'][0]['id'])
        self.assertEqual(imported['registration_readback']['status'], 'preserved')
        self.assertEqual(imported['registration_readback']['checked_files'], ['sequence.json'])
        self.assertEqual(Path(imported['motion_recipe_readback']['sequence']).read_bytes(), sequence.read_bytes())
        copied = Path(imported['directory'])
        (copied / 'sequence.json').unlink()
        record = local.read(copied / 'library-record.json')
        self.assertEqual(companion.motion_registration_readback(record, copied)['registration_readback']['status'], 'diagnostic')

    def test_corrupt_payload_and_static_reference_do_not_enter_motion_manifest(self):
        companion.ensure(self.workspace, repository=str(self.repo))
        row = dict(self.row, kind='reference_frame')
        (self.target/'catalog/assets.jsonl').write_text(json.dumps(row)+'\n')
        self.assertEqual(companion.use(self.workspace,'productions/s/e',row['id'])['status'],'not_imported')
        (self.target/'catalog/assets.jsonl').write_text(json.dumps(self.row)+'\n')
        (self.target/self.row['payload'][0]['path']).write_bytes(b'different')
        with self.assertRaises(ValueError):
            companion.use(self.workspace,'productions/s/e',self.row['id'])
        self.assertEqual(local.read(self.project/'asset_manifest.json')['assets'],[])

    def test_old_companion_cannot_recommend_or_import_withdrawn_material(self):
        companion.ensure(self.workspace, repository=str(self.repo))
        row = {**self.row, 'curation': {'status': 'needs_rebuild', 'reason': 'split parts first'}}
        (self.target/'catalog/assets.jsonl').write_text(json.dumps(row)+'\n')
        self.assertEqual(companion.query(self.workspace)['count'], 0)
        self.assertEqual(companion.query(self.workspace, include_reference=True)['count'], 1)
        result = companion.use(self.workspace, 'productions/s/e', row['id'])
        self.assertEqual(result['status'], 'not_imported')
        self.assertFalse(result['blocks_production'])
        self.assertEqual(local.read(self.project/'asset_manifest.json')['assets'], [])


if __name__ == '__main__':
    unittest.main()
