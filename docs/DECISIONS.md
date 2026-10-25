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
