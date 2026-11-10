import json

from conftest import run


def cues(path):
    return json.loads(path.read_text(encoding="utf-8"))["cues"]


def build(tmp_path, words, *sets, name="subs"):
    out = tmp_path / name
    args = ["build", "--words", words, "-o", out]
    if sets:
        args += ["--set", *sets]
    run("subtitles.py", *args)
    return tmp_path / f"{name}.json"


def words_in(cue):
    return cue["t"].replace("\r", " ").split()


def test_defaults_respect_limits(tmp_path, words_file):
    words, _ = words_file
    data = cues(build(tmp_path, words))
    assert data
    for c in data:
        lines = c["t"].split("\r")
        assert len(lines) <= 2
        assert all(len(line.split()) <= 4 for line in lines)
        assert c["e"] > c["s"]
    assert (tmp_path / "subs.srt").read_text(encoding="utf-8").startswith("1\n00:00:")


def test_sentence_mode_never_crosses_sentences(tmp_path, words_file):
    words, _ = words_file
    data = cues(build(tmp_path, words, 'split_mode="sentence"'))
    for c in data:
        ws = words_in(c)
        for w in ws[:-1]:
            assert not w.endswith((".", "?", "!")), c["t"]


def test_one_line_and_word_limits(tmp_path, words_file):
    words, _ = words_file
    data = cues(build(tmp_path, words, "max_lines=1", "max_words_per_line=3"))
    assert all("\r" not in c["t"] and len(c["t"].split()) <= 3 for c in data)


def test_numbers_are_highlighted_and_kept_with_next_word(tmp_path, words_file):
    words, _ = words_file
    data = cues(build(tmp_path, words))
    hit = [c for c in data if "25,000" in c["t"]]
    assert hit and hit[0]["h"], "number should be highlighted"
    for c in data:
        for line in c["t"].split("\r")[:-1]:
            assert not line.split()[-1][0].isdigit(), f"line ends on a number: {c['t']!r}"


def test_keyword_highlight_and_manual_override(tmp_path, words_file):
    words, _ = words_file
    path = build(tmp_path, words, 'highlight.keywords=["important"]')
    target = next(i for i, c in enumerate(cues(path)) if "important" in c["t"])
    assert cues(path)[target]["h"]
    run("subtitles.py", "highlight", path, "--cue", target, "--clear")
    assert cues(path)[target]["h"] == []


def test_language_detected_from_whisper(tmp_path, words_file):
    words, _ = words_file
    path = build(tmp_path, words, 'case="upper"')
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["rules"]["language"] == "en"
    assert all(c["t"] == c["t"].upper() for c in data["cues"])


def test_turkish_casing(tmp_path):
    w = [{"word": " istanbul", "start": 0.1, "end": 0.5}, {"word": " ılık", "start": 0.6, "end": 0.9}]
    p = tmp_path / "tr.json"
    p.write_text(json.dumps({"language": "tr", "segments": [{"words": w}]}), encoding="utf-8")
    data = cues(build(tmp_path, p, 'case="upper"', name="tr"))
    assert data[0]["t"] == "İSTANBUL ILIK"


def test_plan_maps_zones_and_rejects_overlap(tmp_path, words_file):
    words, _ = words_file
    plan = {"placements": [
        {"words": words.name, "from": 0, "to": 5, "at": 0, "zone": "camera"},
        {"words": words.name, "from": 5, "to": None, "at": 8, "zone": "voice"}]}
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    run("subtitles.py", "build", "--plan", tmp_path / "plan.json", "-o", tmp_path / "p")
    data = json.loads((tmp_path / "p.json").read_text(encoding="utf-8"))
    assert {c["z"] for c in data["cues"]} == {"camera", "voice"}
    assert not any(5 <= c["s"] < 8 for c in data["cues"])      # gap between placements stays empty

    plan["placements"][1]["at"] = 3
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    res = run("subtitles.py", "build", "--plan", tmp_path / "plan.json", "-o", tmp_path / "p", check=False)
    assert res.returncode != 0 and "overlap" in res.stderr


def test_ae_expressions_reference_footage(tmp_path, words_file):
    words, _ = words_file
    path = build(tmp_path, words)
    pos = tmp_path / "pos.json"
    pos.write_text('{"main": [960, 900]}', encoding="utf-8")
    out = run("subtitles.py", "ae-expr", path, "--footage", "subs.json", "--positions", pos).stdout
    assert out.count('footage("subs.json")') == 3
    assert "textIndex" in out
