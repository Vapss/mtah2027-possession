"""Lane restart-team: WHICH TEAM restarts after a tagged stoppage whose tag names none.

    python tools/restart_team.py dfl                       # offline: every variant on DFL
    python tools/restart_team.py --match                   # BAR-ATH, no ground truth
    python tools/restart_team.py --variant agree --labels runs/restart_team/agree.csv --gt public
    python tools/restart_team.py --bench                   # gap-transplant bench, every variant

Why
---
The delivered chain forces possession to the restarting team of every tagged `SET PIECES`
(DECISIONS 30-35), but 32 of BAR-ATH's 59 tags carry no team: all 26 throw-ins and all 6
kick-offs. `engine.restart_controls` skips them, so after a throw-in the engine carries the team
that put the ball out -- by law the wrong one -- until the next uncontested control, and a half
whose kick-off is not seen stays `X` until its first control. This lane names their team, from
two kinds of evidence, and abstains (leaves the restart unforced, as today) when it is ambiguous:

- P, positions (`by_position`): the team holding the ball while the restart is prepared. A frame
  with the ball observed -- inside or OUTSIDE the pitch: a throw-in is held behind the line -- is
  held by a team when its nearest player is within `take_m` of the ball and the other team's
  nearest is `clear_m` or farther (Law 15: opponents stand 2 m from a throw-in; 9,15 m at a
  kick-off). P names a team when every held frame of the tag's window before the estimated restart
  is that team's.
- L, the law (`law_team`): a throw-in or a kick-off after a goal goes to the opponents of the team
  in possession when the ball went out (the stoppage's start, `dead_ball.stoppages`), read on the
  variant's own chain in frame order; the kick-off starting a half goes to the opponents of the
  team that kicked off the other half (named by P).

Four variants combine them (`combine`): `law`, `pos`, `pos+law` (P, L where P abstains) and
`agree` (only where both name the same team). Each is the delivered chain with only those teams
changed; `engine` reproduces `engine.run()` frame for frame. A named restart is forced exactly
like a tagged one, including DECISIONS 32/35: not where the tracking already saw an accepted
control inside the tag's window. Constants and the selection rule are pre-registered in
docs/proposals/lane-restart-team.md.

The DFL corpus has no Smart Tagging, and its dead ball is frozen where it died and jumps to the
restart spot on the first live frame. `dfl_tags` builds synthetic tags from its alive/dead status
and the restart spot (the kind), team-less for throw-ins and kick-offs as ours are, with the
estimate off the true restart by lane d-edges' cycle of errors. P meets the frozen ball there,
not a ball carried to the line: see the proposal, section 5.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import dead_ball, dead_ball_v2, engine  # noqa: E402

FPS = engine.FPS
NONE = engine.NONE

THROW_IN = "Throw-in"
KICK_OFF_START = dead_ball.KICK_OFF_START
KICK_OFF_GOAL = dead_ball.KICK_OFF_GOAL
# The tagged kinds this lane names a team for: in BAR-ATH, exactly the tags without one.
TEAMLESS = (THROW_IN, KICK_OFF_GOAL, KICK_OFF_START)

VARIANTS = ("engine", "law", "pos", "pos+law", "agree")

# The estimate's error on the synthetic DFL tags: lane d-edges' cycle, unchanged.
DFL_ERRORS_S = (-2.0, -1.0, 0.0, 1.0, 2.0)


@dataclass(frozen=True)
class Params:
    """Fixed before any variant met a label (docs/proposals/lane-restart-team.md, section 3)."""

    # Within reach of the ball: the engine's own control radius.
    take_m: float = engine.DEFAULT.radius_m
    # Law 15: at a throw-in every opponent stands at least 2 m from where it is taken (9,15 m at a
    # kick-off, Law 8, so 2 m tells those apart too).
    clear_m: float = 2.0
    # The Smart Tagging phase vote is read this long after a newly forced restart (report only).
    vote_s: float = 5.0


DEFAULT = Params()


# -- the evidence --------------------------------------------------------------------------------


def holders(f: engine.Features, params: Params = DEFAULT) -> np.ndarray:
    """Per frame, `0`/`1` for the team clearly holding the ball, `NONE` when nobody clearly does.

    Positions only, the ball inside or outside the pitch; an unobserved ball or an unknown distance
    is no evidence (`NaN` compares false), and a team with nobody tracked is infinitely far.
    """
    home = np.asarray(f.home_m, dtype=float)
    away = np.asarray(f.away_m, dtype=float)
    near = np.minimum(home, away)
    far = np.maximum(home, away)
    held = np.asarray(f.present, dtype=bool) & (near <= params.take_m) & (far >= params.clear_m)
    team = np.full(len(home), NONE, dtype=np.int8)
    team[held & (home < away)] = 0
    team[held & (away < home)] = 1
    return team


def _half(frame: int, runs: Sequence[tuple[int, int]]) -> tuple[int, int] | None:
    for start, stop in runs:
        if start <= frame < stop:
            return start, stop
    return None


def by_position(
    restart: dead_ball.Restart,
    held: np.ndarray,
    runs: Sequence[tuple[int, int]],
    anchor: int | None = None,
) -> int | None:
    """P: the one team holding the ball in `[tag_start, frame)`, kept inside the restart's half
    and, when `anchor` is known, after the ball went out: before it, the ball was in play and its
    holder is the previous play's, not the restart's (amendment, proposal section 4).

    `None` when nobody holds it in the window, or when both teams do on different frames.
    """
    half = _half(restart.frame, runs)
    if half is None:
        return None
    lo = max(restart.tag_start, half[0], 0, anchor if anchor is not None else 0)
    hi = min(restart.frame, half[1], len(held))
    seen = np.unique(held[lo:hi]) if hi > lo else np.array([], dtype=np.int8)
    seen = seen[seen != NONE]
    return int(seen[0]) if len(seen) == 1 else None


def anchors(ev: dead_ball.Evidence, runs: Sequence[tuple[int, int]]) -> list[int | None]:
    """Per restart, where its tagged stoppage begins (`dead_ball.stoppages`, variant `out`):
    the ball's last exit from the pitch before the tag, or the tag itself. `None` outside a half.

    `stoppages` walks the halves and, inside each, the restarts in order, one stoppage each; this
    walks them the same way to pair them.
    """
    found = iter(dead_ball.stoppages(ev, runs, "out"))
    n = len(ev.out)
    out: list[int | None] = [None] * len(ev.restarts)
    for start, stop in runs:
        start, stop = max(0, start), min(n, stop)
        for i, r in enumerate(ev.restarts):
            if start <= r.frame < stop:
                s = next(found)
                if s.stop != r.frame:
                    raise ValueError(f"stoppage ending at {s.stop} paired with restart {r.frame}")
                out[i] = s.start
    return out


def law_team(state: np.ndarray, anchor: int | None, half_start: int) -> int | None:
    """L: the opponents of the team in possession on the frame before the ball went out."""
    if anchor is None or anchor <= half_start:
        return None
    team = int(state[anchor - 1])
    return None if team == NONE else 1 - team


def combine(variant: str, kind: str, pos: int | None, law: int | None) -> int | None:
    """The team a variant names from P and L, or `None` to leave the restart unforced."""
    if variant == "law":
        # The law alone does not know who kicked off first (a coin toss): its L of a half's
        # kick-off is P of the other half's.
        return None if kind == KICK_OFF_START else law
    if variant == "pos":
        return pos
    if variant == "pos+law":
        return pos if pos is not None else law
    if variant == "agree":
        return pos if pos is not None and pos == law else None
    raise ValueError(f"unknown variant {variant!r}; expected one of {', '.join(VARIANTS[1:])}")


# -- the inference ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Inference:
    """The restarts with the variant's teams, and per restart what each source said.

    `rows` has one entry per team-less restart of a `TEAMLESS` kind: its index in `restarts`,
    kind, frame, P, L, the team named, and whether the chain forces it (DECISIONS 32/35 can still
    cancel a named restart).
    """

    restarts: tuple[dead_ball.Restart, ...]
    rows: tuple[dict, ...]


def infer(
    f: engine.Features,
    ev: dead_ball.Evidence,
    variant: str,
    params: engine.Params = engine.DEFAULT,
    rt: Params = DEFAULT,
    runs: Sequence[tuple[int, int]] | None = None,
) -> Inference:
    """Name the team of every team-less `TEAMLESS` restart of `ev` as `variant` does.

    Restarts are visited in frame order, and L reads the possession of the variant's own chain:
    the delivered decoder with the tagged teams and every team this variant has named so far, so
    a throw-in right after another one sees the first one's team. Other restarts are unchanged.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; expected one of {', '.join(VARIANTS)}")
    runs = [tuple(r) for r in (runs if runs is not None else engine.halves())]
    restarts = list(ev.restarts)
    todo = [i for i, r in enumerate(restarts) if r.team is None and r.kind in TEAMLESS]
    if variant == "engine" or not todo:
        return Inference(tuple(restarts), ())

    ctrl, switch, _ = engine.inputs(f, params, None)
    accepted = switch if switch is not None else ctrl
    held = holders(f, rt)
    anchor = anchors(ev, runs)
    pos = {i: by_position(restarts[i], held, runs, anchor[i]) for i in todo}

    # The kick-off of each half, by law the other half's opponents: exactly one per half.
    starts: dict[tuple[int, int], list[int]] = {}
    for i in todo:
        half = _half(restarts[i].frame, runs)
        if restarts[i].kind == KICK_OFF_START and half is not None:
            starts.setdefault(half, []).append(i)
    other: dict[int, int] = {}
    if len(starts) == 2 and all(len(v) == 1 for v in starts.values()):
        (a,), (b,) = starts.values()
        other = {a: b, b: a}

    teams = [r.team for r in restarts]
    law: dict[int, int | None] = {}
    for i in sorted(todo, key=lambda k: (restarts[k].frame, restarts[k].tag_start)):
        r = restarts[i]
        if r.kind == KICK_OFF_START:
            mate = pos.get(other[i]) if i in other else None
            law[i] = None if mate is None else 1 - mate
        else:
            current = [dataclasses.replace(x, team=t) for x, t in zip(restarts, teams)]
            forced = engine.restart_controls(current, accepted)
            state = engine.decode(ctrl, runs, params.dwell, forced, switch)
            half = _half(r.frame, runs)
            law[i] = law_team(state, anchor[i], half[0]) if half is not None else None
        teams[i] = combine(variant, r.kind, pos[i], law[i])

    named = tuple(dataclasses.replace(x, team=t) for x, t in zip(restarts, teams))
    forced = engine.restart_controls(named, accepted)
    rows = tuple(
        {
            "index": i,
            "kind": restarts[i].kind,
            "frame": restarts[i].frame,
            "pos": pos[i],
            "law": law[i],
            "team": teams[i],
            "forced": teams[i] is not None and forced.get(restarts[i].frame) == teams[i],
        }
        for i in todo
    )
    return Inference(named, rows)


