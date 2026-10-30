"""Lane ball-video: recover the ball from the tactical video where the tracking lost it.

    # the detector runs in its own environment (requirements-video.txt: torch, ultralytics)
    python tools/video_ball.py sample --out runs/video_ball/sample.npz
    python tools/video_ball.py detect --frames runs/video_ball/sample.npz \\
        --out runs/video_ball/sample_det.npz
    python tools/video_ball.py feasibility --frames runs/video_ball/sample.npz \\
        --detections runs/video_ball/sample_det.npz

Why
---
The tracking has no ball on 41% of the graded frames, and the engine has no evidence there. The
rules allow replacing the provided tracking with our own detection, and the tactical video is the
frame-index authority: row `i` of a submission is frame `i` of the video, and the per-frame
homography maps the pitch to the image. So a ball found in pixel `(u, v)` of frame `i` is a ball
at pitch position `H_i^-1 (u, v)`, in the same normalised 0-1 coordinates as the tracking.

Split
-----
Everything that touches the video or a neural network (`read_frames`, `Detector`) imports its
libraries lazily and runs only in the separate environment. Everything that turns detections into
evidence (`to_pitch`, `plausible`, `merge_ball`) is numpy only, so the engine side of the lane
needs nothing the delivered path does not already have.

Nothing here writes a frame, a crop or an image: the detector reads frames from an ffmpeg pipe and
only numbers leave it. The detections themselves are frame-level derived data from the licensed
video, so they live in `runs/` (gitignored) and are never committed.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import games  # noqa: E402

FPS = int(games.GAMES[games.GAME]["fps"])
PITCH_M = np.asarray(games.GAMES[games.GAME]["pitch"], dtype=float)
WIDTH, HEIGHT = 1920, 1080
SPORTS_BALL = 32  # the COCO class id of "sports ball"
SEED = 2027
# Block 1 (the public slice and the bench window) plus one minute each side: never trained on.
EXCLUDED = (11185 - 1500, 18685 + 1500)


# -- the video ---------------------------------------------------------------------------------


def read_frames(video: str | Path, start: int, count: int) -> Iterator[np.ndarray]:
    """Frames `start .. start+count-1` of the video as BGR `(1080, 1920, 3)` arrays.

    `-ss` before `-i` is ffmpeg's accurate seek: it decodes from the previous keyframe and drops
    frames until the requested timestamp, so frame `start` is frame `start` (checked against a
    sequential decode by hash in the proposal, section 2).
    """
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if start:
        cmd += ["-ss", f"{start / FPS:.4f}"]
    cmd += ["-i", str(video), "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    size = WIDTH * HEIGHT * 3
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=size * 4)
    assert process.stdout is not None
    try:
        for _ in range(count):
            buffer = process.stdout.read(size)
            if len(buffer) < size:
                raise RuntimeError(f"video ended before frame {start + count - 1}")
            yield np.frombuffer(buffer, np.uint8).reshape(HEIGHT, WIDTH, 3)
    finally:
        process.stdout.close()
        process.wait()


@dataclass(frozen=True)
class DetectorConfig:
    """What runs on each frame. Fixed in the pre-registration, not swept."""

    weights: str = "yolo11x.pt"
    imgsz: int = 1920  # the native width: the ball is ~6 px across, downscaling erases it
    conf: float = 0.05  # keep weak boxes; the confidence threshold is applied later, in numpy
    max_det: int = 5  # boxes kept per frame, best first
    half: bool = True
    cls: int = SPORTS_BALL  # 0 for the fine-tuned single-class model (proposal, section 4)


DEFAULT_DETECTOR = DetectorConfig()


class Detector:
    """A COCO detector restricted to `sports ball`. Imports torch only when constructed."""

    def __init__(self, config: DetectorConfig = DEFAULT_DETECTOR, device: str = "cuda:0") -> None:
        from ultralytics import YOLO

        self.config = config
        self.device = device
        self.model = YOLO(config.weights)

    def __call__(self, frames: Sequence[np.ndarray]) -> list[np.ndarray]:
        """Per frame, `(k, 5)` float arrays `[u, v, w, h, conf]`, centre in pixels, best first."""
        c = self.config
        results = self.model.predict(
            list(frames),
            imgsz=c.imgsz,
            conf=c.conf,
            classes=[c.cls],
            max_det=c.max_det,
            half=c.half,
            device=self.device,
            verbose=False,
        )
        out = []
        for r in results:
            boxes = r.boxes
            xywh = boxes.xywh.float().cpu().numpy() if len(boxes) else np.zeros((0, 4))
            conf = boxes.conf.float().cpu().numpy() if len(boxes) else np.zeros(0)
            rows = np.column_stack([xywh, conf]).astype(np.float64)
            out.append(rows[np.argsort(-rows[:, 4], kind="stable")])
        return out


def detect_frames(
    video: str | Path,
    frames: np.ndarray,
    detector: Detector,
    batch: int = 8,
) -> tuple[dict[str, np.ndarray], dict]:
    """Run `detector` on the given frame indices, reading contiguous runs in one pass each."""
    frames = np.unique(np.asarray(frames, dtype=np.int64))
    breaks = np.flatnonzero(np.diff(frames) != 1) + 1
    rows: list[np.ndarray] = []
    t_decode = t_detect = 0.0
    for run in np.split(frames, breaks):
        start, count = int(run[0]), len(run)
        reader = read_frames(video, start, count)
        done = 0
        while done < count:
            t0 = time.perf_counter()
            chunk = [next(reader) for _ in range(min(batch, count - done))]
            t1 = time.perf_counter()
            for offset, boxes in enumerate(detector(chunk)):
                index = np.full((len(boxes), 1), start + done + offset, dtype=np.float64)
                rows.append(np.hstack([index, boxes]))
            t_detect += time.perf_counter() - t1
            t_decode += t1 - t0
            done += len(chunk)
        reader.close()
    table = np.vstack(rows) if rows else np.zeros((0, 6))
    detections = {
        "frame": table[:, 0].astype(np.int64),
        # Rounded on the way out: the stored file must not depend on the last bits of a GPU sum.
        "u": np.round(table[:, 1], 1),
        "v": np.round(table[:, 2], 1),
        "w": np.round(table[:, 3], 1),
        "h": np.round(table[:, 4], 1),
        "conf": np.round(table[:, 5], 3),
    }
    timing = {
        "frames": int(len(frames)),
        "decode_s": round(t_decode, 2),
        "detect_s": round(t_detect, 2),
        "fps": round(len(frames) / max(1e-9, t_decode + t_detect), 2),
    }
    return detections, timing


# -- training data for the fine-tuned detector (proposal, section 4) ---------------------------

CROP = 640
LABEL_BOX_PX = 24  # contains the ball for ~80% of ATD projections (8.9 px median offset, p75 16)
NEGATIVE_CLEAR_PX = 48


def project_ball(matrices: np.ndarray, ball: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Normalised pitch positions -> pixels, one homography per row (the starter's `project`)."""
    m = np.asarray(matrices, dtype=float)
    x, y = ball[:, 0], ball[:, 1]
    den = m[:, 2, 0] * x + m[:, 2, 1] * y + m[:, 2, 2]
    return (m[:, 0, 0] * x + m[:, 0, 1] * y + m[:, 0, 2]) / den, (
        m[:, 1, 0] * x + m[:, 1, 1] * y + m[:, 1, 2]
    ) / den


