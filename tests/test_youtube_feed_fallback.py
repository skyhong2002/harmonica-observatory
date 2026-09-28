"""Offline checks of official Atom ingestion and the legacy extractor fallback."""

import datetime as dt
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import youtube_atom
import youtube_ytdlp_fetcher as fetcher


CHANNEL = "UC" + "a" * 22
NOW = dt.datetime(2026, 9, 28, 12, tzinfo=dt.timezone.utc)


def atom_feed(videos):
    entries = []
    for video_id, published in videos:
        entries.append(f"""<entry>
          <id>yt:video:{video_id}</id><yt:videoId>{video_id}</yt:videoId>
          <yt:channelId>{CHANNEL}</yt:channelId><title>A short blues lesson</title>
          <link rel="alternate" href="https://www.youtube.com/shorts/{video_id}"/>
          <published>{published}</published>
          <media:group><media:description>Practice this phrase.</media:description>
            <media:thumbnail url="https://i4.ytimg.com/vi/{video_id}/hqdefault.jpg"/>
          </media:group></entry>""")
    return f"""<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/">
      <yt:channelId>{CHANNEL}</yt:channelId><author><name>Official Artist</name></author>
      {''.join(entries)}</feed>""".encode()


class YoutubeFeedFallbackTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "id": "yt_artist",
            "name": "Artist in directory",
            "url": "https://www.youtube.com/@artist",
            "channel_id": CHANNEL,
            "limit": 5,
        }
        self.keys = set()
        self.options = {
            "base_cmd": ["yt-dlp"], "inbox_keys": self.keys, "max_age_days": 30,
            "timeout_secs": 90, "socket_timeout_secs": 20, "ytdlp_retries": 1,
            "extractor_retries": 1, "timeout_retries": 0, "retry_delay_secs": 0,
            "now": NOW,
        }
        self.legacy_info = {
            "id": "Legacy12345", "title": "Legacy performance", "description": "A concert.",
            "timestamp": (NOW - dt.timedelta(days=1)).timestamp(),
            "thumbnail": "https://i.ytimg.com/vi/Legacy12345/hqdefault.jpg",
            "webpage_url": "https://www.youtube.com/watch?v=Legacy12345",
            "channel": "Legacy Artist",
        }

    def feed_reader(self, payload):
        def read(channel_id, **kwargs):
            return youtube_atom.fetch_entries(
                channel_id, **kwargs, opener=lambda *args, **options: io.BytesIO(payload)
            )
        return read

    def test_atom_short_is_normalized_with_primary_publication_date_and_provenance(self):
        payload = atom_feed([("Short123456", "2026-09-27T23:45:12+05:30")])
        with patch.object(fetcher, "fetch_entries", side_effect=self.feed_reader(payload)) as atom, \
             patch.object(fetcher, "run_ytdlp") as legacy:
            rows = fetcher.fetch_source(self.source, **self.options)
        atom.assert_called_once_with(CHANNEL, timeout=15, limit=5)
        legacy.assert_not_called()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["post_id"], "Short123456")
        self.assertEqual(row["posted_at"], "2026-09-27T18:15:12+00:00")
        self.assertEqual(row["url"], "https://www.youtube.com/shorts/Short123456")
        self.assertEqual(row["text"], "A short blues lesson\nPractice this phrase.")
        self.assertEqual(row["raw_source"], "youtube-atom")
        self.assertEqual(row["source_name"], "Artist in directory")
        self.assertEqual(row["source_display_name"], "Official Artist")
        self.assertEqual(row["source_profile_url"], f"https://www.youtube.com/channel/{CHANNEL}")
        self.assertEqual(row["images"], ["https://i4.ytimg.com/vi/Short123456/hqdefault.jpg"])
        self.assertIn("yt_artist:Short123456", self.keys)

    def test_atom_dedup_age_filter_and_exact_age_boundary(self):
        self.keys.add("yt_artist:Known123456")
        payload = atom_feed([
            ("Known123456", (NOW - dt.timedelta(days=1)).isoformat()),
            ("Old12345678", (NOW - dt.timedelta(days=30, seconds=1)).isoformat()),
            ("Edge1234567", (NOW - dt.timedelta(days=30)).isoformat()),
            ("Fresh123456", NOW.isoformat()),
            ("Fresh123456", NOW.isoformat()),
        ])
        with patch.object(fetcher, "fetch_entries", side_effect=self.feed_reader(payload)), \
             patch.object(fetcher, "run_ytdlp") as legacy:
            first = fetcher.fetch_source(self.source, **self.options)
            second = fetcher.fetch_source(self.source, **self.options)
        legacy.assert_not_called()
        self.assertEqual([row["post_id"] for row in first], ["Edge1234567", "Fresh123456"])
        self.assertEqual(second, [])
        self.assertIn("yt_artist:Old12345678", self.keys)

    def test_zero_max_age_keeps_older_atom_publication(self):
        payload = atom_feed([("Old12345678", "2020-01-01T00:00:00Z")])
        with patch.object(fetcher, "fetch_entries", side_effect=self.feed_reader(payload)), \
             patch.object(fetcher, "run_ytdlp") as legacy:
            rows = fetcher.fetch_source(self.source, **dict(self.options, max_age_days=0))
        self.assertEqual(len(rows), 1)
        legacy.assert_not_called()

    def test_empty_valid_atom_feed_is_success_without_extractor_fallback(self):
        with patch.object(fetcher, "fetch_entries", side_effect=self.feed_reader(atom_feed([]))), \
             patch.object(fetcher, "run_ytdlp") as legacy:
            self.assertEqual(fetcher.fetch_source(self.source, **self.options), [])
        legacy.assert_not_called()
        self.assertEqual(self.keys, set())

    def test_unavailable_or_rejected_atom_feed_uses_legacy_extractor(self):
        for error in [OSError("Feed unavailable"), ValueError("Wrong feed channel")]:
            with self.subTest(error=type(error).__name__):
                self.keys.clear()
                with patch.object(fetcher, "fetch_entries", side_effect=error), \
                     patch.object(fetcher, "run_ytdlp", return_value=json.dumps(self.legacy_info)) as legacy:
                    rows = fetcher.fetch_source(self.source, **self.options)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["post_id"], "Legacy12345")
                self.assertEqual(rows[0]["raw_source"], "yt-dlp")
                self.assertEqual(legacy.call_count, 1)
                self.assertEqual(legacy.call_args.args[1][-1], "https://www.youtube.com/@artist/videos")
                self.assertIn("yt_artist:Legacy12345", self.keys)

    def test_source_without_verified_channel_id_uses_legacy_directly(self):
        source = {key: value for key, value in self.source.items() if key != "channel_id"}
        with patch.object(fetcher, "fetch_entries") as atom, \
             patch.object(fetcher, "run_ytdlp", return_value=json.dumps(self.legacy_info)) as legacy:
            rows = fetcher.fetch_source(source, **self.options)
        atom.assert_not_called()
        legacy.assert_called_once()
        self.assertEqual(rows[0]["raw_source"], "yt-dlp")


if __name__ == "__main__":
    unittest.main()
