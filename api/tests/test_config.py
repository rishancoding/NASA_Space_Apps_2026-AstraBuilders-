"""Local-secret configuration tests use fake values and make no network requests."""
from api import config


def test_local_environment_loads_from_repo_path_not_current_directory(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=local-test-value\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    other_directory = tmp_path / "other"
    other_directory.mkdir()
    monkeypatch.chdir(other_directory)

    assert config.load_environment()
    import os
    assert os.environ["DEEPSEEK_API_KEY"] == "local-test-value"


def test_deployment_environment_overrides_local_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=local-test-value\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deployment-test-value")

    config.load_environment()
    import os
    assert os.environ["DEEPSEEK_API_KEY"] == "deployment-test-value"


def test_missing_local_file_is_optional(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    assert not config.load_environment()
