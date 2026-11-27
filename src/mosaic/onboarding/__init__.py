"""
Interactive onboarding walkthrough for Mosaic.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import TYPE_CHECKING

from .chapters import all_chapters as all_chapters
from .chapters import get_chapter

if TYPE_CHECKING:
    from ..gui import App


def launch_onboarding(main_window: "App", chapter_id: str):
    from .controller import OnboardingController

    chapter = get_chapter(chapter_id)
    controller = OnboardingController(main_window)
    main_window._onboarding_controller = controller
    controller.start(chapter)
