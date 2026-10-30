"""save_espn --parts: gzip+base64 chunks read from the tab are joined and every hash is checked."""
import base64
import gzip
import hashlib
import json
import pathlib
import tempfile
import unittest

from shq.save_espn import join_parts


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class Parts(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.text = json.dumps([{"sport": "nfl", "league_id": 1, "name": "Café ✓", "roster": list(range(500))}])
        b64 = base64.b64encode(gzip.compress(self.text.encode("utf-8"))).decode()
        self.chunks = [b64[i:i + 1000] for i in range(0, len(b64), 1000)]
        for k, c in enumerate(self.chunks):
            # the page wraps each chunk at 100 chars per line; get_page_text keeps the line breaks
            (self.dir / f"espn_part{k}.txt").write_text("\n".join(c[i:i + 100] for i in range(0, len(c), 100)) + "\n",
                                                       encoding="utf-8")

    def test_round_trip(self):
        out = join_parts(sha(self.text), [sha(c) for c in self.chunks], self.dir)
        self.assertEqual(out.read_text(encoding="utf-8"), self.text)

    def test_bad_chunk(self):
        bad = [sha(c) for c in self.chunks]
        bad[0] = "0" * 64
        with self.assertRaisesRegex(ValueError, "chunk 0"):
            join_parts(sha(self.text), bad, self.dir)

    def test_bad_full(self):
        with self.assertRaisesRegex(ValueError, "full snapshot"):
            join_parts("0" * 64, [sha(c) for c in self.chunks], self.dir)


if __name__ == "__main__":
    unittest.main()
