"""Regression tests for the 1.3 review findings and the 1.4 tools."""
import json
import os
import subprocess
import zipfile

import pytest

from conftest import run


@pytest.fixture
def home(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    kk = tmp_path / "KeremKit"
    run("keremkit.py", "init", kk, env=env)
    return kk, env


def two_words(tmp_path, name="w.json"):
    p = tmp_path / name
    p.write_text(json.dumps({"language": "en", "segments": [{"words": [
        {"word": " Hello", "start": 0.1, "end": 0.5}, {"word": " there.", "start": 0.6, "end": 1.0}]}]}), encoding="utf-8")
    return p


# ---------------------------------------------------------------- 2.1 zone end
def test_plan_zone_end_is_at_plus_duration(tmp_path):
    two_words(tmp_path)
    (tmp_path / "plan.json").write_text(json.dumps({"placements": [
        {"words": "w.json", "from": 0, "to": None, "at": 41.2, "zone": "camera"}]}), encoding="utf-8")
    run("subtitles.py", "build", "--plan", tmp_path / "plan.json", "-o", tmp_path / "subs")
    z = json.loads((tmp_path / "subs.json").read_text(encoding="utf-8"))["zones"][0]
    assert z["s"] == 41.2 and z["e"] == pytest.approx(42.2, abs=0.01)


# ---------------------------------------------------------------- 2.2 invalid ranges
def test_invalid_cut_ranges_are_errors(tmp_path):
    w = two_words(tmp_path)
    c = tmp_path / "c.json"
    run("cutlist.py", "build", "--words", w, "--media", tmp_path / "x.mp4", "--duration", 3, "--fps", 30,
        "--silence", "off", "-o", c)
    for args in (["cut", c, "--from", 2, "--to", 1], ["add", c, "--at", 0.3, "--sec", -1],
                 ["add", c, "--from", 2, "--to", 1, "--sec", 1], ["restore", c, "--src-from", 2.5, "--src-to", 1.0],
                 ["cut", c, "--from", 50, "--to", 60]):
        r = run("cutlist.py", *args, check=False)
        assert r.returncode != 0 and "ERROR" in (r.stderr + r.stdout), args


# ---------------------------------------------------------------- 2.3 / 2.4 / 2.5
def test_nested_pref_under_null_parent(home):
    _, env = home
    run("keremkit.py", "pref", "set", "subtitles.look.font=Inter", "design_import.preview.mode=auto", env=env)
    assert run("keremkit.py", "pref", "get", "subtitles.look", env=env).stdout.strip() == '{"font": "Inter"}'


def test_add_missing_or_broken_file(home, tmp_path):
    _, env = home
    r = run("keremkit.py", "add", tmp_path / "nope.json", env=env, check=False)
    assert r.returncode != 0 and "file not found" in r.stderr and "Traceback" not in r.stderr
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    r = run("keremkit.py", "add", bad, env=env, check=False)
    assert r.returncode != 0 and "not valid JSON" in r.stderr


def test_catalog_with_missing_columns_and_reindex(home):
    kk, env = home
    item = kk / "library" / "items" / "ui" / "UI-001_gold"
    item.mkdir(parents=True)
    (item / "meta.json").write_text(json.dumps({"id": "UI-001", "name": "Gold Counter", "category": "ui",
                                                "tags": ["counter"], "summary": "s"}), encoding="utf-8")
    (kk / "library" / "CATALOG.tsv").write_text("id\ttype\tname\tlocal_name\tsummary\tfolder\n"
                                                "UI-001\titem\tGold Counter\t\ts\tlibrary/items/ui/UI-001_gold\n",
                                                encoding="utf-8")
    assert "UI-001" in run("keremkit.py", "search", "gold", env=env).stdout
    assert "TOTAL\t1" in run("keremkit.py", "summary", env=env).stdout
    (kk / "library" / "CATALOG.tsv").write_text("id\ttype\n", encoding="utf-8")
    assert "reindexed=1" in run("keremkit.py", "reindex", env=env).stdout
    assert "UI-001" in run("keremkit.py", "search", "counter", env=env).stdout


# ---------------------------------------------------------------- 2.6 review times
def test_review_with_cutlist_keeps_sentence_span(tmp_path):
    words = [{"word": f" w{i}", "start": i * 1.0, "end": i * 1.0 + 0.8} for i in range(10)]
    words[-1]["word"] = " end."
    p = tmp_path / "long.json"
    p.write_text(json.dumps({"segments": [{"words": words}]}), encoding="utf-8")
    c = tmp_path / "c.json"
    run("cutlist.py", "build", "--words", p, "--media", tmp_path / "x.mp4", "--duration", 11, "--fps", 30,
        "--silence", "off", "--preset", "relaxed", "-o", c)
    out = run("transcript.py", "review", p, "--cutlist", c, "--pause", 5, "--from", 6).stdout
    assert "w0" in out                         # the sentence that reaches past 6 s is still shown
    first = out.splitlines()[0].split(" | ")[0]
    assert first.startswith("00:00")           # chapter time = sentence start


# ---------------------------------------------------------------- 2.7 unpack safety
def test_unpack_rejects_manifest_paths_outside_home(home, tmp_path):
    kk, env = home
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("manifest.json", json.dumps({"rows": [{"id": "UI-001", "type": "item", "category": "ui",
                                                          "folder": str(tmp_path / "outside"), "name": "x"}]}))
        z.writestr("library/items/ui/UI-001_x/meta.json", "{}")
    r = run("keremkit.py", "unpack", evil, env=env, check=False)
    assert r.returncode != 0 and "rejected" in r.stderr
    assert not (tmp_path / "outside").exists()
    for folder in ("../x", "library/../../x", "C:/x"):
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("manifest.json", json.dumps({"rows": [{"id": "UI-001", "type": "item", "folder": folder}]}))
        assert run("keremkit.py", "unpack", evil, env=env, check=False).returncode != 0


# ---------------------------------------------------------------- 2.8 segment-only whisper
def test_subtitles_from_segments_without_word_times(tmp_path):
    p = tmp_path / "seg.json"
    p.write_text(json.dumps({"segments": [{"start": 0, "end": 2, "text": "Hello there my friend"}]}), encoding="utf-8")
    r = run("subtitles.py", "build", "--words", p, "-o", tmp_path / "s")
    assert "WARN" in r.stderr
    cues = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))["cues"]
    assert cues and cues[0]["s"] == 0 and "Hello" in cues[0]["t"]
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"segments": []}), encoding="utf-8")
    r = run("subtitles.py", "build", "--words", empty, "-o", tmp_path / "e", check=False)
    assert r.returncode != 0 and "no words" in r.stderr


