"""
Interactive onboarding walkthrough for Mosaic.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from .chapters import all_chapters, get_chapter


def launch_onboarding(main_window, chapter_id: str):
    from .controller import OnboardingController

    chapter = get_chapter(chapter_id)
    controller = OnboardingController(main_window)
    main_window._onboarding_controller = controller
    controller.start(chapter)
