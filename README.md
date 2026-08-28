# Will It JIT?

Will It JIT? runs popular Python packages' upstream test suites with the CPython
JIT off and on. It also records a paired free-threaded sanity check. Each feature
is compared with its own control so ordinary package or interpreter failures do
not count as JIT regressions.

Package rankings come from
[`hugovk/top-pypi-packages`](https://github.com/hugovk/top-pypi-packages). This
project measures compatibility only, not performance. Sources hosted outside
GitHub are not surveyed yet.
