"""Pytest configuration.

Ensures the repository root is importable so tests can use the top-level
packages (``conductor``, ``config``, ``utils``, ...) regardless of the
directory pytest is invoked from. Without this, collecting a test under
``tests/`` puts only ``tests/`` on ``sys.path`` and ``import conductor``
fails with ModuleNotFoundError.
"""

import os
import sys

_repo_root = os.path.dirname(os.path.abspath(__file__))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
