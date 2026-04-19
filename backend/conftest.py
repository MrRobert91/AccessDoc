import os
import pytest

os.environ.setdefault("OPENROUTER_API_KEY", "sk-test-key")
os.environ.setdefault("TMP_DIR", "/tmp/accessdoc_test")


@pytest.fixture(scope="session", autouse=True)
def _generate_pdf_fixtures():
    """Generate synthetic PDF fixtures once per test session."""
    from pathlib import Path
    fixtures_dir = Path(__file__).parent / "tests" / "fixtures"
    required = ["simple.pdf", "multicolumn.pdf", "complex_tables.pdf", "scanned.pdf"]
    if not all((fixtures_dir / n).exists() for n in required):
        from tests.fixtures.generate_fixtures import make_all
        make_all()
    yield
