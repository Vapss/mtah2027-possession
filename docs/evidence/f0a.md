# F0a — la cadena cierra en una corrida

Ticket #20 F0a. Una corrida, sin datos de partido y sin dependencias nuevas: el baseline que ya
está en el repositorio se codifica como artefacto, se ensambla, pasa el validador oficial y se
puntúa. El número queda en `runs/ledger.jsonl`.

```bash
make f0a
```

Equivale a estas cuatro etapas sobre `runs/f0a/` (el mismo código que los comandos canónicos, con
un directorio propio para no pisar `artifacts/possession.csv`):

```bash
.venv/bin/python tools/onehot.py evaluation/results/baseline_smooth50.csv -o runs/f0a/artifacts/baseline_smooth50.csv
.venv/bin/python tools/assemble.py --artifacts runs/f0a/artifacts -o runs/f0a/submission.csv --json runs/f0a/submission_summary.json
.venv/bin/python evaluation/validate_submission.py runs/f0a/submission.csv
.venv/bin/python tools/score.py --results runs/f0a --out runs/f0a/score --bootstrap 1000 --config configs/assemble_default.json --note "f0a"
```

## Resultado

Slice público: **7.500 frames puntuados, 17 posesiones GT**. Diagnóstico del pipeline, no del
modelo; no es una cifra del partido completo y no prueba generalización.

| métrica | valor |
|---|---:|
| `spellF1` | **0,325581** (publicado: 0,3256) |
| `macroF1` | 0,620733 |
| posesiones predichas | 26 (GT 17) |
| duración media | 10,80 s (GT 14,19 s) |
| fragmentación | 1,43 |
| bootstrap 5–95 `spellF1` | 0,213953 … 0,446512 (1000 draws, 17 posesiones) |

Validador oficial: `Score it against the public ground truth with run_evaluation.py.` — exit 0.

Determinismo: una segunda corrida completa, en un directorio temporal, produce artefacto y
submission byte-idénticos:

| archivo | SHA-256 |
|---|---|
| `runs/f0a/artifacts/baseline_smooth50.csv` | `febb673ebee46ada1e1f924df0f67e6ea3909c41fb582ab0486a8cd1b323b5f6` |
| `runs/f0a/submission.csv` | `6d4e04b80b9016cc16ada99697bf219d3a74b58750dd6d5ec5a4cd5fc32ab4b9` |

Entrada del ledger (una línea por corrida; se muestran los campos que importan):

```json
{"gt": "public", "bootstrap": 1000, "results": "runs/f0a", "note": "f0a",
 "submission": "submission", "spell_f1_mean": 0.325581, "macro_f1": 0.620733, "poss": 26}
```

`make f0a` falla si el `spellF1` deja de ser 0,325581 o el `macroF1` deja de ser 0,620733: al
codificar un baseline ya publicado, una diferencia señala la ruta de ensamblado (`onehot` /
`assemble`), no un cambio de modelo. También falla si la reconstrucción no es byte-idéntica o si
el validador rechaza el archivo.

## Por qué un directorio propio

`make demo` no limpia `artifacts/`, y `make submission` combina **todos** los `*.csv` que
encuentre. En un worktree con un artefacto previo, el score canónico puntúa una mezcla: medido en
este worktree con `artifacts/possession.csv` (`smooth50`) presente, `make demo && make score` da
`spellF1` 0,3568 en vez del 0,4242 publicado para `smooth125`. No es una regresión del código; es
estado de trabajo que `make submission` no puede distinguir de un ensemble deliberado. F0a no
puede caer en eso porque escribe y puntúa solo `runs/f0a/`, y rechaza un workdir con artefactos
ajenos. Para comparar el baseline canónico, correr `make demo submission validate score` sobre un
`artifacts/` limpio (o `make clean` primero).