# -- the chain -------------------------------------------------------------------------------------


def chain(
    f: engine.Features,
    ev: dead_ball.Evidence,
    kinematic: np.ndarray,
    variant: str,
    params: engine.Params = engine.DEFAULT,
    rt: Params = DEFAULT,
) -> np.ndarray:
    """The delivered chain with this variant's restart teams: H/A/D/X for the whole match.

    `D` is the delivered one (tagged stoppages united with the players' `kinematic`, as
    `engine.delivered_dead`), which no team changes; `engine.chain` decodes with the restarts.
    """
    runs = engine.halves()
    dead = dead_ball.dead_mask(ev, runs, "out") | np.asarray(kinematic, dtype=bool)
    restarts = infer(f, ev, variant, params, rt, runs).restarts
    return engine.chain(f, params, restarts, dead)[2]


def match_kinematic() -> np.ndarray:
    """BAR-ATH's players' stoppages, W1 exactly as delivered (DECISIONS 36)."""
    return np.array(engine._players_stoppages())


def bench_methods(
    kinematic: np.ndarray,
) -> dict[str, Callable[[engine.Features, dead_ball.Evidence], np.ndarray]]:
    """Bench methods (`tools/bench.py` signature) for every variant, `engine` included. The bench
    degrades the ball, never the players or the tags, so the players' mask is closed over once;
    P and L still run on the degraded ball."""
    return {v: (lambda f, ev, v=v: chain(f, ev, kinematic, v)) for v in VARIANTS}


