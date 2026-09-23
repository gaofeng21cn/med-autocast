"""Native input compatibility, currentness and inherited review boundaries."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'runtime/native_helpers'))
sys.path.insert(0, str(REPO/'runtime/workbench/scripts'))
from workbench_adapter import preflight_native, tool_inventory, run_tool
from build_release_packages import platform_text


class NativeContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ep = self.root/'productions/s/01_example'
        self.publish = self.root/'publish/s/01_example'
        self.ep.mkdir(parents=True)
        self.publish.mkdir(parents=True)
        for name in ('audio.wav', 'text.srt', 'candidates/scene.mp4', 'review/video.mp4'):
            p=self.ep/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b'contract fixture; no media claim')
        self.plan={'schema':'video_production_plan/v3','episode_id':'01_example',
                   'audio':{'source':'audio.wav','duration_seconds':3},'subtitles':{'source':'text.srt'},
                   'visual_timeline':[{'segment_id':'V01','source_id':'scene','source':'scene.mp4','start':0,'end':3,'source_start':0,'source_end':3}]}
        self.dump('workbench.yaml', {'schema':'medical_video_workbench/v2','series':{'s':{
            'production_root':'productions/s','publish_root':'publish/s','release_catalog':'content/catalog.yaml'}}})
        self.entry={'id':'01_example','xiaohongshu_title':'标题','xiaohongshu_copy':'已审正文',
                    'xiaohongshu_tags':['科普'],'channels_title':'标题','channels_copy':'正文',
                    'channels_tags':['科普'],'pinned_comment':'已审评论'}
        self.dump('content/catalog.yaml',{'series_id':'s','episodes':[self.entry]})
        self.dump('productions/s/01_example/review/production_plan.yaml',self.plan)
        self.master='productions/s/01_example/review/video.mp4'
        shutil.copyfile(self.root/self.master,self.publish/'video.mp4')
        self.dump('publish/s/manifest.json',{'schema':'medical_video_review_package/v1','series_id':'s',
            'full_listening':'pending','medical_review':'pending','episodes':[{'id':'01_example','source':self.master}]})
        self.dump('source-review.json',{'scene':{'accepted':True,'source_ref':'productions/s/01_example/candidates/scene.mp4','usable_range':[0,3]}})
        for platform,name in [('xiaohongshu','小红书文案.txt'),('channels','微信视频号文案.txt')]:
            (self.publish/name).write_text(platform_text(self.entry,platform))
        (self.publish/'发布交付包.md').write_text('审看包，医学与听感待审')

    def dump(self,name,value):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(yaml.safe_dump(value,allow_unicode=True) if p.suffix=='.yaml' else json.dumps(value,ensure_ascii=False))

    def check(self):
        return preflight_native(self.root,'s','01_example','productions/s/01_example/review/production_plan.yaml',self.master,source_review_ref='source-review.json')

    def test_original_yaml_and_review_manifest_without_conversion(self):
        before=sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        result=self.check()
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['review_claims']['medical_review'],'pending')
        self.assertFalse(result['domain_quality_approved'])
        self.assertEqual(before,sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*')))

    def test_formal_v2_manifest_and_plan_v2(self):
        self.plan['schema']='video_production_plan/v2'
        self.dump('productions/s/01_example/review/production_plan.yaml',self.plan)
        self.dump('publish/s/manifest.json',{'schema':'medical_video_series_delivery/v2','series_id':'s',
            'path_base':'manifest_directory','episodes':[{'episode_id':'01_example','video':'01_example/video.mp4'}]})
        self.assertTrue(self.check()['video_bytes_equal'])

    def test_rejected_source_even_with_residual_range(self):
        self.dump('source-review.json',{'scene':{'accepted':False,'usable_range':[0,10]}})
        with self.assertRaisesRegex(ValueError,'拒绝'):self.check()

    def test_legacy_unbound_review_stays_debt(self):
        self.dump('source-review.json',{'scene':{'accepted':True,'usable_range':[0,3]}})
        self.assertEqual(self.check()['quality_debt'][0]['status'],'needs_evidence')

    def test_plan_linked_rejection_is_not_overridden_by_another_approval(self):
        self.dump('new-review.json',{'scene':{'accepted':False,'usable_range':[0,3]}})
        self.plan['visual_timeline'][0]['source_review']='new-review.json'
        self.dump('productions/s/01_example/review/production_plan.yaml',self.plan)
        with self.assertRaisesRegex(ValueError,'拒绝'):self.check()

    def test_stale_video_is_rejected(self):
        (self.publish/'video.mp4').write_bytes(b'old')
        with self.assertRaisesRegex(ValueError,'字节'):self.check()

    def test_stale_platform_copy_is_rejected(self):
        (self.publish/'微信视频号文案.txt').write_text('旧稿')
        with self.assertRaisesRegex(ValueError,'文案'):self.check()

    def test_out_of_range_source_and_wrong_episode_are_rejected(self):
        self.plan['visual_timeline'][0]['source_end']=4
        self.dump('productions/s/01_example/review/production_plan.yaml',self.plan)
        with self.assertRaisesRegex(ValueError,'范围'):self.check()
        self.plan['episode_id']='02_other'
        self.dump('productions/s/01_example/review/production_plan.yaml',self.plan)
        with self.assertRaisesRegex(ValueError,'集号'):self.check()

    def test_local_script_precedence_and_workspace_cwd(self):
        scripts=self.root/'scripts';scripts.mkdir()
        (scripts/'workbench_config.py').write_text("from pathlib import Path\nimport os\nassert Path.cwd()==Path(os.environ['MED_AUTOCAST_WORKSPACE_ROOT'])\n")
        item=next(t for t in tool_inventory(self.root)['tools'] if t['name']=='workbench_config')
        self.assertEqual(item['implementation'],'workspace')
        self.assertEqual(run_tool(self.root,'workbench_config',[]),0)
        self.assertTrue(all(t['exists'] for t in tool_inventory(self.root)['tools']))

    def test_unknown_tool_cannot_execute(self):
        with self.assertRaises(ValueError):run_tool(self.root,'../../other',[])

    def test_review_packager_preserves_other_episodes_and_previous_bytes(self):
        manifest_path=self.root/'publish/s/manifest.json'
        manifest=json.loads(manifest_path.read_text())
        other={'id':'02_other','source':'unchanged','custom_review':'pending'}
        manifest['episodes'].append(other)
        manifest_path.write_text(json.dumps(manifest))
        self.dump('review.json',{'episode':'01_example','production_plan':'productions/s/01_example/review/production_plan.yaml',
            'video_source':self.master,'audio_source':'productions/s/01_example/audio.wav',
            'srt_source':'productions/s/01_example/text.srt','segments':self.plan['visual_timeline'],
            'medical_review':'pending','full_listening':'pending'})
        # Relative source paths in the record use the same episode candidates base.
        args=['--series','s','--episode','01_example','--plan',str(self.root/'productions/s/01_example/review/production_plan.yaml'),
              '--master',str(self.root/self.master),'--review',str(self.root/'review.json')]
        shutil.copytree(REPO/'runtime/workbench/scripts',self.root/'scripts')
        self.assertEqual(run_tool(self.root,'package_review',args),0)
        updated=json.loads(manifest_path.read_text())
        self.assertIn(other,updated['episodes'])
        backups=list((self.root/'publish/s/archive').glob('*/01_example/video.mp4'))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_bytes(),(self.root/self.master).read_bytes())

    def test_incorrect_review_cannot_replace_delivery(self):
        before=(self.publish/'video.mp4').read_bytes()
        self.dump('review.json',{'episode':'02_other'})
        args=['--series','s','--episode','01_example','--plan',str(self.root/'productions/s/01_example/review/production_plan.yaml'),
              '--master',str(self.root/self.master),'--review',str(self.root/'review.json')]
        self.assertNotEqual(run_tool(self.root,'package_review',args,True),0)
        self.assertEqual((self.publish/'video.mp4').read_bytes(),before)

    def test_review_packager_does_not_mix_into_formal_v2_manifest(self):
        self.dump('publish/s/manifest.json',{'schema':'medical_video_series_delivery/v2','series_id':'s','episodes':[]})
        self.dump('review.json',{'episode':'01_example'})
        before=(self.root/'publish/s/manifest.json').read_bytes()
        args=['--series','s','--episode','01_example','--plan',str(self.root/'productions/s/01_example/review/production_plan.yaml'),
              '--master',str(self.root/self.master),'--review',str(self.root/'review.json')]
        self.assertNotEqual(run_tool(self.root,'package_review',args,True),0)
        self.assertEqual((self.root/'publish/s/manifest.json').read_bytes(),before)


if __name__=='__main__':unittest.main()
