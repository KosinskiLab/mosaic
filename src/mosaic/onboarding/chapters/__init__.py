"""
Chapter registry for onboarding walkthrough.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from ..base import OnboardingStep, OnboardingChapter

CHAPTERS: dict[str, type[OnboardingChapter]] = {}


def register(cls: type[OnboardingChapter]):
    CHAPTERS[cls.id] = cls
    return cls


def get_chapter(chapter_id: str) -> OnboardingChapter:
    if chapter_id not in CHAPTERS:
        available = ", ".join(CHAPTERS.keys())
        raise ValueError(f"Unknown chapter '{chapter_id}'. Available: {available}")
    return CHAPTERS[chapter_id]()


def all_chapters() -> list[OnboardingChapter]:
    return [cls() for cls in CHAPTERS.values()]


# Auto-import chapter modules so @register decorators fire.
from . import basics
