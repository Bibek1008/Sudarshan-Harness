"""Actual POSIX descriptor and group behavior; Windows is a legitimate skip."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from sudarshan.execution.filesystem import WorkspaceFiles
from sudarshan.execution.base import ExecutionPermissionError
from tests.test_harness_security import WorkspaceCase


@unittest.skipIf(os.name == "nt", "LIVE POSIX descriptor tests require a POSIX OS")
class PosixDescriptorTests(WorkspaceCase):
    def test_directory_relative_open_survives_path_swap_without_following_link(self):
        files = WorkspaceFiles(self.root)
        files.write_text("nested/file.txt", "original")
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "file.txt").write_text("outside", encoding="utf-8")
        original = os.open
        swapped = False
        def race(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "file.txt" and kwargs.get("dir_fd") is not None and not swapped:
                (self.root / "nested").rename(self.root / "held")
                (self.root / "nested").symlink_to(outside, target_is_directory=True)
                swapped = True
            return original(path, flags, *args, **kwargs)
        # Wrap a real syscall; all descriptor opens and symlink operations are real.
        with patch("os.open", side_effect=race):
            # Preserve the capability check while wrapping the supported syscall.
            with patch.object(os, "supports_dir_fd", os.supports_dir_fd | {os.open}):
                self.assertEqual(files.read_text("nested/file.txt"), "original")
        self.assertTrue(swapped)
        self.assertEqual((outside / "file.txt").read_text(encoding="utf-8"), "outside")
        with self.assertRaises(ExecutionPermissionError):
            files.write_text("nested/file.txt", "blocked")

    def test_fifo_is_rejected_without_blocking(self):
        os.mkfifo(self.root / "pipe")
        with self.assertRaises(ExecutionPermissionError):
            WorkspaceFiles(self.root).read_text("pipe")

    def test_created_file_permissions_and_parent_operations(self):
        files = WorkspaceFiles(self.root)
        files.write_text("unicode/café.txt", "नमस्ते")
        self.assertEqual(files.read_text("unicode/café.txt"), "नमस्ते")
        self.assertEqual((self.root / "unicode/café.txt").stat().st_mode & 0o777, 0o600)
