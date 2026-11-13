"""Docs <-> CLI consistency tests.

The markdown in this skill is not prose for humans: it is the instruction set an
LLM follows. A reference that tells the agent to run `techniques.py search` when
the parser only knows groups/list/show/add/remove is a production bug - the call
always fails, burns a turn and teaches the model nothing.

These tests read the argparse definitions straight from the shipped scripts and
check every `script.py subcommand --flag` mention in SKILL.md, references/ and
assets/ against them. No AE, no media, no network.
"""
import ast
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.join(ROOT, "plugins", "keremkit", "skills", "keremkit")
SCRIPTS = os.path.join(SKILL_DIR, "scripts")

SPAN = re.compile(r"`([^`\n]+)`")
TOOL = re.compile(r"\b([a-z][a-z0-9_]*\.py)\b")
SUBCOMMAND = re.compile(r"^[a-z][a-z0-9-]*$")
FLAG = re.compile(r"(?<![\w-])(--[a-z0-9][a-z0-9-]*)")

# A proposal describes a command that does not exist *yet*; checking it would
# turn "add a --seq filter some day" into a permanent red test.
PROPOSAL = re.compile(r"\bproposal\b", re.IGNORECASE)

MISS = object()


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def flags_of(call):
    """Long and short option strings of one add_argument(...) call."""
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and call.func.attr == "add_argument"):
        return []
    return [arg.value for arg in call.args
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("-")]


def helper_flags(tree):
    """Flags added by helpers such as download.py's add_cookies(parser)."""
    helpers = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            found = [flag for sub in ast.walk(node) for flag in flags_of(sub)]
            if found:
                helpers[node.name] = found
    return helpers


def parser_info(path):
    """Return ({subcommand: {flags}}, {root flags}) for one script.

    The scripts build argparse in a flat block inside main(), so a small
    statement walk is enough: remember which variable holds which parser, then
    attach every add_argument to its owner. Dynamic flags written as
    `"--" + name` in a for loop over literals are expanded.
    """
    tree = ast.parse(read(path))
    helpers = helper_flags(tree)

    subcommands, owners, groups, root_flags = {}, {}, {}, set()
    body = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            body.extend(node.body)

    def owner_of(expr):
        if isinstance(expr, ast.Name):
            if expr.id in owners:
                return owners[expr.id]
            if expr.id in groups:
                return groups[expr.id]
        return MISS

    def add_flags(owner, flags):
        if owner is MISS or owner is None:
            root_flags.update(flags)
        else:
            subcommands[owner].update(flags)

    for stmt in body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            var, value = stmt.targets[0].id, stmt.value
            if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)):
                continue
            kind = value.func.attr
            if kind == "add_parser":
                name = value.args[0].value
                subcommands[name] = set()
                owners[var] = name
            elif kind == "add_subparsers":
                owners[var] = None
            elif kind == "add_mutually_exclusive_group":
                groups[var] = owner_of(value.func.value)
            elif kind == "add_argument":
                add_flags(owner_of(value.func.value), set(flags_of(value)))

        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            func = call.func
            if isinstance(func, ast.Attribute) and func.attr == "add_parser":
                # A parser with no options: `sp.add_parser("where")`.
                subcommands[call.args[0].value] = subcommands.get(call.args[0].value, set())
            elif isinstance(func, ast.Attribute) and func.attr == "add_argument":
                add_flags(owner_of(func.value), set(flags_of(call)))
            elif isinstance(func, ast.Name) and func.id in helpers:
                target = MISS
                for arg in call.args:
                    target = owner_of(arg)
                    if target is not MISS and target is not None:
                        break
                add_flags(target, set(helpers[func.id]))

        elif isinstance(stmt, ast.For):
            iterable = stmt.iter
            names = [e.value for e in iterable.elts
                     if isinstance(e, ast.Constant) and isinstance(e.value, str)] \
                if isinstance(iterable, (ast.Tuple, ast.List)) else []
            loop_var = stmt.target.id if isinstance(stmt.target, ast.Name) else None
            if not names or not loop_var:
                continue
            for sub in ast.walk(stmt):
                if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "add_argument"):
                    continue
                owner = owner_of(sub.func.value)
                for arg in sub.args:
                    if (isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add)
                            and isinstance(arg.right, ast.Name) and arg.right.id == loop_var
                            and isinstance(arg.left, ast.Constant)):
                        add_flags(owner, {arg.left.value + name for name in names})

    return subcommands, root_flags


