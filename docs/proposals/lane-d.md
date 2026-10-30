# Carril D — corriente de balón muerto (#16) sobre el motor (#6)

Estado: **pre-registro** (escrito y commiteado antes de correr ninguna variante contra el ground
truth). Las secciones de medición, recomendación y limitaciones se añaden después, en un commit
aparte, sin tocar esta sección.

## 1. Qué se propone

`tools/dead_ball.py` produce una máscara booleana por frame para todo el partido (`dead_mask`) y
`apply_dead(labels, dead)` escribe `D` sobre las etiquetas `frame,label` del motor
(`python tools/engine.py --labels runs/engine/labels.csv`). El motor nunca emite `D`
(DECISIONS 16 se lo deja a esta corriente).

La parada se modela como un **intervalo** `[inicio, reanudación)`, no como un umbral por frame
(DECISIONS 16): empieza en un evento de balón fuera de juego y termina en la reanudación. Fuentes,
solo las entregadas: tracking (`tools/atd.py`, `tools/engine.features`) y Smart Tagging
(`tools/smart_tagging.load`).

## 2. Lo que se miró antes de escribir esto (sin ground truth)

Solo tracking y tagging, agregados, en todo el partido. Nada de esto lee una etiqueta.

- `SET PIECES`: 59 instancias con `Type` (26 saques de banda, 12 córners, 10 saques de puerta,
  5 tiros libres, 4 saques de centro tras gol, 2 saques de centro de inicio). **Todas duran
  exactamente 35 s, salvo los saques de centro, que duran 5 s**: el tag es una ventana fija
  alrededor de la reanudación, no la parada.
- Saques de centro de inicio: el saque real (frames 11.185 y 113.742, ya verificados en
  `tools/smart_tagging.py`) cae **3,52 s y 3,28 s** después del inicio del tag.
- Ventanas de 35 s promediadas (53 instancias): la mediana de velocidad de los jugadores toca
  fondo entre 0 y +4 s (≈1,0 m/s, frente a ≈2,2 m/s a +10 s), el balón está lento (<1,5 m/s) en
  el 47% de las instancias entre 0 y +4 s y en ~10% fuera de ahí, y el juego se reanuda entre +4 y
  +6 s. Donde se detecta un golpeo tras balón quieto, cae a una mediana de 4,4 s (saque de
  puerta) y 6,3 s (saque de banda) del inicio del tag.
- `GOALS`: 4 instancias de 70–250 s que terminan 1 s después del inicio del saque de centro
  siguiente; describen la jugada y la celebración, no el instante del gol. El balón está visible
  en el 0–14% de los 60 s previos a cada saque de centro tras gol.
- Episodios de balón observado fuera del rectángulo (fusionando huecos ≤ 1 s): 102 en el
  partido, mediana 0,88 s, 46 de ≥ 1 s. 42 van seguidos de una reanudación etiquetada en ≤ 40 s
  (mediana 14,3 s); 60 no. Los saques de banda tienen un inicio de episodio en los 40 s previos
  en 18 de 26 casos; córners 4/12, saques de puerta 5/10.

Además conozco, porque está en DECISIONS 16 y en el brief, que la ventana pública tiene 4 tramos
`D` de 5,5 / 20,4 / 18,3 / 14,5 s. Ninguna constante de abajo se eligió para encajar con eso.

## 3. Constantes (fijas, ninguna se barre)

| constante | valor | por qué |
|---|---:|---|
| reanudación en tags de saque de centro (5 s) | inicio + 3,5 s | saques reales a 3,52 y 3,28 s |
| reanudación en el resto de tags (35 s) | inicio + 5,0 s | perfil de quietud 0..+4 s, juego a +4..+6 s |
| episodio fuera: fusión de huecos | ≤ 25 frames (1 s) | un balón que sale no vuelve en menos de 1 s |
| retrospección máxima desde la reanudación | 40 s | una parada de juego abierto rara vez pasa de 40 s |
| retrospección tras gol (`Kick Off (After Goal)`) | 120 s | celebración + saque de centro |
| quietud: mediana de velocidad de los jugadores, media móvil centrada de 1 s | < 1,5 m/s | ritmo de paseo (≈1,4 m/s); trotar es ≥ 2 m/s |
| episodio fuera sin reanudación etiquetada (solo V4) | ≥ 25 frames fuera | menos de 1 s es ruido de la línea |

Reglas comunes a todas las variantes:

- Todo se recorta a los dos medios tiempos de `games.half_video_blocks`; ninguna parada cruza el
  descanso.
