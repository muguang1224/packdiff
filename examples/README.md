# Examples

## `demo-project.pack.md`

The output of running packdiff on `demo-project/`, committed so you can see what
this tool produces without installing anything:

```bash
python3 examples/regenerate.py     # rebuild it after changing the format
```

`tests/test_examples.py` regenerates the pack and compares it byte for byte
against the committed file, so it cannot silently drift out of date.

## `demo-project/`

A deliberately tiny project — a README, a manifest, two modules, a config
template — arranged to show off what packdiff filters out:

| Path | What it demonstrates |
| --- | --- |
| `cache/response.json` | excluded by the demo's own `.gitignore` |
| `debug.log` | excluded by the demo's own `.gitignore` |
| `assets/logo.png` | excluded as binary, by extension |
| `.env.example` | **kept** — a template is not a secret |
| `src/app.py` | an entry point, so it is admitted first under a token budget |
| `src/util.py` | an ordinary module, so it sorts later |

### A note on `cache/` and `debug.log`

Those two files are in the repository *even though the demo's own `.gitignore`
ignores them*. They were added with `git add -f` on purpose: git ignore rules
only apply to untracked files, so they stay tracked and therefore exist in a
fresh clone, which is what makes the demo demonstrate anything. Without them the
`.gitignore` next to them would be ignoring nothing, and the example would be
quietly hollow.

If you edit them, `git add -A` picks the change up normally — only the initial
add needed the flag.

### Why there is no `.env` here

The secret filter is the most useful thing packdiff does, and it would have been
easy to demonstrate with a fake `.env`. It is deliberately absent: a public
repository is a bad place for any file called `.env`, even one full of
placeholders, and copying a fake credential file into a repository is a habit
worth not encouraging. The filter is covered by dedicated tests instead —
`python -m pytest tests/test_walk.py -k secret`.
