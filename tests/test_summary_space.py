"""layout.summary_end: where a printed summary in the text ends (SUMMARY_SPACE)."""

import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import layout  # noqa: E402

NS = "http://www.tei-c.org/ns/1.0"


def div(xml):
    return etree.fromstring(f'<div xmlns="{NS}">{xml}</div>')


def ends(d):
    return [i for i, e in enumerate(d) if layout.summary_end(e)]


def test_argument_before_text():
    assert ends(div('<head>T</head><argument><p rend="inset">a</p></argument><p>text</p>')) == [1]


def test_argument_last_is_not():
    assert ends(div('<head>T</head><argument><p rend="inset">a</p></argument>')) == []


def test_inset_run_opening_division_after_title():
    d = div('<head>C</head><p>TITLE</p><p rend="inset">S</p><p rend="inset">1</p><p>text</p>')
    assert ends(d) == [3]


def test_inset_in_the_middle_is_not():
    d = div('<p>a</p><p>b</p><p rend="inset">x</p><p>c</p>')
    assert ends(d) == []
