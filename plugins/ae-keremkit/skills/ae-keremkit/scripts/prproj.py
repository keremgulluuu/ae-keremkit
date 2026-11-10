#!/usr/bin/env python3
"""KeremKit Premiere project reader - learn an edit style from a .prproj (read-only, stdlib only).

Commands
  sequences PROJECT.prproj                      one line per sequence: name, size, fps, duration, items
  analyze   PROJECT.prproj --out analysis.json [--seq NAME]
            every track item (time, source, in/out, clip gain, disabled flag, effects with values and
            keyframes, decoded text style) + the nested sequences it uses; prints a short summary.
            Without --seq the sequence with the most clips is used.

ALWAYS run it on a COPY (keremkit.py safe-copy), never on the user's project.

Format notes (verified on Premiere 2026): gzip XML; objects point to each other with ObjectRef /
ObjectURef; time in ticks (254016000000 per second); disabled clip = ClipTrackItem/IsMuted=true;
clip gain AudioClip/Gain (linear); volume Level is linear with +15 dB headroom (0.1778 = 0 dB).
Essential Graphics text ("Source Text") and caption blocks are FlatBuffers without a public schema:
the walker below guesses field types; the field map in decode_text() is best effort.
"""
import argparse
import base64
import gzip
import json
import math
import os
import statistics
import struct
import sys
import xml.etree.ElementTree as ET

TICKS = 254016000000
HEADER = 12   # FlatBuffer blobs: uint64 length + magic 0x11223344


# ---------- schema-less FlatBuffer walker ----------



def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def _i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def _f32(b, o):
    return struct.unpack_from("<f", b, o)[0]


def _string_at(b, o):
    if o + 4 > len(b):
        return None
    n = _u32(b, o)
    if n == 0 or o + 4 + n >= len(b) or n > 100000:
        return None
    if b[o + 4 + n] != 0:
        return None
    raw = b[o + 4:o + 4 + n]
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(ord(c) < 32 and c not in "\r\n\t" for c in s):
        return None
    return s


