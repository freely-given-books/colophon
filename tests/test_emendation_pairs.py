"""EMENDATION_PAIRS: a look-alike word swap is recorded as an emendation."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from teibuild import decisions, settings  # noqa: E402


def token(reg):
    return SimpleNamespace(kind="word", extra={}, reg=reg, gaps=[], macrons=[])


def test_lookalike_is_spelling_by_default(monkeypatch):
    monkeypatch.setattr(settings, "EMENDATION_PAIRS", set())
    t, log = token("intercession"), []
    decisions.apply_to_token(t, "intermission", log, "x")
    assert t.rtype == "spelling"


def test_pair_makes_it_an_emendation(monkeypatch):
    monkeypatch.setattr(settings, "EMENDATION_PAIRS", {("intercession", "intermission")})
    t, log = token("Intercession"), []
    decisions.apply_to_token(t, "Intermission", log, "x")
    assert t.rtype == "emendation" and log[-1][1] == "emendation"