# -- the DFL corpus (offline; public CC-BY data, never mixed with the match data) ------------------

# The DFL instrument that tells a restart's kind from the ball on the first live frame, which DFL
# teleports to the restart spot. Checked only against the counts of DFL's own event files
# (docs/proposals/lane-restart-team.md, section 2.2), never against a team.
DFL_CENTRE_M = 2.0  # from the centre spot: a kick-off
DFL_LINE_M = 1.5  # from a touchline, or beyond it: a throw-in ...
DFL_END_M = 3.0  # ... unless this close to a goal line; near both lines it is a corner


def dfl_ball(r) -> np.ndarray:
    """The ball of an `external.Raw`, laid out like `external.build`: metres from a corner, the
    halves concatenated with `external.HALF_GAP` empty frames between them."""
    from tools import external

    length, width = r.pitch
    parts = []
    for i, s in enumerate(r.sections):
        if i:
            parts.append(np.full((external.HALF_GAP, 2), np.nan))
        parts.append(s.ball + np.array([length / 2, width / 2]))
    return np.concatenate(parts)


def dfl_kind(xy: np.ndarray, pitch: tuple[float, float]) -> str:
    """The kind of a DFL restart from where the ball is put back in play."""
    length, width = pitch
    x, y = float(xy[0]), float(xy[1])
    if np.hypot(x - length / 2, y - width / 2) < DFL_CENTRE_M:
        return KICK_OFF_GOAL
    near_end = x < DFL_END_M or x > length - DFL_END_M
    near_side = y < DFL_LINE_M or y > width - DFL_LINE_M
    if near_side and not near_end:
        return THROW_IN
    if near_end and (y < DFL_END_M or y > width - DFL_END_M):
        return "Corner Kick"
    return "Goal Kick" if near_end else "Free Kick"


