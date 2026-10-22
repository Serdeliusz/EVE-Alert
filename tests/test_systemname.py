"""Reading the system name (F3 region) and matching it with the settings."""

import glob
import unittest
from unittest import mock

import numpy as np

from evealert.tools.systemname import (
    SystemNameReader,
    extract_system_name,
    find_matching_name,
    normalize,
    parse_names,
)


class ParseNamesTests(unittest.TestCase):
    def test_single_and_multiple_names(self):
        self.assertEqual(parse_names("Jita"), ["Jita"])
        self.assertEqual(
            parse_names(" Jita, Perimeter ;1DQ1-A,"), ["Jita", "Perimeter", "1DQ1-A"]
        )
        self.assertEqual(parse_names("Jita, Jita"), ["Jita"])

    def test_empty(self):
        self.assertEqual(parse_names(""), [])
        self.assertEqual(parse_names(None), [])
        self.assertEqual(parse_names(" , ;"), [])


class NormalizeTests(unittest.TestCase):
    def test_confusable_characters(self):
        # OCR reads "1DQ1-A" as "1D01-A" and "O-IOAI" as "0-1OAI"
        self.assertEqual(normalize("1DQ1-A"), normalize("1D01-A"))
        self.assertEqual(normalize("O-IOAI"), normalize("0-1OAI"))
        self.assertEqual(normalize("jita"), normalize("JITA"))

    def test_punctuation_and_spaces(self):
        self.assertEqual(
            normalize("  Jita   1.0 <  Kimotoro "), normalize("Jita 1 0 Kimotoro")
        )


class MatchingTests(unittest.TestCase):
    NAMES = ["Jita", "1DQ1-A", "O-IOAI", "J123456"]

    def check(self, text, expected):
        self.assertEqual(find_matching_name(text, self.NAMES), expected, text)

    def test_matches_location_panel_text(self):
        self.check("Jita 1.0 < Kimotoro < The Forge", "Jita")
        self.check("Jita 1. 0 < Kimotoro", "Jita")
        self.check("1DQ1-A -1.0 < 8-TFDX < Delve", "1DQ1-A")
        self.check("J123456", "J123456")

    def test_matches_ocr_mistakes(self):
        self.check("1D01-A -1.0", "1DQ1-A")
        self.check("0-1OAI 0.0", "O-IOAI")
        # Space before the security status lost
        self.check("Jita1.0 < Kimotoro", "Jita")
        self.check("1DQ1-A-1.0 < 8-TFDX", "1DQ1-A")
        self.check("O-IOAI0.0", "O-IOAI")

    def test_other_systems_do_not_match(self):
        # A wrong match would silence real alarms
        self.check("Jitanen 0.4 < Kimotoro", None)
        self.check("Perimeter 1.0 < Kimotoro", None)
        self.check("1DQ1-B -0.4 < 8-TFDX", None)
        self.check("J1234567", None)
        self.check("XJita 0.5", None)
        self.check("", None)
        self.check(None, None)

    def test_no_names_never_match(self):
        self.assertIsNone(find_matching_name("Jita 1.0", []))
        self.assertIsNone(find_matching_name("Jita 1.0", ["", " "]))


