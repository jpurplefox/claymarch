import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# the examples import each other (seaside uses squirtle)
sys.path[:0] = [str(ROOT), str(ROOT / "examples")]


def pytest_addoption(parser):
    parser.addoption(
        "--accept", action="store_true",
        help="record what the examples generate now as the expected result",
    )
