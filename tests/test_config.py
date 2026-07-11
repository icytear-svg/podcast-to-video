import unittest

from scripts.loop_background_video import parse_corrections as parse_loop_corrections
from scripts.podcast_video import bounded_segment, parse_corrections as parse_classic_corrections


class CorrectionsTests(unittest.TestCase):
    def test_both_renderers_accept_documented_list_format(self):
        value = ["杨航=羊行", "博客=播客"]
        expected = {"杨航": "羊行", "博客": "播客"}
        self.assertEqual(parse_classic_corrections(value), expected)
        self.assertEqual(parse_loop_corrections(value), expected)

    def test_both_renderers_accept_object_format(self):
        value = {"杨航": "羊行"}
        self.assertEqual(parse_classic_corrections(value), value)
        self.assertEqual(parse_loop_corrections(value), value)

    def test_invalid_format_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_classic_corrections("杨航=羊行")
        with self.assertRaises(ValueError):
            parse_loop_corrections([1, 2])


class SegmentTests(unittest.TestCase):
    def test_sample_is_clamped_to_short_audio(self):
        self.assertEqual(bounded_segment(2.0, "sample", None, None), (0.0, 2.0))

    def test_full_duration_accounts_for_start_offset(self):
        self.assertEqual(bounded_segment(100.0, "full", 25.0, None), (25.0, 75.0))

    def test_explicit_duration_is_clamped(self):
        self.assertEqual(bounded_segment(10.0, "sample", 8.0, 20.0), (8.0, 2.0))

    def test_out_of_range_segment_is_rejected(self):
        with self.assertRaises(ValueError):
            bounded_segment(10.0, "full", 10.0, None)
        with self.assertRaises(ValueError):
            bounded_segment(10.0, "sample", 0.0, 0.0)


if __name__ == "__main__":
    unittest.main()