def crop_boxes(
    u: float, v: float, rng: np.random.Generator
) -> tuple[tuple[int, int], tuple[float, float, float, float], tuple[int, int] | None]:
    """A positive crop origin with the ball's label box in crop pixels `(cx, cy, w, h)`, and a
    negative crop origin whose crop stays `NEGATIVE_CLEAR_PX` clear of the box (None if none fits
    in 50 draws). The ball lands anywhere in the positive crop, never within 16 px of its edge."""
    half = LABEL_BOX_PX / 2
    x0 = int(np.clip(round(u - rng.uniform(16, CROP - 16)), 0, WIDTH - CROP))
    y0 = int(np.clip(round(v - rng.uniform(16, CROP - 16)), 0, HEIGHT - CROP))
    cx, cy = u - x0, v - y0
    left, top = max(cx - half, 0.0), max(cy - half, 0.0)
    right, bottom = min(cx + half, float(CROP)), min(cy + half, float(CROP))
    box = ((left + right) / 2, (top + bottom) / 2, right - left, bottom - top)
    negative = None
    for _ in range(50):
        nx = int(rng.integers(0, WIDTH - CROP + 1))
        ny = int(rng.integers(0, HEIGHT - CROP + 1))
        clear = NEGATIVE_CLEAR_PX + half
        if not (nx - clear <= u <= nx + CROP + clear and ny - clear <= v <= ny + CROP + clear):
            negative = (nx, ny)
            break
    return (x0, y0), box, negative


def training_frames(present: np.ndarray, start: int, stop: int, count: int) -> np.ndarray:
    """`count` frames with the tracking's ball, equispaced among those in `[start, stop)`."""
    frames = start + np.flatnonzero(present[start:stop])
    return frames[np.round(np.linspace(0, len(frames) - 1, count)).astype(np.int64)]


