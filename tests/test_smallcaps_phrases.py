"""SMALLCAPS_PHRASES: a phrase found once, and one scoped to a block by its xml:id."""

import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from teibuild.marking import smallcaps_phrases  # noqa: E402

TEI = """<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
<div xml:id="index"><head>TO</head><head>THE AUTHORS</head></div>
<div xml:id="address"><head xml:id="to">TO</head><head>HIS MAJESTY,</head><p>Sire, when</p></div>
</body></text></TEI>"""


def tree():
    return etree.fromstring(TEI.encode())


def segs(root):
    return [s.text for s in root.iter("{http://www.tei-c.org/ns/1.0}seg")]


def test_found_twice_fails():
    with pytest.raises(ValueError, match="found 2 times"):
        smallcaps_phrases(tree(), ["^[TO]$"])


def test_scoped_to_block():
    root = tree()
    smallcaps_phrases(root, [("to", "^[TO]$"), ("address", "^[HIS MAJESTY,]$"), "^[Sire], when"])
    assert segs(root) == ["TO", "HIS MAJESTY,", "Sire"]
    assert root.find(".//{*}div[@{http://www.w3.org/XML/1998/namespace}id='index']/{*}head").text == "TO"


def test_unknown_block():
    with pytest.raises(ValueError, match="no element"):
        smallcaps_phrases(tree(), [("nowhere", "^[TO]$")])
