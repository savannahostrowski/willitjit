# Will It JIT?

Will It JIT? runs popular Python packages' upstream test suites with the CPython
JIT off and on. A failure seen only with the JIT enabled is a lead for
investigation, not automatically a CPython bug.

Package rankings come from
[`hugovk/top-pypi-packages`](https://github.com/hugovk/top-pypi-packages). This
project measures compatibility only, not performance.
