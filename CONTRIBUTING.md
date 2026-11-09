# Contributing

Thanks for taking the time. Bug reports, ideas and pull requests are all welcome.

## Reporting a problem

Open an issue with:

- After Effects version and OS
- The MCP server you use (and its version)
- What you asked Claude, what happened, what you expected
- The one-line output of the script involved, if any (`cutlist.py`, `subtitles.py`, ...)

Please don't attach client footage.

## Working on the code

```bash
git clone https://github.com/keremgulluuu/ae-keremkit.git
cd ae-keremkit
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

`tests/test_repo.py` checks the repository itself: plugin metadata, `SKILL.md` frontmatter, reference links, docs links, examples, changelog/version agreement, Python 3.9 syntax, standard-library-only imports and the claude.ai zip. It needs no After Effects, MCP server, Whisper or media.

Guidelines:

- **Scripts use the Python standard library only.** They run on users' machines with whatever Python they have (3.9+).
- **Keep output short.** Every line a script prints is read by Claude and costs tokens. One result line per command is the norm.
- **Never print media or whole files.** Summaries and paths only.
- **Add a test** for any behaviour change in `scripts/`.
- **Skill text** (`SKILL.md`, `references/`) should stay lean. `SKILL.md` is read on every task; put detail in the reference file that needs it.
- **No personal defaults.** Anything that depends on the user goes into preferences and is asked when needed.

## Releasing

1. Move the `[Unreleased]` notes in `CHANGELOG.md` under the new version heading.
2. Bump `version` in `plugins/ae-keremkit/.claude-plugin/plugin.json` to the same version.
3. Tag `vX.Y.Z` and push the tag. The release workflow checks that the tag matches `plugin.json`, runs the tests, builds the claude.ai zip and attaches it to the release.

The repository tests also check that the newest released `CHANGELOG.md` heading matches `plugin.json`, so the two cannot drift silently.
