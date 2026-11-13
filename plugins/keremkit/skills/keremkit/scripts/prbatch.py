#!/usr/bin/env python3
"""KeremKit Premiere batch runner - many Premiere MCP calls in ONE server process, one short line per step.

Why: every Premiere MCP call made from the chat returns 1-2k tokens of JSON. A build of 40-80 calls costs
60-150k tokens. Run the same calls from a plan file here and the chat sees one line per step; the full answers
go to a results file that is read only when something needs a closer look. Preview tokens work across steps
(one server process).

  list   [REGEX]                       tool names (+ first line of the description)
  schema TOOL                          input schema of one tool
  run    PLAN.json [--out RESULTS.json] [--continue-on-error] [--timeout 120] [--from N] [--rerun]

A plan whose results file already shows applied steps is refused (a new process replays nothing - the steps would
run twice); continue with --from N. idempotency keys are cleaned to [A-Za-z0-9._:-].

PLAN.json:
  {"expected_project_path": "C:/.../work copy.prproj",       # added to every step that has no own value
   "steps": [
     {"tool": "get_sequence_structure", "args": {...}, "pick": ["data.tracks"]},
     {"tool": "ripple_remove_timeline_ranges", "args": {..., "dry_run": true}, "save_as": "preview"},
     {"tool": "ripple_remove_timeline_ranges", "args": {...}, "token_from": "preview"},
     {"tool": "add_keyframe", "args": {...}, "pick": ["data.verified"]}]}
  pick      dotted paths printed on the step's line (default: outcome / verified / error)
  save_as   remember this step's result; token_from NAME copies its confirmationToken into this step
Steps run strictly one after another. The run stops at the first error (and always at a recovery lock,
HOST_RECOVERY_REQUIRED) unless --continue-on-error.

Server: preference tools.premiere_mcp.command (a list), else the "premiere-pro" entry in ~/.claude.json,
else `premiere-pro-mcp` on PATH. Standard library only.
"""
import argparse
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

POINTER = os.path.join(os.path.expanduser("~"), ".keremkit.json")


def server_command():
    try:
        home = json.load(open(POINTER, encoding="utf-8")).get("home")
        prefs = json.load(open(os.path.join(home, "settings", "preferences.json"), encoding="utf-8"))
        cmd = ((prefs.get("tools") or {}).get("premiere_mcp") or {}).get("command")
        if cmd:
            return cmd, {}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    try:
        cfg = json.load(open(os.path.join(os.path.expanduser("~"), ".claude.json"), encoding="utf-8"))
        found = []

        def walk(o):
            if isinstance(o, dict):
                ms = o.get("mcpServers")
                if isinstance(ms, dict) and isinstance(ms.get("premiere-pro"), dict):
                    found.append(ms["premiere-pro"])
                for v in o.values():
                    walk(v)
        walk(cfg)
        if found and found[0].get("command"):
            s = found[0]
            return [s["command"]] + list(s.get("args") or []), dict(s.get("env") or {})
    except (OSError, ValueError):
        pass
    exe = shutil.which("premiere-pro-mcp")
    if exe:
        return [exe], {}
    sys.exit("ERROR: Premiere MCP server not found - set: keremkit.py pref set "
             "'tools.premiere_mcp={\"command\": [\"premiere-pro-mcp\"]}'")


class Client:
    def __init__(self, cmd, env, timeout):
        self.timeout = timeout
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  env=dict(os.environ, **env), text=True, encoding="utf-8", errors="replace",
                                  bufsize=1)
        self.q = queue.Queue()
        self.n = 0
        threading.Thread(target=self._read, daemon=True).start()
        self.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "keremkit-prbatch", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _read(self):
        for line in self.p.stdout:
            line = line.strip()
            if line.startswith("{"):
                try:
                    self.q.put(json.loads(line))
                except ValueError:
                    pass
        self.q.put(None)

    def _send(self, msg):
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()

    def call(self, method, params):
        self.n += 1
        my = self.n
        self._send({"jsonrpc": "2.0", "id": my, "method": method, "params": params})
        end = time.time() + self.timeout
        while time.time() < end:
            try:
                m = self.q.get(timeout=max(0.1, end - time.time()))
            except queue.Empty:
                break
            if m is None:
                raise RuntimeError("server closed")
            if m.get("id") == my:
                return m
        raise TimeoutError(f"no answer to {method} in {self.timeout}s")

    def close(self):
        try:
            self.p.kill()
        except OSError:
            pass


def result_of(m):
    """(ok, data) from a JSON-RPC tools/call answer."""
    if "error" in m:
        return False, m["error"]
    r = m.get("result") or {}
    data = r.get("structuredContent")
    if data is None:
        texts = [c.get("text", "") for c in r.get("content") or [] if c.get("type") == "text"]
        joined = "\n".join(texts)
        try:
            data = json.loads(joined)
        except ValueError:
            data = {"text": joined[:2000]}
    ok = not r.get("isError") and not (isinstance(data, dict) and data.get("ok") is False)
    return ok, data


def dig(d, path):
    for part in path.split("."):
        if isinstance(d, dict):
            d = d.get(part)
        elif isinstance(d, list) and part.isdigit() and int(part) < len(d):
            d = d[int(part)]
        else:
            return None
    return d