def every_parser():
    return {os.path.basename(path): parser_info(path)
            for path in sorted(glob.glob(os.path.join(SCRIPTS, "*.py")))}


def doc_files():
    files = [os.path.join(SKILL_DIR, "SKILL.md")]
    for folder in ("references", "assets"):
        files.extend(sorted(glob.glob(os.path.join(SKILL_DIR, folder, "*.md"))))
    return files


def commands_in(span):
    """Yield (script, subcommand or None, flags) for each tool mention in a span.

    One backticked span can hold several calls (`build ... -> render ...`), and
    the text after a script name holds that call's subcommand and flags.
    """
    matches = list(TOOL.finditer(span))
    for index, match in enumerate(matches):
        script = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(span)
        segment = span[match.end():end]
        words = segment.split()
        subcommand = words[0] if words and SUBCOMMAND.match(words[0]) else None
        yield script, subcommand, FLAG.findall(segment)


def line_problems(line, parsers, where):
    """Problems in one markdown line. Split out so the checker itself can be tested."""
    if PROPOSAL.search(line):
        return []
    problems = []
    for span in SPAN.findall(line):
        for script, subcommand, flags in commands_in(span):
            if script not in parsers:
                continue                      # <home>/tools/x.py is a placeholder
            subcommands, root_flags = parsers[script]
            if subcommands:
                if subcommand is None:
                    continue                  # a bare mention, not a command
                if subcommand not in subcommands:
                    choices = ", ".join(sorted(subcommands))
                    problems.append(
                        f"{where}: {script} has no subcommand {subcommand!r} (choose from {choices})")
                    continue
                allowed = root_flags | subcommands[subcommand]
            else:
                allowed = root_flags
            for flag in flags:
                if flag not in allowed:
                    problems.append(
                        f"{where}: {script} {subcommand or ''} does not accept {flag} (in `{span}`)")
    return problems


def doc_problems():
    parsers = every_parser()
    problems = []
    for path in doc_files():
        where = os.path.relpath(path, ROOT)
        for lineno, line in enumerate(read(path).splitlines(), 1):
            problems.extend(line_problems(line, parsers, f"{where}:{lineno}"))
    return problems


def test_documented_commands_exist():
    problems = doc_problems()
    assert not problems, "docs mention commands the tools reject:\n" + "\n".join(problems)


def test_every_script_is_parsed_and_documented():
    """Guard against the extractor silently seeing nothing (a green but empty test)."""
    parsers = every_parser()
    assert "keremkit.py" in parsers
    assert len(parsers["keremkit.py"][0]) >= 20
    assert "list" in parsers["techniques.py"][0]
    assert "--output" in parsers["subtitles.py"][0]["build"]

    seen = set()
    for path in doc_files():
        for line in read(path).splitlines():
            for span in SPAN.findall(line):
                for script, _, _ in commands_in(span):
                    seen.add(script)
    assert {"keremkit.py", "cutlist.py", "subtitles.py", "transcript.py", "prproj.py"} <= seen


def test_checker_catches_a_missing_subcommand():
    """The self-test: a real bug we found by hand must fail this checker."""
    problems = line_problems("use `techniques.py search` for this", every_parser(), "fake.md:1")
    assert any("has no subcommand 'search'" in problem for problem in problems), problems


def test_checker_catches_a_missing_flag():
    problems = line_problems("run `prproj.py inventory --seq a.json`", every_parser(), "fake.md:1")
    assert any("does not accept --seq" in problem for problem in problems), problems


def test_proposal_lines_are_not_treated_as_commands():
    """token-budget.md proposes `prproj.py inventory --seq`; that is not a bug."""
    line = "   - Proposal: add a `prproj.py inventory --seq` filter."
    assert line_problems(line, every_parser(), "fake.md:1") == []
