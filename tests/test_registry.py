from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime

from willitjit.models import Package
from willitjit.registry import load_registry, validate_registry


class RegistryTests(unittest.TestCase):
    def test_rejects_unsafe_package_name(self) -> None:
        package = Package(
            rank=1,
            name="..",
            downloads=1,
            repository="https://github.com/example/example.git",
            ref="HEAD",
            install=(("-m", "pip", "install", "."),),
            test=("-m", "pytest"),
        )
        with self.assertRaisesRegex(ValueError, "unsafe package name"):
            validate_registry([package])

    def test_rejects_moving_or_too_new_release(self) -> None:
        package = Package(
            rank=1,
            name="example",
            downloads=1,
            repository="https://github.com/example/example.git",
            ref="v1.0.0",
            install=(("-m", "pip", "install", "."),),
            test=("-m", "pytest"),
            release_version="1.0.0",
            release_date="2026-08-01T00:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "needs a pinned release"):
            validate_registry(
                [replace(package, ref="HEAD")],
                release_cutoff="2026-08-11T00:00:00Z",
            )
        with self.assertRaisesRegex(ValueError, "released after the cutoff"):
            validate_registry(
                [replace(package, release_date="2026-08-12T00:00:00Z")],
                release_cutoff="2026-08-11T00:00:00Z",
            )

    def test_bundled_top_hundred(self) -> None:
        dataset, packages = load_registry()
        self.assertEqual(dataset["last_update"], "2026-08-01 06:34:08")
        self.assertEqual(
            dataset["selection"],
            "first 100 packages with official GitHub repositories",
        )
        cutoff = datetime.fromisoformat(dataset["release_cutoff"])
        self.assertEqual(len(packages), 100)
        self.assertNotIn("HEAD", {package.ref for package in packages})
        self.assertTrue(all(package.release_version for package in packages))
        self.assertTrue(all(package.release_date for package in packages))
        self.assertTrue(
            all(
                datetime.fromisoformat(package.release_date) <= cutoff
                for package in packages
            )
        )
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
        scipy = next(package for package in packages if package.name == "scipy")
        self.assertTrue(scipy.recursive_submodules)
        referencing = next(
            package for package in packages if package.name == "referencing"
        )
        self.assertTrue(referencing.recursive_submodules)
        attrs = next(package for package in packages if package.name == "attrs")
        self.assertTrue(attrs.fetch_tags)
        google_auth = next(
            package for package in packages if package.name == "google-auth"
        )
        self.assertEqual(google_auth.sparse_paths, ("packages/google-auth",))
        pydantic_core = next(
            package for package in packages if package.name == "pydantic-core"
        )
        self.assertEqual(
            pydantic_core.repository, "https://github.com/pydantic/pydantic.git"
        )
        self.assertEqual(pydantic_core.sparse_paths, ("pydantic-core",))
        self.assertIn(
            "pydantic-core/pyproject.toml:testing-extra",
            pydantic_core.install[0],
        )
        pillow = next(package for package in packages if package.name == "pillow")
        self.assertFalse(pillow.skip_platforms)
        self.assertIn("jpeg=disable", pillow.install[0])
        self.assertIn("zlib=disable", pillow.install[0])
        botocore = next(package for package in packages if package.name == "botocore")
        self.assertEqual(
            botocore.focused_test,
            ("-m", "pytest", "functional/csm/test_monitoring.py"),
        )
        self.assertIn("not slow", numpy.test)
        multidict = next(package for package in packages if package.name == "multidict")
        self.assertIn("--no-c-extensions", multidict.test)
        sqlalchemy = next(
            package for package in packages if package.name == "sqlalchemy"
        )
        self.assertFalse(any("--group" in command for command in sqlalchemy.install))


if __name__ == "__main__":
    unittest.main()
