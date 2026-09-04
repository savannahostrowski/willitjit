# Package adapters

Each package has one alphabetically named TOML file here. Start with that file,
not runner code. `../dataset.toml` describes the ranking and release cutoff.

- `guidance` links to the upstream files reviewed at the selected release.
- `install` and `uv_sync` describe its dependencies and build steps. Prefer an
  upstream requirements file, lock or dependency group over a copied list.
- `test` is a Python argument list, not a shell command. It runs in `test_cwd`
  under the selected interpreter. Setup runs in `install_cwd`.
- `note` explains the chosen upstream lane and any deliberate differences.
- `skip_reason` disables the package with one visible Not tested reason. It is
  not an incompatibility claim and does not change its place in the ranking.

Inspect a recipe without installing dependencies or running upstream code:

```console
uv run willitjit plan --package aiohttp --runtime free-threaded --platform Windows
```

## Platform and runtime differences

Keep documented differences in `[[package.overrides]]` in the same file. Select
`runtime` (`jit` or `free-threaded`), `platform` (`Linux`, `Darwin`, `Windows`), or
both. Each override needs a reason in `note`.

Matching overrides apply in file order. Commands replace the default commands;
environment values merge with defaults. An omitted field inherits its default;
an empty command list explicitly clears it. Put general rules before specific
ones. The resulting recipe is identical for the baseline and target condition.
Adapters cannot set `PYTHON_JIT` or `PYTHON_GIL`.

The runner checks the actual test environment after installation. Don't launch
tox or nox inside it: that creates a second environment whose interpreter and
toggle may differ. Translate the selected upstream session's setup and test
commands directly, preserving test paths, warning policies and required fixtures.

## Reviewing a change

Read the linked guidance at the new release before accepting an update. The
release updater changes version metadata, not recipes or evidence links; old
links do not establish that a new release is supported.

Keep test-only backports in `../patches/` with their upstream commit in the
filename and adapter note. They must apply identically to both conditions and
remain visible in results. Do not add local failure suppressions, arbitrary
dependency downgrades, or retries to make a result green.

Some upstream jobs need credentials, services, mutable Git dependencies or a
custom interpreter-owning harness. Until a safe, documented lane is established,
mark them Not tested. A documented recipe can still fail on our interpreter;
keep that failure as evidence and validate changes in targeted hosted jobs.

The dated [top-100 source audit](../../../../docs/adapter-audit.md) records the
review behind these recipes. It is not evidence of hosted test success.
