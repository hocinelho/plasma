#!/usr/bin/env python3
"""Fetch the other characters, so the picker has something to pick.

    python scripts/get_avatars.py

Plasma ships with one character, `brunette.glb`. The picker, the labels and
the retargeting for four more have been in place all along —
`frontend/avatars/avatars.json` names every one — but the model files
themselves were never in the repo, so the picker had a single entry and hid
itself. From the outside that is indistinguishable from the feature not
existing, which is exactly how it was read.

They are not committed because they are 66 MB of binaries under
non-commercial sample licences, and this repository is public. A fetch is the
honest way round that: the files come from the upstream project that
published them, under their own terms, onto your machine.

Everything else already works. Every character plays every clip — TalkingHead
retargets the Mixamo skeleton onto whichever rig is loaded — so this only
changes her face and build, never what she can do.
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "frontend" / "avatars"

# met4citizen/TalkingHead, MIT-licensed and the source of the renderer Plasma
# vendors. Pinned to a commit rather than a branch: `main` moving under us
# would silently change which characters arrive.
COMMIT = "eed58d198076a7e1e825f804802921c4d3804d46"
BASE = f"https://raw.githubusercontent.com/met4citizen/TalkingHead/{COMMIT}/avatars"

# Sizes are the real ones, so a slow connection is a known wait rather than a
# hang. Licences matter and are stated plainly: only one of these is free for
# commercial use, and it is not the one Plasma ships with.
AVATARS = [
    ("mpfb.glb", 36.8, "MakeHuman/MPFB — CC0. The only one free for ANY use."),
    ("avaturn.glb", 13.8, "Avaturn sample — realistic. Non-commercial."),
    ("avatarsdk.glb", 12.3, "MetaPerson sample — non-commercial; logo on the shirt."),
    ("vroid.glb", 2.3, "VRoid Studio sample — stylised anime. Permissive."),
]


def fetch(name: str, size_mb: float, note: str) -> bool:
    target = DEST / name
    if target.exists():
        print(f"  {name:<16} already here — skipping")
        return True

    print(f"  {name:<16} {size_mb:>5.1f} MB  {note}")
    # Downloaded to a temporary name and renamed on success: a half-written
    # .glb is picked up by discover_models() and fails to load in the browser
    # with nothing to say why.
    tmp = target.with_suffix(".part")
    try:
        with urllib.request.urlopen(f"{BASE}/{name}", timeout=120) as r, \
                tmp.open("wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                print(f"      {tmp.stat().st_size / 1048576:.1f} MB", end="\r")
        tmp.rename(target)
        print(f"      done ({target.stat().st_size / 1048576:.1f} MB)     ")
        return True
    except (urllib.error.URLError, OSError) as e:
        tmp.unlink(missing_ok=True)
        print(f"      FAILED: {e}")
        return False


def main() -> int:
    if not DEST.is_dir():
        print(f"  {DEST} does not exist — run this from the Plasma repo.")
        return 1

    print("\n  Fetching the other characters from met4citizen/TalkingHead.")
    print("  They are sample models under their own licences — see the notes.\n")

    ok = sum(fetch(*a) for a in AVATARS)
    have = sorted(p.name for p in DEST.glob("*.glb"))

    print(f"\n  {len(have)} character(s) in {DEST.relative_to(ROOT)}: "
          f"{', '.join(have)}")
    if ok < len(AVATARS):
        print("\n  Some downloads failed — a work network may be blocking "
              "raw.githubusercontent.com.\n  You can also copy them by hand:")
        print("      git clone --depth 1 https://github.com/met4citizen/TalkingHead")
        print("      copy TalkingHead\\avatars\\*.glb frontend\\avatars\\")

    if len(have) > 1:
        print("\n  Restart Plasma and the picker appears above her "
              "(it hides itself when there is only one).")
        print("  For the desktop overlay, which has its own storage and no "
              "room for a picker:")
        print('      $env:PLASMA_OVERLAY_MODEL = "vroid.glb"')
    print()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
