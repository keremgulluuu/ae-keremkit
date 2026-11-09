import json
import subprocess

import pytest

from conftest import run


def whisper(tmp_path, spec, name="w.json", language="tr"):
    """spec: list of (word, start, end[, probability])."""
    words = [{"word": " " + w[0], "start": w[1], "end": w[2], **({"probability": w[3]} if len(w) > 3 else {})}
             for w in spec]
    p = tmp_path / name
    p.write_text(json.dumps({"language": language, "segments": [{"words": words}]}, ensure_ascii=False), encoding="utf-8")
    return p


TALK = [
    # false start, then the full sentence
    ("Bugün", 0.50, 0.80), ("size", 0.85, 1.05), ("Kılavd", 1.10, 1.60, 0.31),
    ("Bugün", 2.60, 2.90), ("size", 2.95, 3.15), ("Kılavd'u", 3.20, 3.70, 0.35), ("anlatacağım.", 3.75, 4.40),
    # repeated phrase in the flow
    ("Bu", 5.00, 5.15), ("araç", 5.20, 5.50), ("bu", 5.60, 5.75), ("araç", 5.80, 6.10), ("çok", 6.15, 6.35),
    ("güçlü.", 6.40, 6.80),
    # filler and an intended double
    ("ııı", 7.20, 7.60), ("Yavaş", 8.00, 8.30), ("yavaş", 8.35, 8.65), ("öğreneceğiz.", 8.70, 9.40),
    # mis-heard product name, two words
    ("After", 10.0, 10.3), ("a", 10.32, 10.4, 0.4), ("fax", 10.42, 10.8, 0.38), ("kullanıyoruz.", 10.9, 11.6),
]


def test_review_marks_doubtful_words(tmp_path):
    w = whisper(tmp_path, TALK)
    out = run("transcript.py", "review", w).stdout
    assert "Kılavd(?0.31)" in out
    assert out.splitlines()[0].startswith("00:00.5 |")
    assert "doubtful=4" in out and "language=tr" in out


def test_fix_replaces_by_time_and_keeps_timing(tmp_path):
    w = whisper(tmp_path, TALK)
    corr = tmp_path / "c.json"
    corr.write_text(json.dumps([
        {"time": 1.1, "old": "Kılavd", "new": "Claude"},
        {"time": 3.2, "old": "Kılavd'u", "new": "Claude'u"},
        {"time": 10.3, "old": "a fax", "new": "Effects"},
        {"time": 50, "old": "yok", "new": "x"}]), encoding="utf-8")
    out_p = tmp_path / "fixed.json"
    out = run("transcript.py", "fix", w, "--corrections", corr, "-o", out_p).stdout
    assert "00:01.1 - Kılavd - Claude" in out
    assert "00:10.3 - a fax - Effects" in out
    assert "NOT_FOUND" in out and "applied=3" in out
    words = json.loads(out_p.read_text(encoding="utf-8"))["segments"][0]["words"]
    texts = [x["word"].strip() for x in words]
    assert "Claude" in texts and "Kılavd" not in texts
    eff = next(x for x in words if x["word"].strip() == "Effects")
    assert eff["start"] == 10.32 and eff["end"] == 10.8 and eff["corrected_from"] == "a fax"
    assert "After" in texts                                    # untouched neighbour


def test_repeats_finds_retakes_repeats_fillers(tmp_path):
    w = whisper(tmp_path, TALK)
    rep = tmp_path / "rep.json"
    out = run("transcript.py", "repeats", w, "-o", rep).stdout
    data = json.loads(rep.read_text(encoding="utf-8"))["removals"]
    kinds = {(r["kind"], r["removed"]): r for r in data}
    retake = kinds[("retake", "Bugün size Kılavd")]
    assert retake["apply"] and retake["src_in"] == 0.5 and retake["src_out"] == 2.6
    rep_phrase = kinds[("repeat", "Bu araç")]
    assert rep_phrase["apply"] and rep_phrase["src_out"] == 5.6
    assert kinds[("filler", "ııı")]["apply"]
    double = kinds[("stutter", "Yavaş")]
    assert not double["apply"] and double["confidence"] == "low"   # intended reduplication is asked, not cut
    assert "ASK" in out and "AUTO" in out

    run("transcript.py", "accept", rep, "--ids", str(double["id"]))
    assert json.loads(rep.read_text(encoding="utf-8"))["removals"][double["id"] - 1]["apply"]


def test_cut_uses_audio_silence_and_removals(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg not installed")
    # tone where speech is, real silence between; Whisper-like word ends run into the pauses
    speech = [(0.5, 1.6), (2.6, 4.4), (5.0, 6.8), (8.0, 9.4), (10.0, 11.6)]
    expr = "+".join(f"between(t,{a},{b})" for a, b in speech)
    media = tmp_path / "talk.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='0.4*sin(2*PI*220*t)*({expr})':s=48000:d=12.5", str(media)], check=True)
    sloppy = [(w[0], w[1], w[2] + 0.5) for w in TALK]            # word ends 0.5 s too late
    w = whisper(tmp_path, sloppy)
    words_only, audio = tmp_path / "a.json", tmp_path / "b.json"
    run("cutlist.py", "build", "--words", w, "--media", media, "--preset", "tight", "--silence", "off", "-o", words_only)
    out = run("cutlist.py", "build", "--words", w, "--media", media, "--preset", "tight", "-o", audio).stdout
    assert "audio+words" in out
    d_words = json.loads(words_only.read_text(encoding="utf-8"))["out_duration"]
    d_audio = json.loads(audio.read_text(encoding="utf-8"))["out_duration"]
    true_speech = sum(b - a for a, b in speech)
    assert d_audio < d_words
    assert d_audio == pytest.approx(true_speech + 5 * 0.13, abs=0.6)

    rep = tmp_path / "rep.json"
    run("transcript.py", "repeats", w, "-o", rep)
    final = tmp_path / "c.json"
    out = run("cutlist.py", "build", "--words", w, "--media", media, "--preset", "tight", "--remove", rep, "-o", final).stdout
    assert "repeats_removed=" in out
    cl = json.loads(final.read_text(encoding="utf-8"))
    assert cl["out_duration"] < d_audio - 1.5                     # false start + repeat + filler gone
    kept = [(s["src_in"], s["src_out"]) for s in cl["segments"]]
    assert not any(a < 1.0 < b for a, b in kept)                  # the false start is cut
