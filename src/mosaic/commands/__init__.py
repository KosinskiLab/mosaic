"""
Mosaic command interface — headless command dispatch and interactive shell.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from .registry import CommandRegistry
from .session import Session

__all__ = ["CommandRegistry", "Session"]
