import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_status_page  # noqa: E402


class PersistentSourceErrorTests(unittest.TestCase):
    def setUp(self):
        self.source_by_id = {
            "threads_example": {"id": "threads_example", "type": "rss", "platform": "threads"},
            "x_example": {"id": "x_example", "type": "rss", "platform": "x"},
        }

    def state(self, error):
        return {
            "sources": {
                source_id: {
                    "source_type": "rss",
                    "consecutive_errors": 4,
                    "last_error": error,
                    "last_error_at": "2026-10-16T06:00:00+00:00",
                }
                for source_id in self.source_by_id
            }
        }

    def test_backed_off_threads_upstream_outage_stays_hidden(self):
        rows = build_status_page.persistent_source_errors(
            self.state("RSSHub HTTP 503: Error: Failed to fetch thread data"), self.source_by_id, []
        )
        self.assertEqual([row["source_id"] for row in rows], ["x_example"])

    def test_backed_off_feed_with_other_errors_is_reported(self):
        rows = build_status_page.persistent_source_errors(self.state("HTTP 500"), self.source_by_id, [])
        self.assertEqual(sorted(row["source_id"] for row in rows), ["threads_example", "x_example"])
        self.assertTrue(all(row["error"].startswith("連續失敗 4 次") for row in rows))


if __name__ == "__main__":
    unittest.main()
