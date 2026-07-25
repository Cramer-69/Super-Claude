"""Pytest configuration.

Ensures the repository root is importable so tests can use the top-level
packages (``conductor``, ``config``, ``utils``, ...) regardless of the
directory pytest is invoked from. Without this, collecting a test under
``tests/`` puts only ``tests/`` on ``sys.path`` and ``import conductor``
fails with ModuleNotFoundError.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
