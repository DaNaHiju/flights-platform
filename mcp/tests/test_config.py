import pytest

from brisa_mcp.config import DEFAULT_API_URL, load_settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("BRISA_API_URL", raising=False)
    monkeypatch.delenv("BRISA_TIMEOUT_SECONDS", raising=False)
    settings = load_settings()
    assert settings.api_url == DEFAULT_API_URL == "http://10.100.102.12/api"
    assert settings.timeout_seconds == 40


def test_env_overrides_and_trailing_slash(monkeypatch):
    monkeypatch.setenv("BRISA_API_URL", "http://localhost:8000/api/")
    monkeypatch.setenv("BRISA_TIMEOUT_SECONDS", "12.5")
    settings = load_settings()
    assert settings.api_url == "http://localhost:8000/api"
    assert settings.timeout_seconds == 12.5


@pytest.mark.parametrize("bad", ["abc", "0", "-3"])
def test_bad_timeout_stops_the_server_with_a_clear_message(monkeypatch, bad):
    monkeypatch.setenv("BRISA_TIMEOUT_SECONDS", bad)
    with pytest.raises(SystemExit, match="BRISA_TIMEOUT_SECONDS"):
        load_settings()
