"""Audit ELASTIC reception coverage against external DFL files; never score a model.

Only the two preregistered development matches in docs/proposals/elastic-feasibility.md are
accepted. Input files stay under runs/external; the output contains aggregate counts only.
Reading parquet requires an exploratory installation of pyarrow or fastparquet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import external  # noqa: E402

DEVELOPMENT = ("J03WMX", "J03WN1")
FRAME = re.compile(r'<Frame N="(\d+)"')
PERIODS = {1: "firstHalf", 2: "secondHalf"}
EXPECTED_SHA256 = {
    "J03WMX": {
        "anotaciones": "3bf246033e8df7028563f8b90ecf338212063b6aed9ac6772741d429feded52b",
        "metadatos": "a884728647a564cf8b20e5223a1d04a5da6f6725e1e506c8651505327c197ba9",
        "tracking": "d3dd92e509421a6466acb0a083c009035f1751bc5fd9ef42ffa8f20d01cf7d49",
    },
    "J03WN1": {
        "anotaciones": "20cf64b5169099ed3577c30a6bf23eda316fea6f5927e1061496f5f6dccf7681",
        "metadatos": "5490286436c86e6f80a538d2b1b379d0efd016e0defcaf594bc59d9ef5079f4c",
        "tracking": "56ef948961a18e150dba0b7b16869d0008ff66f3050a0c355d31fa5b8ec2fcec",
    },
}


def roster(path: Path) -> dict[str, str | None]:
    """Map ELASTIC's team/shirt identifier to a unique DFL player ID, or None if ambiguous."""
    mapping: dict[str, set[str]] = defaultdict(set)
    for team in ET.parse(path).getroot().findall(".//Team"):
        role = {"home": "home", "guest": "away"}.get(team.get("Role", "").lower())
        if role is None:
            continue
        for player in team.findall("./Players/Player"):
            number, person = player.get("ShirtNumber"), player.get("PersonId")
            if number and number.isdigit() and person:
                mapping[f"{role}_{int(number)}"].add(person)
    return {key: next(iter(value)) if len(value) == 1 else None for key, value in mapping.items()}


def prepare(events: pd.DataFrame, players: dict[str, str | None]) -> tuple[list[dict], Counter]:
    """Classify each annotated reception without using the DFL possession label as a filter."""
    required = {"period_id", "receiver_id", "receive_frame_id", "spadl_type"}
    if not required.issubset(events.columns):
        raise ValueError(f"missing annotation columns: {sorted(required - set(events.columns))}")
    counts: Counter = Counter(total_events=len(events))
    valid = []
    for row in events.itertuples(index=False):
        receiver, frame, period = row.receiver_id, row.receive_frame_id, row.period_id
        if pd.isna(receiver) or pd.isna(frame):
            counts["missing_reception"] += 1
            continue
        counts["has_reception"] += 1
        if period not in PERIODS:
            counts["invalid_period"] += 1
            continue
        try:
            numeric = float(frame)
        except (ValueError, TypeError):
            numeric = math.nan
        if not math.isfinite(numeric) or not numeric.is_integer():
            counts["invalid_frame"] += 1
            continue
        if receiver in {"out_left", "out_right", "out_top", "out_bottom"}:
            counts["terminal_out"] += 1
            continue
        if receiver in {"goal_left", "goal_right"}:
            counts["terminal_goal"] += 1
            continue
        if receiver not in players:
            counts["receiver_not_in_roster"] += 1
            continue
        if players[receiver] is None:
            counts["receiver_ambiguous"] += 1
            continue
        valid.append(
            {
                "period": int(period),
                "frame": int(numeric),
                "person": players[receiver],
                "receiver": receiver,
                "kind": str(row.spadl_type),
                "actor": getattr(row, "player_id", None),
            }
        )
    counts["eligible_for_tracking_check"] = len(valid)
    return valid, counts


