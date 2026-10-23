"""Per-frame boolean masks from the Smart Tagging XML.

Smart Tagging is Metrica's automatic tactical annotation of the *tactical* video: phases of play
and set pieces, 638 intervals, each with a code and a few labels (Team, Type, Half). It is a
free prior -- not ground truth -- so this module only turns it into the shape the rest of the
pipeline speaks, a boolean array indexed by video frame.

Time base
---------
`<start>` and `<end>` are seconds from the first frame of the tactical video, which is the clock
the submission is indexed to, so `video_frame = round(seconds * 25)` needs no offset. That is
verified on the delivered file rather than assumed: the tagged kickoffs straddle the real kickoff
frames (11185 and 113742). A constant offset fitted to one half would break the other, so if the
export ever changes clocks, fix the base rather than adding a magic number.

Half-open intervals
-------------------
`[start_frame, end_frame)` -- the last frame inside a phase is `end_frame - 1`, matching how the
rest of this repository treats intervals. `starter/load_smart_tagging.py` is the organisers'
reference for the same file; it is not imported here because it is read-only reference code,
prints from a time-base check, and treats `end_frame` as inclusive, which would grow every mask
by one frame. The parsing below is the minimum this repository needs.

Phases, not possessions
-----------------------
A "BUILD UP" can be longer than a possession, shorter than one, or cover two. These masks say
"the annotator saw this kind of phase here", never "this team had the ball here". Using them as
labels inherits the annotator's false positives and false negatives; using them as a prior does
not.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402

# FPS comes from games.py: the tagging is exported against the tactical video, and that module is
# the one place the rate is stated. N_FRAMES is the submission length, so every mask lines up with
# an artifact row without the caller checking.
FPS = games.GAMES[games.GAME]["fps"]
N_FRAMES = games.source_frames()


def path() -> Path:
    """The Smart Tagging XML named by games.asset_paths(), whether or not it exists."""
    return Path(games.asset_paths()["smart_tagging"])


def _text(instance: ET.Element, tag: str) -> str:
    """A child element's text, naming the instance when the export leaves it out."""
    value = instance.findtext(tag)
    if value is None:
        raise ValueError(f"instance {instance.findtext('ID')}: missing <{tag}>")
    return value


def load(xml_path: str | Path | None = None) -> list[dict]:
    """Every `<instance>`, in file order: id, code, frames, seconds and tags.

    Frames are half-open and clipped to the match window, 0..199318 inclusive, instead of dropping
    out-of-range instances: `len(load())` still describes the file (638) and a per-code count stays
    comparable across exports. An interval that falls entirely outside the match collapses to
    empty, which is exactly what it contributes to a mask.
    """
    source = Path(xml_path) if xml_path is not None else path()
    instances = []
    for instance in ET.parse(source).iter("instance"):
        start_s = float(_text(instance, "start"))
        end_s = float(_text(instance, "end"))
        # round(), not int(): the tags are accurate to about a second, so nearest-frame is the
        # honest conversion and it matches the reference loader's choice.
        start_frame = min(N_FRAMES, max(0, round(start_s * FPS)))
        end_frame = min(N_FRAMES, max(0, round(end_s * FPS)))
        instances.append(
            {
                "id": int(_text(instance, "ID")),
                "code": _text(instance, "code").strip(),
                "start_frame": start_frame,
                # Guard against a reversed interval: an empty slice is recoverable, an inverted
                # one is a silent off-by-whole-match bug.
                "end_frame": max(start_frame, end_frame),
                "start_s": start_s,
                "end_s": end_s,
                "tags": {
                    label.findtext("group"): label.findtext("text")
                    for label in instance.findall("label")
                },
            }
        )
    return instances


def _normalised(codes: str | Iterable[str]) -> set[str]:
    """Codes as a set of stripped upper-case names; one string is one code, not characters."""
    if isinstance(codes, str):
        codes = [codes]
    return {str(code).strip().upper() for code in codes}


def mask(instances: list[dict], codes: str | Iterable[str]) -> np.ndarray:
    """Boolean array of length N_FRAMES, True on frames covered by any of `codes`.

    Overlaps are expected -- the annotator tags the same frame as "BUILD UP" and "PROGRESSION" --
    and writing True twice is a no-op, so no priority between codes is needed or implied.
    """
    wanted = _normalised(codes)
    marked = np.zeros(N_FRAMES, dtype=bool)
    for instance in instances:
        if (instance.get("code") or "").strip().upper() not in wanted:
            continue
        # Clip again rather than trusting load(): mask() is also called with hand-built instances,
        # and a numpy slice whose bound is past the end silently shrinks instead of complaining.
        start = max(0, int(instance["start_frame"]))
        end = min(N_FRAMES, int(instance["end_frame"]))
        if end > start:
            marked[start:end] = True
    return marked


def summary(instances: list[dict]) -> dict[str, int]:
    """How many instances carry each code, most frequent first, ties alphabetical.

    Upper-cased so a lowercase export does not split one code into two rows.
    """
    counts: dict[str, int] = {}
    for instance in instances:
        code = (instance.get("code") or "").strip().upper()
        counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def main() -> int:
    instances = load()
    counts = summary(instances)
    print(f"{len(instances)} Smart Tagging instances from {path()}")
    print("\ncodes")
    for code, count in counts.items():
        print(f"  {code:<34} {count:>4}")
    print("\nframes marked")
    for code in ("SET PIECES", "GOALS"):
        frames = int(mask(instances, code).sum())
        print(f"  {code:<34} {frames:>7}  ({frames / N_FRAMES:.1%} of the match)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
