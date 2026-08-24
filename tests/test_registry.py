from __future__ import annotations

import unittest

from willitjit.registry import load_registry


class RegistryTests(unittest.TestCase):
    def test_bundled_top_fifty(self) -> None:
        dataset, packages = load_registry()
        self.assertEqual(dataset["last_update"], "2026-08-01 06:34:08")
        self.assertEqual(len(packages), 50)
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
                "pydantic-core",
                "grpcio-status",
                "attrs",
                "s3transfer",
                "h11",
                "fsspec",
                "annotated-types",
                "protobuf",
                "markupsafe",
                "httpx",
                "httpcore",
                "typing-inspection",
                "pandas",
                "platformdirs",
                "pathspec",
                "python-dotenv",
                "jinja2",
                "filelock",
                "pyjwt",
                "s3fs",
                "litellm",
                "jmespath",
                "tqdm",
                "aiohttp",
                "yarl",
            ],
        )
        numpy = next(package for package in packages if package.name == "numpy")
        self.assertTrue(numpy.recursive_submodules)
        protobuf = next(package for package in packages if package.name == "protobuf")
        self.assertIn(
            ("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python"),
            protobuf.environment,
        )
        aiohttp = next(package for package in packages if package.name == "aiohttp")
        self.assertTrue(aiohttp.recursive_submodules)


if __name__ == "__main__":
    unittest.main()