- Una parada nunca empieza antes de la reanudación anterior (la del tag previo).
- `Kick Off (Start)`: antes del primer saque de un medio tiempo el balón no está en juego, así que
  la parada empieza en el primer frame del medio tiempo, sin tope de retrospección.
- `apply_dead` solo escribe `D` donde la máscara es `True`; el resto de etiquetas no cambia.

## 4. Variantes (cuatro, ni una más)

- **V1 `tag`** — solo Smart Tagging: `D = [inicio del tag, reanudación)` para cada `SET PIECES`.
  La parada mínima que el tag sostiene por sí solo (3,5–5 s).
- **V2 `out`** — V1, y además, si en `[reanudación − retrospección, inicio del tag)` empieza un
  episodio de balón fuera, la parada empieza en el primer frame fuera del **último** de esos
  episodios: `D = [inicio del episodio, reanudación)`.
- **V3 `out+still`** — V2, y cuando no hay episodio fuera, la parada se extiende hacia atrás desde
  el inicio del tag mientras el campo esté quieto (regla de quietud de la tabla), con el mismo tope
  de retrospección.
- **V4 `out+still+untagged`** — V3, y además cada episodio fuera de ≥ 1 s **sin** reanudación
  etiquetada en los 40 s siguientes a su inicio abre una parada propia:
  `D = [inicio del episodio, primer frame posterior con el balón observado dentro del campo)`,
  con tope de 40 s. Es la única que puede ver paradas que el tagger no etiquetó.

## 5. Mediciones (para cada variante, mismas para todas)

Con el scorer oficial (`evaluation/possession_metrics.py`, vía `tools/compare_submissions.py`)
sobre el slice público, contra las etiquetas del motor:

- `spellF1`, `macroF1`, Δ pareado de `spellF1` y `n_discordant` frente al motor;
- TP / FP / FN a IoU 0,5;
- precisión y recall de `D` por frame en la ventana pública;
- `python tools/blocks.py` del motor con y sin `D`: `%D` por bloque en todo el partido.

## 6. Regla de selección (pre-registrada)

1. **Compuertas**, todas obligatorias:
   - Δ pareado de `spellF1` frente al motor **≥ 0** en el slice público (dirección, no prueba);
   - precisión de `D` por frame en la ventana pública **≥ 0,5**;
   - `%D` en los dos medios tiempos del partido **≤ 40%** y **ningún bloque con `%D` ≥ 50%**.
2. Entre las que pasan, se recomienda la primera en este **orden de prior**, sin mirar cuál tiene
   el `spellF1` más alto: **V3 > V4 > V2 > V1**. V3 es el modelo físico completo (evento de salida
   o quietud como inicio, reanudación etiquetada como fin: dos fuentes independientes por parada);
   V4 añade paradas sin ancla de reanudación, cuyo fin es menos fiable; V2 y V1 son ablaciones.
3. Una diferencia de `spellF1` entre variantes que pasan no altera el orden, sea del tamaño que
   sea: 17 posesiones no ordenan métodos (AGENTS.md, EVALUATION.md).
4. Si ninguna pasa, la recomendación es **no escribir `D`** y el resultado se reporta como
   negativo.

---

*Lo que sigue se escribió después de medir. Las secciones 1–6 son las del commit `8bb690a` sin
cambios.*

## 7. Cómo se reproducen los números

```bash
export MTAH_DATA_DIR=...                 # el bundle licenciado
python tools/engine.py --labels runs/engine/labels.csv
for v in tag out out+still out+still+untagged; do
  python tools/dead_ball.py --labels runs/engine/labels.csv --variant "$v" \
      --out "runs/dead_ball/$v.csv" --gt public                       # %D, fuentes, precisión/recall de D
  python tools/compare_submissions.py runs/engine/labels.csv "runs/dead_ball/$v.csv" --gt public
done
mkdir -p runs/lane-d/results && cp runs/engine/labels.csv runs/lane-d/results/engine.csv
for v in tag out out+still out+still+untagged; do cp "runs/dead_ball/$v.csv" "runs/lane-d/results/engine+$v.csv"; done
python evaluation/run_evaluation.py --gt public --results runs/lane-d/results --out runs/lane-d/eval --no-detail
python tools/blocks.py runs/lane-d/results/engine.csv runs/lane-d/results/engine+*.csv
```

`runs/` está ignorado por Git; ninguna salida frame a frame sale del disco local. Las cuatro salidas
son deterministas (mismo SHA-256 antes y después de refactorizar `stoppages()`).