# ---------------------------------------------------------------- 2.9 m4a / 2.10 digest
def test_audio_only_render_to_m4a(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg not installed")
    w = two_words(tmp_path)
    wav = tmp_path / "v.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=300:d=2", str(wav)], check=True)
    c = tmp_path / "c.json"
    run("cutlist.py", "build", "--words", w, "--media", wav, "--silence", "off", "-o", c)
    out = tmp_path / "v.m4a"
    run("cutlist.py", "render", c, "-o", out, "--run")
    assert out.exists() and out.stat().st_size > 0


def test_digest_missing_fields(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"items": [{"name": "B", "layers": [{"name": "x"}]}]}), encoding="utf-8")
    out = run("digest.py", p, "--comp", "B").stdout
    assert "None" not in out and "size ?" in out


# ---------------------------------------------------------------- silence threshold
def test_speech_relative_silence_threshold(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg not installed")
    media = tmp_path / "talk.wav"
    # quiet speaker (-30 dBFS-ish) over room noise: a fixed -40 dB threshold would miss the pauses
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "aevalsrc='0.04*sin(2*PI*220*t)*(between(t,0.5,1.5)+between(t,3,4))+0.006*(random(0)-0.5)':s=48000:d=5",
                    str(media)], check=True)
    w = tmp_path / "w.json"
    w.write_text(json.dumps({"segments": [{"words": [{"word": " a", "start": 0.5, "end": 2.2},
                                                     {"word": " b", "start": 3.0, "end": 4.6}]}]}), encoding="utf-8")
    c = tmp_path / "c.json"
    out = run("cutlist.py", "build", "--words", w, "--media", media, "--preset", "tight", "-o", c).stdout
    assert "audio+words" in out
    assert json.loads(c.read_text(encoding="utf-8"))["out_duration"] < 2.6   # 2 s of speech + pads, word tails trimmed


