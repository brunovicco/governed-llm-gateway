import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class DocumentTests(unittest.TestCase):
    def test_required_adrs_are_accepted(self) -> None:
        for number in range(1, 6):
            matches = list((ROOT / "docs/adr").glob(f"ADR-{number:04d}-*.md"))
            self.assertEqual(len(matches), 1)
            self.assertIn("Status: Accepted", matches[0].read_text(encoding="utf-8"))

    def test_source_roadmap_is_preserved(self) -> None:
        source = ROOT / "docs/project/SOURCE_ROADMAP.txt"
        text = source.read_text(encoding="utf-8")
        self.assertIn("Governed LLM Gateway — Project Plan", text)
        self.assertIn("Phase 0 — Architecture Gate", text)


if __name__ == "__main__":
    unittest.main()
