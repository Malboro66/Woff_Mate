"""Regression tests for platform-specific journal editor behavior."""

from unittest.mock import patch

import pytest

import woff_editor


def test_open_editor_rejects_missing_windows_startfile():
    with (
        patch.object(woff_editor.platform, "system", return_value="Windows"),
        patch.object(woff_editor.os, "startfile", None, create=True),
        pytest.raises(RuntimeError, match="os.startfile não está disponível"),
    ):
        woff_editor.open_editor("journal.txt")
