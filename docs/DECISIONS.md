# Decisions

One entry per rule, threshold or trade-off that someone would otherwise have to reverse-engineer
from the code. Newest last. Keep entries short: what was decided, why, and what it costs.

---

## 1. A single writer for the graded file

**Decided.** `tools/assemble.py` is the only code that writes `submissions/submission.csv`. Jobs
emit `frame,p_home,p_away,p_dead,confidence` into `artifacts/`.

**Why.** The submission format is strict -- exactly 199,319 rows, frames in order, no blank cells,
labels in `H A D X` -- and a file that fails those checks scores nothing at all. With several
people producing candidate files, format bugs multiply and each one costs a whole entry. One writer
means one place to be right, and it lets a job be developed against its own signal without touching
the deliverable.

**Cost.** Every job pays the adapter cost of expressing itself as probabilities, including jobs that
only ever produce hard labels (`tools/onehot.py` handles that case).

---

## 2. Probabilities plus a confidence, not hard labels

**Decided.** The artifact carries three probabilities and a `confidence`, and the assembler combines
artifacts by weighting each one with its confidence (explicit `--weight` overrides).

**Why.** Two signals disagree about the same frame sooner or later -- dead-ball detection versus the
possession engine is exactly that case. Hard labels force a merge rule chosen by whoever writes the
merger first; probabilities let the disagreement be visible and weighted. `confidence = 0` gives a
job a clean way to abstain on frames it knows nothing about, and it maps onto the submission's own
`X` label.

**Cost.** The weighted mean is a simplicity choice, not a calibrated ensemble. If two artifacts are
strongly correlated, confidence-weighting double-counts them.

---

## 3. Bootstrap on by default

**Decided.** `make score` always runs `run_evaluation.py --bootstrap 1000`, and the ledger records
the draw count.

**Why.** The public ground truth covers 5 minutes: 7,500 graded frames, 17 possessions,
21 segments. The effective sample size is the segment count, not the frame count, so a `spellF1`
delta of a few hundredths carries no information. Measured on the shipped baseline, 1000 draws give
a 5-95 percentile interval of **0.2667 .. 0.5939** for `spellF1` -- the scorer prints "gaps below
~0.33 are within noise". On the full match the band is far tighter (~0.04, per EVALUATION.md); the
public slice is a sanity check and the two must never be quoted interchangeably.

**Cost.** Slower scoring, and a band wide enough that most "improvements" visible locally are noise.
That is the honest answer rather than a defect: it also means the public slice cannot rank two
plausible methods, so the ledger should be read for direction, not for decimals.

---

## 4. Freeze the organisers' code and lint only ours

**Decided.** `evaluation/`, `starter/` and `games.py` are read-only and excluded from ruff.

**Why.** `evaluation/run_evaluation.py` is the script that produces the official result; a local
edit makes our numbers incomparable to the board. Reformatting them would also turn every upstream
merge into a conflict, and the repository must keep tracking `upstream`.

**Cost.** Some upstream rough edges stay rough. If one is real, it belongs in an upstream issue.

---

## 5. `X` is not used as a safety net yet

**Decided.** The assembler's `--abstain-below` defaults to `0.0` and `--x-outside-halves` is off.

**Why.** `spellF1` fills an abstention with the previous label in the same half, so an `X` costs
nothing mid-possession and a lot across a hand-over, while `macroF1` charges it as a miss. Both
behaviours are measurable but neither is measured yet, and a default that silently abstains would
change every comparison in the ledger.

**Cost.** The pipeline does not exploit the free option. Whoever measures it should record the
before/after here and then change the default deliberately.

---

## 6. Data guard in pre-commit, not only in `.gitignore`

**Decided.** `tools/guard_data.py` blocks `data/`, archives, video, frame dumps and files over
5 MB, and the check runs in pre-commit and in CI.

**Why.** The downloaded bundle arrives as archives next to the repository, untracked and one
`git add -A` from being published to a public repository that the organisers will clone. `.gitignore`
covers the unpacked directory and not the archives, and it says nothing about derived frame-level
exports.

**Cost.** Legitimate large files need an explicit decision. None are expected here.

---

## 7. Ingest decides by content hash, not by filename or flags

**Decided.** `tools/ingest.py` treats a destination whose bytes already match the archive as
*present*, never rewrites it -- even under `--force` -- and aborts the whole run before writing
anything if a destination is tracked by git and differs.

**Why.** The bundle ships a `README.md` that is byte-identical to the committed `data/README.md`, so
a name-based rule would either skip a real asset or overwrite a tracked file. Re-running ingest on a
good tree has to be a no-op that leaves mtimes alone, otherwise "did the data change?" becomes
unanswerable. The preflight exists because a half-unpacked tree looks like a successful run.

**Cost.** Proving "present" means hashing both sides: cheap for the 8 small assets, slower for the
196 MB tracking file. Accepted, because a wrong overwrite costs more than a few seconds of I/O.

---

## 8. Smart Tagging intervals are half-open, unlike the reference loader

**Decided.** `tools/smart_tagging.py` maps `<start>`/`<end>` to `round(seconds * 25)` and treats
`end_frame` as exclusive: `[start_frame, end_frame)`.

**Why.** Every other interval in this repository is half-open, and a mask that disagrees by one frame
per instance is the kind of error that survives review. `starter/load_smart_tagging.py` is inclusive
and is not imported: it is read-only reference code, it prints from a time-base check, and importing
it would make our pipeline depend on a file the organisers may change. The one-frame difference is
documented in the module docstring instead.

**Cost.** Our counts differ from the reference by at most 59 frames on `SET PIECES`. Verified on the
delivered file: union of the 59 intervals is 43,987 frames (22.1% of the match); `GOALS` covers
16,503 frames (8.3%) because the annotator tags the whole goal sequence, not the restart.

---

## 9. Our contract is deliberately stricter than the official validator

**Decided.** `tools/contract.py` rejects a submission with an extra column and one with a leading
index column. `evaluation/validate_submission.py` -- the file that decides the competition -- accepts
both.

**Why.** Measured, not assumed. A probe compared the two on the same files, and they agree on the
five cases that actually happen (a trailing blank line, an Excel BOM, CRLF endings, quoted labels, a
header written as `frame, label`): all five pass both. They disagree on exactly two, and in the safe
direction -- we are the strict one. That order matters: a harness stricter than the organiser blocks
a file that might have scored, which is annoying and visible. The opposite order silently ships a
file that scores nothing.

**Cost.** `make submission && make validate` can block a file the official validator would have
accepted. If that ever happens to a real submission, the fix is to relax `SUBMISSION_COLUMNS` in
`tools/contract.py` and record it here, not to hand-edit the CSV.

---

## 10. CI does not run the tests that need the match data

**Decided.** The bundle-dependent tests skip themselves in CI: 10 of 60 on a clean clone, 50 pass.
The authoritative gate is `make ci` **run locally with the bundle unpacked**; GitHub Actions proves
the harness works on a machine that has no data.

**Why.** The data is gated and licensed for the competition only -- it cannot be in the repository or
in a public CI cache, and putting it there is the one rule that ends a submission. The ten skipped
tests are precisely the ones carrying this repository's real claims: the byte-identical regeneration
of the four baselines, the 638 Smart Tagging instances, and the 43,987 frames of `SET PIECES`. Losing
them in CI is the price of not shipping the data.

**Cost.** A green check in GitHub no longer means "the numbers still hold", and someone will read it
that way. Two mitigations are available and neither is implemented: a small synthetic bundle fixture
so ingest and Smart Tagging parsing run on every push (the 638-instance assertions would still need
real data), or a documented rule that the PR checklist item is a pasted local `make ci`. Until one
exists, treat CI as a syntax gate and the local run as the evidence.

---

## 11. The pandas version is part of the contract until there is a lock

