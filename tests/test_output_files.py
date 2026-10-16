import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from output_files import write_text_if_changed


class OutputFilesTests(unittest.TestCase):
    def test_create_skip_and_change_exact_bytes(self):
        for atomic in (False, True):
            with self.subTest(atomic=atomic), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "output.txt"
                temp = path.with_suffix(".tmp")
                kwargs = {"temp_path": temp} if atomic else {}
                self.assertTrue(write_text_if_changed(path, "口琴\r\n", **kwargs))
                os.utime(path, ns=(1000000000, 1000000000))
                before = path.stat()
                self.assertFalse(write_text_if_changed(path, "口琴\r\n", **kwargs))
                self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)
                self.assertEqual(path.stat().st_ino, before.st_ino)
                self.assertFalse(temp.exists())
                self.assertTrue(write_text_if_changed(path, "口琴\n", **kwargs))
                self.assertEqual(path.read_bytes(), "口琴\n".encode())
                if atomic:
                    self.assertNotEqual(path.stat().st_ino, before.st_ino)

    def test_read_errors_are_not_silenced(self):
        with mock.patch.object(Path, "read_bytes", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                write_text_if_changed(Path("output"), "text")
