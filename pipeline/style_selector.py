"""
Weekly style rotation. Returns the brain name for the current ISO week.
Override with DJKYOKO_BRAIN env var.
"""
import datetime
import os

ROTATION = [
    "solomun",
    "afterlife",
    "taleous",
    "bodzin",
    "bicep",
    "maceoplex",
    "benbohmer",
    "baumel",      # Patrice Bäumel — added for week 8
    "dixon",       # Dixon/Innervisions — added for week 9
    "massano",     # Massano solo — added for week 10
]


def current_brain() -> str:
    """Return brain name for this week. DJKYOKO_BRAIN env var overrides."""
    override = os.environ.get("DJKYOKO_BRAIN")
    if override:
        return override
    week = datetime.date.today().isocalendar()[1]
    return ROTATION[week % len(ROTATION)]


def next_brain() -> str:
    """Return what next week's brain will be."""
    week = datetime.date.today().isocalendar()[1] + 1
    return ROTATION[week % len(ROTATION)]