> **Sustituida por la decisión 27** (`uv.lock`, #9). Se conserva como registro del riesgo que cerró.

**Decided.** `requirements.txt` stays as the organisers wrote it -- `numpy`, `pandas`, unpinned -- and
we accept the risk until `uv lock` lands. The risk is recorded here rather than silently tolerated.

**Why.** `tests/test_regression_baseline.py` proves reproducibility by regenerating the four shipped
baselines and demanding `git diff` come back empty. That is a byte-level assertion on pandas' CSV
writer. It passes on pandas 3.0.6 (the version in the venv this repository was verified against), and
it can fail on another version for reasons that have nothing to do with our code.

**Cost.** If it fails, the message says "starter/baseline.py no longer reproduces the committed
baseline CSVs", which points at the organisers' script and not at the dependency -- a misleading
error, which is worse than a plain failure. Pinning the interpreter and the two libraries closes it;
that is task E1, and it is a deliverable requirement anyway ("pinned dependencies").

---

## 12. Acceptance criteria are a paired Δ`spellF1`, never `f1_D` or `macroF1`

**Decided.** Every issue in the backlog is judged by the paired Δ`spellF1` of the submission with the
change versus without it, with `n_discordant` reported. `macroF1` and `f1_D` are reported and never
decide a merge.

**Why.** Measured, and it is not close:

| política | macroF1 | spellF1 |
|---|---|---|
| `smooth50` tal cual | 0.6207 | 0.3256 |
| + `SET PIECES` como `D` | 0.6675 | 0.2732 |
| + etiqueta previa en los huecos de balón | 0.5105 | 0.3805 |

The first change *raises* the tie-break metric by 0.047 while *lowering* the ranked metric by 0.052.
The issue as originally written (`SET PIECES` as `D`, acceptance = passes the format validator) would
have merged a regression. Four issues were framed that way. `f1_D` and `spellF1` are in fact in
reverse order across the four shipped baselines (`smooth125`: f1_D 0.146 / spellF1 0.4242; `raw`:
f1_D 0.420 / spellF1 0.0378).

**Cost.** Slower reviews: every PR needs a paired comparison and a discordant-pair count instead of a
single number. And most local deltas land inside the noise band, so many PRs will honestly close as
"no concluyente" -- which is the correct answer and an unsatisfying one.

---

## 13. The public slice cannot measure anything that depends on missing ball

**Decided.** No decision about multi-camera fusion (`C2`) is taken on public-slice evidence. The
artifact exists, is weighted **0** by default, and the technical document explains why it was
dropped.

**Why.** The graded 5 minutes are the easiest part of the match: **88.2%** of their frames have the
ball detected, against **56.9%** over the full match (113,488 / 199,319). Fusion can only act where
the tactical feed has no ball, so the public slice systematically under-samples the only regime where
it applies, and the other 43% of the match has no public ground truth at all. On top of that,
`P(sin balón | D) = 0.336`, so two thirds of dead-ball frames have the ball visible and are not a
ball-recovery problem either.

**Cost.** We are deliberately leaving a possible gain unexplored, and we cannot prove the decision
right -- only that it cannot be proven locally. That is the honest state; the alternative is
spending 25% of the effort on a signal no experiment in this repository can score.

---

## 14. El lector ATD valida la huella del export, no solo su forma

**Decidido.** `tools/atd.py` es el único módulo que conoce el formato del tracking crudo. Además de
la estructura (ids `1..N` consecutivos, `N = games.source_frames()`, 46 slots × 3 canales, el balón
en el último campo), al cargar compara la huella medida de la entrega: 113.488 frames con balón
presente, mediana de 22 slots ocupados en juego y 12 en el descanso.

La presencia del balón se decide por `x` e `y`, y la forma se valida **por slot**, no por el total
del registro: un slot con cuatro canales y otro con dos suma lo mismo y desplazaría en silencio todas
las coordenadas siguientes.

**Por qué.** Leer el balón del primer campo de cada línea da **40,0%** de presencia y un hueco
fantasma de 52.239 frames; del último da los 113.488 / 199.319 (56,9%) correctos. Y exigir los tres
canales daría **5,0%**: solo 9.909 de los 113.488 balones presentes traen `z` (8,7%), porque el
export solo rellena la tercera coordenada cuando el balón está en el aire.

De paso, la premisa del issue #28 sobre el descanso es falsa: la mediana no es "casi nadie" sino
**12 jugadores**, y el balón se detecta en **18.961 de los 20.156 frames** de descanso (94%). Eso
importa para #27 y para el stream A: el tracking no se detiene, así que ni "sin jugadores" ni "sin
balón" discriminan balón muerto. El lector lo deja como test explícito para que nadie lo reconstruya
sobre la premisa contraria.

**Coste.** Las cifras están atadas a este partido y a esta exportación: otro partido, o una entrega
corregida, falla en `load()` hasta actualizar `FINGERPRINTS`. Es intencional — un error al cargar es
preferible a un número silenciosamente falso aguas abajo. El coste real: 3 s y 230 MB por proceso la
primera vez, compartido después por caché y con los arrays en solo lectura.

---

## 15. El grafo del código es una ayuda de lectura, no una dependencia

**Decidido.** `make graph` construye `graphify-out/` con `graphify extract . --code-only`, y ese
directorio está en `.gitignore`. Graphify no entra en `pyproject.toml`, ni en `make dev`, ni en
`make ci`, ni en el camino que regenera la submission.

**Por qué.** El artefacto que se entrega tiene que poder regenerarse con Python 3.12, numpy y pandas
(regla 8 de `AGENTS.md`); graphify arrastra su propio árbol de tree-sitters y no aporta nada a ese
camino. Instalarlo como herramienta aparte (`uv tool install graphifyy`) mantiene el entorno del
harness pequeño y reproducible.

No se commitea el grafo por dos razones concretas: queda obsoleto en el siguiente commit, y un
`graph.json` de medio megabyte revisado como si fuera código esconde el diff de cuatro líneas que
importa. `GRAPH_REPORT.md` sí nombre el commit del que se construyó, que es la forma honesta de
saber si hay que rehacerlo.

El pase semántico (docs, PDFs, imágenes) queda apagado: requiere clave de LLM, mete un modelo en
medio de un repo cuya regla es que las etiquetas salgan de código determinista, y añadiría bordes
`INFERRED` que aquí nadie necesita. El grafo es 97% `EXTRACTED` justamente por eso.

En CI, `make graph-check` construye el grafo y falla si la salida deja de estar ignorada (la línea
de `.gitignore` es una regla, no un deseo) o si `GRAPH_REPORT.md` nombra un commit distinto de
`HEAD` (un mapa que describe otro árbol). Es un job aparte porque graphify no puede ser requisito
de `make ci`: quien no lo tenga instalado tiene que poder correr el harness igual.

**Coste.** 2,4 s y 576 nodos para este repo, sin red. Quien quiera nombres de comunidades legibles
tiene que configurar un backend; sin él, el informe dice "Community N" y sigue sirviendo para
navegar. Y es un mapa, no una verdad: un god node es una invitación a leer `file:line`.

---

## 16. `D` no se detecta por el balón, se decide por estado

**Decidido.** Ningún job etiqueta `D` a partir de un umbral del track del balón. Las señales de
balón (ausencia, fuera de campo, velocidad, distancia al jugador) entran como **disparadores de
precisión** dentro de un modelo con memoria de estado; el stream A (#5, #10, #16) se construye
sobre contexto: reanudaciones, fuera de juego, saques, celebraciones.

**Por qué.** Medido en la ventana pública (7.500 frames, 1.469 de `D`, 4 tramos), y reproducible con
`python tools/characterize_d.py` (documento en `docs/analysis/d-characterization.md`):

| señal | P(D \| señal) | P(señal \| D) | lift |
|---|---:|---:|---:|
| balón fuera del campo | 98,1% | 7,1% | 5,01 |
| balón ausente | 55,8% | 33,6% | 2,85 |
| `SET PIECES` | 56,1% | 45,4% | 2,86 |
| balón lento (<1 m/s) | 19,4% | 6,7% | 0,99 |
| balón a >5 m del jugador | 27,3% | 23,6% | 1,39 |
| `BUILD UP` (control) | 9,2% | 2,0% | 0,47 |

Los tramos de `D` duran 5,5 / 20,4 / 18,3 / 14,5 s (mediana 16,4 s): es estructura, no ruido de
frame. El balón dentro de `D` rueda a 2,70 m/s de mediana (frente a 5,74 vivo) y está a 2,89 m del
jugador más cercano (frente a 1,65 m): se mueve más despacio y más lejos, pero **ni está quieto ni
está solo**, así que "balón parado" y "balón perdido" no son la misma cosa que `D`.

`BUILD UP` está en la tabla como control: si algún día su lift sube de 1, la medición está mal.

**Coste.** El techo de las señales de balón es bajo por construcción: la mejor de todas (fuera de
campo) cubre el 7,1% de `D`. Y la ventana pública es la parte del partido con más balón detectado
(88,2% frente a 56,9%), así que ahí la cobertura está sobrestimada; en el partido completo estas
señales cubrirán aún menos. Lo que queda es contexto, y el contexto hay que modelarlo.

---

## 17. Comparar submissions pareadas sin confundir el test de signos con `spellF1`

**Decidido.** `tools/compare_submissions.py` compara dos CSV con el scorer oficial y reporta el delta
de `spellF1` para cada IoU y su promedio, junto con posesiones verdaderas/predichas, emparejadas,
perdidas y espurias. Expone además las banderas de emparejamiento de cada posesión, su duración y el
grupo corta (<4 s) / larga (≥4 s), para que los análisis posteriores puedan reutilizarlas. El
jackknife quita una posesión verdadera cada vez, conserva todas las predicciones y vuelve a ejecutar
el emparejamiento completo; así la sensibilidad también incluye predicciones espurias y posibles
reasignaciones. Cada fold conserva `spellF1`, TP/FP/FN y delta por umbral.

El comando añade una prueba exacta de signos a IoU 0,5 como diagnóstico separado: cuenta qué
configuración empareja cada posesión verdadera en las que discrepan, y reporta empates y
`n_discordant`. Su p-valor **no es** una prueba de significancia para el delta de `spellF1`: no
incluye la penalización global por posesiones predichas sin pareja. Además, su interpretación
requiere signos independientes y equiprobables bajo la nula; posesiones del mismo partido pueden
depender unas de otras.

**Uso.** `python tools/compare_submissions.py A.csv B.csv --gt public` imprime JSON reproducible.
`--gt` también acepta `private` en un entorno que tenga ese ground truth o una ruta CSV explícita.
El comando no escribe submissions ni el ledger.

**Coste.** La ventana pública solo tiene 17 posesiones. El score y el jackknife describen la
sensibilidad de esa muestra; ni el delta local ni el p-valor diagnóstico prueban generalización al
partido completo.

---

## 18. Emisión B5: identidad desde XML y evidencia física fija

**Decidido.** `tools/emision.py` obtiene la pertenencia a equipo del XML ATD, usando el equipo local
como `H` y el visitante como `A`. El metadata se debe mantener alineado con los 46 slots ordenados
por id; se falla cerrado si cambia el formato o el reparto medido de 24/22. Smart Tagging `Team`
sirve únicamente de ancla diagnóstica, nunca de etiqueta de entrenamiento.

La primera propuesta de emisión fue voto top-5 con sigma fijo de **1,84 m**, mezclado con centroide
y densidad a 10 m. La ablación preregistrada de la sección 19 no la mejoró frente a `argmin`, por
lo que no es la salida final. El artefacto entregado usa el mínimo de distancia por equipo y
softmax con temperatura fija **2,857386876 m**, calibrada in-sample por log-loss H/A en los 5.640
frames públicos vivos con balón observado. `confidence = max(p_home, p_away) × ball_present`, así
el job se abstiene cuando no observa balón. `p_dead` mantiene el suelo débil 0,02 y suma 0,15 solo
fuera del rectángulo del campo. La rapidez y los contextos se conservan como diagnósticos de la
ablación, no alteran la emisión final. No hay decodificación temporal.

**Por qué.** El XML identifica los equipos de cada track: 24 locales (Barcelona) y 22 visitantes
(Atletic Club); no hace falta inferir identidades por posición. La ablación no mostró mejora del
voto suave sobre `argmin`; se conserva la referencia calibrada. Sigma viene de la distancia mediana
medida balón→jugador y no se barre aquí; cualquier búsqueda de sigma o k pertenece al barrido
pre-registrado de #22. La temperatura final se documenta como calibración in-sample del GT público,
no como ajuste con estimación independiente.

**Coste.** La emisión sigue siendo frame-local y el `D` es deliberadamente débil. La accuracy y
las pérdidas H/A solo se interpretan en frames vivos con balón observado. Sin balón, H/A queda
uniforme y `confidence=0`; el campo es `max(p_home,p_away) × ball_present` e incluye el suelo D.
Las métricas del slice público son diagnóstico, no evidencia de generalización al partido completo.

---

## 19. Ablación B5 preregistrada: voto, vecinos y confianza

**Preregistro (antes de correr las variantes).** La unidad de evaluación es cada frame público H/A
con balón observado; no se incluyen D/X ni frames sin balón en accuracy o pérdidas H/A. Se reportan
accuracy, log-loss y Brier binario para H y A por separado y agregados. La referencia `argmin`
elige el equipo del jugador más cercano; su probabilidad es softmax de las distancias mínimas al
jugador local y visitante, con una temperatura escalar calibrada minimizando log-loss H/A sobre la
misma muestra pública mediante búsqueda áurea determinista en `T ∈ [0,01; 100]`. Esa calibración
es in-sample y solo es una referencia descriptiva.

Se ejecutan exactamente estas tres variantes, sin rejilla ni selección posterior:

1. **Vecino único.** Probabilidad H/A por softmax de distancias mínimas por equipo con escala fija
   1,84 m; `confidence = exp(-d_min / 1,84 m)`. La clase dura es el equipo del jugador más cercano.
2. **Voto top-3.** Peso gaussiano `exp(-d² / (2 × 1,84²))` sobre los tres jugadores más cercanos,
   con la mezcla de contexto vigente 0,80 voto, 0,10 centroide y 0,10 densidad a 10 m. Conserva la
   fórmula actual de `confidence` basada en masa del voto y rapidez.
3. **Sin densidad.** Top-5 vigente y centroide, se elimina el término de densidad; los pesos
   restantes se renormalizan a 8/9 y 1/9. Conserva la `confidence` vigente.

La curva de selective prediction se reporta para el artefacto actual con cortes predefinidos
`max(p_home,p_away) >= 0,55 / 0,60 / 0,70 / 0,80`: cobertura sobre los frames elegibles y accuracy
entre los cubiertos. Se reporta aparte la misma curva con el campo `confidence`, que expresa peso
del job y no debe confundirse con `max(p)`. Si ninguna variante mejora al `argmin` calibrado en
log-loss, la conclusión de B5 será no concluyente: conservar `argmin` más su confianza para #6, sin
seleccionar una variante por accuracy ni por spellF1 crudo.

**Resultado de la corrida preregistrada.** Reproducir con
`python tools/ablate_emision.py --output /tmp/ablation34.json`. En 5.640 frames H/A con balón,
la temperatura calibrada in-sample del `argmin` fue 2,857 m. `Log-loss` total es la media sobre
frames; H/A muestra pérdida por etiqueta verdadera. Brier es la media de los errores binarios
one-vs-rest de H y A; al condicionar a H/A y normalizar sus dos probabilidades, ambos Brier por
clase son iguales.

| Variante | Accuracy | Log-loss | Log-loss H/A | Brier H/A |
|---|---:|---:|---:|---:|
| `argmin` con temperatura calibrada | 0,7784 | 0,4705 | 0,4220 / 0,5470 | 0,1557 / 0,1557 |
| (a) vecino único, sigma 1,84 m | 0,7784 | 0,4952 | 0,4394 / 0,5830 | 0,1589 / 0,1589 |
| (b) voto top-3 + contexto | 0,7617 | 0,5254 | 0,4750 / 0,6049 | 0,1705 / 0,1705 |
| (c) top-5 + centroide, sin densidad | 0,7631 | 0,5433 | 0,4918 / 0,6245 | 0,1735 / 0,1735 |
| top-5 + contexto actual | 0,7606 | 0,5228 | 0,4717 / 0,6031 | 0,1701 / 0,1701 |

Ninguna variante mejora log-loss o Brier del comparador. La accuracy de (a) iguala el argmin, y
las otras quedan por debajo. Por el criterio preregistrado, **B5 no demuestra una emisión mejor**;
para #6 se conserva `argmin` calibrado, con `confidence=max(p_home,p_away) × ball_present`. No se
elige variante por accuracy ni se atribuye mejora de spellF1 sin #35.

La curva siguiente corresponde al artefacto top-5 anterior a la decisión final, no al entregado:

| Corte | Cobertura | Accuracy cubierta |
|---:|---:|---:|
| 0,55 | 0,914 | 0,785 |
| 0,60 | 0,862 | 0,795 |
| 0,70 | 0,766 | 0,819 |
| 0,80 | 0,646 | 0,837 |

En el artefacto top-5 anterior, la curva separada del campo `confidence` fue menos estable (corte
0,55: 0,645/0,818; 0,60: 0,628/0,820; 0,70: 0,580/0,824; 0,80: 0,465/0,807,
cobertura/accuracy). Esa columna no era `max(p)`.

**Artefacto final entregado: argmin calibrado.** Reproducir con
`python tools/emision.py --output /tmp/possession.csv`. En los 5.640 frames vivos con balón:
accuracy **0,778369**, log-loss H/A **0,421965 / 0,547026** (log-loss total **0,470548**, que
redondea a **0,4705**), Brier H/A **0,155681 / 0,155681** cuando H/A se renormaliza a dos clases.
En el CSV sin renormalizar, `p_dead` reduce H/A; por eso el log-loss directo del artefacto es
H/A **0,442168 / 0,567381**, media **0,4908**. La diferencia media de 0,020262 es exactamente
la masa D: 5.638 frames puntuables tienen `p_dead=0,02` y dos fuera de campo tienen `p_dead=0,17`.
El artefacto regenerado desde el commit validado reproduce esos valores; no era un CSV viejo ni un
cambio de clasificador. Temperatura fija `T=2,857386876 m`,
estimada in-sample por búsqueda áurea de log-loss. En los frames puntuables, como
`confidence=max(p_home,p_away) × ball_present`, sus curvas de confianza y `max(p)` coinciden:

| Corte de `confidence` | Cobertura | Accuracy cubierta |
|---:|---:|---:|
| 0,55 | 0,867 | 0,807 |
| 0,60 | 0,774 | 0,831 |
| 0,65 | 0,677 | 0,848 |
| 0,70 | 0,593 | 0,865 |
| 0,80 | 0,411 | 0,912 |
| 0,90 | 0,240 | 0,971 |
| 0,95 | 0,113 | 0,983 |

Al seleccionar exactamente el 65% de los frames vivos con balón por confianza, la cobertura
observada es 0,650, accuracy **0,856** y corte efectivo `confidence=0,664506`. Al corte numérico
0,65, cobertura/accuracy es 0,677/0,848. Los 391 frames vivos sin balón se excluyen de la
puntuación H/A; sus probabilidades H/A son uniformes y `confidence=0`.

## 20. B6 post-procesa estructura con reglas fijas, sin podar por duración promedio

**Decidido.** `tools/postprocess.py` aplica reglas deterministas a etiquetas H/A/D dentro de runs
video-temporales explícitos. La CLI usa los dos bloques de mitad de `games.py` como intervalos
semiabiertos; cualquier fila fuera de ellos se conserva. Dentro de cada run, X se rellena hacia
adelante (y hacia atrás solo al inicio) para decidir la estructura, y luego se restaura en las
mismas filas. Un run enteramente X queda igual.

Los parámetros son fijos: los segmentos H/A de 1–14 frames se absorben; un D de 1–14 solo se
absorbe si tiene dos vecinos inmediatos H/A iguales; y las interrupciones de 1–14 frames entre
tramos del mismo equipo se fusionan mediante esas mismas reglas locales. Los tramos de 15 frames o
más no se absorben ni se fusionan por esta regla. Si un segmento H/A corto no tiene vecino del mismo
equipo, se absorbe al vecino de mayor duración original; en empate se consulta la distancia a 355
frames y luego se prefiere el anterior. La referencia de 355 frames solo desempata; no elimina
posesiones por ser cortas. Cada operación reduce el número de runs RLE y el bucle termina en punto
fijo, con límite defensivo de `n_frames+1`. Cualquier otro umbral o variante corresponde al barrido
pre-registrado de #22.

**Baseline y resultado público.** El baseline se generó desde el commit de `dev` `d9e0bfb` con
`python tools/emision.py --output artifacts/possession.csv`; H/A toma el argmin del artefacto y las
filas con `confidence=0` se emiten como X. Los archivos reproducibles `runs/argmin_baseline.csv`,
`runs/argmin_baseline_metrics.json` y `runs/postprocess_comparison.json` son locales e ignorados
por Git. SHA-256 del baseline: `3a402d4236acb8deb25e71453792b7fa31c6bd5abbfa1cbf03e1e85d401ff701`.
La comparación usa `tools/compare_submissions.py` y el scorer oficial sobre el slice público (17
posesiones); no prueba generalización al partido completo. El baseline no contiene etiquetas D,
por lo que la regla D es un no-op en esta comparación y solo se ejerce mediante sus pruebas
sintéticas.

| IoU | Antes TP/FP/FN | Antes P/R/F1 | Después TP/FP/FN | Después P/R/F1 |
|---:|---:|---:|---:|---:|
| 0,3 | 9 / 119 / 8 | 0,070 / 0,529 / 0,124 | 15 / 35 / 2 | 0,300 / 0,882 / 0,448 |
| 0,5 | 2 / 126 / 15 | 0,016 / 0,118 / 0,028 | 4 / 46 / 13 | 0,080 / 0,235 / 0,119 |
| 0,7 | 0 / 128 / 17 | 0 / 0 / 0 | 2 / 48 / 15 | 0,040 / 0,118 / 0,060 |

El conteo baja de 128 a 50 predicciones, frente a 17 posesiones GT; `n_pred` es diagnóstico, no
objetivo de aceptación. El delta medio pareado de `spellF1` es **+0,14094**, con `n_discordant=2`
(2 victorias, 0 derrotas; test exacto de signos p=0,5, diagnóstico por posesión, no prueba del
delta). La magnitud supera la referencia de ruido de ~0,04 del partido completo, pero el slice
público solo tiene 17 posesiones y 2 discordancias; no establece generalización al partido completo.
No se ajustaron parámetros después de medir.

Reproducción (con el bundle táctico disponible):

```bash
python tools/emision.py --output artifacts/possession.csv
python -c 'import pandas as pd; a=pd.read_csv("artifacts/possession.csv"); live=a.confidence.to_numpy()>0; labels=a[["p_home","p_away"]].idxmax(axis=1).map({"p_home":"H","p_away":"A"}); labels.loc[~live]="X"; pd.DataFrame({"frame":a.frame,"label":labels}).to_csv("runs/argmin_baseline.csv",index=False,lineterminator="\n")'
python tools/postprocess.py runs/argmin_baseline.csv runs/postprocessed.csv
python tools/compare_submissions.py runs/argmin_baseline.csv runs/postprocessed.csv --gt public
make lint
make test
make guard
```

La evidencia de esos artefactos está fijada en
`docs/evidence/b6_public_manifest.json`; `make verify-b6` reconstruye baseline, salida y
comparación desde `artifacts/possession.csv`, y falla si cualquier versión, métrica o SHA-256 cambia.
La regeneración de ese artefacto exige el bundle táctico licenciado. La diferencia entre 128 y la
nota anterior de 129 se debe a la política explícita `confidence=0 → X`, no a un cambio de emisión.

## 21. El jackknife por posesión se lee también por clase de duración

**Decidido.** `tools/compare_submissions.py` conserva el jackknife leave-one-possession-out de #29
(17 folds: se quita una posesión verdadera, se conservan todas las predicciones y se vuelve a
ejecutar el emparejamiento completo). Añade el desglose pre-registrado de #8 en dos clases de
duración: **corta < 4 s** y **larga ≥ 4 s**. En el slice público son 6 y 11 de 17.

Para que el desglose no invente una segunda regla de emparejamiento, cada clase usa el mismo match
greedy uno-a-uno y los mismos IoU que el scorer. En la clase `c`:

- `TP_c` y `FN_c` son posesiones verdaderas de esa clase emparejadas y perdidas;
- `FP_global = n_pred - TP_total` es el mismo para las dos clases y para A/B;
- `spellF1_c = 2·TP_c / (2·TP_c + FN_c + FP_global)`.

Así `TP_corta + TP_larga = TP_total` y `FN_corta + FN_larga = FN_total`, y una predicción espuria
baja las dos F1 sin mover ningún `TP`. `spellF1_c` **no es el `spellF1` oficial**: se emite con
`official: false` y `metric: class_restricted_spell_f1_shared_fp`, y se acompaña de
`recall_c = TP_c / n_gt_c`, que no depende de `FP_global`. Los F1 por clase **no son aditivos** y no
suman el agregado; solo `TP` y `FN` son una descomposición exacta. El delta por clase indica si un
cambio movió las cortas, las largas o ambas; el agregado oficial sigue siendo el número de
aceptación. El bootstrap no se usa como test: es una cota marginal de cada submission y ya lo
produce `tools/score.py`.

**Uso.** `python tools/compare_submissions.py A.csv B.csv --gt public --class-breakdown` imprime,
por fold y en agregado, `spellF1`, TP/FP/FN y el desglose `by_possession_class`, además de las 17
banderas por posesión a IoU 0,3 / 0,5 / 0,7 y del test de signos separado. La tabla JSON es la que
#14 adjunta al ledger. El comando no escribe submissions ni ledger. Sin el flag, la salida queda
igual que antes: el manifiesto de B6 hashea ese JSON y no debe invalidarse por un cambio de otro
carril.

**Coste.** Con 17 posesiones (6 cortas, 11 largas) una clase tiene todavía menos muestra que el
total: los deltas por clase son diagnóstico de sensibilidad, no prueba de generalización al partido
completo. Un delta agregado se sigue citando con `n_discordant` y declarando `n=17`.

---

## 22. F0a corre aislado y fija el valor público

**Decidido.** `make f0a` ejecuta la cadena completa — `onehot` del baseline `smooth50` →
`assemble` → validador oficial → `score` — dentro de `runs/f0a/`, falla si el `spellF1` no es
`0,325581` o el `macroF1` no es `0,620733`, y exige que artefacto y submission reconstruidos
desde cero sean byte-idénticos. El ledger recibe una línea por corrida. Después corre la misma
cadena con `artifacts/possession.csv` (`--artifact`, o `make f0a ARTIFACT=...`) en
`runs/f0a/artifact/`: esa corrida no fija métricas —el número es del modelo, no del ensamblado— y
su nota lleva el SHA-256 del artefacto. Si el artefacto no existe (bundle licenciado ausente), se
salta con un mensaje y no falla.

**Por qué.** F0a (#20) existe para cerrar el riesgo "no sabemos si el pipeline funciona" antes de
modelar. Un run que solo "sale bien" no protege de eso: fijar el valor publicado convierte un
cambio involuntario en la ruta de ensamblado en un fallo con dos números, y deja explícito que el
diagnóstico es el pipeline, no el modelo. El baseline prueba la fontanería; el artefacto real
prueba la cadena con el modelo dentro y deja en el ledger el número que de verdad se va a
entregar. El directorio propio evita sobrescribir
`artifacts/possession.csv`, que es el artefacto real del bundle licenciado y la entrada de
`make verify-b6`: pisarlo con un baseline destruiría evidencia de otro carril. Los comandos
canónicos (`make submission`, `make validate`, `make score`) no cambian.

**Costo.** CI puntúa tres veces — el `demo` de `smooth125`, el baseline de F0a y el artefacto si
está — unos 10 s más. Los números son del slice público de 17 posesiones: sirven para comprobar
alineación y formato, nunca como prueba de generalización ni para elegir entre versiones.

---

## 23. La abstención se propaga y sale `X`, no la decide el orden de columnas

**Decidido.** Cuando todos los artefactos tienen `confidence = 0` en un frame, `combine()` conserva
esa condición (probabilidades uniformes, `confidence = 0`) y `decide()` emite `X` antes de aplicar
`--abstain-below`. Un `--weight` explícito sigue contando ese artefacto: es un opt-in deliberado,
no un desempate.

**Por qué.** Ticket #44. B5 sin balón emite `p_home = p_away = 0,49`, `p_dead = 0,02` con
`confidence = 0`; el promedio no ponderado y el `argmax` por orden de `PROB_COLUMNS` convertían
"sin opinión" en `H`. Artefacto del clon de validación
(`sha256 f55ec7f343a2…`, 199.319 filas): 64.643 frames sin balón dentro de los medios tiempos,
los 64.643 salían `H`; ahora salen `X` (0 `H`/`A`/`D`). Fuera de los medios tiempos, otros 21.188
pasan de `H` a `X`. Slice público con el scorer oficial, sin tocar pesos ni umbrales: `macroF1`
0,4322 → **0,4573**, `spellF1` 0,0405 → **0,0441**, predicciones `A` intactas (49.524).

**Costo.** Un artefacto que use `confidence = 0` para "poco fiable" en vez de "sin opinión" ahora
se abstiene en vez de votar; ese es el contrato que AGENTS.md ya declaraba, y `--weight` permite
forzarlo. La medición es del slice público de 17 posesiones: la mejora no se declara generalización.

---

## 24. Los tramos de hueco no llevan política propia: el slice no puede decidir ninguno

**Decidido.** La política de un hueco de balón es la misma en los cuatro tramos del ticket (`≤25`,
`26–125`, `126–500`, `>500` frames): **arrastrar el estado, nunca `D` por ausencia de balón**. La
tabla por tramo existe como diagnóstico reproducible (`tools/band_gaps.py` →
`docs/analysis/ball-gap-bands.md`), no como fuente de umbrales. La regla se aplicó mecánicamente con
el criterio pre-registrado en #10: un tramo se declara medido solo si tiene un hueco puntuado que
parta una posesión o contenga una transición, mueve ≥2 posesiones en el mismo sentido, alcanza
`|Δ| ≥ 0,04` y sobrevive a quitar cualquiera de sus huecos uno a uno.

**Por qué.** Medido, y el resultado es que **ningún tramo pasa**. El único que mueve `spellF1` es
126–500 (+0,05491, 2 discordancias), y ese Δ se cae a **+0,01588 con 0 discordancias** al quitar un
solo hueco: el de 232 frames en [17.047, 17.279), dentro de la posesión #14. Los otros tres tramos
dan Δ exactamente `0,00000` porque sus huecos no tocan un solo frame puntuado: 26–125 tiene 1 hueco
en todo el partido y >500 tiene 44 (el **67% del déficit de balón**, 43.292 frames) y ninguno cae en
la ventana pública. `D` en el hueco, que es la alternativa que la tabla compara, pierde o empata en
todos los tramos donde se puede medir: −0,00740 en ≤25 y +0,02680 frente a +0,05491 en 126–500.

Además, en la cadena que se entrega `fill` y `X` empatan **exactamente** en `spellF1`: el scorer
oficial rellena `X` con la etiqueta previa del medio tiempo. La única diferencia entre las dos es
`macroF1`, que no decide.

**Coste.** El tramo con más frames es el que no se puede medir, y su política queda decidida por
principio (decisión 16), no por dato: si arrastrar el estado es peor que otra cosa en huecos de más
de 500 frames, este repositorio no puede saberlo con el slice público. Toda la evidencia local
descansa en 4 posesiones GT (#1, #2, #5, #14) de las 17 del slice. Y el `p90` de 845 frames dice que
el tramo grande no es un caso raro: es donde está el trabajo. Cualquier barrido de cortes de banda
sobre esta muestra encuentra lo que quiera; por eso los cortes son los del ticket y no se barren.

---

## 25. La entrega de respaldo es `smooth50` con los huecos arrastrados, y no predice `D`

**Decidido.** `make backup` produce `submissions/backup.csv`, la entrega que se manda si ningún
modelo propio la supera antes del freeze (#26). La cadena regenera todo desde el bundle, sin
parámetros nuevos: `starter/baseline.py --window 50` → `tools/ball_gaps.py` (la regla de #5,
escrita por Bruno en el PR #42; se recupera solo el modo `frame,label`, con el valor a arrastrar
leído de la entrada, y la definición de hueco pasa a ser la única del repositorio) → `tools/onehot.py` →
`tools/assemble.py` → validador oficial. Dos corridas desde cero dan el mismo archivo
(`sha256 cb4eeef3617f…`).

**Por qué esta y no otra.** De los cuatro baselines, `smooth50` es el que mejor rinde en el partido
completo (0,2433, el suelo publicado); `smooth125` gana en el slice y pierde en el partido, que es
justo la trampa que documenta `EVALUATION.md`. Sobre `smooth50`, arrastrar la etiqueta en los huecos
de balón es la regla medida que sube `spellF1` sin barrer nada (decisión 12). Elegirla es una
decisión por prior, no por el mejor número del slice, y no se puede sostener de otro modo: la
decisión 24 mostró que el Δ cae a **+0,01588 con 0 discordancias** si se quita un solo hueco (232
frames, dentro de la posesión #14). El número es dirección, no evidencia. La cadena propia B5 + B6 queda por debajo
(0,1851 en el slice), así que no puede ser el respaldo.

Medido en el slice público (17 posesiones; dirección, no generalización):

| submission | spellF1 | macroF1 | posesiones | TP @ IoU 0,5 |
|---|---:|---:|---:|---:|
| `baseline_smooth50` | 0,3256 | 0,6207 | 26 | 7 |
| **respaldo** | **0,3805** | 0,5105 | 24 | 9 |

Δ pareado **+0,0549**, `n_discordant = 2` (2–0), bootstrap 5–95 de `spellF1` 0,2537 .. 0,5073.
Estructura en los dos medios tiempos del partido completo, sin ground truth:

| submission | % `D` | posesiones/min | mediana | spells < 2 s |
|---|---:|---:|---:|---:|
| `baseline_smooth50` | 32,3% | 5,61 | 4,6 s | 31% |
| respaldo | **0,0%** | 3,75 | 7,9 s | 15% |

**Coste.** El respaldo **no predice ningún `D`**: el único `D` del baseline venía de "no veo el
balón", y el relleno lo elimina entero. Cambian 54.707 frames, no solo los `D`: un cambio de equipo
que el baseline ponía dentro de un hueco se desplaza al final del hueco. Cada parada real se funde con las
posesiones vecinas: `H D H` en la verdad se convierte en una sola posesión `H`. En el slice eso sale
a cuenta, y la tasa de posesiones queda cerca del prior físico (3,75 frente a ~3,4 por minuto, contra
5,61 de `smooth50`), pero el `D` real queda sin resolver; es trabajo de #16 y del motor (#6). El
`macroF1` baja 0,11, el precio esperado (decisión 12).

---

## 26. El holdout estructural son 22 bloques de 5 minutos, y se lee como cordura, no como métrica

**Decidido.** `make blocks` (`tools/blocks.py`) describe cada submission en los 22 bloques del
partido y escribe `docs/analysis/blocks.md`. Cada medio tiempo de `games.half_video_blocks` se corta
en bloques consecutivos de 7.500 frames desde su primer frame; el último de cada medio es más corto
(3,0 y 2,9 min). El bloque 1 coincide exactamente con la ventana pública (11.185..18.684). Por
bloque: balón detectado, posesiones que empiezan en él, su tasa por minuto y su duración media (la
referencia de 14,2 s es una media, así que no se compara con una mediana), la parte del bloque que
cubre la posesión más larga que lo toca, `%D`, `%H`, y la cobertura y el acuerdo del Smart Tagging.
La columna de la posesión más larga existe porque contar cada posesión en su bloque de inicio
esconde justo el fallo que se busca: una posesión arrastrada que empieza en un bloque y llena el
siguiente deja en este solo unos fragmentos cortos. Las abstenciones se rellenan como las rellena
el scorer antes de contar nada. No se lee ningún ground truth.

**Qué vota el Smart Tagging** (`smart_tagging.possession_votes`, reutilizable por #6): una fase
ofensiva (`BUILD UP`, `PROGRESSION`, `CREATING CHANCES`, `ATTACKING TRANSITION`, `BALL IN FINAL
THIRD`, `BALL IN THE BOX`, `PLAYERS IN THE BOX`, `LONG BALL`) vota por su `Team`; una defensiva
(`DEFENDING IN …`, `DEFENSIVE TRANSITION`) vota por el otro equipo. `SET PIECES` y `GOALS` no votan:
dicen quién reanuda o quién marcó, no quién tiene un balón vivo. `N/A` no vota. Un frame cuenta
como *cubierto* solo si todos sus votos van a un mismo equipo.

**Cómo se lee.** Es un test de cordura, no una métrica: no se optimiza y no entra en ningún
criterio de aceptación como número. Lo que sí hace es **bloquear**: una configuración que gana en el
bloque 1★ pero deja un bloque fuera de lo físicamente plausible (sin posesiones, o con una tasa de
otro orden de magnitud que la de sus vecinos con presencia de balón parecida) se reporta como
regresión. El informe se adjunta a cada PR que cambie la emisión o el decodificador, y ninguna
decisión de release (#26) se toma sin él.

**Lo que ya muestra** (respaldo de la decisión 25 frente a `smooth50`):

- El bloque público es el más fácil: 88,2% de balón, frente a 19,9–36,9% en los bloques 7, 9, 11
  y 18.
- En esos bloques el respaldo baja a 1,0–1,8 posesiones/min con duraciones medias de 33–44 s
  (`smooth50`: 4,7–10,6 s), y una sola posesión cubre el **77,2%** del bloque 18 y el 70,8% del 7
  (`smooth50`: 7,5% y 14,0%). El arrastre estira posesiones a través de huecos largos. En el
  partido, la duración media del respaldo es 16,0 s frente a 7,2 s de `smooth50` y la referencia
  de 14,2 s.
- Su acuerdo con el Smart Tagging en el partido es **62,2%**, por debajo del 67,2% de `smooth50`, y
  cae a 24,8% en el bloque 11 y 30,9% en el 18. El arrastre copia el equipo anterior durante huecos
  que el slice no puede medir (decisión 24); el Smart Tagging dice que ahí se equivoca a menudo.

**Coste.** El acuerdo con el Smart Tagging no es acierto: el Smart Tagging es automático y, medido
contra la ventana pública, cubre el 70,5% de los frames vivos y acierta el **68,0%** de ellos (el
`argmin` del tracking acierta 77,8% en los vivos con balón). Es una segunda
opinión independiente del tracking, no un árbitro. Y las referencias de tasa y duración salen del
propio slice público, así que no se convierten en una banda de aceptación (#35).

---

## 27. El entorno de reproducción está fijado en `uv.lock` (sustituye el riesgo de la decisión 11)

**Decidido.** El intérprete y las dos librerías que escriben la submission están fijados:
`pyproject.toml` tiene `requires-python = "==3.12.*"`, `numpy==2.5.4` y `pandas==3.0.6`;
`.python-version` fija el parche, 3.12.3; y `uv.lock` fija todo lo demás, con `pytest`, `ruff` y el
grupo `starter` de los notebooks incluidos. Las versiones viven ahí y en ningún otro sitio.

- **CI** construye el entorno con `uv sync --locked`, que **falla si `uv.lock` no corresponde a
  `pyproject.toml`**. `--frozen` no sirve para eso: instala el lock viejo sin avisar. Está
  comprobado: con una dependencia añadida sin `uv lock`, `--frozen` sale con 0 y `--locked` con 1.
- **`make install` / `make dev` / `make starter`** usan `--locked --inexact`: solo añaden, así que
  ninguno desinstala lo que puso otro. CI sincroniza exacto porque construye el entorno de
  reproducción y nada más.
- **`requirements.txt`** queda como lo escribieron los organizadores: es su referencia, no la nuestra.
  `requirements-dev.txt` se elimina: lo sustituye el grupo `dev`.
- La sintaxis sigue siendo compatible con 3.9 (`ruff` con `target-version = "py39"`). Lo que se
  fija es el entorno que regenera el archivo, no el lenguaje en que está escrito.

**Por qué estas versiones.** Son las que registró la evidencia del equipo
(`docs/evidence/b6_public_manifest.json`: Python 3.12.3, numpy 2.5.4, pandas 3.0.6; F0a). Con un
entorno creado solo desde el lock, en una máquina que antes tenía pandas 3.1.0, se reproduce lo
publicado: la suite, el respaldo de la decisión 25 con el mismo SHA-256 (`cb4eeef3617f…`),
`docs/analysis/blocks.md` idéntico salvo la línea del comando, y F0a con su valor fijado y la
reconstrucción byte a byte.

**Coste.** Subir de versión es un cambio de contrato, no un mantenimiento: hay que volver a
regenerar y comparar la submission y la evidencia fijada. Y `make verify-b6` sigue fallando con las
versiones fijadas, incluso con el parche exacto de Python que registró la evidencia (el SHA-256 de
`artifacts/possession.csv` no coincide, aunque las submissions que
se derivan de él sí). La causa no son las dependencias: queda el sistema operativo (la evidencia se
generó en Linux) o el bundle, y se investiga aparte.

---

## 28. `make repro` construye la entrega dos veces desde cero, y la entrega es una cadena en Python

**Decidido.** `tools/repro.py` (#15) construye la cadena entregada dos veces, cada una en su propio
directorio borrado bajo `runs/repro/`, y compara los dos archivos byte a byte: sale con 0 e imprime
un solo SHA-256 si coinciden, y con 1 si no. Hoy la cadena entregada es el respaldo de la decisión
25, que pasa a vivir en `tools/backup.py`; `make backup` y `make repro` solo lo llaman. Cuando un
modelo sustituya al respaldo, entra en `repro.CHAINS` y el default cambia con esa decisión.

**Por qué en Python y no solo en el Makefile.** `make` no viene en un Windows de serie, y la regla 3
del concurso dice que el repositorio regenera el archivo, no que lo regenera en Linux. Con la cadena
en un módulo, la reproducción es `python tools/backup.py` en cualquier sistema, el test puede
construirla dos veces, y el Makefile no lleva una segunda copia de los pasos que pueda divergir. Cada
paso sigue corriendo como proceso propio con el mismo intérprete, como lo correría `make`.

**Coste.** Construir dos veces cuesta el doble de tiempo, y el test que lo hace necesita el bundle,
así que CI no lo ejecuta. Antes del freeze (#26), `make repro` se corre a mano en el entorno fijado
de la decisión 27; su hash es el que se archiva con la entrega.

---

## 29. El motor (#6) asigna la posesión al último balón controlado, con umbrales físicos pre-registrados

**Decidido.** `tools/engine.py` etiqueta cada frame con el equipo del **último control**: un frame es
de control para un equipo cuando el balón está observado, su jugador más cercano está a ≤ `radius_m`,
el rival no está igual de cerca y el balón va a ≤ `speed_mps`. Entre controles se arrastra el estado
dentro de cada medio tiempo, y un cambio necesita `dwell` frames seguidos de control rival, fechado
al primero. Es la definición de `CHALLENGE.md`: la posesión cambia cuando el rival gana posesión
*controlada*; en balones disputados o sueltos se queda con el último equipo. El motor no emite `D`
(lo hará el stream de balón muerto, #16).

**Valores, fijados por física antes del barrido:** `radius_m = 1,5` (alcance más ruido del tracking;
la distancia mediana balón→jugador es 1,84 m), `speed_mps = 5` (una conducción rápida; un pase va a
10 m/s o más), `dwell = 1` (sin espera: un control ya es control).

**Por qué este diseño, medido antes de escribirlo** (slice público, frames vivos con balón):

| balón | acierto del jugador más cercano |
|---|---:|
| < 2 m/s | 91,1% |
| 10–20 m/s | 66,4% |
| > 20 m/s | 38,8% |
| jugador a < 1 m | 90,6% |
| jugador a 4–8 m | 62,0% |

Con el balón en vuelo, el jugador más cercano suele ser un rival que pasa cerca: esa es la raíz del
parpadeo que fragmenta el `argmin`. El control filtra exactamente eso.

**Exploración ya hecha (declarada).** Antes de este pre-registro se probaron 5 configuraciones en el
análisis exploratorio: (1,0 m, 4 m/s, 1), (1,5, 5, 1), (1,5, 5, 5), (2,0, 6, 5), (1,5, 5, 10), con
`spellF1` público entre 0,366 y 0,451. La configuración elegida por prior es la segunda (0,4390),
no la de mayor número (0,4513, dentro del ruido).

**Pre-registro del barrido** (#22), escrito antes de correrlo:

- Rejilla: `radius_m` ∈ {1,0; 1,5; 2,0} × `speed_mps` ∈ {3; 5; 7} × `dwell` ∈ {1; 5; 12}: 27
  configuraciones.
- Por configuración: `spellF1` y `macroF1` públicos, Δ pareado y `n_discordant` frente al default,
  posesiones/min en el partido, y acuerdo con el Smart Tagging en el partido y en los bloques con
  menos balón (7, 9, 11, 18), que es la única señal independiente fuera del slice.
- **Regla de selección:** se entrega el default. Solo se sustituye si otra configuración le gana con
  ≥ 6 posesiones discordantes en el mismo sentido (test de signos p ≤ 0,031) **y** no empeora el
  acuerdo con el Smart Tagging ni rompe la estructura de un bloque (decisión 26). Si no, el barrido es
  un mapa de sensibilidad: dice si el default está en una meseta o en un pico.

---

## 30. Integración del motor: balón muerto del carril D y la reanudación como control (pre-registro)

**Contexto.** Los dos carriles paralelos de #6 terminaron y el coordinador reprodujo sus números:

- **Carril F (formación en huecos): negativo.** El clasificador de formación acierta 80,4% en
  bloques no vistos, pero el acuerdo con el Smart Tagging en los frames de hueco solo pasa de 71,3%
  a 72,9%, bajo el umbral pre-registrado de +2 puntos, y una variante baja el `spellF1` público
  (−0,029). No entra en la cadena; se conserva como evidencia (`docs/proposals/lane-f.md`).
- **Carril D (balón muerto, #16): positivo.** Cada parada es un intervalo desde la salida del balón
  del campo hasta la reanudación del Smart Tagging (variante V2 `out`). Sobre el motor: `spellF1`
  0,4390 → 0,4667, precisión de `D` 0,907, recall 0,384, 12,3% de `D` en el partido. V3 y V4 empatan
  en el slice y no pasan el filtro de bloques (decisión 26) (`docs/proposals/lane-d.md`).

**Pre-registro de la integración**, escrito antes de medirla:

- **I0** = motor + máscara `D` V2. Es lo que ya está medido.
- **I1** = I0 + **la reanudación es un control**: en el frame de reanudación de cada `SET PIECES`
  con `Team` conocido, ese equipo controla el balón (se inyecta en `engine.control` antes de decodificar).
  Es la regla del fútbol, no un parámetro: quien saca un lateral, un córner, una falta o un saque de
  puerta tiene el balón. Hoy el motor arrastra el equipo de antes de la parada hasta el siguiente
  control.
- **Regla de selección:** se entrega I1, por principio, salvo que en el slice pierda posesiones en el
  pareado frente a I0 (`wins_a > wins_b`) o rompa la estructura de un bloque (decisión 26). Si pasa
  eso, se entrega I0.
- Se reporta además, como comprobación de la premisa, en cuántas reanudaciones del slice el `Team`
  del Smart Tagging coincide con el equipo del ground truth justo después.

**Resultado** (medido después del pre-registro, slice público y partido completo):

| cadena | spellF1 | macroF1 | posesiones/min | `D` en el partido | acuerdo ST |
|---|---:|---:|---:|---:|---:|
| motor solo (decisión 29) | 0,4390 | 0,5113 | 3,25 | 0% | 74,0% |
| I0 = motor + `D` | 0,4667 | 0,7082 | 3,63 | 12,3% | 73,0% |
| **I1 = I0 + reanudación como control** | **0,4585** | 0,7066 | 3,59 | 12,3% | 73,1% |

I1 frente a I0: Δ −0,0081 con **0 posesiones discordantes** (cambian bordes, no posesiones) y
ningún bloque roto. **Por la regla pre-registrada se entrega I1**, aunque I0 tenga un número
ligeramente mayor: elegir a posteriori el número más alto es exactamente lo que el pre-registro
existe para impedir. La premisa (quien reanuda tiene el balón) solo se pudo comprobar en una
reanudación del slice, y se cumple; descansa sobre todo en el reglamento, no en esta muestra.

**Coste.** El recall de `D` es bajo (0,384): solo hay 59 reanudaciones etiquetadas, y una parada sin
salida del balón del campo (una falta en juego) no se detecta. El bloque con más `D` llega a 41,8%,
por encima del 19,6% del slice; es el de una celebración de gol, y queda como límite conocido.

**La entrega candidata pasa a ser el motor (I1).** Supera al respaldo de la decisión 25 en el slice
(0,4585 frente a 0,3805) y en estructura: acuerdo con el Smart Tagging 73,1% frente a 62,2%, y 3,59
posesiones/min frente a 3,75 con el respaldo estirando posesiones en los huecos largos. `tools/repro.py`
cambia su cadena por defecto a `engine` (decisión 28) y `make repro` compara con
`submissions/engine.csv`. El respaldo se mantiene construible con `make backup` como red de seguridad
hasta el freeze (#26).

---

## 31. Dos correcciones de principio a la cadena entregada, tras la revisión de #52 (pre-registro)

La revisión de código de #52 encontró dos reglas que contradicen principios ya escritos. Se adoptan
**por principio**, escritas aquí antes de medir su efecto. La medición solo las revierte si pierden
posesiones en el pareado frente a I1 (`wins_a > wins_b`) o rompen la estructura de un bloque
(decisión 26).

1. **Un balón fuera del campo no se controla.** `engine.control` aceptaba un balón observado fuera
   del rectángulo de juego: un jugador que lo recoge para sacar cambiaba la posesión. Un balón fuera
   del campo no está en juego (es la premisa del carril D), así que no hay control. La reanudación ya
   da la posesión a quien saca (decisión 30).
2. **Menos de un segundo fuera del campo no abre una parada.** El carril D aplica ese mínimo
   (`untagged_min_out_s`) solo a la variante sin etiqueta, con la razón escrita en su código: es ruido
   del tracking en la línea, no un balón fuera. En V2, un parpadeo así hasta 40 s antes de una
   reanudación de falta, sin que el balón haya salido de verdad, abre una parada de hasta 40 s. Se
   aplica el mismo mínimo a V2.

Además, sin cambiar la entrega con `dwell = 1`: la reanudación **fuerza** el cambio de posesión en el
decodificador en lugar de inyectarse como un frame de control, que con `dwell > 1` no tenía efecto; y
el barrido de la decisión 29 pasa a medir la cadena entregada, no solo el motor desnudo, y su regla de
selección se aplica tal como está escrita (test de signos p ≤ 0,031, más ganadas que perdidas, y sin
empeorar el acuerdo con el Smart Tagging).

**Resultado y una desviación declarada del pre-registro.** La regla de arriba solo preveía revertir
por el pareado o por los bloques, y daba por buena la premisa de cada corrección. Al medir, la
premisa de la corrección 2 resultó **falsa**, así que se revierte aunque la regla no lo pidiera:

- **Corrección 2, revertida.** Al exigir 1 s fuera del campo, el `D` predicho en el slice cae de 622
  a 545 frames y los aciertos de 564 a 487: **los 77 frames eliminados eran `D` real**. El 55% de las
  salidas del balón dura menos de un segundo (mediana 22 frames): la cámara táctica ve el balón fuera
  solo un instante antes de perderlo. Eso no es ruido en la línea, es la forma normal de una salida
  en este dato. El riesgo que señaló la revisión (un parpadeo de verdad, 35 s antes de una falta sin
  salida) sigue siendo posible y queda como límite conocido.
- **Corrección 1, mantenida.** En la cadena entregada es neutra: Δ 0,0 con 0 posesiones
  discordantes (los 20 frames de control fuera del campo del slice caen dentro de paradas ya
  marcadas `D`). Se mantiene porque es el reglamento. En el motor desnudo, sin reanudaciones, sí baja
  el número (0,4390 → 0,4195), porque nadie devuelve el balón tras una salida; ese motor no es lo que
  se entrega.

Cadena entregada final: **`spellF1` 0,4585**, 12,3% de `D`, acuerdo con el Smart Tagging 73,1%,
reproducible con SHA-256 `4e0ed39b52ed…`.

---

## 32. La reanudación solo se fuerza si el tracking no vio ya el juego reanudado (pre-registro)

La segunda revisión de #52 señaló que el frame de reanudación es una **estimación** (inicio del
`SET PIECES` + 5 s, o + 3,5 s en un saque de centro), y que forzar la posesión ahí puede deshacer lo
que el tracking **observó**: un saque rápido a +2 s y un robo con control a +4 s quedan revertidos al
equipo que sacó.

**Decidido, antes de medir:** la reanudación se fuerza solo si en su ventana `[inicio del tag, frame
de reanudación)` no hay ningún frame de control. Si lo hay, el juego ya se reanudó y el tracking manda:
una observación vale más que una estimación. Si dos reanudaciones caen en el mismo frame con equipos
distintos, ninguna se fuerza; es una etiqueta ambigua y no se resuelve por el orden del XML.

**Regla de selección:** se adopta salvo que pierda posesiones en el pareado frente a la cadena de la
decisión 31 (`wins_a > wins_b`) o rompa un bloque. Y, como enseñó la decisión 31, se comprueba la
premisa: cuántas reanudaciones del partido tienen ya un control dentro de su ventana.

**Resultado.** En el slice, neutro: Δ 0,0 con 0 posesiones discordantes, y la estructura no cambia
(3,64 posesiones/min, 12,3% de `D`, acuerdo con el Smart Tagging 73,1%). Se adopta por la regla. La
premisa se comprueba en el partido: **10 de las 27 reanudaciones con equipo conocido ya tienen un
control observado en su ventana**, y en 2 de esas 10 el primer control es del rival: son justo los
casos que antes se revertían al equipo que sacaba. Se fuerzan 17 de 27. Cadena entregada: SHA-256
`1cdab582ee6b…`.

---

## 33. Banco de trasplante de huecos: se usa para el balón perdido, no para la escala temporal

**Decidido.** `tools/bench.py` puntúa un método en la ventana pública con el patrón de balón ausente
de cada uno de los otros 19 bloques completos de 5 minutos, contra el ground truth real. Es la
métrica principal para todo lo que depende de los huecos de balón (imputación, balón muerto sin
balón visible, detección propia del balón), que hasta ahora se decidía por principio (decisión 24).

- **Cobertura efectiva.** El balón no se puede devolver donde el bloque 1 ya lo perdió, así que la
  ventana degradada conserva el balón solo donde lo vieron el bloque 1 y el donante. Cada fila
  reporta esa cobertura efectiva, no la del donante.
- **`LOW_BALL = 50%`** de cobertura efectiva separa el régimen que el slice público no puede mostrar
  (el partido tiene 56,9% de balón; los bloques 7, 9, 11, 15, 18, 19 y 20 quedan por debajo). La
  tabla dice cuántos donantes promedia cada fila.

**Calibración** contra los números oficiales del partido completo (que nadie aquí puede ver como
etiquetas): para los baselines `smooth` reconstruidos, el banco da 0,0345 / 0,1854 / 0,2150 con
ventanas 0 / 25 / 50, frente a 0,0486 / 0,1996 / 0,2433 oficiales. Predice la caída por balón
perdido, algo pesimista. **No** predice `smooth125` (banco 0,2910, oficial 0,2242): ese pierde en el
partido porque su ventana de 5 s fusiona posesiones más cortas que las del bloque 1, y el banco
conserva la estructura de posesiones del bloque 1. Por eso, para un método con escala temporal
propia el guardarraíl sigue siendo el informe de bloques (decisión 26).

**Motor (decisión 32):** 0,4585 limpio, 0,3516 de media (n = 19) y 0,2782 en los 6 donantes con
menos de la mitad del balón. Es la estimación más honesta disponible de su rendimiento en el
partido completo.

---

## 34. Ronda 1 de investigación: entra el decodificador sin disputa; la imputación en huecos espera

**Contexto.** Cinco carriles en paralelo (vídeo, imputación, balón muerto v2, decodificador, corpus
externo), cada uno con su pre-registro antes de medir y con los números reproducidos por el
coordinador. Los dos primeros en terminar son positivos según sus propias reglas:

- **Decodificador V2 `uncontested`** (`docs/proposals/lane-decode.md`): un control del rival solo
  cambia la posesión si el jugador más cercano del equipo que la tiene está a más de 1,5 m; un duelo
  no la cambia (la regla de duelo de la literatura, sin constante nueva). Slice 0,4585 → 0,5189
  (0 discordantes, jackknife todo positivo), banco 0,3516 → 0,3792 (poco balón 0,2782 → 0,3021),
  3,29 posesiones/min, acuerdo con el Smart Tagging 73,4%.
- **Imputación V2** (`docs/proposals/lane-impute.md`): en un hueco cuyos extremos son de equipos
  distintos, un único punto de cambio colocado por un modelo auto-supervisado (formación, balón
  interpolado, anclas). Banco 0,3516 → 0,3875, acierto en frames ocultos 0,61 → 0,77; slice sin
  cambio. El coordinador comprobó que no hay fuga del balón oculto: todo se calcula desde las
  features degradadas.

**Se suman en el banco:** juntos dan 0,5189 limpio y **0,4143** de media (poco balón 0,3095).

**Pero el Smart Tagging contradice a la imputación en los huecos reales.** En los frames que la
imputación cambia, el Smart Tagging coincide con el nuevo equipo en el 43% (en los bloques con poco
balón, una sola decisión de 679 frames, 0%), y su acuerdo en los bloques 7, 9, 11 y 18 cae de 72,4%
a 66,0%. En el slice, el Smart Tagging acierta el 98% de los frames vivos **sin balón** (391): dentro
de un hueco real es un juez fiable. El banco y el Smart Tagging no se contradicen por azar: el banco
trasplanta huecos sobre jugadas donde el balón sí se veía, y los huecos reales ocurren en jugadas
concretas (balón aéreo, pelotazo, área llena). Es la limitación que declara la decisión 33.

**Decidido.**

- **Entra el decodificador V2** en la cadena entregada: mejora en los tres instrumentos y no tiene
  señal en contra.
- **La imputación queda fuera de la entrega**, sin declararla negativa: tiene a favor el banco y en
  contra la única evidencia sobre huecos reales. Se reevalúa si el carril de vídeo recupera balón en
  huecos reales, que daría verdad física para juzgarla.
- **V3 `touch` y V5 del decodificador** (0,56 y 0,58 en el slice) se aplazan al corpus externo con
  posesión real: su riesgo es de escala temporal, que ni el slice ni el banco pueden juzgar.

**Adenda: V6 sustituye a V2, condicionada al corpus externo.** El seguimiento del carril midió la
única combinación sin escala temporal que faltaba, V6 = `mid` + `uncontested`, con una regla escrita
por el coordinador antes de medir (adoptarla si pasa las tres compuertas frente a V2 y no baja la
media de poco balón). La cumple: slice 0,5189 → 0,5405 (0–2 a IoU 0,5, jackknife +0,011 .. +0,022),
banco 0,3792 → 0,3944 (poco balón 0,3021 → 0,3072), 3,25 posesiones/min, Smart Tagging 73,1%. Se
adopta por esa regla, con una cautela declarada: las dos posesiones que gana son las mismas que ganaba
`mid` solo, cuya regla salió de mirar las latencias del slice, y el banco usa esas mismas 17
posesiones. **Si el corpus externo, que no está contaminado, la sitúa por debajo de V2, se revierte.**

El bloque 11 (19,9% de balón) no es un problema de decodificación: una posesión de 163 s tiene balón
en el 17,5% de sus frames, y ~78 s dependen de un duelo de 0,2 s justo tras un hueco de 69,5 s. Es un
problema de huecos de balón.

**Adenda 2: el corpus externo revierte V6 a V2.** El carril externo convirtió los 7 partidos abiertos
de DFL/IDSSE (CC-BY) en un corpus puntuable (`tools/external.py`, `docs/analysis/external*.md`). Su
compuerta de dominio **falla**: la verdad de DFL tiene 4,58 posesiones/min, mediana de 3,8 s y
41–52% de `D` (nuestro partido: 3,4/min, 7,6 s, 19,6%), así que **no sirve para fijar escalas de
tiempo ni reglas de `D`**. Sí reproduce la pérdida relativa por balón perdido del banco (−28% frente
a −34%) y el mismo orden entre métodos, lo que valida el banco desde fuera.

Con su regla pre-registrada, V6 queda por debajo de V2 (0,2319 frente a 0,2394 degradado; V2 gana 6
de 7 partidos), así que **se revierte a V2**, como decía la adenda anterior. El matiz se declara: lo
que V6 añade es solo redatar los cambios, que depende de la definición de la verdad, y la de DFL es
otra; pero la regla estaba escrita y no se reinterpreta. `touch` y V5 pierden 7 de 7 frente a su
referencia sin `touch`, con tasas más lejos de la verdad: alarma de escala temporal, siguen fuera.

**Integración.** La regla del duelo entra en `tools/engine.py` (`Params.duel = True`, `uncontested`,
`decode(switch=…)`), con etiquetas idénticas frame a frame al V2 del carril. `engine.D31` conserva el
motor anterior, contra el que los carriles midieron y archivaron. Cadena entregada: **slice 0,5189**,
banco 0,3792 (poco balón 0,3021).

---

## 35. Una reanudación solo se cancela por un control que el decodificador acepta (pre-registro)

La revisión de #54 encontró una interacción entre la decisión 32 y la regla del duelo (34): una
reanudación se cancela si en su ventana hay *cualquier* control, también uno disputado; pero el
decodificador ignora el disputado. Resultado: ni la reanudación ni el control cambian la posesión, y
el equipo que no saca se queda el balón durante el saque del rival.

**Decidido, antes de medir:** la ventana de la decisión 32 mira solo los controles que el
decodificador acepta (los que no son duelo). El principio de la 32 era que una **observación de
posesión** vale más que una estimación; un duelo no observa posesión. Regla: se adopta salvo que
pierda posesiones en el pareado frente a la cadena actual o rompa un bloque.

Además, un caso límite declarado: si una mitad empieza con una reanudación forzada antes de su primer
control, el motor trata un primer control disputado del rival como duelo (no cambia la posesión que
dio la reanudación), y `decoder.decode` lo acepta como primer evento. El motor es el coherente con la
regla; en BAR-ATH el caso no ocurre (V2 y la cadena entregada son idénticos frame a frame).

**Resultado.** En BAR-ATH no cambia **ni un frame** de la cadena entregada (la interacción no ocurre en
este partido): mismo slice 0,5189, mismo banco 0,3792, mismos bloques. Se adopta por la regla, como
robustez; un test sintético fija el caso que corrige.

---

## 36. El balón muerto también se lee en los jugadores (carril dead-v2, regla W1)

**Contexto.** El recall de `D` de la cadena era 0,384: solo se detectaban las paradas con salida del
balón del campo y reanudación etiquetada. El carril dead-v2 (`docs/proposals/lane-dead-v2.md`)
construyó un detector de paradas sin balón y sin identidades, a partir de la velocidad de los
jugadores, con **todas sus constantes fijadas en los 7 partidos abiertos de DFL** (CC-BY, con estado
vivo/muerto por frame), no en nuestro slice. Pre-registro antes de medir; números reproducidos por el
coordinador.

**Decidido (W1 `rule`).** A las paradas etiquetadas se une cada tramo de ≥ 4 s en que el percentil 90
de las velocidades de los jugadores (el segundo más rápido de ~21), promediado sobre ±1 s, va por
debajo de 2 m/s; cerrando huecos vivos de < 1 s, medio tiempo a medio tiempo, y nunca con menos de 8
jugadores seguidos. Solo numpy, sin pesos. `engine.delivered_dead()` es la única definición del `D`
entregado; la usan `run`, el banco y el barrido.

**Por qué**, medido sobre la cadena con la regla del duelo:

| | sin W1 | con W1 |
|---|---:|---:|
| `spellF1` slice | 0,5189 | 0,5368 (+0,018, 1–0; jackknife cambia de signo: dirección) |
| banco, media / poco balón | 0,3792 / 0,3021 | **0,4351 / 0,3595** |
| precisión / recall de `D` (slice) | 0,907 / 0,384 | 0,877 / 0,897 |
| acuerdo con el Smart Tagging | 73,4% | **77,1%** |
| corpus DFL (motor D31) | 0,376 | 0,432 (7 de 7 partidos) |

La evidencia fuerte no es el slice (17 posesiones, una discordante) sino tres fuentes independientes
de él que dicen lo mismo: el banco, el Smart Tagging y los partidos de DFL.

**Coste.** El 40,3% de los frames de los medios tiempos pasa a ser `D`, frente al 19,6% del slice; el
bloque máximo llega a 65,5% (bloque 9). No es una anomalía: el balón está en juego unos 55–60 de los
90 minutos de un partido, y los primeros 5 minutos son un tramo especialmente vivo. Las variantes con
modelo aprendido puntúan más en el slice (0,5026 sobre el motor anterior) pero fallan la compuerta de
precisión de `D` (0,787 < 0,80, por desbordar los bordes de la parada) y quedan fuera.

**Adenda (revisión de #54).** La regla decía que un frame sin cuantil de velocidad propio (menos de 8
jugadores seguidos) nunca es `D`, pero el código comprobaba la media de la ventana de ±1 s, no el
frame. Corregido para que cumpla la regla escrita: cambian 452 frames, el `D` del partido pasa de
40,3% a 40,0%, y el slice (0,5368) y el banco (0,4351 / 0,3595) no cambian. La regla calcula ahora
solo la señal que usa, no las 29 columnas del modelo, y la máscara de jugadores se calcula siempre
sobre los medios tiempos del partido. `engine.delivered_dead` usa `dead_ball_v2.dead_union`: una
sola definición del `D` entregado. Repro: `72c98ed4bb4a…`.