_TEAM = {"H": 0, "A": 1}


def dfl_tags(
    truth: np.ndarray,
    ball: np.ndarray,
    pitch: tuple[float, float],
    out: np.ndarray,
    runs: Sequence[tuple[int, int]],
    errors_s: Sequence[float] = DFL_ERRORS_S,
    params: dead_ball.Params = dead_ball.DEFAULT,
) -> tuple[tuple[dead_ball.Restart, ...], tuple[int | None, ...]]:
    """Synthetic Smart Tagging for a DFL match, and the true restarting team of each tag.

    Per half, a `Kick Off (Start)` on its first live frame; then, per run of `D` strictly inside
    the half, a tag when its frozen ball lies outside the pitch on its last dead frame (lane
    d-edges' rule) or when the restart is a throw-in or a kick-off (`dfl_kind`). Throw-ins and
    kick-offs carry no team, as ours do; the others carry the truth's. The estimate sits
    `errors_s[i % len]` seconds off the true restart (cycled over the tags in frame order, kept
    inside the half and at least one frame after the stoppage's first dead frame) and the tag
    starts 5 s before it (3,5 s for a kick-off), as
    `dead_ball.restarts` dates ours. The true team is the one the truth names on the first live
    frame, `None` where it names none.
    """
    truth = np.asarray(truth)
    out = np.asarray(out, dtype=bool)
    found: list[tuple[dead_ball.Restart, int | None]] = []

    def tag(true: int, kind: str, a: int, floor: int, b: int, team: int | None) -> None:
        # The estimate never lands before the ball went out (`floor`, amendment, proposal
        # section 5); the tag may still start before it, as a real 5 s tag can.
        error = errors_s[len(found) % len(errors_s)]
        frame = min(max(true + int(round(error * FPS)), floor), b - 1)
        offset = params.kick_off_restart_s if kind.startswith("Kick Off") else params.restart_s
        tag_start = max(a, frame - params.frames(offset))
        restart = dead_ball.Restart(frame, tag_start, kind, team)
        found.append((restart, _TEAM.get(str(truth[true]))))

    for a, b in runs:
        dead = truth[a:b] == "D"
        live = np.flatnonzero(~dead)
        if not live.size:
            continue
        tag(a + int(live[0]), KICK_OFF_START, a, a, b, None)
        for start, stop in dead_ball_v2.runs_of(dead):
            start, stop = a + start, a + stop
            if start == a or stop >= b:
                continue
            kind = dfl_kind(ball[stop], pitch)
            if kind not in TEAMLESS and not out[stop - 1]:
                continue
            team = None if kind in TEAMLESS else _TEAM.get(str(truth[stop]))
            tag(stop, kind, a, start + 1, b, team)
    found.sort(key=lambda item: (item[0].frame, item[0].tag_start))
    return tuple(r for r, _ in found), tuple(t for _, t in found)


