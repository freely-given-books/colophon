"""A gap's fill of words and stops, modernized word by word (MODERNIZE_FILLS): "dead Frames;"
is "dead frames;" in the reading text, as the words around it are (Religious Affections, 1746).

  uv run --project colophon --group dev pytest colophon/tests
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from teibuild import settings as S  # noqa: E402
from teibuild.words import fill_reg_words  # noqa: E402


def setup_module():
    S.LOWERCASE_COMMON_NOUNS = {"frames", "behaviour", "behavior", "speech"}


def test_words_cased_like_the_text():
    assert fill_reg_words("dead Frames;", False) == "dead frames;"
    assert fill_reg_words("Speech, or", False) == "speech, or"


def test_a_stop_in_the_fill_starts_the_next_sentence():
    assert fill_reg_words("so? immediately", False) == "so? Immediately"


def test_a_number_after_a_stop_does_not():
    assert fill_reg_words("Gal. 5. 16, to the End", False).endswith("16, to the End")


def test_sentence_start_capitalizes_the_first_word():
    assert fill_reg_words("they therefore,", True) == "They therefore,"
