# Will It JIT?

Will It JIT? runs popular Python packages' upstream test suites with the CPython
JIT off and on. A failure seen only with the JIT enabled is a lead for
investigation, not automatically a CPython bug.

Package rankings come from
[`hugovk/top-pypi-packages`](https://github.com/hugovk/top-pypi-packages). This
project measures compatibility only, not performance.

## Run

The runner installs dependencies and executes third-party code. Use a disposable
machine, VM, or container.

```console
uv sync --locked
uv run willitjit check-python --python /path/to/jit/python
uv run willitjit run --python /path/to/jit/python --package packaging
```

Results and logs are written below `runs/`. Run `uv run willitjit --help` for all
commands.

## App

```console
cd frontend
npm install
npm run dev
```

The Vite frontend reads `frontend/public/data/results.json`. `./build_app.sh`
builds the frontend into `api/static`, where FastAPI serves it with `/health`
and `/metrics`.

## CI

The weekly workflow tests the top 20 packages on Linux, macOS, and Windows using
CPython 3.15.0rc1. Four package shards run per platform. It uploads
the raw evidence and a merged JSON artifact, but does not commit results, update
the website, or deploy anything.

## Check

```console
uv run prek run --all-files
uv run python -m unittest discover -s tests -v
(cd frontend && npm run build)
(cd api && uv run pytest -q)
```
