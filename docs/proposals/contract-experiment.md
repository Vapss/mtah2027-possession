# Experimento de contrato: el único cambio admisible y la prueba de congelación

Estado: **medido hoy sobre `origin/dev` = `89693fa`**, con el bundle licenciado montado fuera del
repo. Los comandos están al final.

## Pregunta

Quedan 13 días y la aclaración del 3-nov prohíbe elegir con el ground truth. ¿Qué experimento, si
alguno, puede todavía mejorar el archivo que se entrega sin romper esa regla? El embudo va de
arriba (el contrato) hacia abajo (la palanca), y descarta todo lo que no puede cambiar el CSV o no
tiene juez admisible.

## Embudo

| candidato | qué mediría | veredicto |
|---|---|---|
| Rejilla de 27 configuraciones en DFL | si 1,5 / 5 / 1 sobrevive fuera | **no**: DFL tiene 4,58 pos/min y la cadena 3,62; el corpus premia fragmentar y elige la esquina (2,0 / 7 / 1) |
| Estabilidad con σ = 0,85 m | centro de la meseta sin GT | **no**: un predictor constante es perfectamente estable; sin ancla de acierto no decide |
| `dwell` / duelo por acuerdo con Smart Tagging | más inercia = más acuerdo | **no**: ST premia la inercia; no es juez de fechas |
| Ronda 7 de fechado | mover el cambio | **no**: D42 ya la midió con juez externo (Metrica); error 0,04–0,16 s |
| Vídeo o imputación de huecos | rellenar el 41% sin balón | **no**: negativos y sin juez admisible que los readmita |
| Fusión con el broadcast (C2) | posesión en los huecos tácticos | **no para 13 días**: #7 (sincronía) abierto; sin medir localmente |
| Post-proceso B6 | absorber micro-segmentos | **no**: sus constantes salen del slice; #35 fuera de `repro` |
| **U1 `onset`** | adelantar el inicio de las paradas W1 | **sí**: constantes fijadas en DFL, 7/7 allí, y el negativo local es nulo a IoU 0,5 |
| **Prueba de congelación** | que el contrato se sostenga | **sí**: es la única que puede fallar en silencio |

## A. U1 `onset`, medido de punta a punta

Se reconstruyó la cadena entregada y la variante U1 (`tools/dead_ball_v3.py --variant onset`) con
el bundle licenciado. La cadena entregada reproduce byte a byte el SHA `72c98ed4…`.

| métrica | entregado | U1 | Δ |
|---|---:|---:|---:|
| `spellF1` (media de 5 IoU) | **0,5368** | 0,5263 | **−0,0105** |
| `macroF1` | 0,8533 | 0,8585 | +0,0052 |
| IoU 0,5 TP/FP/FN | 11 / 10 / 6 | 11 / 10 / 6 | **idéntico** |
| IoU 0,3 TP/FP/FN | 13 / 8 / 4 | 12 / 9 / 5 | −1 |
| IoU 0,6 TP/FP/FN | 9 / 12 / 8 | 10 / 11 / 7 | +1 |
| precisión de `D` (slice) | 0,8768 | 0,8666 | −0,0102 |
| recall de `D` (slice) | 0,8965 | 0,9333 | **+0,0368** |
| `%D` del partido | 40,0% | 43,5% | +3,5 pp |
| posesiones del partido | 383 | 372 | −11 |
| posesiones/min | 3,62 | 3,51 | −0,11 |
| duración media | 10,0 s | 9,6 s | −0,4 s |
| acuerdo con Smart Tagging | 77,1% | **77,8%** | +0,7 pp |

Evidencia externa ya registrada (`lane-dead-v3` §2.1, §9): en DFL el inicio de W1 llega **5,4 s
tarde**; `onset` lo lleva a **0,5 s** (3,25 m/s), con precisión de frame 0,954 → 0,919 y recall
0,682 → 0,790, y **gana los 7 partidos** con y sin balón. Las constantes se fijaron allí: ninguna
se barrió contra el partido (§3).

### Por qué el −0,0105 local no manda

El slice público son 5 minutos del **inicio** del partido: 19,6% de `D` y 88,2% de balón
detectado, contra 56,9% de balón en el partido. Las paradas son justo el régimen que ese bloque
sub-muestrea; DFL, donde U1 gana 7/7, tiene 40,7–51,7% de `D`. Un cambio que actúa sobre el inicio
de las paradas se mide en el slice con la mitad del peso que tendrá en el partido. El −0,0105 es
además **0 discordantes** a IoU 0,5: no mueve ninguna posesión en el umbral que ordena, solo el
borde de una posesión corta a 0,3.

## B. Prueba de congelación (contrato)

Clon limpio de `origin/dev`, `uv sync --locked`, bundle por symlink fuera del repo.

| prueba | resultado |
|---|---|
| `make engine` (build + validador oficial) | 14,2 s, 199.319 filas, válido |
| `make repro` (dos builds + comparación) | 34,0 s, SHA igual a `72c98ed4…` |
| build con `evaluation/gt` **borrado** | SHA idéntico |
| build con la red deshabilitada (`unshare -rn`) | SHA idéntico |
| `pytest -q` | **588 passed, 5 skipped** (DFL/Metrica ausentes) |
| RSS máximo | 931 MiB |

## Regla de decisión, escrita antes de mirar

Se adopta U1 si y solo si: (1) DFL sigue 7/7 con las constantes fijas; (2) el acuerdo con Smart
Tagging no baja (77,8 ≥ 77,1); (3) la estructura pasa (ningún bloque > 70% de `D`, ≥ 1 posesión
por bloque, 3,4 ± 0,5 pos/min → 3,51); (4) el slice **se reporta una vez** y no es compuerta.
Las cuatro se cumplen. La decisión de cambiar el CSV es del lead; el experimento solo dice que es
admisible y que la evidencia admisible lo favorece.

Si se adopta: `make engine`, `make repro`, validador, hash nuevo, y en el informe el −0,0105 con
sus 0 discordantes y n = 17, marcado in-sample.

## Comandos literales

```bash
git clone https://github.com/Vapss/mtah2027-possession.git && cd mtah2027-possession
git checkout origin/dev
ln -s <bundle>/tactical data/tactical && ln -s <bundle>/broadcast data/broadcast
uv sync --locked --inexact
.venv/bin/python tools/engine.py --build runs/engine --submission submissions/engine.csv
.venv/bin/python tools/repro.py --against submissions/engine.csv
.venv/bin/python tools/dead_ball_v3.py --variant onset --labels /tmp/u1.csv --gt public
.venv/bin/python tools/score.py --no-ledger   # o possession_metrics.evaluate en un script
```

## Límites

- DFL usa otra definición de posesión (4,58/min, 41–52% de `D`): sirve para el **tiempo** de la
  parada, no para la escala. Es lo único que se le pide.
- El 3,4 pos/min de referencia sale del slice; se usa como cordura, no como objetivo.
- Si el partido real tuviera ~20% de `D` como el slice, U1 añadiría paradas donde no las hay. Es
  el riesgo declarado de la apuesta.
- No hay juez local de fechas de parada: Smart Tagging es demasiado grueso (sus fases `SET PIECES`
  cubren 43.987 frames y solo 35% son `D` en la cadena).
