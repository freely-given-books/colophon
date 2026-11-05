"""The proofread tools without a model: slips planted where they say, the
marker's sentences chosen and written as the policy reads them."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from proof import bench, marked  # noqa: E402

PARA = ("He that believeth on him is not condemned, and the love of God is shed abroad "
        "in our hearts; for of him, and through him, and to him, are all things, to whom "
        "be glory for ever. Then they came to him from the city, and he spoke to them.\n")


def test_plant(tmp_path):
    after = tmp_path / "after"
    after.mkdir()
    for k in range(4):
        (after / f"chapter-{k:02d}.typ").write_text("= Head\n\n" + "\n".join([PARA] * 6))
    targets = bench.plant(tmp_path, n=6, seed=1)
    assert len(targets) == 6
    assert bench.plant(tmp_path, n=6, seed=1) == targets            # seeded: the same slips
    for t in targets:
        words = bench.WORD.findall(bench.plain((tmp_path / "planted" / t["file"]).read_text()))
        new = bench.plain(t["new"]).split()
        if new:                                    # a dropped word has nothing to point at
            letters = lambda ws: [re.sub(r"\W", "", w) for w in ws]
            assert letters(words[t["w1"]:t["w1"] + len(new)]) == letters(new)


def test_marked(tmp_path):
    data = {"chapter-01.typ": [["He", 0.0, None, -15.0], ["came", -1.0, "went", -1.0],
                               ["to", -0.1, "to", -0.1], ["them.", -2.0, None, -15.0],
                               ["And", 0.0, None, -15.0], ["or", -16.0, "the", -0.5],
                               ["God", -0.2, None, -15.0], ["spoke.", -1.0, None, -15.0]]}
    top, picked, total, used, seed = marked.choose(data, share=0.5, sample=0.0, seed=7)
    assert total == 8 and [s[1] for s in top] == [4]          # the "or" sentence first
    assert marked.line(data, top[0]) == "01 15.0 And [[or]](the?) God spoke."
    assert re.match(r"01 +\d", marked.line(data, marked.sentences(data)[0]))
    assert json.dumps(seed) == "7"
