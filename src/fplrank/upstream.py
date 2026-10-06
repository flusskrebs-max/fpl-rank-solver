"""Import Sertalp's vendored solver and patch it for one call. The vendored code itself is never edited."""

import sys
from contextlib import contextmanager

from fplrank.paths import UPSTREAM_DIR


def solve_module():
    """His `run/solve.py`, imported as `solve` the way `run/simulations.py` does."""
    for path in (UPSTREAM_DIR, UPSTREAM_DIR / "run"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import solve

    return solve


@contextmanager
def patched(module, **replacements):
    """Replace attributes of `module` for the duration of the block."""
    originals = {name: getattr(module, name) for name in replacements}
    for name, value in replacements.items():
        setattr(module, name, value)
    try:
        yield
    finally:
        for name, value in originals.items():
            setattr(module, name, value)