def short(v, n=160):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    return s if len(s) <= n else s[:n - 3] + "..."


DEFAULT_PICK = ("data.outcome", "data.verified", "receipt.outcome", "error.code", "error.message", "message")


KEY_RX = re.compile(r"[^A-Za-z0-9._:-]+")


def clean_keys(args):
    """idempotency keys must match ^[A-Za-z0-9._:-]+$ (an effect name with spaces stopped a plan once)."""
    for k in ("idempotency_key", "idempotencyKey"):
        if isinstance(args.get(k), str):
            args[k] = KEY_RX.sub("_", args[k]).strip("_") or "k"
    return args


def applied_steps(out):
    try:
        old = json.load(open(out, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [r for r in old if isinstance(r, dict) and r.get("ok")]


def cmd_run(a):
    plan = json.load(open(a.plan, encoding="utf-8"))
    steps = plan["steps"] if isinstance(plan, dict) else plan
    epp = plan.get("expected_project_path") if isinstance(plan, dict) else None
    out = a.out or os.path.splitext(a.plan)[0] + ".results.json"
    done = applied_steps(out)
    if done and not a.start and not a.rerun:
        # every run is a new server process: idempotency keys do NOT carry over, so a re-run applies everything again
        nxt = max(r["step"] for r in done) + 1
        sys.exit(f"ALREADY_RUN {len(done)} step(s) of this plan were applied ({out}). Re-running would apply them "
                 f"twice. Continue with --from {nxt}, or --rerun only if you undid them.")
    first = a.start or 1
    cmd, env = server_command()
    cli = Client(cmd, env, a.timeout)
    saved, failed = {}, 0
    results = [r for r in done if r["step"] < first] if a.start else []
    try:
        for i, st in enumerate(steps, 1):
            if i < first:
                continue
            args = clean_keys(dict(st.get("args") or {}))
            if epp and "expected_project_path" not in args and not st.get("no_project_guard"):
                args["expected_project_path"] = epp
            if st.get("token_from"):
                src = saved.get(st["token_from"]) or {}
                tok = dig(src, "data.confirmationToken") or dig(src, "confirmationToken") or dig(src, "data.confirmation_token")
                if not tok:
                    print(f"#{i} {st['tool']} SKIP no confirmation token in '{st['token_from']}'")
                    failed += 1
                    break
                args["confirmation_token"] = tok
            try:
                ok, data = result_of(cli.call("tools/call", {"name": st["tool"], "arguments": args}))
            except (TimeoutError, RuntimeError) as e:
                ok, data = False, {"error": str(e)}
            results.append({"step": i, "tool": st["tool"], "ok": ok, "result": data})
            if st.get("save_as"):
                saved[st["save_as"]] = data
            picks = st.get("pick") or [p for p in DEFAULT_PICK if dig(data, p) is not None][:3]
            shown = " ".join(f"{p.split('.')[-1]}={short(dig(data, p))}" for p in picks)
            print(f"#{i} {st['tool']} {'OK' if ok else 'ERR'} {shown}".rstrip())
            text = json.dumps(data, ensure_ascii=False)
            if "HOST_RECOVERY_REQUIRED" in text:
                print("STOP recovery lock (HOST_RECOVERY_REQUIRED): inspect_operation_recovery, show the user, "
                      "acknowledge only after their review")
                failed += 1
                break
            if not ok:
                failed += 1
                if not a.continue_on_error:
                    print("STOP first error - see the results file")
                    break
    finally:
        cli.close()
        with open(out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"DONE steps={len(results)}/{len(steps)} errors={failed} -> {out}")
    sys.exit(1 if failed else 0)


def cmd_list(a):
    import re
    cmd, env = server_command()
    cli = Client(cmd, env, a.timeout)
    try:
        tools = (cli.call("tools/list", {}).get("result") or {}).get("tools") or []
    finally:
        cli.close()
    rx = re.compile(a.regex or ".", re.I)
    for t in tools:
        if a.schema:
            if t["name"] == a.schema:
                print(json.dumps({"description": t.get("description"), "input": t.get("inputSchema")}, indent=1)[:8000])
                return
            continue
        if rx.search(t["name"]) or rx.search(t.get("description") or ""):
            print(f"{t['name']}\t{(t.get('description') or '').splitlines()[0][:120] if t.get('description') else ''}")
    if a.schema:
        print(f"NOT_FOUND {a.schema}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    li = sp.add_parser("list")
    li.add_argument("regex", nargs="?")
    li.add_argument("--timeout", type=float, default=60)
    sc = sp.add_parser("schema")
    sc.add_argument("tool")
    sc.add_argument("--timeout", type=float, default=60)
    r = sp.add_parser("run")
    r.add_argument("plan")
    r.add_argument("--out")
    r.add_argument("--continue-on-error", action="store_true")
    r.add_argument("--from", dest="start", type=int, help="start at step N (steps before it count as applied)")
    r.add_argument("--rerun", action="store_true", help="run again although the results file shows applied steps")
    r.add_argument("--timeout", type=float, default=120, help="seconds per call")
    a = ap.parse_args()
    if a.cmd == "schema":
        a.schema, a.regex = a.tool, None
        return cmd_list(a)
    if a.cmd == "list":
        a.schema = None
        return cmd_list(a)
    return cmd_run(a)


if __name__ == "__main__":
    main()