def prepare(
    video: str | Path,
    out: Path,
    split: str,
    frames: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    seed: int = SEED,
) -> dict:
    """Write positive and negative crops (JPEG 95) with YOLO labels under `out/images|labels/split`.

    Reads the span `frames.min()..frames.max()` sequentially and keeps the selected frames. The
    crops are derived licensed data: `runs/` only, never opened by an image tool, deleted after.
    """
    import cv2

    rng = np.random.default_rng(seed)
    images, labels = out / "images" / split, out / "labels" / split
    images.mkdir(parents=True, exist_ok=True)
    labels.mkdir(parents=True, exist_ok=True)
    wanted = {int(f): k for k, f in enumerate(frames)}
    start, stop = int(frames.min()), int(frames.max()) + 1
    n_pos = n_neg = 0
    for offset, image in enumerate(read_frames(video, start, stop - start)):
        k = wanted.get(start + offset)
        if k is None:
            continue
        (x0, y0), (cx, cy, w, h), negative = crop_boxes(float(u[k]), float(v[k]), rng)
        name = f"{split}_{start + offset:06d}"
        cv2.imwrite(
            str(images / f"{name}_p.jpg"),
            image[y0 : y0 + CROP, x0 : x0 + CROP],
            [cv2.IMWRITE_JPEG_QUALITY, 95],
        )
        (labels / f"{name}_p.txt").write_text(
            f"0 {cx / CROP:.6f} {cy / CROP:.6f} {w / CROP:.6f} {h / CROP:.6f}\n", encoding="ascii"
        )
        n_pos += 1
        if negative is not None:
            nx, ny = negative
            cv2.imwrite(
                str(images / f"{name}_n.jpg"),
                image[ny : ny + CROP, nx : nx + CROP],
                [cv2.IMWRITE_JPEG_QUALITY, 95],
            )
            (labels / f"{name}_n.txt").write_text("", encoding="ascii")
            n_neg += 1
    return {"split": split, "positives": n_pos, "negatives": n_neg}


# -- pixels to pitch (numpy only) ----------------------------------------------------------------


