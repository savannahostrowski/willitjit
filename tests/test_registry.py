from __future__ import annotations

import unittest

from willitjit.registry import load_registry


class RegistryTests(unittest.TestCase):
    def test_bundled_top_hundred(self) -> None:
        dataset, packages = load_registry()
        self.assertEqual(dataset["last_update"], "2026-08-01 06:34:08")
        self.assertEqual(
            dataset["selection"],
            "first 100 packages with official GitHub repositories",
        )
        self.assertEqual(len(packages), 100)
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
                "pip",
                "rich",
                "markdown-it-py",
                "rpds-py",
                "uvicorn",
                "starlette",
                "jsonschema",
                "wheel",
                "multidict",
                "google-auth",
                "propcache",
                "pyasn1",
                "fastapi",
                "aiohappyeyeballs",
                "frozenlist",
                "pytz",
                "mdurl",
                "pillow",
                "referencing",
                "importlib-metadata",
                "websockets",
                "opentelemetry-semantic-conventions",
                "trove-classifiers",
                "jsonschema-specifications",
                "aiosignal",
                "virtualenv",
                "zipp",
                "opentelemetry-sdk",
                "googleapis-common-protos",
                "tzdata",
                "wrapt",
                "sniffio",
                "hatchling",
                "google-api-core",
                "greenlet",
                "opentelemetry-api",
                "pyasn1-modules",
                "annotated-doc",
                "pydantic-settings",
                "scipy",
                "grpcio",
                "textual",
                "huggingface-hub",
                "regex",
                "pyarrow",
                "colorama",
                "tenacity",
                "soupsieve",
                "sqlalchemy",
                "distro",
            ],
        )
        self.assertEqual(packages[-6].rank, 95)
        self.assertEqual(packages[-5].rank, 97)
        self.assertEqual(packages[-1].rank, 101)
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
