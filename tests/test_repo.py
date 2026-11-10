"""Repository consistency tests.

These checks need no After Effects, no MCP server, no Whisper and no media:
they only look at the files that make up the plugin, the skill and the docs.

They are the cheap guard against the kind of drift that is easy to miss in
review: a reference that is no longer linked, a changelog that does not match
the plugin version, a zip built with Windows path separators, or a script that
quietly starts depending on a third-party package.
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(ROOT, "plugins", "ae-keremkit")
SKILL_DIR = os.path.join(PLUGIN_DIR, "skills", "ae-keremkit")
SCRIPTS = os.path.join(SKILL_DIR, "scripts")
REFERENCES = os.path.join(SKILL_DIR, "references")
TOOLS = (
    "keremkit.py",
    "transcript.py",
    "cutlist.py",
    "subtitles.py",
    "editplan.py",
    "audio.py",
    "sfx.py",
    "qc.py",
    "techniques.py",
    "tokens.py",
    "presets.py",
    "videoref.py",
    "previews.py",
    "assets.py",
    "digest.py",
)
ASSET_FILES = ("techniques.json",)
SKILL_FRONTMATTER_KEYS = {
    "name", "description", "license", "compatibility", "metadata", "allowed-tools",
}

MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTML_IMAGE = re.compile(r'<img[^>]+src="([^"]+)"')


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rel(path):
    return os.path.relpath(path, ROOT)


def skill_text():
    return read(os.path.join(SKILL_DIR, "SKILL.md"))


def skill_frontmatter():
    text = skill_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must start with YAML frontmatter"
    return match.group(1)


def test_marketplace_and_plugin_metadata_agree():
    marketplace = load_json(os.path.join(ROOT, ".claude-plugin", "marketplace.json"))
    plugin = load_json(os.path.join(PLUGIN_DIR, ".claude-plugin", "plugin.json"))

    entries = {entry["name"]: entry for entry in marketplace["plugins"]}
    assert plugin["name"] in entries, "plugin is not listed in marketplace.json"
    assert entries[plugin["name"]]["source"] == "./plugins/ae-keremkit"
    assert plugin["name"] == os.path.basename(PLUGIN_DIR)
    assert re.fullmatch(r"\d+\.\d+\.\d+", plugin["version"]), plugin["version"]


def test_skill_frontmatter_is_valid():
    frontmatter = skill_frontmatter()
    keys = set(re.findall(r"^([a-z_-]+):", frontmatter, re.MULTILINE))
    unsupported = keys - SKILL_FRONTMATTER_KEYS
    assert not unsupported, f"unsupported frontmatter keys: {unsupported}"
    assert {"name", "description"} <= keys

    name = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE).group(1).strip()
    assert name == os.path.basename(SKILL_DIR)

    description = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE).group(1)
    assert 0 < len(description) <= 1024, f"description is {len(description)} characters"


def test_every_reference_is_linked_and_every_tool_is_mentioned():
    text = skill_text()
    for name in sorted(os.listdir(REFERENCES)):
        if name.endswith(".md"):
            assert f"references/{name}" in text, f"{name} is not linked from SKILL.md"
    for name in TOOLS:
        assert name in text, f"{name} is not mentioned in SKILL.md"
        assert os.path.exists(os.path.join(SCRIPTS, name))
    assets = os.path.join(SKILL_DIR, "assets")
    for name in ASSET_FILES:
        assert os.path.exists(os.path.join(assets, name))


def test_init_copies_every_tool():
    source = read(os.path.join(SCRIPTS, "keremkit.py"))
    tree = ast.parse(source)
    copied = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "TOOLS" in targets:
                copied = ast.literal_eval(node.value)
                break
    assert copied is not None, "could not find the TOOLS tuple in keremkit.py"
    assert set(copied) == set(TOOLS) | set(ASSET_FILES)


def markdown_files():
    yield os.path.join(ROOT, "README.md")
    yield os.path.join(ROOT, "CONTRIBUTING.md")
    docs = os.path.join(ROOT, "docs")
    for name in sorted(os.listdir(docs)):
        if name.endswith(".md"):
            yield os.path.join(docs, name)


def test_relative_links_and_images_resolve():
    missing = []
    for path in markdown_files():
        text = read(path)
        targets = MARKDOWN_LINK.findall(text) + HTML_IMAGE.findall(text)
        for target in targets:
            target = target.split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
            if not os.path.exists(resolved):
                missing.append(f"{rel(path)} -> {target}")
    assert not missing, "broken local links:\n" + "\n".join(missing)


def test_example_and_metadata_json_are_valid():
    folders = [
        os.path.join(ROOT, "examples"),
        os.path.join(SKILL_DIR, "assets"),
        os.path.join(ROOT, ".claude-plugin"),
        os.path.join(PLUGIN_DIR, ".claude-plugin"),
    ]
    for folder in folders:
        for name in sorted(os.listdir(folder)):
            if name.endswith(".json"):
                load_json(os.path.join(folder, name))


def test_changelog_newest_release_matches_plugin_version():
    plugin = load_json(os.path.join(PLUGIN_DIR, ".claude-plugin", "plugin.json"))
    changelog = read(os.path.join(ROOT, "CHANGELOG.md"))
    versions = re.findall(r"^##\s+\[(\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)
    assert versions, "CHANGELOG.md has no released version heading"
    assert versions[0] == plugin["version"], (
        f"plugin.json says {plugin['version']} but the newest released "
        f"CHANGELOG entry is {versions[0]}"
    )


def test_runtime_scripts_only_import_the_standard_library():
    stdlib = getattr(sys, "stdlib_module_names", None)
    if stdlib is None:
        pytest.skip("sys.stdlib_module_names requires Python 3.10+")

    offenders = []
    for folder in (SCRIPTS, os.path.join(ROOT, "tools")):
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".py"):
                continue
            tree = ast.parse(read(os.path.join(folder, name)))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    modules = [(node.module or "").split(".")[0]]
                else:
                    continue
                offenders.extend(
                    f"{name}: {module}"
                    for module in modules
                    if module and module not in stdlib and f"{module}.py" not in os.listdir(folder)
                )
    assert not offenders, "third-party imports in shipped scripts:\n" + "\n".join(offenders)


def test_all_python_files_parse_as_python_39():
    skipped = {".git", "__pycache__", ".pytest_cache", "dist", ".venv", "venv", "node_modules"}
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in skipped)
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            try:
                ast.parse(read(path), filename=path, feature_version=(3, 9))
            except SyntaxError as exc:
                pytest.fail(f"{rel(path)} is not valid Python 3.9 syntax: {exc}")


def test_build_skill_zip_is_portable(tmp_path):
    # Copy only what the builder needs so the real dist/ folder is never touched.
    shutil.copytree(PLUGIN_DIR, tmp_path / "plugins" / "ae-keremkit")
    (tmp_path / "tools").mkdir()
    builder = os.path.join(ROOT, "tools", "build_skill.py")
    shutil.copy2(builder, tmp_path / "tools" / "build_skill.py")

    result = subprocess.run(
        [sys.executable, str(tmp_path / "tools" / "build_skill.py")],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr

    plugin = load_json(tmp_path / "plugins" / "ae-keremkit" / ".claude-plugin" / "plugin.json")
    archive = tmp_path / "dist" / f"ae-keremkit-{plugin['version']}.zip"
    assert archive.exists()

    with zipfile.ZipFile(archive) as z:
        names = z.namelist()

    assert names
    assert all(name.startswith("ae-keremkit/") for name in names)
    assert all("\\" not in name for name in names), "zip entries must use POSIX separators"
    assert "ae-keremkit/SKILL.md" in names
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
    assert len(names) == len(set(names)), "zip contains duplicate entries"
