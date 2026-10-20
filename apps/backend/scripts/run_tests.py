"""Run mocked-provider tests in a disposable database, never the app database."""
import os
from pathlib import Path
import sys
import tempfile
import unittest


def main():
    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend))
    with tempfile.TemporaryDirectory(prefix="cropgrid-tests-") as directory:
        database = Path(directory) / "test.db"
        os.environ["DATABASE_URL"] = "sqlite:///" + database.as_posix()
        os.environ["CROPGRID_SEED_DEMO"] = "true"
        # Tests explicitly supply mock credentials where required. Never contact
        # a real provider or provision a real administrator through this runner.
        for name in ("ADMIN_EMAIL", "ADMIN_PASSWORD", "OPENAI_API_KEY", "PAYSTACK_SECRET_KEY"):
            os.environ[name] = ""
        try:
            suite = unittest.defaultTestLoader.discover(str(backend / "tests"))
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            return 0 if result.wasSuccessful() else 1
        finally:
            module = sys.modules.get("app.database")
            if module is not None:
                module.engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
