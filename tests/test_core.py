import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import remote  # noqa: E402
import volumes  # noqa: E402


class VolumesTest(unittest.TestCase):
    def test_archive_name(self):
        self.assertEqual(volumes.archive_name("a.b", datetime(2026, 11, 23, 9, 5, 7)),
                         "a.b_20261123-090507.tar.gz")

    def test_sha256(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"abc")
        self.assertEqual(volumes.sha256_file(f.name),
                         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        os.remove(f.name)


class RestoreStepsTest(unittest.TestCase):
    def test_node_refuses_first_and_quotes(self):
        steps = remote.restore_steps("node", "a b", "/tmp/x.tar.gz")
        self.assertEqual(steps[0][0], "! docker volume inspect 'a b' >/dev/null 2>&1")
        self.assertIn("-v 'a b':/v -v /tmp:/a:ro alpine tar xzf /a/x.tar.gz -C /v", steps[2][0])

    def test_shared_refuses_non_empty_first(self):
        steps = remote.restore_steps("shared", "db", "/tmp/x.tar.gz", "/mnt/nfs/")
        self.assertEqual(steps[0][0], '[ -z "$(ls -A /mnt/nfs/db 2>/dev/null)" ]')
        self.assertEqual(steps[2][0], "tar xzf /tmp/x.tar.gz -C /mnt/nfs/db")

    def test_shared_needs_folder(self):
        with self.assertRaises(ValueError):
            remote.restore_steps("shared", "db", "/tmp/x.tar.gz", "")

    def test_injection_is_quoted(self):
        steps = remote.restore_steps("shared", "x;rm -rf /", "/tmp/x.tar.gz", "/mnt")
        self.assertIn("'/mnt/x;rm -rf /'", steps[1][0])


if __name__ == "__main__":
    unittest.main()
