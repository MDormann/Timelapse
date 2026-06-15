"""Tests for snapshot.py"""

import configparser
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

import snapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config(tmp_path: Path, extra: str = "") -> Path:
    """Write a minimal valid config.ini and return its path."""
    cfg_text = (
        "[camera]\n"
        "host = 192.168.1.100\n"
        "user = admin\n"
        "password = secret\n"
        "channel = 0\n"
        "timeout = 15\n"
        "\n"
        "[nas]\n"
        f"path = {tmp_path}\n"
        "filename_prefix = snapshot\n"
        + extra
    )
    cfg_file = tmp_path / "config.ini"
    cfg_file.write_text(cfg_text)
    return cfg_file


def make_mock_response(content: bytes = b"\xff\xd8\xff", content_type: str = "image/jpeg", status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.headers = {"Content-Type": content_type}
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_returns_configparser_when_file_exists(self, tmp_path, monkeypatch):
        cfg_file = make_config(tmp_path)
        monkeypatch.setattr(snapshot, "CONFIG_FILE", cfg_file)
        cfg = snapshot.load_config()
        assert isinstance(cfg, configparser.ConfigParser)
        assert cfg.get("camera", "host") == "192.168.1.100"

    def test_exits_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(snapshot, "CONFIG_FILE", tmp_path / "nonexistent.ini")
        with pytest.raises(SystemExit) as exc_info:
            snapshot.load_config()
        assert exc_info.value.code == 1

    def test_parses_all_sections(self, tmp_path, monkeypatch):
        cfg_file = make_config(tmp_path)
        monkeypatch.setattr(snapshot, "CONFIG_FILE", cfg_file)
        cfg = snapshot.load_config()
        assert cfg.has_section("camera")
        assert cfg.has_section("nas")

    def test_parses_optional_fields_with_fallback(self, tmp_path, monkeypatch):
        # channel and timeout are optional (have fallbacks in main)
        cfg_text = (
            "[camera]\n"
            "host = cam\n"
            "user = u\n"
            "password = p\n"
            "\n"
            "[nas]\n"
            f"path = {tmp_path}\n"
        )
        cfg_file = tmp_path / "config.ini"
        cfg_file.write_text(cfg_text)
        monkeypatch.setattr(snapshot, "CONFIG_FILE", cfg_file)
        cfg = snapshot.load_config()
        assert cfg.getint("camera", "channel", fallback=0) == 0
        assert cfg.getint("camera", "timeout", fallback=15) == 15


# ---------------------------------------------------------------------------
# random_rs
# ---------------------------------------------------------------------------

class TestRandomRs:
    def test_default_length_is_16(self):
        result = snapshot.random_rs()
        assert len(result) == 16

    def test_custom_length(self):
        assert len(snapshot.random_rs(8)) == 8
        assert len(snapshot.random_rs(32)) == 32

    def test_only_lowercase_alphanumeric(self):
        for _ in range(20):
            result = snapshot.random_rs()
            assert result.isalnum()
            assert result == result.lower()

    def test_two_calls_are_different(self):
        # With 36^16 possibilities, collision probability is negligible
        assert snapshot.random_rs() != snapshot.random_rs()


# ---------------------------------------------------------------------------
# fetch_snapshot
# ---------------------------------------------------------------------------

class TestFetchSnapshot:
    def test_returns_bytes_on_success(self):
        fake_data = b"\xff\xd8\xff" + b"\x00" * 100
        mock_resp = make_mock_response(content=fake_data)
        with patch("snapshot.requests.get", return_value=mock_resp) as mock_get:
            result = snapshot.fetch_snapshot("192.168.1.1", "admin", "pass", 0, 10)
        assert result == fake_data
        mock_get.assert_called_once()

    def test_url_contains_host_and_credentials(self):
        mock_resp = make_mock_response()
        with patch("snapshot.requests.get", return_value=mock_resp) as mock_get:
            snapshot.fetch_snapshot("cam.local", "myuser", "mypass", 2, 5)
        url = mock_get.call_args[0][0]
        assert "cam.local" in url
        assert "user=myuser" in url
        assert "password=mypass" in url
        assert "channel=2" in url

    def test_url_contains_random_rs_param(self):
        mock_resp = make_mock_response()
        with patch("snapshot.requests.get", return_value=mock_resp) as mock_get:
            snapshot.fetch_snapshot("cam.local", "admin", "pass", 0, 5)
        url = mock_get.call_args[0][0]
        assert "rs=" in url

    def test_raises_on_http_error(self):
        mock_resp = make_mock_response(status_code=401)
        mock_resp.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")
        with patch("snapshot.requests.get", return_value=mock_resp):
            with pytest.raises(requests.HTTPError):
                snapshot.fetch_snapshot("cam.local", "admin", "wrong", 0, 5)

    def test_raises_value_error_on_non_image_content_type(self):
        # Camera returns HTML login page when credentials are wrong
        mock_resp = make_mock_response(content_type="text/html; charset=utf-8")
        with patch("snapshot.requests.get", return_value=mock_resp):
            with pytest.raises(ValueError, match="Content-Type"):
                snapshot.fetch_snapshot("cam.local", "admin", "badpass", 0, 5)

    def test_raises_on_timeout(self):
        with patch("snapshot.requests.get", side_effect=requests.exceptions.Timeout):
            with pytest.raises(requests.exceptions.Timeout):
                snapshot.fetch_snapshot("cam.local", "admin", "pass", 0, 1)

    def test_raises_on_connection_error(self):
        with patch("snapshot.requests.get", side_effect=requests.exceptions.ConnectionError):
            with pytest.raises(requests.exceptions.ConnectionError):
                snapshot.fetch_snapshot("unreachable", "admin", "pass", 0, 5)

    def test_timeout_is_forwarded_to_requests(self):
        mock_resp = make_mock_response()
        with patch("snapshot.requests.get", return_value=mock_resp) as mock_get:
            snapshot.fetch_snapshot("cam.local", "admin", "pass", 0, 30)
        assert mock_get.call_args[1]["timeout"] == 30

    def test_stream_mode_is_enabled(self):
        mock_resp = make_mock_response()
        with patch("snapshot.requests.get", return_value=mock_resp) as mock_get:
            snapshot.fetch_snapshot("cam.local", "admin", "pass", 0, 5)
        assert mock_get.call_args[1]["stream"] is True

    def test_accepts_image_jpeg_content_type(self):
        mock_resp = make_mock_response(content_type="image/jpeg")
        with patch("snapshot.requests.get", return_value=mock_resp):
            result = snapshot.fetch_snapshot("cam.local", "admin", "pass", 0, 5)
        assert result == mock_resp.content

    def test_accepts_image_png_content_type(self):
        mock_resp = make_mock_response(content_type="image/png")
        with patch("snapshot.requests.get", return_value=mock_resp):
            result = snapshot.fetch_snapshot("cam.local", "admin", "pass", 0, 5)
        assert result == mock_resp.content


# ---------------------------------------------------------------------------
# save_snapshot
# ---------------------------------------------------------------------------

class TestSaveSnapshot:
    def test_creates_daily_subdirectory(self, tmp_path):
        data = b"\xff\xd8\xff"
        snapshot.save_snapshot(data, tmp_path, "snap")
        subdirs = list(tmp_path.iterdir())
        assert len(subdirs) == 1
        assert subdirs[0].is_dir()

    def test_daily_dir_name_is_todays_date(self, tmp_path):
        from datetime import datetime
        data = b"\xff\xd8\xff"
        snapshot.save_snapshot(data, tmp_path, "snap")
        today = datetime.now().strftime("%Y-%m-%d")
        assert (tmp_path / today).is_dir()

    def test_written_file_contains_correct_data(self, tmp_path):
        data = b"\xff\xd8\xff" + b"\xab\xcd" * 50
        dest = snapshot.save_snapshot(data, tmp_path, "snap")
        assert dest.read_bytes() == data

    def test_filename_contains_prefix(self, tmp_path):
        dest = snapshot.save_snapshot(b"\x00", tmp_path, "mycam")
        assert dest.name.startswith("mycam_")

    def test_filename_ends_with_jpg(self, tmp_path):
        dest = snapshot.save_snapshot(b"\x00", tmp_path, "snap")
        assert dest.suffix == ".jpg"

    def test_filename_contains_timestamp(self, tmp_path):
        from datetime import datetime
        dest = snapshot.save_snapshot(b"\x00", tmp_path, "snap")
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in dest.name

    def test_returns_path_to_written_file(self, tmp_path):
        data = b"\xff\xd8\xff"
        dest = snapshot.save_snapshot(data, tmp_path, "snap")
        assert isinstance(dest, Path)
        assert dest.exists()

    def test_works_when_directory_already_exists(self, tmp_path):
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        (tmp_path / today).mkdir()
        # Should not raise even though the dir is already there
        dest = snapshot.save_snapshot(b"\x00", tmp_path, "snap")
        assert dest.exists()

    def test_creates_nested_directories(self, tmp_path):
        # nas_path itself may have subdirs that don't exist yet
        deep_path = tmp_path / "a" / "b"
        deep_path.mkdir(parents=True)
        dest = snapshot.save_snapshot(b"\x00", deep_path, "snap")
        assert dest.exists()


# ---------------------------------------------------------------------------
# main (integration)
# ---------------------------------------------------------------------------

class TestMain:
    def test_exits_when_nas_path_missing(self, tmp_path, monkeypatch):
        cfg_file = make_config(tmp_path)
        monkeypatch.setattr(snapshot, "CONFIG_FILE", cfg_file)
        # Point NAS path to a location that doesn't exist
        non_existent = tmp_path / "does_not_exist"
        with patch("snapshot.Path") as mock_path_cls:
            # Make the nas path.exists() return False
            mock_nas = MagicMock()
            mock_nas.exists.return_value = False
            mock_path_cls.return_value = mock_nas
            with pytest.raises(SystemExit) as exc_info:
                snapshot.main()
        assert exc_info.value.code == 1

    def test_happy_path_calls_fetch_and_save(self, tmp_path, monkeypatch):
        cfg_file = make_config(tmp_path)
        monkeypatch.setattr(snapshot, "CONFIG_FILE", cfg_file)

        fake_data = b"\xff\xd8\xff"
        with (
            patch("snapshot.fetch_snapshot", return_value=fake_data) as mock_fetch,
            patch("snapshot.save_snapshot") as mock_save,
        ):
            snapshot.main()

        mock_fetch.assert_called_once_with("192.168.1.100", "admin", "secret", 0, 15)
        mock_save.assert_called_once()
        save_args = mock_save.call_args[0]
        assert save_args[0] == fake_data
        assert save_args[2] == "snapshot"

    def test_happy_path_uses_config_defaults(self, tmp_path, monkeypatch):
        # Config without channel/timeout/filename_prefix to exercise fallbacks
        cfg_text = (
            "[camera]\n"
            "host = cam\n"
            "user = u\n"
            "password = p\n"
            "\n"
            "[nas]\n"
            f"path = {tmp_path}\n"
        )
        cfg_file = tmp_path / "config.ini"
        cfg_file.write_text(cfg_text)
        monkeypatch.setattr(snapshot, "CONFIG_FILE", cfg_file)

        with (
            patch("snapshot.fetch_snapshot", return_value=b"\x00") as mock_fetch,
            patch("snapshot.save_snapshot"),
        ):
            snapshot.main()

        _, _, _, channel, timeout = mock_fetch.call_args[0]
        assert channel == 0
        assert timeout == 15

    def test_fetch_exception_propagates(self, tmp_path, monkeypatch):
        cfg_file = make_config(tmp_path)
        monkeypatch.setattr(snapshot, "CONFIG_FILE", cfg_file)

        with patch("snapshot.fetch_snapshot", side_effect=requests.exceptions.ConnectionError("unreachable")):
            with pytest.raises(requests.exceptions.ConnectionError):
                snapshot.main()