def to_pitch(matrices: np.ndarray, u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pixel centres -> normalised pitch `(x, y)`, one homography per row (the ground plane).

    `matrices[k]` maps the pitch to the image for the frame of detection `k` (the starter's
    convention), so the inverse goes the other way. A ball in the air sits above its ground point,
    so its projection lands *behind* it, further from the camera -- the error grows with height.
    """
    inverse = np.linalg.inv(np.asarray(matrices, dtype=float))
    u, v = np.asarray(u, dtype=float), np.asarray(v, dtype=float)
    den = inverse[:, 2, 0] * u + inverse[:, 2, 1] * v + inverse[:, 2, 2]
    x = (inverse[:, 0, 0] * u + inverse[:, 0, 1] * v + inverse[:, 0, 2]) / den
    y = (inverse[:, 1, 0] * u + inverse[:, 1, 1] * v + inverse[:, 1, 2]) / den
    return x, y


def best_per_frame(
    frame: np.ndarray, conf: np.ndarray, n_frames: int, min_conf: float = 0.0
) -> np.ndarray:
    """Index into the detection table of each frame's most confident box, `-1` where none."""
    best = np.full(n_frames, -1, dtype=np.int64)
    keep = np.flatnonzero(conf >= min_conf)
    # Ascending confidence, so the last write per frame is the best; ties go to the earlier row.
    order = keep[np.lexsort((-np.arange(len(keep)), conf[keep]))]
    best[frame[order]] = order
    return best


# -- plausibility and merge (numpy only) ---------------------------------------------------------


@dataclass(frozen=True)
class Filter:
    """Which video balls count as evidence. Fixed in the pre-registration (proposal, section 3)."""

    min_conf: float = 0.3
    # The tracking's own ball ranges over -0.04..1.04: on the pitch or just outside it (a ball
    # going out is still a ball). Anything further out is a spectator's ball or a false box.
    margin: float = 0.05
    # The hardest shot is ~35 m/s. Two balls `k` frames apart further than this allows are not
    # the same ball. The ground projection of a lofted ball moves faster than the ball itself,
    # so this bound is loose on purpose.
    max_speed_mps: float = 35.0
    # A ball is accepted only when another ball (video or tracking) within this many frames
    # agrees with it: an isolated single-frame box is the commonest false positive.
    support_frames: int = 5
    slack_m: float = 1.0  # detection noise added to the speed bound


DEFAULT_FILTER = Filter()


def candidates(
    det: dict[str, np.ndarray], matrices: np.ndarray, n_frames: int, flt: Filter = DEFAULT_FILTER
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Best box per frame above `min_conf`, projected: `(x, y, ok)` per frame, NaN where none."""
    best = best_per_frame(det["frame"], det["conf"], n_frames, flt.min_conf)
    has = best >= 0
    x = np.full(n_frames, np.nan)
    y = np.full(n_frames, np.nan)
    rows = best[has]
    x[has], y[has] = to_pitch(matrices[det["frame"][rows]], det["u"][rows], det["v"][rows])
    lo, hi = -flt.margin, 1 + flt.margin
    ok = has & (x >= lo) & (x <= hi) & (y >= lo) & (y <= hi)
    x[~ok] = np.nan
    y[~ok] = np.nan
    return x, y, ok


def supported(
    x: np.ndarray, y: np.ndarray, ok: np.ndarray, ref: np.ndarray, flt: Filter = DEFAULT_FILTER
) -> np.ndarray:
    """`ok` frames whose ball is consistent with another ball within `support_frames`.

    `ref` is `(n, 2)` normalised positions of the reference balls (video candidates and the
    tracking's ball, NaN where none). A frame never supports itself.
    """
    pos = np.column_stack([x, y]) * PITCH_M
    refm = ref * PITCH_M
    keep = np.zeros(len(x), dtype=bool)
    for k in range(1, flt.support_frames + 1):
        bound = flt.max_speed_mps * k / FPS + flt.slack_m
        for shift in (k, -k):
            other = np.full_like(refm, np.nan)
            if shift > 0:
                other[shift:] = refm[:-shift]
            else:
                other[:shift] = refm[-shift:]
            dist = np.hypot(*(pos - other).T)
            keep |= ok & (dist <= bound)
    return keep


def video_ball(
    det: dict[str, np.ndarray],
    matrices: np.ndarray,
    tracking_ball: np.ndarray,
    flt: Filter = DEFAULT_FILTER,
) -> tuple[np.ndarray, np.ndarray]:
    """Per frame, the accepted video ball `(n, 2)` (NaN where none) and its mask."""
    n = len(matrices)
    x, y, ok = candidates(det, matrices, n, flt)
    # References: the tracking where it has a ball, the video candidates elsewhere.
    ref = np.array(tracking_ball[:, :2], dtype=float)
    lost = np.isnan(ref[:, 0])
    ref[lost, 0], ref[lost, 1] = x[lost], y[lost]
    keep = supported(x, y, ok, ref, flt)
    xy = np.column_stack([x, y])
    xy[~keep] = np.nan
    return xy, keep


def merge_ball(tracking_ball: np.ndarray, video_xy: np.ndarray, video_ok: np.ndarray) -> np.ndarray:
    """The tracking's ball where it has one; the accepted video ball in its gaps.

    The tracking is never overwritten: where both exist it is the reference the whole engine was
    built and measured on. A filled ball gets z = NaN, which nothing downstream reads.
    """
    merged = np.array(tracking_ball, dtype=float)
    fill = np.isnan(merged[:, 0]) & np.asarray(video_ok, dtype=bool)
    merged[fill, 0] = video_xy[fill, 0]
    merged[fill, 1] = video_xy[fill, 1]
    merged[fill, 2] = np.nan
    return merged


# -- the variants (pre-registered, proposal section 2) -----------------------------------------


@dataclass(frozen=True)
class Variant:
    name: str
    min_conf: float | None  # None: no video (the delivered engine, V0)
    dead_from_video: bool = False  # V3: the dead-ball out/inside evidence also reads the video


VARIANTS = {
    "V0": Variant("V0", None),
    "V1": Variant("V1", 0.2),
    "V2": Variant("V2", 0.5),
    "V3": Variant("V3", 0.2, dead_from_video=True),
}


def out_inside(ball: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """As `dead_ball.load_evidence` reads a ball: observed outside / inside the [0, 1]² pitch."""
    x, y = ball[:, 0], ball[:, 1]
    present = ~np.isnan(x) & ~np.isnan(y)
    with np.errstate(invalid="ignore"):
        off = (x < 0) | (x > 1) | (y < 0) | (y > 1)
    return present & off, present & ~off


def labels_with_ball(
    variant: Variant,
    players: np.ndarray,
    teams,
    ball: np.ndarray,
    ev,
    det: dict[str, np.ndarray] | None,
    matrices: np.ndarray,
    allow: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """The delivered chain (`engine.chain`, D from `dead_ball` variant `out`) on `ball` plus, for a
    video variant, the accepted video ball in its gaps. `allow` restricts which frames the video
    may fill (the B-joint bench). Returns `(labels, filled)`."""
    from tools import atd, dead_ball, engine

    filled = np.zeros(len(ball), dtype=bool)
    merged = ball
    if variant.min_conf is not None and det is not None:
        xy, ok = video_ball(det, matrices, ball, Filter(min_conf=variant.min_conf))
        if allow is not None:
            ok = ok & allow
        merged = merge_ball(ball, xy, ok)
        filled = ok & np.isnan(ball[:, 0])
    f = engine.features(atd.Tracking(players, merged), teams)
    if variant.dead_from_video:
        out, inside = out_inside(merged)
        ev = dataclasses.replace(ev, out=out, inside=inside)
    dead = dead_ball.dead_mask(ev, engine.halves(), "out")
    return engine.chain(f, engine.DEFAULT, ev.restarts, dead)[2], filled


def bench_video(
    variant: Variant,
    design: str,
    players: np.ndarray,
    teams,
    ball: np.ndarray,
    ev,
    det: dict[str, np.ndarray] | None,
    matrices: np.ndarray,
    gt: np.ndarray,
    cut,
    donor_video: np.ndarray | None = None,
) -> list[dict]:
    """`tools/bench.py`'s transplant with the video allowed to refill the transplanted gaps.

    `opt`: the video of block 1 fills wherever it passes the filter (an upper bound: block 1's
    frames are the easy ones). `joint`: only where the donor itself had an accepted video ball on
    that frame of its real gap, so the video's coverage has the real gaps' amount and length.
    The filter's temporal support sees the degraded tracking, never the deleted ball.
    """
    import possession_metrics as pm

    if design not in ("opt", "joint"):
        raise ValueError(f"unknown bench design {design!r}")
    window = (cut[0].start, cut[0].stop)
    size = window[1] - window[0]

    def score(b: np.ndarray, e, allow: np.ndarray | None) -> tuple[float, int]:
        lab, filled = labels_with_ball(variant, players, teams, b, e, det, matrices, allow)
        return float(pm.evaluate(gt, pm.label_codes(list(lab)))["spell_f1_mean"]), int(
            filled[window[0] : window[1]].sum()
        )

    present = ~np.isnan(ball[:, 0])
    spell, n_filled = score(ball, ev, None)
    rows = [
        {
            "donor": "1★",
            "ball": float(present[window[0] : window[1]].mean()),
            "spell_f1": spell,
            "filled": n_filled,
        }
    ]
    for block in cut[1:]:
        if block.stop - block.start < size:
            continue
        donor = present[block.start : block.start + size]
        keep = np.ones(len(ball), dtype=bool)
        keep[window[0] : window[1]] = donor
        degraded = np.array(ball, dtype=float)
        degraded[~keep, :2] = np.nan
        ev2 = dataclasses.replace(ev, out=ev.out & keep, inside=ev.inside & keep)
        allow = None
        if design == "joint":
            if donor_video is None:
                raise ValueError("the joint design needs the donor's accepted video balls")
            allow = np.ones(len(ball), dtype=bool)
            allow[window[0] : window[1]] = donor_video[block.start : block.start + size]
        spell, n_filled = score(degraded, ev2, allow)
        rows.append(
            {
                "donor": str(block.index),
                "ball": float(donor.mean()),
                "spell_f1": spell,
                "filled": n_filled,
            }
        )
    return rows


# -- feasibility (no ground truth) -------------------------------------------------------------


def sample_frames(
    present: np.ndarray,
    runs: Sequence[tuple[int, int]],
    n_clusters: int = 200,
    length: int = 10,
    seed: int = SEED,
) -> dict[str, np.ndarray]:
    """Two frame sets inside the halves: runs of `length` frames with the tracking's ball on every
    frame, and runs with it on none. Clusters keep the seeks cheap; 200 x 10 = 2000 frames each."""
    rng = np.random.default_rng(seed)
    inside = np.zeros(len(present), dtype=bool)
    for start, stop in runs:
        inside[start:stop] = True
    out = {}
    for name, want in (("with_ball", True), ("gap", False)):
        ok = inside & (present == want)
        # A start is valid when the whole run of `length` frames qualifies.
        window = np.convolve(ok.astype(int), np.ones(length, dtype=int), "valid") == length
        starts = np.flatnonzero(window)
        chosen = np.sort(rng.choice(starts, size=n_clusters, replace=False))
        out[name] = (chosen[:, None] + np.arange(length)[None, :]).ravel()
    return out


def agreement(
    det: dict[str, np.ndarray],
    frames: np.ndarray,
    ball_xy: np.ndarray,
    matrices: np.ndarray,
    thresholds: Sequence[float],
) -> list[dict]:
    """Against the tracking's ball: per confidence threshold, how often the best box exists and how
    often it lies within 1 / 2 m of the tracking ball (recall), and among frames with a box, how
    often it is within 2 m (precision against the tracking)."""
    n = len(matrices)
    x, y = to_pitch(matrices[det["frame"]], det["u"], det["v"])
    rows = []
    for t in thresholds:
        best = best_per_frame(det["frame"], det["conf"], n, t)[frames]
        has = best >= 0
        err = np.full(len(frames), np.inf)
        dx = (x[best[has]] - ball_xy[frames[has], 0]) * PITCH_M[0]
        dy = (y[best[has]] - ball_xy[frames[has], 1]) * PITCH_M[1]
        err[has] = np.hypot(dx, dy)
        rows.append(
            {
                "conf": t,
                "found": float(has.mean()),
                "recall_1m": float((err <= 1).mean()),
                "recall_2m": float((err <= 2).mean()),
                "precision_2m": float((err[has] <= 2).mean()) if has.any() else float("nan"),
                "median_err_m": float(np.median(err[has])) if has.any() else float("nan"),
            }
        )
    return rows


def diagnose(
    det: dict[str, np.ndarray],
    frames: np.ndarray,
    ball: np.ndarray,
    players_m: np.ndarray,
    matrices: np.ndarray,
    min_conf: float = 0.3,
) -> dict:
    """Alignment (agreement with the tracking at frame `i + k`), the any-box oracle, and where the
    false positives sit. `players_m` is `(n, slots, 2)` in metres."""
    n = len(matrices)
    frames = np.unique(frames)
    x, y = to_pitch(matrices[det["frame"]], det["u"], det["v"])
    best = best_per_frame(det["frame"], det["conf"], n, min_conf)[frames]
    has = best >= 0
    f, b = frames[has], best[has]

    def err(at: np.ndarray, rows: np.ndarray) -> np.ndarray:
        dx = (x[rows] - ball[at, 0]) * PITCH_M[0]
        return np.hypot(dx, (y[rows] - ball[at, 1]) * PITCH_M[1])

    offsets = {}
    for k in (-4, -2, -1, 0, 1, 2, 4):
        at = f + k
        ok = (at >= 0) & (at < n)
        at = np.clip(at, 0, n - 1)
        ok &= ~np.isnan(ball[at, 0])
        offsets[k] = float((err(at[ok], b[ok]) <= 1).mean())
    e0 = err(f, b)
    inset = np.isin(det["frame"], frames)
    all_err = err(det["frame"][inset], np.flatnonzero(inset))
    hit = np.zeros(n, dtype=bool)
    hit[det["frame"][inset][all_err <= 2]] = True
    far = e0 > 5
    px, py = x[b[far]] * PITCH_M[0], y[b[far]] * PITCH_M[1]
    gap_to_player = np.nanmin(
        np.hypot(players_m[f[far], :, 0] - px[:, None], players_m[f[far], :, 1] - py[:, None]),
        axis=1,
    )
    spots = np.array([[52.65, 34.0], [11.0, 34.0], [PITCH_M[0] - 11.0, 34.0]])
    on_spot = np.min(np.hypot(px[:, None] - spots[:, 0], py[:, None] - spots[:, 1]), axis=1) <= 1
    return {
        "min_conf": min_conf,
        "within_1m_at_offset": offsets,
        "error_percentiles_m": np.percentile(e0, [25, 50, 75]).round(2).tolist(),
        "oracle_any_box_2m": float(hit[frames].mean()),
        "false_over_5m_share": float(far.mean()),
        "false_nearest_player_median_m": float(np.nanmedian(gap_to_player)),
        "false_within_1_5m_of_player": float(np.mean(gap_to_player <= 1.5)),
        "false_within_1m_of_a_spot": float(on_spot.mean()),
        "box_wh_median_px": [float(np.median(det["w"])), float(np.median(det["h"]))],
    }


def video_only_features(tracking, teams, det, matrices, flt: Filter):
    """Engine features with the ball taken from the video alone (the tracking's ball dropped).

    Support comes from other video balls only, never from the tracking, so the comparison with
    the tracking's own control on the same frames is not circular.
    """
    from tools import atd, engine

    x, y, ok = candidates(det, matrices, len(matrices), flt)
    keep = supported(x, y, ok, np.column_stack([x, y]), flt)
    ball = np.full((len(matrices), 3), np.nan)
    ball[keep, 0], ball[keep, 1] = x[keep], y[keep]
    return engine.features(atd.Tracking(tracking.players_array, ball), teams)


def control_agreement(
    det, matrices, tracking, teams, sets, ctrl_atd, state, live, thresholds
) -> list[dict]:
    """The engine's control computed from the video ball, against the tracking's.

    The engine reads the ball only through control frames (a player within 1.5 m, a slow ball),
    so a video ball matters only where it makes one. Per threshold: on frames with the tracking's
    ball, how many video controls there are and how many name the other team than the tracking's
    control; on both frame sets, how often a video control agrees with the engine's decoded state.
    """
    from tools import engine

    rows = []
    for t in thresholds:
        cv = engine.control(video_only_features(tracking, teams, det, matrices, Filter(min_conf=t)))
        wb, gap = sets["with_ball"], sets["gap"]
        v, a = cv[wb], ctrl_atd[wb]
        both = (v != engine.NONE) & (a != engine.NONE)
        row = {
            "conf": t,
            "atd_control_share": float((a != engine.NONE).mean()),
            "video_control_share": float((v != engine.NONE).mean()),
            "other_team_vs_atd_control": float((v[both] != a[both]).mean()),
            "gap_video_control_share": float((cv[gap] != engine.NONE).mean()),
        }
        for name, fr in (("with_ball", wb), ("gap", gap)):
            vc = (cv[fr] != engine.NONE) & live[fr]
            row[f"{name}_n_live_controls"] = int(vc.sum())
            row[f"{name}_agree_state"] = float((cv[fr][vc] == state[fr][vc]).mean())
        rows.append(row)
    return rows


def load_matrices() -> np.ndarray:
    """The tactical homographies, `(n, 3, 3)`: the starter's own loader, imported, not copied."""
    sys.path.insert(0, str(REPO_ROOT / "starter"))
    import load_homography

    matrices, _err, valid = load_homography.load()
    if not valid.all():
        raise ValueError("the tactical homography is expected valid on every frame")
    return matrices


def operating_threshold(rows: Sequence[dict], target: float) -> float | None:
    """The smallest threshold whose precision within 2 m reaches `target` (section 4), or None."""
    ok = [r["conf"] for r in rows if r["precision_2m"] >= target]
    return min(ok) if ok else None


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as data:
        return {key: data[key] for key in data.files}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ball from the tactical video (lane ball-video)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sample", help="choose the feasibility frames (tracking only)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--span", type=int, nargs=2, action="append", help="restrict to [START, STOP)")
    p = sub.add_parser("prepare", help="training crops for the fine-tuned detector (video env)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--count", type=int, default=6000)
    p.add_argument("--span", type=int, nargs=2, required=True, metavar=("START", "STOP"))
    p.add_argument("--split", default="train")
    p = sub.add_parser("detect", help="run the detector on frames (video environment)")
    p.add_argument("--frames", type=Path, help="npz of frame-index arrays")
    p.add_argument("--range", type=int, nargs=2, metavar=("START", "STOP"), help="half-open")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--weights", default=DetectorConfig.weights)
    p.add_argument("--imgsz", type=int, default=DetectorConfig.imgsz)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--cls", type=int, default=SPORTS_BALL)
    p = sub.add_parser("train", help="fine-tune the single-class detector (video env)")
    p.add_argument("--data", type=Path, required=True, help="the dataset folder from `prepare`")
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--weights", default="yolo11s.pt")
    p = sub.add_parser("feasibility", help="detections against the tracking ball")
    p.add_argument("--frames", type=Path, required=True)
    p.add_argument("--detections", type=Path, required=True)
    p.add_argument("--thresholds", type=float, nargs="+", help="default: the section-1 list")
    p.add_argument("--control-thresholds", type=float, nargs="+", default=[0.2, 0.3, 0.5])
    p = sub.add_parser("evaluate", help="variants on the public slice and the transplant bench")
    p.add_argument("--detections", type=Path, required=True, help="video balls for the variants")
    p.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=sorted(VARIANTS))
    p.add_argument("--design", choices=("opt", "joint"), default="opt")
    p.add_argument("--labels-dir", type=Path, help="write each variant's frame,label CSV here")
    p.add_argument("--json", type=Path, help="write the bench rows here")
    args = parser.parse_args(argv)

    from tools import atd
    from tools.ball_gaps import half_runs

    if args.command == "sample":
        _ball, present = atd.load("tactical").ball()
        chosen = sample_frames(present, [tuple(r) for r in args.span] if args.span else half_runs())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        np.savez(args.out, **chosen)
        print(json.dumps({k: len(v) for k, v in chosen.items()}))
        return 0
    if args.command == "detect":
        if args.range:
            frames = np.arange(*args.range)
        else:
            frames = np.unique(np.concatenate(list(_load_npz(args.frames).values())))
        config = DetectorConfig(weights=args.weights, imgsz=args.imgsz, cls=args.cls)
        detections, timing = detect_frames(games.video_path(), frames, Detector(config), args.batch)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        np.savez(args.out, **detections)
        print(json.dumps({"config": config.__dict__, **timing}))
        return 0
    if args.command == "train":
        return _train(args)
    if args.command == "prepare":
        ball, present = atd.load("tactical").ball()
        frames = training_frames(present, *args.span, args.count)
        if np.any((frames >= EXCLUDED[0]) & (frames < EXCLUDED[1])):
            raise ValueError("training frames overlap the excluded public window")
        u, v = project_ball(load_matrices()[frames], ball[frames])
        stats = prepare(games.video_path(), args.out, args.split, frames, u, v)
        print(json.dumps(stats))
        return 0
    if args.command == "feasibility":
        from tools import dead_ball, emision, engine

        sets = _load_npz(args.frames)
        det = _load_npz(args.detections)
        matrices = load_matrices()
        tracking = atd.load("tactical")
        ball, _present = tracking.ball()
        n = len(matrices)
        thresholds = args.thresholds or (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7)
        rows = agreement(det, sets["with_ball"], ball, matrices, thresholds)
        for row in rows:
            best = best_per_frame(det["frame"], det["conf"], n, row["conf"])
            row["gap_found"] = float((best[sets["gap"]] >= 0).mean())
        teams = emision.team_slots()
        ev = dead_ball.load_evidence()
        dead = dead_ball.dead_mask(ev, engine.halves(), "out")
        f = engine.features(tracking, teams)
        _ctrl, state, lab = engine.chain(f, engine.DEFAULT, ev.restarts, dead)
        live = (state != engine.NONE) & (lab != "D")
        ctrl_rows = control_agreement(
            det,
            matrices,
            tracking,
            teams,
            sets,
            engine.control(f),
            state,
            live,
            args.control_thresholds,
        )
        players_m = tracking.players_array[:, :, :2] * PITCH_M
        diag = diagnose(det, sets["with_ball"], ball, players_m, matrices)
        report = {
            "position": rows,
            "control": ctrl_rows,
            "diagnose": diag,
            "operating": {str(t): operating_threshold(rows, t) for t in (0.90, 0.95)},
        }
        print(json.dumps(report, indent=1))
        return 0
    if args.command == "evaluate":
        return _evaluate(args)
    return 2


TRAIN = {
    # Fixed in the addendum (proposal, section 4). The ball's pixel scale is physical, so no scale
    # or colour augmentation; mosaic would paste balls from other frames next to real ones.
    "imgsz": CROP,
    "epochs": 20,
    "batch": 16,
    "seed": 0,
    "deterministic": True,
    "hsv_h": 0.0,
    "hsv_s": 0.0,
    "hsv_v": 0.0,
    "mosaic": 0.0,
    "fliplr": 0.5,
    "scale": 0.0,
    "workers": 2,
    "plots": False,
}


def _train(args: argparse.Namespace) -> int:
    import os

    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    from ultralytics import YOLO

    data = args.data.resolve()
    yaml = data / "ball.yaml"
    yaml.write_text(
        f"path: {data.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: ball\n",
        encoding="utf-8",
    )
    model = YOLO(args.weights)
    model.train(
        data=str(yaml), project=str(args.project.resolve()), name="ft", exist_ok=True, **TRAIN
    )
    print(json.dumps({"weights": str(args.project.resolve() / "ft" / "weights" / "last.pt")}))
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    import pandas as pd

    from tools import atd, bench, dead_ball, emision
    from tools.contract import check_submission

    det = _load_npz(args.detections)
    matrices = load_matrices()
    tracking = atd.load("tactical")
    ball, present = tracking.ball()
    teams = emision.team_slots()
    ev = dead_ball.load_evidence()
    _f, _ev, gt, cut = bench.load()
    out: dict[str, dict] = {}
    for name in args.variants:
        variant = VARIANTS[name]
        lab, filled = labels_with_ball(
            variant, tracking.players_array, teams, ball, ev, det, matrices
        )
        if args.labels_dir:
            table = pd.DataFrame({"frame": np.arange(len(lab)), "label": lab})
            check_submission(table, args.labels_dir / f"{name}.csv")
            args.labels_dir.mkdir(parents=True, exist_ok=True)
            table.to_csv(args.labels_dir / f"{name}.csv", index=False, lineterminator="\n")
        donor_video = None
        if args.design == "joint" and variant.min_conf is not None:
            _xy, ok = video_ball(det, matrices, ball, Filter(min_conf=variant.min_conf))
            donor_video = ok & ~present
        rows = bench_video(
            variant,
            args.design,
            tracking.players_array,
            teams,
            ball,
            ev,
            det,
            matrices,
            gt,
            cut,
            donor_video,
        )
        out[name] = {
            "summary": bench.summary(rows),
            "rows": rows,
            "filled_match": int(filled.sum()),
        }
        print(
            name, json.dumps(out[name]["summary"]), "filled", out[name]["filled_match"], flush=True
        )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
