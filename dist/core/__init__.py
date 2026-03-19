# -*- coding: utf-8 -*-
"""
Core package.

Some modules are imported as `from core import db` across the codebase.
When frozen with PyInstaller, implicit submodule import may fail, so we
explicitly expose `db` here to make imports reliable.
"""

# Explicit re-export for statements like `from core import db`.
from . import db

__all__ = ["db"]
