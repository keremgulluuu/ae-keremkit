import json

from conftest import run

PAGE = """<!doctype html><html><head><style>
:root{--bg:#0A0C0F;--ink:#EAEEF3;--accent:#C6FF3C;--line:rgba(234,238,243,.13);--ease:cubic-bezier(.22,.9,.28,1)}
@font-face{font-family:Inter;src:url(data:font/woff;base64,AAAA) format('woff')}
.poster{background:var(--bg);border:1px solid var(--line);border-radius:24px;background-size:64px 64px}
.poster h1{font-family:Inter,Arial,sans-serif;font-size:clamp(53px,6.6vw,88px);font-weight:400;letter-spacing:-.063em;line-height:1.055;color:var(--ink)}
.poster h1 strong{font-weight:900;color:var(--accent)}
.hero::before{background:radial-gradient(ellipse 460px 240px at 94% 0%,rgba(198,255,60,.19),transparent 76%)}
.reveal{transition:opacity .72s var(--ease)}
.unrelated{color:#123456;font-family:Comic Sans MS;border-radius:3px}
</style></head><body><div class="poster"></div></body></html>"""


def extract(tmp_path, *scopes):
    src = tmp_path / "page.html"
    src.write_text(PAGE, encoding="utf-8")
    out = tmp_path / "tokens.json"
    args = [src, "-o", out]
    for s in scopes:
        args += ["--scope", s]
    printed = run("tokens.py", *args).stdout
    return json.loads(out.read_text(encoding="utf-8")), printed


def test_palette_type_and_ae_values(tmp_path):
    t, printed = extract(tmp_path)
    assert t["palette"]["accent"]["hex"] == "#C6FF3C"
    assert t["palette"]["accent"]["ae"] == [0.7765, 1.0, 0.2353]
    assert t["palette"]["line"]["alpha"] == 0.13
    assert "Inter" in t["type"]["fonts"]
    assert 88 in t["type"]["sizes_px"]                          # clamp() -> largest px
    assert any(x["value"] == -63 for x in t["type"]["tracking_ae"])
    assert 24 in t["shape"]["radius_px"]
    assert t["motion"]["easing"][0]["feel"].startswith("ease-out")
    assert 0.72 in t["motion"]["durations_s"]
    assert len(printed.splitlines()) <= 7                       # stays cheap to read


def test_glows_are_parsed(tmp_path):
    t, _ = extract(tmp_path)
    glow = t["effects"]["glows"][0]
    assert glow["color"] == "#C6FF3C" and glow["name"] == "accent"
    assert glow["opacity"] == 0.19 and glow["at_percent"] == [94, 0]


def test_scope_ignores_other_parts(tmp_path):
    t, _ = extract(tmp_path, ".poster")
    assert "Comic Sans MS" not in t["type"]["fonts"]
    assert 3 not in t["shape"]["radius_px"]
    full, _ = extract(tmp_path)
    assert "Comic Sans MS" in full["type"]["fonts"]


def test_lottie_source(tmp_path):
    lottie = {"fr": 30, "ip": 0, "op": 90, "w": 1080, "h": 1920, "fonts": {"list": [{"fFamily": "Inter"}]},
              "layers": [{"shapes": [{"ty": "fl", "c": {"k": [0.776, 1, 0.235, 1]}}],
                          "ks": {"p": {"k": [{"o": {"x": [0.22], "y": [0.9]}, "i": {"x": [0.28], "y": [1]}}]}}}]}
    src = tmp_path / "anim.json"
    src.write_text(json.dumps(lottie), encoding="utf-8")
    out = tmp_path / "t.json"
    run("tokens.py", src, "-o", out)
    t = json.loads(out.read_text(encoding="utf-8"))
    assert t["lottie"] == {"size": [1080, 1920], "fps": 30, "duration_s": 3.0, "layers": 1}
    assert t["type"]["fonts"] == ["Inter"]
    assert t["motion"]["easing"][0]["cubic_bezier"] == [0.22, 0.9, 0.28, 1]
