from __future__ import annotations

import sys

from .runner import run
from .sites import SCRAPERS


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    targets = args or list(SCRAPERS)
    return run(targets)


if __name__ == "__main__":
    raise SystemExit(main())
