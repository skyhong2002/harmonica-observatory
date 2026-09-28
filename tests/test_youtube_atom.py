import datetime as dt
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from youtube_atom import MAX_FEED_BYTES, fetch_entries


CHANNEL = "UC" + "a" * 22
OTHER_CHANNEL = "UC" + "b" * 22
VIDEO = "Abc123_-xyz"
SECOND_VIDEO = "Def456_-uvw"
FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL}"


def entry(video_id=VIDEO, **overrides):
    fields = {
        "channel": CHANNEL,
        "published": "2026-09-27T23:45:12+05:30",
        "link": f"https://www.youtube.com/shorts/{video_id}",
        "title": "Blues &amp; bending",
        "atom_id": f"yt:video:{video_id}",
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    }
    fields.update(overrides)
    return f"""<entry>
      <id>{fields['atom_id']}</id><yt:videoId>{video_id}</yt:videoId>
      <yt:channelId>{fields['channel']}</yt:channelId>
      <title>{fields['title']}</title>
      <link rel="alternate" href="{fields['link']}"/>
      <published>{fields['published']}</published><updated>2026-09-28T12:00:00Z</updated>
      <media:group><media:description>A short lesson &amp; demonstration.</media:description>
      <media:thumbnail url="{fields['thumbnail']}"/></media:group>
    </entry>"""


def feed(entries="", channel=CHANNEL):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/">
      <yt:channelId>{channel}</yt:channelId><author><name>Official Artist</name></author>
      {entries}</feed>""".encode()


class YoutubeAtomTests(unittest.TestCase):
    def fetch(self, payload, **kwargs):
        self.requests = []

        def opener(request, timeout):
            self.requests.append((request.full_url, timeout))
            return io.BytesIO(payload)

        return fetch_entries(CHANNEL, opener=opener, **kwargs)

    def test_short_metadata_preserves_exact_publication_time(self):
        rows = self.fetch(feed(entry()), timeout=4)
        self.assertEqual(self.requests, [(FEED_URL, 4)])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["id"], VIDEO)
        self.assertEqual(row["title"], "Blues & bending")
        self.assertEqual(row["description"], "A short lesson & demonstration.")
        self.assertEqual(row["webpage_url"], f"https://www.youtube.com/shorts/{VIDEO}")
        expected = dt.datetime(2026, 9, 27, 18, 15, 12, tzinfo=dt.timezone.utc).timestamp()
        self.assertEqual(row["timestamp"], expected)
        self.assertEqual(row["channel"], "Official Artist")
        self.assertEqual(row["channel_id"], CHANNEL)
        self.assertEqual(row["channel_url"], f"https://www.youtube.com/channel/{CHANNEL}")
        self.assertEqual(row["thumbnail"], f"https://i.ytimg.com/vi/{VIDEO}/hqdefault.jpg")

    def test_watch_urls_fractional_seconds_dedup_and_valid_entry_limit(self):
        first = entry(published="", title="No publication date")
        second = entry(published="2026-09-28T01:02:03.125Z", link=f"https://www.youtube.com/watch?v={VIDEO}")
        rows = self.fetch(feed(first + second + second + entry(SECOND_VIDEO)), limit=2)
        self.assertEqual([row["id"] for row in rows], [VIDEO, SECOND_VIDEO])
        self.assertEqual(rows[0]["timestamp"] % 1, 0.125)
        self.assertEqual(len(self.fetch(feed(second + entry(SECOND_VIDEO)), limit=1)), 1)

    def test_live_feed_channel_suffix_requires_matching_author_uri(self):
        payload = feed(entry(thumbnail=f"https://i4.ytimg.com/vi/{VIDEO}/hqdefault.jpg"), channel=CHANNEL[2:])
        with self.assertRaises(ValueError):
            self.fetch(payload)
        payload = payload.replace(b"</author>", f"<uri>https://www.youtube.com/channel/{CHANNEL}</uri></author>".encode())
        rows = self.fetch(payload)
        self.assertEqual(rows[0]["channel_id"], CHANNEL)
        self.assertEqual(rows[0]["thumbnail"], f"https://i4.ytimg.com/vi/{VIDEO}/hqdefault.jpg")
        with self.assertRaises(ValueError):
            self.fetch(payload.replace(f"/channel/{CHANNEL}".encode(), f"/channel/{OTHER_CHANNEL}".encode()))

    def test_foreign_missing_or_malformed_feed_rejected(self):
        for payload in [feed(channel=OTHER_CHANNEL), feed(channel=""), b"<feed", b"<html/>",
                        b'<!DOCTYPE feed [<!ENTITY x "value">]><feed/>']:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.fetch(payload)

    def test_invalid_individual_entries_are_skipped_without_date_guessing(self):
        invalid = [
            {"channel": OTHER_CHANNEL}, {"channel": ""}, {"published": ""},
            {"published": "2026-09-27"}, {"published": "2026-09-27T01:02:03"},
            {"published": "2026-02-30T01:02:03Z"}, {"title": " "},
            {"published": "2026-09-27T01:02:03+05:60"},
            {"link": f"https://example.org/watch?v={VIDEO}"},
            {"link": f"https://www.youtube.com/watch?v={SECOND_VIDEO}"},
            {"link": f"https://www.youtube.com.evil.example/shorts/{VIDEO}"},
            {"atom_id": f"yt:video:{SECOND_VIDEO}"},
        ]
        for fields in invalid:
            with self.subTest(fields=fields):
                self.assertEqual(self.fetch(feed(entry(**fields))), [])
        self.assertEqual(self.fetch(feed(entry("bad-video-id"))), [])
        self.assertEqual(self.fetch(feed(entry().replace("<published>", "<ignored>").replace("</published>", "</ignored>"))), [])

    def test_untrusted_optional_thumbnail_is_not_returned(self):
        rows = self.fetch(feed(entry(thumbnail="https://example.org/image.jpg")))
        self.assertEqual(rows[0]["thumbnail"], "")

    def test_empty_feed_and_zero_limit(self):
        self.assertEqual(self.fetch(feed()), [])
        self.assertEqual(self.fetch(b"not fetched", limit=0), [])
        self.assertEqual(self.requests, [])

    def test_invalid_channel_and_limit_never_make_request(self):
        def unexpected(*args, **kwargs):
            self.fail("Invalid parameters must not cause a request")

        for channel in ["@artist", "UCshort", "UC" + "a" * 23, CHANNEL + "\n", None]:
            with self.subTest(channel=channel), self.assertRaises(ValueError):
                fetch_entries(channel, opener=unexpected)
        for limit in [-1, 1.5, True]:
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                fetch_entries(CHANNEL, limit=limit, opener=unexpected)

    def test_size_cap_rejects_oversized_payload(self):
        class CappedResponse(io.BytesIO):
            def read(inner, size=-1):
                self.assertEqual(size, MAX_FEED_BYTES + 1)
                return super().read(size)

        with self.assertRaises(ValueError):
            fetch_entries(CHANNEL, opener=lambda *args, **kwargs: CappedResponse(b" " * (MAX_FEED_BYTES + 2)))

    def test_redirected_response_and_transport_failures_are_not_silently_accepted(self):
        class RedirectedResponse(io.BytesIO):
            def geturl(self):
                return "https://example.org/feed.xml"

        with self.assertRaises(ValueError):
            fetch_entries(CHANNEL, opener=lambda *args, **kwargs: RedirectedResponse(feed()))

        def unavailable(*args, **kwargs):
            raise TimeoutError("Timed out")

        with self.assertRaises(TimeoutError):
            fetch_entries(CHANNEL, opener=unavailable)


if __name__ == "__main__":
    unittest.main()
