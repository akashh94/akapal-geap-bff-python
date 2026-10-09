"""Runnable checks for the non-trivial logic (no network, no SDK).

    python -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point the store at a throwaway DB before importing it.
os.environ["DATABASE_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.setdefault("SESSION_SECRET", "test-secret")

from app.events import StreamDeltaPlanner  # noqa: E402
from app.store import (  # noqa: E402
    get_active_thread,
    owns_thread,
    save_thread,
)


def plan(events):
    planner = StreamDeltaPlanner()
    deltas = []
    for event in events:
        deltas.extend(planner.process(event))
    return deltas


class StreamDeltaPlannerTests(unittest.TestCase):
    def test_forwards_partial_chunks_and_suppresses_the_final_repeat(self):
        deltas = plan(
            [
                {"author": "user", "content": {"parts": [{"text": "hi"}]}},
                {"author": "agent", "partial": True, "content": {"parts": [{"text": "Hel"}]}},
                {"author": "agent", "content": {"parts": [{"text": "Hello!"}]}},
            ]
        )
        self.assertEqual(deltas, ["Hel"])

    def test_non_streaming_turn_still_yields_its_text(self):
        deltas = plan(
            [{"author": "agent", "content": {"parts": [{"text": "Hello!"}]}}]
        )
        self.assertEqual(deltas, ["Hello!"])

    def test_blank_line_between_different_authors(self):
        deltas = plan(
            [
                {"author": "a", "content": {"parts": [{"text": "one"}]}},
                {"author": "b", "content": {"parts": [{"text": "two"}]}},
            ]
        )
        self.assertEqual(deltas, ["one", "\n\n", "two"])

    def test_joins_multiple_parts_in_one_event(self):
        deltas = plan(
            [
                {
                    "author": "a",
                    "content": {"parts": [{"text": "one "}, {"text": "two"}]},
                }
            ]
        )
        self.assertEqual(deltas, ["one two"])

    def test_ignores_non_dict_and_missing_parts(self):
        self.assertEqual(plan([None, {}, {"author": "a"}]), [])


class StoreTests(unittest.TestCase):
    def test_ownership_and_active_thread(self):
        save_thread("u1", "s1")
        self.assertTrue(owns_thread("u1", "s1"))
        self.assertFalse(owns_thread("u2", "s1"))
        self.assertEqual(get_active_thread("u1"), "s1")
        self.assertIsNone(get_active_thread("nobody"))

    def test_save_is_idempotent(self):
        save_thread("u3", "s9")
        save_thread("u3", "s9")
        self.assertEqual(get_active_thread("u3"), "s9")


if __name__ == "__main__":
    unittest.main()
