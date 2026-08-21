from __future__ import annotations

import unittest

from jit_package_compat.registry import load_registry


class RegistryTests(unittest.TestCase):
    def test_bundled_top_twenty_five(self) -> None:
        dataset, packages = load_registry()
        self.assertEqual(dataset["last_update"], "2026-08-01 06:34:08")
        self.assertEqual(len(packages), 25)
        self.assertEqual(
            [package.name for package in packages],
            [
                "boto3",
                "packaging",
                "typing-extensions",
                "certifi",
                "urllib3",
                "idna",
                "requests",
                "charset-normalizer",
                "setuptools",
                "botocore",
                "cryptography",
                "cffi",
                "pluggy",
                "pygments",
                "pyyaml",
                "python-dateutil",
                "six",
                "aiobotocore",
                "numpy",
                "pycparser",
                "pydantic",
                "pytest",
                "click",
                "iniconfig",
                "anyio",
            ],
        )
        numpy = next(package for package in packages if package.name == "numpy")
        self.assertTrue(numpy.recursive_submodules)


if __name__ == "__main__":
    unittest.main()