def inspect_tracking(path: Path, events: list[dict]) -> dict[str, Any]:
    """Stream only relevant frame IDs and report coverage, not coordinates or frame-level data."""
    targets = {(PERIODS[e["period"]], e["frame"]) for e in events}
    people = {(PERIODS[e["period"]], e["person"], e["frame"]) for e in events}
    ball: dict[tuple[str, int], tuple[int | None, int | None]] = {}
    observed: set[tuple[str, str, int]] = set()
    section = team = person = None
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.startswith("<FrameSet "):
                found, who = external._FRAMESET.search(line), external._PERSON.search(line)
                section, team = found.groups() if found else (None, None)
                person = who.group(1) if who else None
            elif line.startswith("</FrameSet"):
                section = team = person = None
            elif line.startswith("<Frame ") and section in PERIODS.values():
                frame = FRAME.match(line)
                if not frame:
                    continue
                number = int(frame.group(1))
                if team == "BALL" and (section, number) in targets:
                    label = external._BALL.search(line)
                    if label:
                        owner = int(label.group(1)) if label.group(1) else None
                        status = int(label.group(2)) if label.group(2) else None
                        ball[(section, number)] = (owner, status)
                    else:
                        ball[(section, number)] = (None, None)
                elif person and (section, person, number) in people:
                    observed.add((section, person, number))
    counts: Counter = Counter()
    statuses: Counter = Counter()
    ownership: Counter = Counter()
    owner_comparison: Counter = Counter()
    for event in events:
        key = (PERIODS[event["period"]], event["frame"])
        if key not in ball:
            counts["ball_frame_missing"] += 1
            continue
        counts["ball_frame_present"] += 1
        owner, status = ball[key]
        statuses[str(status)] += 1
        ownership[str(owner)] += 1
        expected = {"home": 1, "away": 2}.get(event["receiver"].split("_", 1)[0])
        if owner not in (1, 2) or expected is None:
            owner_comparison["unknown"] += 1
        elif owner == expected:
            owner_comparison["same"] += 1
        else:
            owner_comparison["different"] += 1
        if (key[0], event["person"], key[1]) in observed:
            counts["receiver_frame_present"] += 1
        else:
            counts["receiver_frame_missing"] += 1
    return {
        "coverage": dict(sorted(counts.items())),
        "ball_status": dict(statuses),
        "ball_owner": dict(ownership),
        "receiver_vs_ball_owner": dict(owner_comparison),
    }


def summarize(
    events: pd.DataFrame, players: dict[str, str | None], tracking: Path
) -> dict[str, Any]:
    valid, counts = prepare(events, players)
    keys = [(e["period"], e["frame"], e["receiver"]) for e in valid]
    by_frame: dict[tuple[int, int], set[str]] = defaultdict(set)
    for period, frame, receiver in keys:
        by_frame[(period, frame)].add(receiver)
    relations: Counter = Counter()
    for event in valid:
        actor = event["actor"]
        receiver = event["receiver"]
        if actor not in players or players[actor] is None:
            relations["actor_unknown"] += 1
        elif actor.split("_", 1)[0] == receiver.split("_", 1)[0]:
            relations["same_team"] += 1
        else:
            relations["opposing_team"] += 1
    competing = sum(
        len({receiver.split("_", 1)[0] for receiver in receivers}) > 1
        for receivers in by_frame.values()
    )
    return {
        "events": dict(sorted(counts.items())),
        "event_types": dict(sorted(Counter(e["kind"] for e in valid).items())),
        "actor_vs_receiver": dict(sorted(relations.items())),
        "duplicate_reception_rows": len(keys) - len(set(keys)),
        "frames_with_multiple_receivers": sum(
            len(receivers) > 1 for receivers in by_frame.values()
        ),
        "frames_with_opposing_receivers": competing,
        **inspect_tracking(tracking, valid),
    }


