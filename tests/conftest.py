import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "plugins", "keremkit", "skills", "keremkit", "scripts")

SENTENCE = ("Hello everyone today I want to show you something really important "
            "let's look at the screen here we have 25,000 people and that is a great result. "
            "So how did it happen? Let me explain it step by step").split()


def run(script, *args, env=None, check=True):
    """Run a kit script the way users do (isolated interpreter) and return stdout."""
    cmd = [sys.executable, "-I", os.path.join(SCRIPTS, script), *map(str, args)]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    if check and res.returncode != 0:
        raise AssertionError(f"{script} {args} failed:\n{res.stdout}\n{res.stderr}")
    return res


@pytest.fixture
def words_file(tmp_path):
    """Whisper-style JSON with word timestamps and a few long pauses."""
    t, words = 0.6, []
    pauses = [0.05, 0.1, 0.3, 0.5]
    for i, w in enumerate(SENTENCE):
        d = 0.18 + 0.03 * len(w)
        words.append({"word": " " + w, "start": round(t, 3), "end": round(t + d, 3)})
        t += d + (1.4 if i in (5, 12, 19) else pauses[i % 4])
    path = tmp_path / "cam.json"
    path.write_text(json.dumps({"language": "en", "segments": [{"words": words}]}), encoding="utf-8")
    return path, round(t + 1, 2)


@pytest.fixture
def has_ffmpeg():
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