@dataclass(frozen=True)
class DflMatch:
    """One DFL match in our shape, with the players' stoppages and what tags need rebuilding."""

    match: object  # external.Match, its evidence holding the synthetic tags
    kinematic: np.ndarray  # W1 on its players
    truths: tuple[int | None, ...]  # the true team of each tag
    ball: np.ndarray
    pitch: tuple[float, float]


def dfl_load(match_id: str, errors_s: Sequence[float] = DFL_ERRORS_S) -> DflMatch:
    from tools import dead_ball_v3, external

    r = external.raw(match_id)
    m = external.build(r)
    players, runs = dead_ball_v3.dfl_players(r)
    kin = dead_ball_v2.kinematic_mask(players, (), runs, "rule")
    ball = dfl_ball(r)
    return dfl_retag(DflMatch(m, kin, (), ball, r.pitch), errors_s)


def dfl_retag(d: DflMatch, errors_s: Sequence[float]) -> DflMatch:
    """The same match with its synthetic tags rebuilt under another error cycle."""
    m = d.match
    tags, truths = dfl_tags(m.truth, d.ball, d.pitch, m.evidence.out, m.runs, errors_s)
    m = dataclasses.replace(m, evidence=dataclasses.replace(m.evidence, restarts=tags))
    return dataclasses.replace(d, match=m, truths=truths)


def kind_group(kind: str) -> str:
    return {THROW_IN: "throw-in", KICK_OFF_GOAL: "kick-off-goal", KICK_OFF_START: "kick-off-start"}[
        kind
    ]


def accuracy(inference: Inference, truths: Sequence[int | None]) -> dict[str, dict[str, int]]:
    """Per kind group and in total: restarts with a known true team, and for the variant's team,
    P and L, how many decided and how many were right."""
    out: dict[str, dict[str, int]] = {}
    for row in inference.rows:
        true = truths[row["index"]]
        if true is None:
            continue
        for group in (kind_group(row["kind"]), "all"):
            c = out.setdefault(group, {"n": 0})
            c["n"] += 1
            for source in ("team", "pos", "law"):
                said = row.get(source)
                if said is None:
                    continue
                c[f"{source}_decided"] = c.get(f"{source}_decided", 0) + 1
                c[f"{source}_right"] = c.get(f"{source}_right", 0) + int(said == true)
    return out


def _add(total: dict, part: dict) -> None:
    for group, counts in part.items():
        g = total.setdefault(group, {})
        for key, value in counts.items():
            g[key] = g.get(key, 0) + value