# ---------------------------------------------------------------- word indices
def test_words_listing_and_index_fix(tmp_path):
    w = two_words(tmp_path)
    out = run("transcript.py", "words", w).stdout
    assert "0:Hello 1:there." in out
    corr = tmp_path / "c.json"
    corr.write_text(json.dumps([{"index": 0, "new": "Claude"}]), encoding="utf-8")
    fixed = tmp_path / "f.json"
    assert "#0 Hello - Claude" in run("transcript.py", "fix", w, "--corrections", corr, "-o", fixed).stdout
    ws = json.loads(fixed.read_text(encoding="utf-8"))["segments"][0]["words"]
    assert ws[0]["word"].strip() == "Claude" and ws[0]["start"] == 0.1 and ws[1]["word"].strip() == "there."


# ---------------------------------------------------------------- edit plan
def test_editplan_times_and_rules(tmp_path):
    words = [{"word": f" w{i}" + ("." if i % 5 == 4 else ""), "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(30)]
    (tmp_path / "w.json").write_text(json.dumps({"segments": [{"words": words}]}), encoding="utf-8")
    (tmp_path / "clip.mp4").write_bytes(b"x")
    plan = {"words": "w.json", "fps": 30, "keys": [1, 2],
            "shots": [{"at": 0, "kind": "host"}, {"at": 4, "kind": "clip", "file": "clip.mp4", "in": 0},
                      {"at": 8, "kind": "clip", "file": "clip.mp4", "in": 1.0},
                      {"at": 12, "kind": "host"}, {"at": 20, "kind": "host"}]}
    p = tmp_path / "edit.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    times = tmp_path / "t.json"
    out = run("editplan.py", "check", p, "-o", times).stdout
    rows = json.loads(times.read_text(encoding="utf-8"))["shots"]
    assert rows[1]["start"] == pytest.approx(2.0 - 1 / 30, abs=0.001)       # one frame before word 4
    assert all(abs(r["start"] * 30 - round(r["start"] * 30)) < 1e-2 for r in rows)
    assert "repeats seconds" in out                                       # clip 0-2 s then 1-3 s
    assert "both 'host'" in out and "keys (max 1)" in out
    assert out.strip().splitlines()[-1].startswith("OK")

    plan["shots"][0]["at"] = 1
    plan["shots"][2]["file"] = "missing.mp4"
    p.write_text(json.dumps(plan), encoding="utf-8")
    r = run("editplan.py", "check", p, check=False)
    assert r.returncode != 0 and "ERROR first shot" in r.stdout and "file not found" in r.stdout


# ---------------------------------------------------------------- sfx / videoref
def test_sfx_synthesis(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg not installed")
    out = run("sfx.py", "make", "whoosh", "pop", "-o", tmp_path, "--variants", 2).stdout
    assert "made=4" in out
    for f in ("whoosh_1.wav", "whoosh_2.wav", "pop_1.wav", "pop_2.wav"):
        assert (tmp_path / f).stat().st_size > 1000
    assert run("sfx.py", "make", "nope", "-o", tmp_path, check=False).returncode != 0


def test_videoref_package(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg not installed")
    v = tmp_path / "ref.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=red:s=180x320:r=30:d=1",
                    "-f", "lavfi", "-t", "1.5", "-i", "mandelbrot=s=180x320:r=30",
                    "-f", "lavfi", "-i", "color=c=blue:s=180x320:r=30:d=1",
                    "-f", "lavfi", "-i", "sine=f=440:d=3.5",
                    "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1[v]", "-map", "[v]", "-map", "3:a",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(v)],
                   check=True)
    out = run("videoref.py", v, "-o", tmp_path / "pkg", "--thumb", 90, "--move", 1.0).stdout
    assert "shots=3" in out
    data = json.loads((tmp_path / "pkg" / "data.json").read_text(encoding="utf-8"))
    assert data["cuts"] == pytest.approx([1.0, 2.5], abs=0.04)
    assert data["shots"][0]["palette"][0]["hex"].startswith("#F") or data["shots"][0]["palette"][0]["hex"].startswith("#E")
    assert data["shots"][1]["motion"]                                  # the mandelbrot zoom moves
    assert (tmp_path / "pkg" / "sheets" / "00_overview.jpg").exists()
    assert "## Shots (3" in (tmp_path / "pkg" / "README.md").read_text(encoding="utf-8")
