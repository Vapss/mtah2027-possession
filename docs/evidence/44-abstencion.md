# #44 — la abstención se propaga y sale `X`

Antes: `combine()` disolvía "ningún artefacto opina" en un promedio no ponderado y `decide()`
desempataba por orden de `PROB_COLUMNS`, así que un frame sin balón de B5
(`p_home = p_away = 0,49`, `p_dead = 0,02`, `confidence = 0`) salía `H`. Después: si todos los
artefactos se abstienen, el frame sale `X`.

## Artefacto y comandos

Artefacto del clon de validación (no regenerado en esta corrida), 199.319 filas:

```text
sha256 f55ec7f343a29e96d996bd6594f4fa1cfa8a147f2a39c2080b42a4b5edbcc99c
```

```bash
# antes: tools/assemble.py de origin/dev ec9938e
python tools/assemble.py --artifacts <dir> -o sub_before.csv
# después: esta rama
python tools/assemble.py --artifacts <dir> -o sub_after.csv
python tools/score.py --results <dir> --bootstrap 1000 --no-ledger
```

Ningún peso ni umbral se tocó (`--abstain-below` sigue en 0,0 y no participa de este cambio).

## Frames sin balón

"Sin balón" = `confidence = 0` en el artefacto, dentro de los dos medios tiempos según `games.py`.

| frames sin balón dentro de medios tiempos | antes `H` | antes `A`/`D`/`X` | después `X` | después `H`/`A`/`D` |
|---|---:|---:|---:|---:|
| 64.643 | 64.643 | 0 / 0 / 0 | **64.643** | 0 / 0 / 0 |

Otros 21.188 frames sin balón fuera de los medios tiempos pasan de `H` a `X`. El total de `H`
baja de 149.795 a 63.964 y el de `X` sube de 0 a 85.831; `A` queda intacto en 49.524.

## Scorer oficial, slice público

7.500 frames puntuados, 17 posesiones GT. Diagnóstico, no generalización.

| versión | `macroF1` | `spellF1` | `X` en frames puntuados | posesiones predichas |
|---|---:|---:|---:|---:|
| antes | 0,4322 | 0,0405 | 0 | 131 |
| después | **0,4573** | **0,0441** | 885 (11,80%) | 128 |

`spellF1` no empeora; `macroF1` mejora. La submission resultante
(`sha256 3a402d4236acb8deb25e71453792b7fa31c6bd5abbfa1cbf03e1e85d401ff701`) coincide con el
baseline que B6 construye con la política explícita `confidence = 0 → X`, lo que confirma que el
ensamblador y esa evidencia aplican ahora la misma regla.

## Límites

El artefacto concreto fija las cifras: otro artefacto B5 da otros conteos (Amoeba reporta 65.619
sin balón, Bruno 30.516 con el regenerado). La causa y la dirección del arreglo no dependen de esa
cifra. Ninguna conclusión de generalización: 17 posesiones y un solo artefacto.