def _rates(counts: dict[str, dict[str, int]]) -> dict[str, dict[str, float | int]]:
    out: dict[str, dict[str, float | int]] = {}
    for group, c in counts.items():
        row: dict[str, float | int] = {"n": c.get("n", 0)}
        for source in ("team", "pos", "law"):
            decided = c.get(f"{source}_decided", 0)
            row[f"{source}_decided"] = decided
            row[f"{source}_coverage"] = decided / c["n"] if c.get("n") else float("nan")
            row[f"{source}_accuracy"] = (
                c.get(f"{source}_right", 0) / decided if decided else float("nan")
            )
        out[group] = row
    return out


def _dfl_infer(d: DflMatch, variant: str, degraded: bool, donors) -> Inference:
    from tools import external

    m = external.degrade(d.match, donors) if degraded else d.match
    with external.halves_of(m):
        return infer(m.features, m.evidence, variant, runs=m.runs)


def dfl(matches: Sequence[str] | None = None) -> dict:
    """Every variant on every DFL match: the named teams against the truth, clean and with our
    ball (cycled errors) and clean with each error fixed, and official spellF1 against `engine`."""
    from tools import external

    donors = external.our_ball_halves()
    names = list(matches or external.MATCHES)
    spell = {v: {"clean": [], "degraded": []} for v in VARIANTS}
    acc = {v: {"clean": {}, "degraded": {}} for v in VARIANTS[1:]}
    fixed = {f"{v}|{e:+g}": {} for v in VARIANTS[1:] for e in DFL_ERRORS_S}
    for match in names:
        d = dfl_load(match)
        for variant in VARIANTS:
            method = lambda f, ev, v=variant, k=d.kinematic: chain(f, ev, k, v)  # noqa: E731
            for degraded in (False, True):
                row = external.score(method, [d.match], degraded, donors).iloc[0]
                spell[variant]["degraded" if degraded else "clean"].append(float(row["spell_f1"]))
                if variant != "engine":
                    inf = _dfl_infer(d, variant, degraded, donors)
                    _add(acc[variant]["degraded" if degraded else "clean"], accuracy(inf, d.truths))
        for error in DFL_ERRORS_S:
            de = dfl_retag(d, (error,))
            for variant in VARIANTS[1:]:
                inf = _dfl_infer(de, variant, False, donors)
                _add(fixed[f"{variant}|{error:+g}"], accuracy(inf, de.truths))
    result: dict = {"matches": names, "variants": {}}
    base_c, base_d = spell["engine"]["clean"], spell["engine"]["degraded"]
    for variant in VARIANTS:
        clean, degr = spell[variant]["clean"], spell[variant]["degraded"]
        entry: dict = {
            "spell_f1_clean": clean,
            "spell_f1_degraded": degr,
            "mean_clean": float(np.mean(clean)),
            "mean_degraded": float(np.mean(degr)),
            "wins_clean": int(sum(x > y for x, y in zip(clean, base_c))),
            "wins_degraded": int(sum(x > y for x, y in zip(degr, base_d))),
            "losses_clean": int(sum(x < y for x, y in zip(clean, base_c))),
            "losses_degraded": int(sum(x < y for x, y in zip(degr, base_d))),
        }
        if variant != "engine":
            entry["accuracy_clean"] = _rates(acc[variant]["clean"])
            entry["accuracy_degraded"] = _rates(acc[variant]["degraded"])
        result["variants"][variant] = entry
    result["fixed_error_accuracy_clean"] = {key: _rates(c) for key, c in fixed.items()}
    return result


# -- BAR-ATH, without ground truth ----------------------------------------------------------------