## 8. Mediciones

Slice público, 17 posesiones, 7.500 frames graduados, 1.469 de `D`. El motor solo da
`spellF1` 0,4390; con el `D` verdadero insertado daría 0,5333 (brief, no recalculado aquí).

| variante | `spellF1` | `macroF1` | Δ pareado | `n_discordant` | TP / FP / FN @ IoU 0,5 | posesiones pred. | precisión `D` | recall `D` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| motor (sin `D`) | 0,4390 | 0,5113 | — | — | 10 / 14 / 7 | 24 | — | 0 |
| V1 `tag` | 0,4465 | 0,5899 | +0,0075 | 0 | 10 / 16 / 7 | 26 | 0,776 | 0,132 |
| **V2 `out`** | **0,4667** | **0,7082** | **+0,0276** | 0 | 10 / 15 / 7 | 25 | **0,907** | **0,384** |
| V3 `out+still` | 0,4667 | 0,7082 | +0,0276 | 0 | 10 / 15 / 7 | 25 | 0,907 | 0,384 |
| V4 `out+still+untagged` | 0,4667 | 0,7082 | +0,0276 | 0 | 10 / 15 / 7 | 25 | 0,907 | 0,384 |

V2, V3 y V4 dan **exactamente** las mismas etiquetas dentro de la ventana pública: ahí cada
reanudación etiquetada tiene un episodio de balón fuera antes, así que la quietud no se usa, y no
hay ningún episodio largo sin reanudación. El slice no puede distinguirlas; lo que las separa es el
resto del partido.

Partido completo, en los dos medios tiempos (sin ground truth):

| variante | `%D` | paradas | origen de cada parada | mediana |
|---|---:|---:|---|---:|
| V1 `tag` | 6,2% | 59 | 2 saque inicial, 57 solo tag | 5,0 s |
| V2 `out` | 12,3% | 59 | 2 saque inicial, 28 balón fuera, 29 solo tag | 5,4 s |
| V3 `out+still` | 24,1% | 59 | 2 saque inicial, 28 balón fuera, 26 quietud, 3 solo tag | 19,9 s |
| V4 `out+still+untagged` | 25,1% | 74 | V3 + 15 episodios fuera sin tag | 16,1 s |

`%D` por bloque (`tools/blocks.py`; el motor solo da 0,0% en los 22):

| bloque | balón | V1 | V2 | V3 | V4 |
|---|---:|---:|---:|---:|---:|
| 1★ | 88,2% | 3,3% | 8,3% | 8,3% | 8,3% |
| 2 | 82,7% | 5,0% | 9,5% | 14,5% | 14,5% |
| 3 | 76,5% | 3,3% | 13,3% | 13,3% | 13,3% |
| 4 | 72,3% | 6,7% | 9,4% | 18,1% | 18,1% |
| 5 | 56,0% | 5,0% | 6,0% | 37,5% | 37,5% |
| 6 | 64,7% | 4,5% | 14,3% | 29,1% | 29,1% |
| 7 | 36,9% | 2,8% | 11,6% | **50,4%** | **50,4%** |
| 8 | 57,2% | 3,3% | 9,2% | 9,2% | 9,2% |
| 9 | 29,0% | 2,8% | 22,9% | 34,6% | 34,6% |
| 10 | 53,7% | 5,0% | 5,0% | 25,7% | 27,3% |
| 11 | 19,9% | 0,0% | 0,0% | 0,0% | 13,7% |
| 12 | 87,8% | 40,9% | 41,8% | 41,8% | 42,2% |
| 13 | 67,4% | 6,7% | 9,9% | 11,5% | 12,7% |
| 14 | 73,5% | 3,3% | 8,9% | 16,1% | 19,9% |
| 15 | 45,2% | 5,0% | 15,8% | 34,6% | 34,6% |
| 16 | 73,7% | 3,3% | 4,9% | 16,6% | 17,4% |
| 17 | 61,0% | 5,1% | 8,8% | 15,3% | 17,5% |
| 18 | 20,3% | 4,4% | 4,4% | 44,1% | 44,1% |
| 19 | 48,6% | 8,3% | 28,1% | 37,3% | 37,3% |
| 20 | 47,9% | 0,0% | 0,0% | 0,0% | 0,0% |
| 21 | 60,0% | 10,0% | 14,9% | 39,0% | 40,6% |
| 22 | 71,7% | 5,7% | 23,1% | 23,1% | 27,1% |
| **partido** | 59,3% | **6,2%** | **12,3%** | **24,1%** | **25,1%** |