def file_hash(path: Path) -> str:
    """Fingerprint an external input without writing or displaying its rows."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_hashes(match: str, actual: dict[str, str]) -> None:
    """Reject mismatched inputs instead of misattributing them to the documented revisions."""
    if actual != EXPECTED_SHA256[match]:
        raise ValueError(f"external input fingerprints differ for {match}")


def report(results: dict[str, dict[str, Any]]) -> str:
    """Format aggregate results and provenance; no predicted labels are involved."""
    command = " ".join(
        ("python tools/elastic_audit.py all --write", "docs/analysis/elastic-feasibility.md")
    )
    lines = [
        "# ELASTIC: factibilidad de recepciones externas para #63",
        "",
        "Auditoría descriptiva de los partidos de desarrollo; no puntúa ni elige una variante.",
        "Protocolo previo: `docs/proposals/elastic-feasibility.md`. `J03WPY` sigue reservado.",
        "Los eventos ELASTIC y el dataset DFL se distribuyen bajo CC BY 4.0: citar Kim et al.,",
        "ELASTIC (CIKM 2026, doi:10.1145/3799682.3841035) y Bassek et al. (Scientific Data 12:195,",
        "doi:10.1038/s41597-025-04505-y). El código ELASTIC no se incorpora.",
        "",
        "| Medida | J03WMX | J03WN1 |",
        "|---|---:|---:|",
    ]
    rows = [
        ("Eventos totales", lambda r: r["events"]["total_events"]),
        ("Eventos sin recepción", lambda r: r["events"].get("missing_reception", 0)),
        (
            "Periodo o frame inválido",
            lambda r: r["events"].get("invalid_period", 0) + r["events"].get("invalid_frame", 0),
        ),
        (
            "Destinos terminales fuera / gol",
            lambda r: (
                f"{r['events'].get('terminal_out', 0)} / {r['events'].get('terminal_goal', 0)}"
            ),
        ),
        (
            "Receptores no presentes o ambiguos en plantel",
            lambda r: (
                r["events"].get("receiver_not_in_roster", 0)
                + r["events"].get("receiver_ambiguous", 0)
            ),
        ),
        ("Recepciones elegibles", lambda r: r["events"]["eligible_for_tracking_check"]),
        ("Frame de balón presente", lambda r: r["coverage"].get("ball_frame_present", 0)),
        ("Balón en juego según DFL", lambda r: r["ball_status"].get("1", 0)),
        ("Frame de receptor presente", lambda r: r["coverage"].get("receiver_frame_present", 0)),
        (
            "Receptor del equipo rival al actor",
            lambda r: r["actor_vs_receiver"].get("opposing_team", 0),
        ),
        ("Frames con receptores de ambos equipos", lambda r: r["frames_with_opposing_receivers"]),
        (
            "Equipo receptor distinto al propietario DFL",
            lambda r: r["receiver_vs_ball_owner"].get("different", 0),
        ),
    ]
    for title, metric in rows:
        lines.append(f"| {title} | {metric(results['J03WMX'])} | {metric(results['J03WN1'])} |")
    lines += [
        "",
        "La coincidencia de receptor y propietario DFL es una descripción entre fuentes, no",
        "exactitud: pueden diferir por balón suelto, acciones de un toque, convenciones o fechas.",
        "ELASTIC asigna `receiver_id` al colapsar acciones finales, incluidas acciones de un toque",
        "y algunas acciones defensivas; no equivale automáticamente a control sostenido (ver",
        "`sync/utils.py` en la revisión de ELASTIC citada abajo).",
        "El origen de las fechas en animaciones del mismo tracking introduce dependencia. Los",
        "eventos no constituyen automáticamente posesiones. Distinguir contacto de control sigue",
        "pendiente; esta auditoría no autoriza elegir umbrales ni la regla del duelo.",
        "",
        "Reproducir con el entorno fijado del proyecto más `pyarrow==26.0.1` (solo exploración)",
        "y los archivos externos en `runs/external/`:",
        f"`{command}`.",
        "El script no lee datos del partido de competición.",
        "",
        "Fuente: ELASTIC `e245224aad7450961eca40954ae2bc85e1e6e696`; espejo DFL",
        "`pysport/idsse-data` revisión `a715a38dfbaf5f58e431727c2b78d174101a703c`.",
        "Hashes SHA-256 de los archivos leídos:",
        "",
    ]
    for match in DEVELOPMENT:
        for kind, digest in results[match]["input_sha256"].items():
            lines.append(f"- `{match}` {kind}: `{digest}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("match", choices=(*DEVELOPMENT, "all"))
    parser.add_argument("--write", type=Path, help="write an aggregate report (requires all)")
    args = parser.parse_args()
    if args.write and args.match != "all":
        parser.error("--write requires all")
    external_dir = ROOT / "runs" / "external"
    results = {}
    for match in DEVELOPMENT if args.match == "all" else (args.match,):
        metadata, tracking = external._files(match, external_dir / "idsse")
        source = external_dir / "elastic" / "benchmark" / "gt" / f"{match}.parquet"
        hashes = {
            "anotaciones": file_hash(source),
            "metadatos": file_hash(metadata),
            "tracking": file_hash(tracking),
        }
        check_hashes(match, hashes)
        result = summarize(pd.read_parquet(source), roster(metadata), tracking)
        result["input_sha256"] = hashes
        results[match] = result
    if args.write:
        with args.write.open("w", encoding="utf-8", newline="\n") as destination:
            destination.write(report(results))
    else:
        print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