def st_after(
    rows: Sequence[dict], votes: np.ndarray, rt: Params = DEFAULT
) -> dict[str, float | int]:
    """The Smart Tagging phase vote in `[frame, frame + vote_s)` after each forced named restart:
    frames voting for one side only that agree with the forced team, and restarts whose majority
    of such frames does."""
    width = int(round(rt.vote_s * FPS))
    frames = agree = restarts = majority = 0
    for row in rows:
        if not row.get("forced"):
            continue
        v = votes[row["frame"] : row["frame"] + width]
        single = (v[:, 0] > 0) ^ (v[:, 1] > 0)
        if not single.any():
            continue
        side = np.where(v[single, 0] > 0, 0, 1)
        hit = int((side == row["team"]).sum())
        frames += int(single.sum())
        agree += hit
        restarts += 1
        majority += int(2 * hit > int(single.sum()))
    return {
        "restarts_with_vote": restarts,
        "restarts_majority_agree": majority,
        "frames_with_vote": frames,
        "frame_agreement": agree / frames if frames else float("nan"),
    }


def match_report() -> dict:
    """Every variant on BAR-ATH, aggregates only: who decides what, P against L, the Smart Tagging
    after each newly forced restart (docs/proposals/lane-restart-team.md, measurement 2)."""
    from tools import atd, emision, smart_tagging

    f = engine.features(atd.load("tactical"), emision.team_slots())
    ev = dead_ball.load_evidence()
    votes = smart_tagging.possession_votes(smart_tagging.load())
    out: dict = {}
    for variant in VARIANTS[1:]:
        inf = infer(f, ev, variant)
        kinds: dict[str, dict[str, int]] = {}
        for row in inf.rows:
            k = kinds.setdefault(kind_group(row["kind"]), {})
            k["n"] = k.get("n", 0) + 1
            for key, flag in (
                ("pos_decided", row["pos"] is not None),
                ("law_decided", row["law"] is not None),
                ("both_decided", row["pos"] is not None and row["law"] is not None),
                ("both_agree", row["pos"] is not None and row["pos"] == row["law"]),
                ("named", row["team"] is not None),
                ("forced", bool(row["forced"])),
            ):
                k[key] = k.get(key, 0) + int(flag)
        throw = kinds.get("throw-in", {})
        both = throw.get("both_decided", 0)
        out[variant] = {
            "by_kind": kinds,
            "throw_in_pos_vs_law": {
                "both_decided": both,
                "agreement": throw.get("both_agree", 0) / both if both else float("nan"),
            },
            "st_after_forced": st_after(inf.rows, votes),
        }
    return out


def _json_default(value):
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value).__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Which team restarts (lane restart-team)")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("dfl", help="every variant on DFL with synthetic tags, clean and degraded")
    parser.add_argument("--variant", choices=VARIANTS, default="agree")
    parser.add_argument("--labels", type=Path, help="write the frame,label CSV here")
    parser.add_argument("--gt", choices=["public"], help="score against the public slice")
    parser.add_argument("--bench", action="store_true", help="gap-transplant bench, all variants")
    parser.add_argument("--match", action="store_true", help="BAR-ATH aggregates, no ground truth")
    args = parser.parse_args(argv)
    try:
        if args.command == "dfl":
            print(json.dumps(dfl(), indent=2, default=_json_default))
            return 0
        if args.match:
            print(json.dumps(match_report(), indent=2, default=_json_default))
            return 0
        if args.bench:
            from tools import bench

            f, ev, gt, cut = bench.load()
            for name, method in bench_methods(match_kinematic()).items():
                print(name, json.dumps(bench.summary(bench.bench(method, f, ev, gt, cut))))
            return 0

        from tools import atd, emision

        f = engine.features(atd.load("tactical"), emision.team_slots())
        ev = dead_ball.load_evidence()
        labels = chain(f, ev, match_kinematic(), args.variant)
        result: dict = {"variant": args.variant}
        if args.labels:
            from tools.contract import check_submission

            table = pd.DataFrame({"frame": np.arange(len(labels)), "label": labels})
            table = check_submission(table, args.labels)
            args.labels.parent.mkdir(parents=True, exist_ok=True)
            table.to_csv(args.labels, index=False, lineterminator="\n")
        if args.gt:
            from tools import dead_ball_v3

            result["public"] = dead_ball_v3._public_report(labels)
    except (OSError, ValueError, RuntimeError) as problem:
        print(f"restart_team failed: {problem}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
