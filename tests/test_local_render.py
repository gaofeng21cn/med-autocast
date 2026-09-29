"""Opt-in browser/encoder regression using an initialized, isolated workbench."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / 'runtime/workbench/scripts'
RUNTIME = os.environ.get('MED_AUTOCAST_TEST_WORKSPACE')


@unittest.skipUnless(RUNTIME and all(shutil.which(name) for name in ('node', 'ffmpeg', 'ffprobe')),
                     'Set MED_AUTOCAST_TEST_WORKSPACE to an initialized workbench for real rendering')
class LocalRenderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.env = {**os.environ, 'MED_AUTOCAST_WORKSPACE_ROOT': str(Path(RUNTIME).resolve())}
        from PIL import Image
        Image.new('RGB', (32, 32), '#377a70').save(self.project / 'paper.png')
        self.html = '''<!doctype html><html><head><link rel="icon" href="data:,"></head>
<body style="margin:0"><canvas id="film" width="320" height="180"></canvas>
<script>
const image = new Image(); image.src = 'paper.png';
const ready = image.decode();
window.__seek = async t => {await ready;
  const ctx = document.querySelector('canvas').getContext('2d');
  ctx.fillStyle = '#fafafa'; ctx.fillRect(0,0,320,180);
  ctx.drawImage(image,40+t*80,60,60,60);
};
</script></body></html>'''
        (self.project / 'index.html').write_text(self.html)
        manifest = {'schema': 'medical_animation_assets/v1', 'assets': [{
            'asset_id': 'paper', 'path': 'paper.png', 'source_type': 'authored_graphic',
            'medical': False, 'visual_meaning': 'technical motion fixture',
            'must_not_imply': 'medical or artistic approval', 'status': 'pending_review',
        }], 'shots': [{'shot_id': 'B01', 'asset_ids': ['paper']}]}
        (self.project / 'asset_manifest.json').write_text(json.dumps(manifest))
        self.audio = self.project / 'audio.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'anullsrc=r=24000:cl=mono', '-t', '0.5', str(self.audio)], check=True)
        self.output = self.project / 'output.mp4'

    def invoke(self, shared=True, output=None):
        args = [sys.executable, '-B', str(SCRIPTS / 'render_javascript_animation.py'),
                '--project-root', str(self.project), '--review-candidate',
                '--output', str(output or self.output)]
        if shared:
            args += ['--audio', str(self.audio), '--width', '320', '--height', '180']
        else:
            args += ['--fps', '12']
        return subprocess.run(args, env=self.env, text=True, capture_output=True, timeout=60)

    def test_real_shared_render_and_legacy_project_entry(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
                                                    '-of', 'json', str(self.output)]))
        video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        self.assertEqual(video['avg_frame_rate'], '24/1')
        self.assertEqual(video['codec_name'], 'h264')
        self.assertTrue(any(s['codec_type'] == 'audio' for s in probe['streams']))
        from PIL import Image, ImageChops
        frames = sorted(self.project.glob('.render-*/frame-*.png'), key=lambda p: int(p.stem.split('-')[1]))
        with Image.open(frames[0]) as first, Image.open(frames[-1]) as last:
            self.assertTrue(any(high > low for low, high in first.convert('RGB').getextrema()))
            self.assertIsNotNone(ImageChops.difference(first.convert('RGB'), last.convert('RGB')).getbbox())
        receipt = json.loads(self.output.with_suffix('.receipt.json').read_text())
        self.assertFalse(receipt['release_eligible'])
        before = self.output.read_bytes()
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertEqual(before, self.output.read_bytes())
        # Legacy render/mux remains episode-owned; verify ordering and argument forwarding.
        work = self.project / 'work'
        work.mkdir()
        (work / 'render_frames.mjs').write_text("import fs from 'node:fs'; fs.writeFileSync('render-args.json', JSON.stringify(process.argv.slice(2)));")
        (work / 'mux.mjs').write_text("import fs from 'node:fs'; fs.readFileSync('render-args.json'); fs.copyFileSync('output.mp4', 'legacy.mp4');")
        legacy = self.project / 'legacy.mp4'
        result = self.invoke(shared=False, output=legacy)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.project / 'render-args.json').read_text()), ['--fps=12'])
        self.assertEqual(legacy.read_bytes(), before)

    def test_missing_css_resource_cannot_publish_video(self):
        (self.project / 'index.html').write_text(self.html.replace('</head>', '<link rel="stylesheet" href="missing.css"></head>'))
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing.css', result.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.with_suffix('.receipt.json').exists())


if __name__ == '__main__':
    unittest.main()
