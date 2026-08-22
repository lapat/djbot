#!/usr/bin/env python3
"""
Tests for curate.py's find_youtube_id — no network calls, subprocess mocked.

Run:  python -m pytest tests/ -v
"""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import patch

from mixer.curate import find_youtube_id


def _fake_result(stdout: str):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_returns_first_id_on_success():
    with patch("subprocess.run", return_value=_fake_result("abc123XYZ90\n")):
        assert find_youtube_id("Some Artist", "Some Title") == "abc123XYZ90"


def test_returns_none_on_empty_output():
    with patch("subprocess.run", return_value=_fake_result("")):
        assert find_youtube_id("Some Artist", "Some Title") is None


def test_returns_none_on_timeout_instead_of_raising():
    # A hung/slow search for one track must not crash the whole curation
    # step — the caller already treats None as "skip this one" for the
    # normal not-found case (see mixer/curate.py's find_youtube_id docstring).
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="yt-dlp", timeout=20)):
        assert find_youtube_id("Some Artist", "Some Title") is None


def test_returns_none_on_os_error_instead_of_raising():
    with patch("subprocess.run", side_effect=OSError("yt-dlp not found")):
        assert find_youtube_id("Some Artist", "Some Title") is None