def _is_table(b, t):
    if t < 0 or t + 4 > len(b):
        return False
    vt = t - _i32(b, t)
    if vt < 0 or vt + 4 > len(b):
        return False
    vsize, tsize = _u16(b, vt), _u16(b, vt + 2)
    if vsize < 4 or vsize % 2 or vsize > 200 or tsize < 4 or tsize > 4000:
        return False
    if vt + vsize > len(b) or t + tsize > len(b):
        return False
    for i in range((vsize - 4) // 2):
        fo = _u16(b, vt + 4 + 2 * i)
        if fo and fo >= tsize:
            return False
    return True


def _scalar(b, o, size):
    if size >= 4:
        f = _f32(b, o)
        i = _u32(b, o)
        if i == 0:
            return 0
        if 1e-4 < abs(f) < 1e6:
            return round(f, 4)
        return i
    if size == 2:
        return _u16(b, o)
    return b[o]


def walk_table(b, t, depth=0, seen=None):
    seen = seen if seen is not None else set()
    if depth > 12 or t in seen:
        return "<loop>"
    seen.add(t)
    vt = t - _i32(b, t)
    vsize, tsize = _u16(b, vt), _u16(b, vt + 2)
    offs = []
    for i in range((vsize - 4) // 2):
        fo = _u16(b, vt + 4 + 2 * i)
        if fo:
            offs.append((fo, i))
    offs.sort()
    out = {}
    for k, (fo, idx) in enumerate(offs):
        nxt = offs[k + 1][0] if k + 1 < len(offs) else tsize
        size = nxt - fo
        o = t + fo
        val = None
        if size >= 4:
            target = o + _u32(b, o)
            s = _string_at(b, target)
            if s is not None and (len(s) > 1 or not _is_table(b, target)):
                val = s
            elif target < len(b) and _u32(b, o) != 0 and _is_table(b, target):
                val = walk_table(b, target, depth + 1, seen)
            elif target + 4 <= len(b) and _u32(b, o) != 0:
                n = _u32(b, target)
                if 0 < n < 2000 and target + 4 + 4 * n <= len(b):
                    items = []
                    ok = True
                    for j in range(n):
                        eo = target + 4 + 4 * j
                        et = eo + _u32(b, eo)
                        s2 = _string_at(b, et)
                        if s2 is not None:
                            items.append(s2)
                        elif _is_table(b, et):
                            items.append(walk_table(b, et, depth + 1, seen))
                        else:
                            ok = False
                            break
                    if ok:
                        val = items
                    elif n < 64:
                        # vector of scalars (floats/ints)
                        val = [_scalar(b, target + 4 + 4 * j, 4) for j in range(n)]
        if val is None:
            if size >= 8 and size % 4 == 0 and size <= 32:
                # inline struct (e.g. a colour): keep each 4-byte word
                val = [_scalar(b, o + 4 * j, 4) for j in range(size // 4)]
                if len(val) == 1:
                    val = val[0]
            else:
                val = _scalar(b, o, min(size, 8))
        out[str(idx)] = val
    return out


def fb_decode(raw):
    """raw: bytes of the decoded base64 blob (with Premiere's 12-byte header)."""
    b = raw[HEADER:]
    if len(b) < 8:
        return {}
    root = _u32(b, 0)
    if not _is_table(b, root):
        return {}
    return walk_table(b, root)


def fb_flatten(tree, prefix=""):
    """Yield (path, value) for every leaf."""
    if isinstance(tree, dict):
        for k, v in tree.items():
            yield from flatten(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(tree, list) and tree and isinstance(tree[0], (dict, list)):
        for i, v in enumerate(tree):
            yield from flatten(v, f"{prefix}[{i}]")
    else:
        yield prefix, tree



def sec(t):
    return round(int(t) / TICKS, 3)


class Project:
    def __init__(self, path):
        data = open(path, "rb").read()
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        self.root = ET.fromstring(data)
        self.by = {}
        for e in self.root:
            k = e.get("ObjectID") or e.get("ObjectUID")
            if k:
                self.by[k] = e

    def ref(self, el):
        if el is None:
            return None
        k = el.get("ObjectRef") or el.get("ObjectURef")
        return self.by.get(k) if k else None

    def sequences(self):
        return self.root.findall("Sequence")

    def seq_by_uid(self, uid):
        e = self.by.get(uid)
        return e if e is not None and e.tag == "Sequence" else None


# ---------- generic helpers ----------

def first_value(start_kf):
    """'-9144..,100.,0,0,...' -> '100.'"""
    if not start_kf:
        return None
    parts = start_kf.split(",")
    return parts[1] if len(parts) > 1 else None


def num(v):
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return v


def keyframes(text, ticks_per_s=TICKS):
    out = []
    for k in (text or "").split(";"):
        p = k.split(",")
        if len(p) >= 2 and p[0].lstrip("-").isdigit():
            out.append([round(int(p[0]) / ticks_per_s, 3), num(p[1]) if ":" not in p[1] else p[1]])
    return out


def param_info(proj, pel):
    p = proj.ref(pel)
    if p is None:
        return None
    name = p.findtext("Name")
    info = {"name": name}
    sk = p.findtext("StartKeyframe")
    if sk:
        info["value"] = num(first_value(sk)) if ":" not in (first_value(sk) or "") else first_value(sk)
    cv = p.findtext("CurrentValue")
    if cv is not None and "value" not in info:
        info["value"] = num(cv)
    kf = p.findtext("Keyframes")
    if kf:
        info["keyframes"] = keyframes(kf)
    if p.tag == "ArbVideoComponentParam":
        v = p.find("StartKeyframeValue")
        if v is not None and v.text:
            info["blob"] = v.text
    return info


def component_list(proj, chain_ref):
    chain = proj.ref(chain_ref)
    out = []
    if chain is None:
        return out
    comps = chain.find("ComponentChain/Components")
    if comps is None:
        return out
    for c in comps:
        comp = proj.ref(c)
        if comp is None:
            continue
        if comp.tag == "VideoFilterComponent":
            core = comp.find("Component")
            entry = {"match": comp.findtext("MatchName"), "name": core.findtext("DisplayName") if core is not None else None}
        elif comp.tag == "AudioFilterComponent":
            core = comp.find("AudioComponent/Component")
            entry = {"match": comp.findtext("FilterMatchName"), "name": comp.findtext("AudioComponent/Component/DisplayName")}
        else:
            core = comp.find("Component")
            entry = {"match": comp.tag, "name": None}
        params = []
        if core is not None and core.find("Params") is not None:
            for pel in core.find("Params"):
                pi = param_info(proj, pel)
                if pi:
                    params.append(pi)
        entry["params"] = params
        out.append(entry)
    return out


# ---------- text decoding ----------

def _rgb(tbl, default=255):
    """Colour tables store channels as bytes; channels equal to the schema
    default are omitted. Default appears to be 255 for fills, 0 elsewhere."""
    if not isinstance(tbl, dict):
        return None
    return [tbl.get(str(i), default) if isinstance(tbl.get(str(i), default), int) else default for i in range(3)]


def decode_text(blob_b64):
    try:
        tree = fb_decode(base64.b64decode(blob_b64))
    except Exception:
        return None
    t = tree.get("0", {})
    if not isinstance(t, dict):
        return None
    runs = []
    for run in t.get("0", []) if isinstance(t.get("0"), list) else []:
        if not isinstance(run, dict):
            continue
        st = run.get("1", {}) if isinstance(run.get("1"), dict) else {}
        runs.append({
            "text": run.get("0"),
            "size": st.get("1"),
            "fill_rgb": _rgb(st.get("2"), 255) if "2" in st else [255, 255, 255],
            "stroke_rgb": _rgb(st.get("4"), 0) if "4" in st else None,
            "stroke_on": st.get("5") == 1,
            "stroke_width": st.get("6"),
            "gradient": "21" in st,
        })
    shadow = None
    sh = t.get("37")
    if isinstance(sh, list) and sh and isinstance(sh[0], dict):
        s = sh[0]
        shadow = {"rgb": _rgb(s.get("0"), 0), "opacity": s.get("2"), "distance_or_blur": s.get("5"), "angle_or_size": s.get("6")}
    fonts = t.get("1") if isinstance(t.get("1"), list) else []
    return {
        "fonts": fonts,
        "box": [t.get("2"), t.get("3")],
        "align_code": t.get("4"),
        "runs": runs,
        "shadow": shadow,
        "has_background": "40" in t,
        "anim": "33" in t and isinstance(t.get("33"), dict) and isinstance(t["33"].get("0"), list),
    }


# ---------- sequence walk ----------

def source_of(proj, subclip):
    """Return (kind, name, path_or_seq)."""
    if subclip is None:
        return ("unknown", None, None)
    name = subclip.findtext("Name")
    clip = proj.ref(subclip.find("Clip"))
    if clip is None:
        return ("unknown", name, None)
    src = proj.ref(clip.find("Clip/Source"))
    if src is None:
        return ("unknown", name, None)
    if src.tag in ("VideoSequenceSource", "AudioSequenceSource"):
        sq = proj.ref(src.find("SequenceSource/Sequence"))
        return ("nested", name, sq.findtext("Name") if sq is not None else None)
    media = proj.ref(src.find("MediaSource/Media"))
    path = None
    if media is not None:
        path = media.findtext("ActualMediaFilePath") or media.findtext("FilePath")
    kind = "media" if path else "generated"
    return (kind, name, path)


def clip_inout(proj, subclip):
    clip = proj.ref(subclip.find("Clip")) if subclip is not None else None
    if clip is None:
        return None, None
    i, o = clip.findtext("Clip/InPoint"), clip.findtext("Clip/OutPoint")
    return (sec(i) if i else None, sec(o) if o else None)


def track_items(proj, track_el):
    ct = track_el.find("ClipTrack")
    out, trans = [], []
    if ct is None:
        return out, trans
    for ti in ct.findall("ClipItems/TrackItems/TrackItem"):
        it = proj.ref(ti)
        if it is None:
            continue
        cti = it.find("ClipTrackItem")
        tri = cti.find("TrackItem")
        start = int(tri.findtext("Start") or 0)
        end = int(tri.findtext("End") or 0)
        sub = proj.ref(cti.find("SubClip"))
        kind, name, src = source_of(proj, sub)
        i, o = clip_inout(proj, sub)
        comps = component_list(proj, cti.find("ComponentOwner/Components"))
        speed = cti.findtext("PlaybackSpeed")
        clip = proj.ref(sub.find("Clip")) if sub is not None else None
        gain = clip.findtext("Gain") if clip is not None else None
        out.append({
            "start": sec(start), "end": sec(end), "dur": sec(end - start),
            "name": name, "kind": kind, "src": src, "in": i, "out": o,
            "speed": num(speed) if speed else None,
            "reversed": cti.findtext("Reversed") == "true",
            "clip_gain_db": round(20 * math.log10(float(gain)), 1) if gain and float(gain) > 0 else None,
            "effects": comps,
            # Premiere writes a disabled clip (Enable unticked) as ClipTrackItem/IsMuted=true
            "disabled": cti.findtext("IsMuted") == "true",
        })
    for ti in ct.findall("TransitionItems/TrackItems/TrackItem"):
        it = proj.ref(ti)
        if it is None:
            continue
        tt = it.find("TransitionTrackItem")
        tri = tt.find("TrackItem")
        start = int(tri.findtext("Start") or 0)
        end = int(tri.findtext("End") or 0)
        trans.append({"start": sec(start), "end": sec(end), "dur": sec(end - start),
                      "name": tt.findtext("DisplayName"), "match": tt.findtext("MatchName")})
    return out, trans


def sequence_info(proj, s, deep=True):
    info = {"name": s.findtext("Name"), "uid": s.get("ObjectUID"), "video": [], "audio": []}
    for t in s.find("TrackGroups"):
        g = proj.ref(t.find("Second"))
        if g is None:
            continue
        tg = g.find("TrackGroup")
        if g.tag == "VideoTrackGroup":
            fr = int(tg.findtext("FrameRate") or 0)
            info["fps"] = round(TICKS / fr, 3) if fr else None
            rect = (g.findtext("FrameRect") or "").split(",")
            if len(rect) == 4:
                info["size"] = [int(rect[2]), int(rect[3])]
        kind = {"VideoTrackGroup": "video", "AudioTrackGroup": "audio"}.get(g.tag)
        if kind is None or tg.find("Tracks") is None:
            continue
        for idx, tr in enumerate(tg.find("Tracks")):
            T = proj.ref(tr)
            if T is None:
                continue
            items, trans = track_items(proj, T) if deep else ([], [])
            track = {"index": idx + 1, "items": items, "transitions": trans}
            if kind == "audio":
                track["mute"] = T.findtext("AudioTrack/Muted") == "true"
                track["track_fx"] = component_list(proj, T.find("AudioTrack/ComponentOwner/Components"))
            info[kind].append(track)
    ends = [it["end"] for k in ("video", "audio") for tr in info[k] for it in tr["items"]]
    info["duration"] = max(ends) if ends else 0
    return info


# ---------- summaries ----------

def db(lin):
    try:
        lin = float(lin)
    except (TypeError, ValueError):
        return None
    if lin <= 0:
        return -144.0
    # Premiere stores clip Level as linear gain with 0 dB = 1.0 / 0.1778? use 20log10 and offset
    return round(20 * math.log10(lin) + 15.0, 1)


def pct(lst, q):
    if not lst:
        return None
    s = sorted(lst)
    k = (len(s) - 1) * q
    f = math.floor(k)
    c = min(f + 1, len(s) - 1)
    return round(s[f] + (s[c] - s[f]) * (k - f), 3)


def stats(durs):
    if not durs:
        return None
    return {"n": len(durs), "mean": round(statistics.mean(durs), 3), "median": round(statistics.median(durs), 3),
            "p10": pct(durs, 0.1), "p90": pct(durs, 0.9), "min": round(min(durs), 3), "max": round(max(durs), 3)}


def summarize(info):
    summ = {"sequence": {k: info.get(k) for k in ("name", "size", "fps", "duration")}}
    vt = []
    for tr in info["video"]:
        kinds = {}
        for it in tr["items"]:
            k = "text" if any(e["match"] == "AE.ADBE Text" for e in it["effects"]) else it["kind"]
            kinds[k] = kinds.get(k, 0) + 1
        vt.append({"track": f"V{tr['index']}", "n": len(tr["items"]), "kinds": kinds,
                   "names": sorted({it["name"] for it in tr["items"] if it["name"]})[:12],
                   "durations": stats([it["dur"] for it in tr["items"]]),
                   "transitions": [t["name"] for t in tr["transitions"]]})
    summ["video_tracks"] = vt
    at = []
    for tr in info["audio"]:
        lv = []
        for it in tr["items"]:
            for e in it["effects"]:
                for p in e["params"]:
                    if p["name"] == "Level" and isinstance(p.get("value"), float):
                        lv.append(p["value"])
        tfx = []
        for e in tr.get("track_fx", []):
            for p in e["params"]:
                if p.get("name") in ("Volume", "Level", "Mute") or "keyframes" in p:
                    tfx.append({"fx": e["match"], "param": p.get("name"), "value": p.get("value"),
                                "db": db(p.get("value")) if p.get("name") in ("Volume", "Level") else None,
                                "keyframes": len(p.get("keyframes", []))})
        at.append({"track": f"A{tr['index']}", "n": len(tr["items"]), "mute": tr.get("mute"),
                   "names": sorted({it["name"] for it in tr["items"] if it["name"]})[:20],
                   "clip_level_db": sorted({db(v) for v in lv}),
                   "track_params": tfx})
    summ["audio_tracks"] = at
    return summ


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("project")
    a.add_argument("--out", required=True)
    a.add_argument("--seq")
    s = sub.add_parser("sequences")
    s.add_argument("project")
    args = ap.parse_args()
    proj = Project(args.project)
    if args.cmd == "sequences":
        for sq in proj.sequences():
            i = sequence_info(proj, sq)
            n = sum(len(t["items"]) for k in ("video", "audio") for t in i[k])
            print(f"{i['name']}\t{i.get('size')}\t{i.get('fps')}\t{i['duration']}s\t{n} items")
        return
    seqs = proj.sequences()
    if args.seq:
        found = [x for x in seqs if x.findtext("Name") == args.seq]
        if not found:
            sys.exit(f"ERROR: no sequence named {args.seq!r} (see: prproj.py sequences)")
        target = found[0]
    elif not seqs:
        sys.exit("ERROR: the project has no sequences")
    else:
        target = max(seqs, key=lambda x: sum(len(t["items"]) for k in ("video", "audio") for t in sequence_info(proj, x)[k]))
    info = sequence_info(proj, target)
    # decode text blobs in place
    for tr in info["video"]:
        for it in tr["items"]:
            for e in it["effects"]:
                for p in e["params"]:
                    if "blob" in p:
                        if p["name"] == "Source Text":
                            p["text"] = decode_text(p["blob"])
                        del p["blob"]
    # nested sequences used
    nested = sorted({it["src"] for k in ("video", "audio") for tr in info[k] for it in tr["items"] if it["kind"] == "nested" and it["src"]})
    info["nested_sequences"] = {}
    for n in nested:
        sq = [x for x in seqs if x.findtext("Name") == n]
        if sq:
            ni = sequence_info(proj, sq[0])
            for tr in ni["video"]:
                for it in tr["items"]:
                    for e in it["effects"]:
                        for p in e["params"]:
                            if "blob" in p:
                                if p["name"] == "Source Text":
                                    p["text"] = decode_text(p["blob"])
                                del p["blob"]
            info["nested_sequences"][n] = ni
    info["summary"] = summarize(info)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    print(json.dumps(info["summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
