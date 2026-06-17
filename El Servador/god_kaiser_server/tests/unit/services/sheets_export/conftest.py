import pytest


@pytest.fixture(autouse=True)
def skip_sheets_export_tests():
    pytest.skip("Google Sheets Export not supported on this server")
