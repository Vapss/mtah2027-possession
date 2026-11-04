"""Test-only audit hook inherited by Python subprocesses, never used in production."""

import os
import sys

root = os.environ.get("POSSESSION_GT_GUARD_ROOT")
if root:
    forbidden = os.path.normcase(os.path.realpath(os.path.join(root, "evaluation", "gt")))

    def audit(event, args):
        if event != "open" or not args or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = os.path.normcase(os.path.realpath(os.fsdecode(args[0])))
        try:
            inside = os.path.commonpath((path, forbidden)) == forbidden
        except ValueError:  # different Windows drives
            inside = False
        if inside:
            # A swallowed PermissionError must not make the enclosing build appear clean.
            log = os.environ.get("POSSESSION_GT_GUARD_LOG")
            if log:
                with open(log, "a", encoding="utf-8") as marker:
                    marker.write("blocked\n")
            raise PermissionError("GT access forbidden during submission build")

    sys.addaudithook(audit)
    started = os.environ.get("POSSESSION_GT_GUARD_STARTED")
    if started:
        with open(started, "a", encoding="utf-8") as marker:
            marker.write(f"{os.getpid()}\n")

    if os.environ.get("POSSESSION_SYNTHETIC_BUILD") == "1":
        # Replace only unavailable licensed inputs; the actual build and its subprocesses run.
        import numpy as np

        import games
        from tools import atd, dead_ball, dead_ball_v2, emision

        n = games.source_frames()

        def tracking(*args, **kwargs):
            players = np.zeros((n, 2, 3))
            players[:, 0, :2] = (0.4, 0.5)
            players[:, 1, :2] = (0.8, 0.5)
            ball = np.zeros((n, 3))
            ball[:, :2] = (0.4, 0.5)
            return atd.Tracking(players, ball)

        class Evidence:
            restarts = ()

        atd.load = tracking
        emision.team_slots = lambda *_args: emision.TeamSlots(np.array([0, 1]), "H", "A", 1, 1)
        dead_ball.load_evidence = lambda: Evidence()
        dead_ball.dead_mask = lambda *args: np.zeros(n, dtype=bool)
        dead_ball_v2.match_kinematic = lambda *args: np.zeros(n, dtype=bool)
        dead_ball_v2.dead_union = lambda *args: np.zeros(n, dtype=bool)