class ExtractNameTests(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(extract_system_name("Jita 1.0 < Kimotoro < The Forge"), "Jita")
        self.assertEqual(extract_system_name("Jita 1. 0 <Kimotoro"), "Jita")
        self.assertEqual(extract_system_name("1DQ1-A -1.0 < 8-TFDX < Delve"), "1DQ1-A")
        self.assertEqual(extract_system_name("1DQ1-A-1.0 < 8-TFDX"), "1DQ1-A")
        self.assertEqual(
            extract_system_name("New Caldari 1.0 < Okkelen"), "New Caldari"
        )
        self.assertEqual(extract_system_name("J123456"), "J123456")
        self.assertEqual(extract_system_name(""), "")
        self.assertEqual(extract_system_name(None), "")


class FakeEngine:
    """Stands in for RapidOCR."""

    def __init__(self, lines):
        self.lines = lines
        self.calls = 0

    def __call__(self, image):
        self.calls += 1
        result = [
            [[[0, top], [10, top], [10, top + 5], [0, top + 5]], text, 0.9]
            for top, text in self.lines
        ]
        return result, None


class ReaderTests(unittest.TestCase):
    def make_reader(self, lines):
        reader = SystemNameReader()
        reader._engine = FakeEngine(lines)
        return reader

    def test_lines_are_joined_top_to_bottom(self):
        reader = self.make_reader([(20, "Kimotoro"), (2, "Jita 1.0 <")])
        image = np.zeros((40, 100, 3), dtype=np.uint8)
        self.assertEqual(reader.read(image), "Jita 1.0 < Kimotoro")

    def test_unchanged_image_is_not_read_again(self):
        reader = self.make_reader([(0, "Jita 1.0")])
        image = np.zeros((20, 100, 3), dtype=np.uint8)
        reader.read(image)
        reader.read(image.copy())
        self.assertEqual(reader._engine.calls, 1)
        changed = image.copy()
        changed[:, :50] = 255
        reader.read(changed)
        self.assertEqual(reader._engine.calls, 2)
        reader.read(changed, use_cache=False)
        self.assertEqual(reader._engine.calls, 3)

    def test_empty_image(self):
        reader = self.make_reader([])
        self.assertIsNone(reader.read(None))
        self.assertEqual(reader.read(np.zeros((20, 100, 3), dtype=np.uint8)), "")

    def test_engine_errors_return_none(self):
        reader = SystemNameReader()
        reader._engine = mock.Mock(side_effect=RuntimeError("boom"))
        self.assertIsNone(reader.read(np.zeros((20, 100, 3), dtype=np.uint8)))

    def test_missing_engine_is_reported(self):
        reader = SystemNameReader()
        with mock.patch.dict("sys.modules", {"rapidocr_onnxruntime": None}):
            self.assertFalse(reader.preload())
            self.assertIsNone(reader.read(np.zeros((20, 100, 3), dtype=np.uint8)))
        self.assertTrue(reader.error)


def _real_ocr_available():
    try:
        import rapidocr_onnxruntime  # pylint: disable=import-outside-toplevel,unused-import
    except Exception:  # pylint: disable=broad-exception-caught
        return False
    return bool(
        glob.glob("/usr/share/fonts/**/LiberationSans-Regular.ttf", recursive=True)
    )


@unittest.skipUnless(_real_ocr_available(), "RapidOCR or test font not installed")
class RealOcrTests(unittest.TestCase):
    """Reads rendered location panel text with the real OCR models."""

    @classmethod
    def setUpClass(cls):
        cls.reader = SystemNameReader()
        cls.font = glob.glob(
            "/usr/share/fonts/**/LiberationSans-Regular.ttf", recursive=True
        )[0]

    def render(self, text, size=13):
        # pylint: disable=import-outside-toplevel
        from PIL import Image, ImageDraw, ImageFont

        image = Image.new("RGB", (250, size + 8), (18, 20, 24))
        ImageDraw.Draw(image).text(
            (3, 2), text, fill=(205, 205, 205), font=ImageFont.truetype(self.font, size)
        )
        return np.array(image)[:, :, ::-1].copy()

    def test_reads_and_matches(self):
        names = ["Jita", "1DQ1-A"]
        for text, expected in [
            ("Jita 1.0 < Kimotoro < The Forge", "Jita"),
            ("1DQ1-A -1.0 < 8-TFDX < Delve", "1DQ1-A"),
            ("Jitanen 0.4 < Kimotoro", None),
        ]:
            for size in (11, 13, 16):
                read = self.reader.read(self.render(text, size), use_cache=False)
                self.assertEqual(
                    find_matching_name(read, names), expected, (text, size, read)
                )


if __name__ == "__main__":
    unittest.main()
