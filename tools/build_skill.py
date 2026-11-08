#!/usr/bin/env python3
"""Package the skill as a zip for claude.ai (Customize > Skills > + > Upload a skill).

    python tools/build_skill.py            -> dist/ae-keremkit-<version>.zip
"""
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "ae-keremkit")
SKILL = os.path.join(PLUGIN, "skills", "ae-keremkit")
SKIP_DIRS = {"__pycache__", ".pytest_cache"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}


def check_frontmatter():
    with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        sys.exit("SKILL.md has no frontmatter")
    keys = re.findall(r"^([a-z_-]+):", m.group(1), re.M)
    allowed = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    extra = set(keys) - allowed
    if extra:
        sys.exit(f"SKILL.md frontmatter has keys claude.ai rejects: {', '.join(sorted(extra))}")
    desc = re.search(r"^description: (.*)$", m.group(1), re.M).group(1)
    if len(desc) > 1024:
        sys.exit(f"description is {len(desc)} chars; keep it under 1024")


def main():
    check_frontmatter()
    with open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
        version = json.load(f)["version"]
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", f"ae-keremkit-{version}.zip")
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(SKILL):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(files):
                if name in SKIP_FILES or name.endswith(".pyc"):
                    continue
                full = os.path.join(base, name)
                z.write(full, os.path.join("ae-keremkit", os.path.relpath(full, SKILL)))
                count += 1
    print(f"{out} ({count} files)")


if __name__ == "__main__":
    main()
