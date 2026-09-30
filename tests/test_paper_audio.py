"""Exercise real local mixing, voice preservation, and sidechain recovery."""

import array
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

MIXER = Path(__file__).resolve().parents[1] / "runtime/workbench/templates/animation/paper_theatre/scripts/mix_audio.py"
RATE = 48000


def write_signal(path, frequency, amplitude, active):
    samples = array.array("h", (
        round(amplitude * 32767 * math.sin(2 * math.pi * frequency * i / RATE)) if active(i / RATE) else 0
        for i in range(7 * RATE)
    ))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(samples.tobytes())


def rms(path, start, end):
    data = subprocess.check_output([
        "ffmpeg", "-v", "error", "-ss", str(start), "-i", str(path),
        "-t", str(end - start), "-ac", "1", "-f", "f32le", "-",
    ])
    samples = array.array("f")
    samples.frombytes(data)
    return math.sqrt(sum(x * x for x in samples) / len(samples))


@unittest.skipUnless(shutil.which("ffmpeg"), "real mixing needs FFmpeg")
class PaperAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "score.json").write_text(json.dumps({"duration": 7, "shots": [], "sounds": []}))
        (self.root / "asset_manifest.json").write_text('{"assets": []}')
        self.voice = self.root / "voice.wav"
        write_signal(self.voice, 230, .3, lambda t: 1 <= t < 3)
        self.voice_hash = hashlib.sha256(self.voice.read_bytes()).hexdigest()

    def mix(self, *options):
        subprocess.run([
            sys.executable, str(MIXER), "--project", str(self.root),
            "--voice", str(self.voice), "--output", str(self.root / "mixed.wav"), *options,
        ], check=True, capture_output=True, text=True)
        receipt = json.loads((self.root / "audio/mix-receipt.json").read_text())
        self.assertEqual(hashlib.sha256(self.voice.read_bytes()).hexdigest(), self.voice_hash)
        self.assertEqual(receipt["voice_sha256"], self.voice_hash)
        self.assertEqual(receipt["sample_rate"], RATE)
        self.assertEqual(receipt["channels"], 2)
        self.assertFalse(receipt["voice_resynthesized"])
        self.assertEqual(receipt["full_listening"], "pending")
        return receipt

    def test_music_ducks_during_voice_and_recovers_after_silence(self):
        write_signal(self.root / "music.wav", 530, .08, lambda _: True)
        plan = self.root / "music-plan.json"
        plan.write_text(json.dumps({"tracks": [{"id": "bed", "path": "music.wav", "gain": .5}]}))
        receipt = self.mix("--music-plan", str(plan))
        self.assertEqual(len(receipt["music_tracks"]), 1)
        before = self.root / "audio/music-prepared.wav"
        after = self.root / "audio/music-ducked.wav"
        self.assertLess(rms(after, 1.8, 2.8) / rms(before, 1.8, 2.8), .7)
        self.assertGreater(rms(after, 5.2, 5.8) / rms(before, 5.2, 5.8), .95)

    def test_voice_only_path_keeps_music_silent_and_encodes_stereo(self):
        receipt = self.mix()
        self.assertEqual(receipt["music_tracks"], [])
        self.assertEqual(rms(self.root / "audio/music-ducked.wav", 1.8, 2.8), 0)
        self.assertGreater(rms(self.root / "mixed.wav", 1.8, 2.8), .01)
        info = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(self.root / "mixed.wav"),
        ]))["streams"][0]
        self.assertEqual(info["channels"], 2)
        self.assertEqual(info["sample_rate"], str(RATE))
