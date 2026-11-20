"""Every example must keep generating exactly the same scene.

A change to the library that is not meant to change the pictures must leave
these alone. When a change IS meant to (or an example was edited), look at
the result in the viewer and then record it as the new expected one:

    python -m pytest --accept
"""
import hashlib
import json
from pathlib import Path

import pytest

from claymarch.__main__ import generate

ROOT = Path(__file__).resolve().parent.parent
RECORD = Path(__file__).with_name("examples.json")
# a file whose name starts with _ holds pieces the examples share
EXAMPLES = sorted(
    p.stem for p in (ROOT / "examples").glob("*.py")
    if not p.stem.startswith("_")
)


def fingerprint(name, out):
    generate(ROOT / "examples" / f"{name}.py", out)
    return hashlib.sha256((out / "scene.glsl").read_bytes()).hexdigest()


@pytest.mark.parametrize("name", EXAMPLES)
def test_example_generates_the_same_scene(name, tmp_path, request):
    found = fingerprint(name, tmp_path)
    record = json.loads(RECORD.read_text()) if RECORD.exists() else {}
    if request.config.getoption("--accept"):
        record[name] = found
        RECORD.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        return
    assert name in record, (
        f"{name} has no recorded result yet: python -m pytest --accept"
    )
    assert found == record[name], (
        f"examples/{name}.py no longer generates the same scene. If that "
        "was the idea, check it in the viewer and run: "
        "python -m pytest --accept"
    )
