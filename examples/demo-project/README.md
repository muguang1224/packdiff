# Demo service

A deliberately tiny project used to generate `../demo-project.pack.md`.

It exists so that visitors can see the output of `ctxpack` without installing
anything, and so that the test suite has a real directory tree to assert on.

Things worth noticing in the generated pack:

* `cache/` and `debug.log` are absent — the `.gitignore` above excluded them.
* `assets/logo.png` is absent — binary files are dropped by extension.
* `.env.example` **is** present — a template is not a secret.
* `src/util.py` is present but sits last, because it is a plain module rather
  than an entry point.