El bloque 12 lleva ~39 puntos de `D` en todas las variantes por la regla del saque inicial: el
segundo medio tiempo de `games.half_video_blocks` empieza 117 s antes del saque real, y antes del
saque el balón no está en juego. Esos frames no se gradúan (CHALLENGE.md), así que no mueven el score.

## 9. Recomendación: **V2 `out`**

Aplicando la regla de la sección 6 tal cual:

| compuerta | V1 | V2 | V3 | V4 |
|---|---|---|---|---|
| Δ `spellF1` ≥ 0 | sí (+0,0075) | sí (+0,0276) | sí (+0,0276) | sí (+0,0276) |
| precisión `D` ≥ 0,5 | sí (0,776) | sí (0,907) | sí (0,907) | sí (0,907) |
| `%D` partido ≤ 40% | sí (6,2%) | sí (12,3%) | sí (24,1%) | sí (25,1%) |
| ningún bloque ≥ 50% | sí (40,9%) | sí (41,8%) | **no (50,4%, bloque 7)** | **no (50,4%, bloque 7)** |

V3 y V4 caen por el bloque 7; en el orden de prior (V3 > V4 > V2 > V1) la primera que pasa es
**V2**. Que V2 también tenga el `spellF1` más alto del slice no es la razón: empata con V3 y V4.

Qué hace V2: cada reanudación etiquetada cierra una parada, y la parada empieza en el último
episodio de balón observado fuera del campo en los 40 s anteriores (120 s tras un gol); sin episodio,
la parada es solo la parte del tag anterior a la reanudación (3,5–5 s). En el slice, el 90,7% de lo
que marca es `D` de verdad y cubre el 38,4% del `D` verdadero.

**Lo que esto no prueba.** +0,0276 con `n_discordant = 0`: a IoU 0,5 ninguna posesión verdadera
cambia de estado, y ahí el Δ es **negativo** (−0,0116: una predicción más, 25 frente a 24, sin un
emparejamiento más). El Δ medio sale de los otros cuatro umbrales, donde V2 empareja una posesión
más que el motor (+0,034 / +0,035 / +0,040 / +0,042 a 0,3 / 0,4 / 0,6 / 0,7). Está muy por debajo de la banda de ~0,3 que AGENTS.md pide para leer un Δ local como
algo más que dirección. El único argumento fuerte es estructural: precisión de `D` 0,907 y ningún
bloque fuera de lo plausible.

## 10. Limitaciones conocidas

- **El bloque 7 lo tumba un solo gol.** En V3, la quietud antes del saque de centro tras ese gol se
  extiende hasta el tope de 120 s (40% del bloque, 3.000 frames). Un campo "quieto" durante dos
  minutos enteros antes del saque incluye por fuerza la jugada del gol, así que el tope y no la
  física decide ese intervalo. Una V3 con la quietud limitada a 40 s también tras un gol es una
  variante **nueva**: hay que pre-registrarla antes de medirla, no elegirla ahora.
- **Recall bajo, y por construcción.** Smart Tagging etiqueta 59 reanudaciones en todo el partido;
  un partido real tiene bastantes más (faltas, fueras de juego, cambios, lesiones: solo 5 tiros
  libres etiquetados). Cada reanudación sin tag es una parada que V2 no ve y dos posesiones que se
  funden. V4 es el intento de cubrirlas y el slice no puede medirlo (0 episodios en la ventana).
- **29 de 59 paradas son solo los 3,5–5 s del tag**: sin balón fuera observado (córners y saques de
  puerta cruzan la línea de fondo, donde la cámara táctica pierde el balón), el inicio real de la
  parada queda sin evidencia y la posesión anterior se alarga hasta el tag.
- **Tiros libres**: el perfil de los 5 tags sitúa el golpeo cerca de +10 s, no +5 s, así que su `D`
  termina ~5 s antes. Se mantuvo la constante pre-registrada; con 5 instancias no hay base para una
  propia.
- **El motor no se reinicia en la reanudación.** Tras la `D`, el motor arrastra el equipo que tenía
  el estado hasta el primer control del otro, así que la primera posesión tras una parada puede
  empezar con el equipo equivocado. Es integración (#6), no de este módulo.
- **El slice no separa V2, V3 y V4**, y la ventana pública es la parte del partido con más balón
  (88,2%): la cobertura del disparador "balón fuera" está sobrestimada ahí (DECISIONS 13 y 16).
