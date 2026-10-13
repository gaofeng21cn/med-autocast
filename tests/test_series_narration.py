"""The bundled series entry must operate on the caller's workspace and timings."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "runtime/workbench/scripts"))
import render_series_tts as series
from init_workbench import initialize
from build_episode_timelines import build_cues


class SeriesNarrationTests(unittest.TestCase):
    def test_explicit_workspace_episode_range_and_actual_gap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = (Path(temp) / "workspace").resolve()
            initialize(root)
            workbench = root / "workbench.yaml"
            config = yaml.safe_load(workbench.read_text())
            config["series"] = {"sample": {"content_root": "content/sample", "production_root": "productions/sample"}}
            workbench.write_text(yaml.safe_dump(config))
            for name in ("01_first", "02_second"):
                p = root / "content/sample/episodes" / name / "01_narration.md"
                p.parent.mkdir(parents=True)
                p.write_text("## B01 开头\n看字<还|HAI2>清楚。\n")
            called = []

            def synthesize(workspace, narration, output, *args, **kwargs):
                self.assertEqual(workspace, root.resolve())
                self.assertEqual(kwargs["gap_seconds"], .45)
                source = json.loads(narration.read_text())
                self.assertEqual(source["beats"][0]["text"], "看字还清楚。")
                self.assertEqual(source["beats"][0]["tts_text"], "看字<还|HAI2>清楚。")
                called.append(output)
                audio = output / "narration-normalized.wav"
                with wave.open(str(audio), "wb") as wav:
                    wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                    wav.writeframes(b"\0" * 48000)
                receipt = {"audio": str(audio), "backend": "voice", "beats": [], "generated": ["B01"], "reused": [], "full_listening": "pending"}
                (output / "narration_beats.json").write_text(json.dumps(receipt))
                return receipt

            with patch.object(series, "synthesize", side_effect=synthesize), patch.object(sys, "argv", [
                "render_series_tts", "--workspace", str(root), "--series", "sample", "--end-episode", "1", "--silence-ms", "450"
            ]):
                series.main()
            self.assertEqual(len(called), 1)
            self.assertEqual(called[0], root / "productions/sample/01_first/audio/local_voice")
            receipt = json.loads((called[0] / "narration_beats.json").read_text())
            self.assertEqual(receipt["audio_source"], "audio/local_voice/narration-normalized.wav")
            self.assertEqual(receipt["duration"], 1.0)
            self.assertEqual(receipt["full_listening"], "pending")
            self.assertFalse((called[0] / "voxcpm2-narration.wav").exists())

    def test_asr_word_timing_accounts_for_trimmed_reference_take(self):
        manifest = {"beats": [{"id": "B01", "text": "你好。", "start": .32, "end": 2.32, "trimmed_head_seconds": .4}]}
        alignment = {"beats": [{"id": "B01", "segments": [{"start": .4, "end": 2.4,
            "words": [{"word": "你好", "start": .4, "end": 2.4}]}]}]}
        before = json.dumps(alignment)
        cue = build_cues(manifest, alignment)[0]
        self.assertEqual(cue["start"], .32)
        self.assertEqual(cue["end"], 2.32)
        self.assertEqual(json.dumps(alignment), before)
