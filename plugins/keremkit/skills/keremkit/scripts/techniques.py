#!/usr/bin/env python3
"""KeremKit techniques - the editing techniques the kit knows, plus the user's own.

  groups                          list the groups with counts
  list  [--group G]               technique names with one-line descriptions
  show  ID                        full card
  add   --id ID --group G --name NAME --what TEXT [--when TEXT] [--how TEXT] [--auto]
                                  add/replace a user technique (KeremKit/settings/techniques.json)
  remove ID                       remove a user technique

Built-in techniques ship with the skill (assets/techniques.json); user techniques override
them by id. Output is short on purpose - Claude translates and presents it to the user.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILTIN = [os.path.join(HERE, "..", "assets", "techniques.json"), os.path.join(HERE, "techniques.json")]


def rjson(p, default=None):
    if p and os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return default


def home_dir(override):
    if override:
        return os.path.abspath(override)
    ptr = rjson(os.path.join(os.path.expanduser("~"), ".keremkit.json"), {})
    return ptr.get("home") or os.path.join(os.path.expanduser("~"), "Documents", "KeremKit")


def load_all(home):
    base = next((rjson(p) for p in BUILTIN if os.path.exists(p)), {"groups": {}, "techniques": []})
    user = rjson(os.path.join(home, "settings", "techniques.json"), {"groups": {}, "techniques": []})
    groups = dict(base.get("groups", {}))
    groups.update(user.get("groups", {}))
    by_id = {t["id"]: dict(t, source="built-in") for t in base.get("techniques", [])}
    for t in user.get("techniques", []):
        by_id[t["id"]] = dict(t, source="user")
    return groups, list(by_id.values()), user


def cmd_groups(a):
    groups, techs, _ = load_all(home_dir(a.home))
    for g, label in groups.items():
        n = sum(1 for t in techs if t["group"] == g)
        print(f"{g}\t{n}\t{label}")


def cmd_list(a):
    groups, techs, _ = load_all(home_dir(a.home))
    shown = [t for t in techs if not a.group or t["group"] == a.group]
    if not shown:
        print("NO_TECHNIQUES" + (f" in group {a.group}" if a.group else ""))
        return
    for t in shown:
        flag = "auto" if t.get("auto") else "manual"
        print(f"{t['id']}\t{t['name']}\t[{flag}{', user' if t['source'] == 'user' else ''}]\t{t['what']}")


def cmd_show(a):
    _, techs, _ = load_all(home_dir(a.home))
    t = next((x for x in techs if x["id"] == a.id or x["name"].lower() == a.id.lower()), None)
    if not t:
        print("NO_MATCH")
        return
    for k in ("id", "group", "name", "aka", "what", "when", "how", "params", "auto", "source"):
        if t.get(k) not in (None, "", []):
            v = t[k]
            print(f"{k}\t{json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v}")


def save_user(home, user):
    p = os.path.join(home, "settings", "techniques.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(user, f, ensure_ascii=False, indent=1)


def cmd_add(a):
    home = home_dir(a.home)
    groups, _, user = load_all(home)
    if a.group not in groups:
        user.setdefault("groups", {})[a.group] = a.group_label or a.group
    t = {"id": a.id, "group": a.group, "name": a.name, "what": a.what, "when": a.when or "", "how": a.how or "",
         "auto": bool(a.auto), "aka": a.aka or []}
    user["techniques"] = [x for x in user.get("techniques", []) if x["id"] != a.id] + [t]
    save_user(home, user)
    print(f"OK technique {a.id} ({a.group})")


def cmd_remove(a):
    home = home_dir(a.home)
    _, _, user = load_all(home)
    before = len(user.get("techniques", []))
    user["techniques"] = [x for x in user.get("techniques", []) if x["id"] != a.id]
    save_user(home, user)
    print("OK removed" if len(user["techniques"]) < before else "NOT_A_USER_TECHNIQUE (built-ins cannot be removed)")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("groups")
    l = sp.add_parser("list")
    l.add_argument("--group")
    s = sp.add_parser("show")
    s.add_argument("id")
    ad = sp.add_parser("add")
    for k in ("id", "group", "name", "what"):
        ad.add_argument("--" + k, required=True)
    ad.add_argument("--group-label")
    ad.add_argument("--when")
    ad.add_argument("--how")
    ad.add_argument("--aka", nargs="*")
    ad.add_argument("--auto", action="store_true")
    r = sp.add_parser("remove")
    r.add_argument("id")
    a = ap.parse_args()
    {"groups": cmd_groups, "list": cmd_list, "show": cmd_show, "add": cmd_add, "remove": cmd_remove}[a.cmd](a)


if __name__ == "__main__":
    main()
