import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('medcast',Path(__file__).resolve().parents[1]/'runtime/native_helpers/medcast.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        for name in ['master.mp4','old.mp4','voice.wav','captions.srt','source.mp4','evidence.json']:(self.root/name).write_text('fixture only')
        self.current={'schema':'opl_medcast_current_selection/v1','series_id':'s1','revision':'r2','episode_ids':['01'],'master_refs':{'01':'master.mp4'}}
        self.delivery={'schema':'opl_medcast_delivery/v1','series_id':'s1','revision':'r2','intent':'review','episodes':[{'episode_id':'01','master_ref':'master.mp4','narration_ref':'voice.wav','subtitles_ref':'captions.srt','shots':[{'source_id':'shot1','source_ref':'source.mp4','source_range':[0,3]}],'reviews':{}}]}
        self.sources={'shot1':{'accepted':True,'source_ref':'source.mp4','usable_range':[0,6]}}
    def run_check(self):
        for n,d in [('current',self.current),('delivery',self.delivery),('sources',self.sources)]: (self.root/f'{n}.json').write_text(json.dumps(d))
        return m.preflight(self.root,'delivery.json','current.json','sources.json')
    def test_review_preserves_debt(self):
        result=self.run_check();self.assertEqual(len(result['quality_debt']),5);self.assertFalse(result['domain_quality_approved'])
    def test_rejected_source_overrides_residual_range(self):
        self.sources['shot1']['accepted']=False
        with self.assertRaises(m.ContractError):self.run_check()
    def test_unknown_source_not_approved(self):
        del self.sources['shot1']['accepted']
        with self.assertRaises(m.ContractError):self.run_check()
    def test_out_of_range(self):
        self.delivery['episodes'][0]['shots'][0]['source_range']=[5,7]
        with self.assertRaises(m.ContractError):self.run_check()
    def test_nonfinite_range(self):
        self.delivery['episodes'][0]['shots'][0]['source_range']=[0,float('nan')]
        with self.assertRaises(m.ContractError):self.run_check()
    def test_old_master_with_current_revision(self):
        self.delivery['episodes'][0]['master_ref']='old.mp4'
        with self.assertRaises(m.ContractError):self.run_check()
    def test_wrong_selection(self):
        self.current['episode_ids']=['02']
        with self.assertRaises(m.ContractError):self.run_check()
    def test_duplicate_selection(self):
        self.delivery['episodes']*=2
        with self.assertRaises(m.ContractError):self.run_check()
    def test_path_escape(self):
        self.delivery['episodes'][0]['master_ref']='../outside.mp4'
        with self.assertRaises(m.ContractError):self.run_check()
    def test_false_publication_claim(self):
        self.delivery['intent']='publication_candidate'
        with self.assertRaises(m.ContractError):self.run_check()
    def test_review_bound_to_old_master(self):
        self.delivery['episodes'][0]['reviews']['technical']={'status':'passed','evidence_ref':'evidence.json','artifact_ref':'old.mp4'}
        with self.assertRaises(m.ContractError):self.run_check()
    def test_all_pass_is_not_publication_authority(self):
        self.delivery['intent']='publication_candidate'
        self.delivery['episodes'][0]['reviews']={key:{'status':'passed','evidence_ref':'evidence.json','artifact_ref':'master.mp4'} for key in m.REVIEW_GATES}
        self.assertFalse(self.run_check()['publication_authorized'])
    def test_symlink_escape(self):
        (self.root/'escape').symlink_to(self.root.parent,target_is_directory=True)
        with self.assertRaises(m.ContractError):m.local_path(self.root,'escape/private',exists=False)

class AssetTest(unittest.TestCase):
    def test_optional_video_review_and_rejected_video(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'assets/keyframes';base.mkdir(parents=True)
            (base/'frame.png').write_text('fixture')
            common={'file':'frame.png','admission':{'decision':'reference_library_only'}}
            catalog={'schema':'medical_keyframe_library/v1','assets':[
                dict(common,id='static',related_video_review=None),
                dict(common,id='rejected',related_video_review={'snapshot':{'accepted':False,'usable_range':[0,3]}})]}
            (base/'catalog.json').write_text(json.dumps(catalog))
            result=m.query_assets(root)
            self.assertEqual(result['count'],2)
            self.assertTrue(result['assets'][1]['related_video_rejected'])
            self.assertIsNone(result['assets'][1]['related_video_usable_range'])

if __name__=='__main__':unittest.main()
