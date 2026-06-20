"""
DJ Set Builder — entry point.

Usage:
  python build_set.py luno      # builds DJ LUNOBOT set (hours_before_light)
  python build_set.py solomun   # builds DJ SOLOMONBOT set (sorry_i_am_late)

Each brain lives in brains/<name>.py and defines: SET_NAME, SET_NOTES,
TRACKS, CF_BARS, OUTRO_BARS, SNIPPET_SEC.

Core build logic is in mixer/set_builder.py — shared by all brains.
"""
import sys, importlib, os

sys.path.insert(0, os.path.dirname(__file__))
from mixer.set_builder import build_full_set

AVAILABLE = ["luno", "solomun", "afterlife", "test3"]

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in AVAILABLE:
        print(f"\nUsage: python build_set.py [{' | '.join(AVAILABLE)}]\n")
        for name in AVAILABLE:
            mod = importlib.import_module(f"brains.{name}")
            print(f"  {name:<10} → output/{mod.SET_NAME}/")
        print()
        sys.exit(1)

    brain_name = sys.argv[1]
    brain = importlib.import_module(f"brains.{brain_name}")
    print(f"\n  Brain: {brain_name.upper()}  ({brain.STYLE_NAME})")
    build_full_set(brain)

if __name__ == "__main__":
    main()
