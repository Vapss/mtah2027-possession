# Carril d-edges — dónde TERMINA una parada

Estado: **medido — resultado negativo** (sección 9). Las secciones 1–6 se escribieron y commitearon
(`7d19f6d`) antes de correr ninguna variante contra ninguna etiqueta (DFL, slice, banco); las 7–10
se añadieron después, en un commit aparte, sin tocar las 1–6 salvo esta línea de estado.

Código: `tools/dead_ball_edges.py`; pruebas: `tests/test_dead_ball_edges.py`. Este documento no
cambia el motor ni `docs/DECISIONS.md`: el coordinador integra.

## 1. Qué se propone

El `D` entregado (decisiones 30–36) es la **unión** de las paradas etiquetadas (balón fuera →
reanudación del Smart Tagging, fechada en inicio del tag + 5 s; saque de centro + 3,5 s) y de las
paradas de los jugadores W1. Una unión termina donde termina **la más tardía** de las dos. Así que
una parada etiquetada sigue en `D` mientras los jugadores sigan lentos, aunque el tag diga que el
balón ya está en juego.

El balón está en juego desde la reanudación, diga lo que diga la velocidad de los jugadores. Es el
mismo principio que `dead_ball.stoppages` ya aplica al **inicio** de una parada (nunca empieza antes
de la reanudación anterior); aquí se aplica al final.

## 2. Lo que se miró antes de escribir esto (declarado)

Nada de esta sección toca una etiqueta del partido; lo de DFL no puntúa ninguna variante.

### 2.1 El partido, sin ground truth (`python tools/dead_ball_edges.py --explore`)

| | valor |
|---|---:|
| reanudaciones etiquetadas | 59 |
| … con un tramo W1 en curso en el frame estimado | 26 (44%) |
| cuánto sigue W1 tras la estimación, s, p10/25/50/75/90 | 0,58 / 0,81 / 1,60 / 5,75 / 11,8 |
| frames de W1 tras las estimaciones (lo que corta `cut`) | 2.518 (100,7 s) |
| reanudaciones que `kick` re-fecha | 46 de 59 |
| balón rápido − estimación, s, p10/25/50/75/90 | −1,12 / −0,43 / +1,16 / +2,30 / +2,84 |
| … antes de la estimación | 15 de 46 |
| `%D` en los medios tiempos: `engine` / `cut` / `kick` / `cut+onset` / `kick+onset` | 40,0 / 38,4 / 38,4 / 42,0 / 42,0% |

Lectura: cuando W1 cubre una reanudación etiquetada, la alarga una mediana de 1,6 s y a veces
mucho más (p90 11,8 s): son los frames donde la verdad ya está en juego y el reanudador controla el
balón dentro de `D` (lo que el carril dating vio en tres posesiones del slice, ver 2.4). El primer
balón rápido (≥ 10 m/s) dentro del campo cae una mediana de 1,2 s **después** de la estimación de
+5 s, no antes: la estimación suele ser temprana, no tardía. Por eso la ventana de `kick` se centra
en la estimación (sección 4) en lugar de terminar en ella, como sugería el brief.

### 2.2 DFL (7 partidos, estado vivo/muerto por frame)

- **El balón de DFL está congelado mientras está muerto**: el 100% de los frames muertos tienen
  desplazamiento nulo del balón (0,7% de los vivos), y en el primer frame vivo el balón salta
  (velocidad aparente mediana 153 m/s, p10 43). La reanudación es un teletransporte. Ninguna regla
  que feche con el balón puede juzgarse ahí: la encontraría en el salto. Las reglas de los
  jugadores y el principio del corte sí.
- Con la reanudación verdadera, W1 está en curso en 225 de 696 reanudaciones y la sobrepasa poco
  (mediana 0,6 s, p90 1,9 s; 8.264 frames vivos en total). El corte en DFL es pequeño.
- El final de W1 frente a la verdad (todas sus paradas): p10/25/50/75/90 = −20,1 / −4,5 / −0,7 /
  +0,3 / +1,0 s; el 9,6% termina más de 1 s tarde. Es lo que dead-v3 ya midió (fin 0,7 s antes).

### 2.3 Otros caminos mirados y descartados

- **Muestras abiertas de Metrica (g1, g2)**, con reanudaciones anotadas por eventos: el balón no
  está en el tracking durante las paradas (g2: 3,8% de presencia en los 3 s antes de un `SET PIECE`),
  así que tampoco pueden juzgar una fecha por balón. No se usan.
- **La regla E2 del brief para paradas sin tag** (terminar en el primer control seguido de
  movimiento del balón): de 76 tramos W1 sin reanudación etiquetada, solo 7 contienen un control
  seguido de un balón ≥ 10 m/s, y 2 de ellos a 12–18 s del final del tramo (balón movido durante la
  parada, el riesgo que el brief señala). Efecto potencial mínimo y sin juez externo (DFL congela el
  balón muerto): no se propone.

### 2.4 Lo que se sabía del slice antes de esto (contaminado, declarado)

El carril dating (sección 9 de `lane-dating.md`) vio, mirando el slice después de medir, que en
tres posesiones verdaderas (#6, #14, #17) todos los frames de retraso son `D` predicho y el nuevo
equipo controla el balón dentro (hasta 48 frames). Esa pista motivó el carril; no se usó para elegir
ninguna regla ni constante, y por eso la aceptación descansa sobre DFL, el banco y el informe de
bloques además del slice.

## 3. Constantes (fijas; ninguna se barre contra etiquetas)

| constante | valor | de dónde |
|---|---:|---|
| corte (`cut`) | sin constante | principio: el balón está en juego desde la reanudación |
| `kick_mps` | 10 m/s | `engine.Params`: un pase va a 10 m/s o más; balón colocado, llevado o conducido, más lento |
| ventana de `kick` | `[inicio del tag, inicio + 2 × offset)` | centrada en la estimación entregada, tan lejos después como el inicio del tag está antes (10 s; 7 s en un saque de centro) |
| `onset` (U1) | 3,25 m/s, 40 s, barreras = reanudaciones entregadas | dead-v3 sin cambios (DFL) |
| errores de los tags sintéticos de DFL | ciclo −2, −1, 0, +1, +2 s | alrededor de "el juego se reanuda entre +4 y +6 s del tag" (`lane-d.md`) |

## 4. Variantes (cuatro, ni una más)

Todas son la cadena entregada (`engine.DEFAULT`: control, regla del duelo, reanudaciones forzadas
con las decisiones 32/35) y cambian solo lo que dice su nombre. Referencia: **`engine`** =
`bench.METHODS["engine"]` = `engine.run()` (lo fija un test con el bundle).

- **E1 `cut`** — cada reanudación etiquetada (frame entregado) termina el tramo de los jugadores
  que la contiene: los frames W1 desde la reanudación hasta el final de ese tramo pasan a vivos. Un
  tramo que no contiene una reanudación no cambia.
- **E2 `kick`** — E1 con la reanudación fechada por el balón: el primer frame de la ventana en que
  el balón se ve dentro del campo a ≥ 10 m/s (desconocido falla cerrado); sin él, la estimación
  entregada. La ventana se recorta al medio tiempo y empieza después de la reanudación anterior
  (un saque nunca fecha dos). El frame re-fechado cierra la parada etiquetada, corta W1 y es donde
  la reanudación da el balón a su equipo (decisiones 30–32 sin cambios).
- **E3 `cut+onset`** — E1 sobre W1 con los inicios llevados a su onset (U1 de dead-v3, sin cambios).
- **E4 `kick+onset`** — E2 sobre W1 con onset.

## 5. Mediciones (todas, para cada variante y para `engine`)

1. **DFL** (`python tools/dead_ball_edges.py dfl`), con tags sintéticos (`dfl_tags`): una
   reanudación por parada verdadera cuyo balón congelado está fuera del campo (balón fuera, lo que
   cubre nuestro Smart Tagging), equipo = el de la verdad en el primer frame vivo, estimación
   desplazada de la verdadera por el ciclo de errores y tag 5 s antes. `D` = paradas etiquetadas ∪
   paradas de los jugadores (W1 o W1+onset), reanudaciones forzadas como en el motor. Se informa:
   `spellF1` oficial por partido, limpio y con nuestro balón (`external.score`), partidos ganados a
   `engine` (estrictamente mayor), precisión/recall/F1 de `D` por frame, y error de bordes de los
   tramos `D` frente a la verdad (`dead_ball_v3.edge_offsets`): mediana y mediana de \|·\| de inicio
   y fin, media de \|fin\|, parte de finales > 1 s tarde; además \|fin\| con el error fijo en cada
   valor del ciclo. **Para E2/E4, DFL es optimista** (el balón salta en la reanudación verdadera):
   sus números en DFL no cuentan como evidencia de la fecha por balón.
2. **Slice público**: `spellF1`, `macroF1`, posesiones predichas, precisión y recall de `D`;
   Δ pareado, `n_discordant`, ganadas motor/variante con
   `tools/compare_submissions.py engine.csv V.csv --gt public`.
3. **Banco** (`python tools/dead_ball_edges.py --bench`): limpio, media de donantes, media con poco
   balón, peor donante.
4. **Informe de bloques** (`tools/blocks.py`): `%D` y posesiones/min por bloque y en el partido,
   acuerdo con el Smart Tagging.

## 6. Regla de selección (pre-registrada)

1. **Compuertas**, todas obligatorias, frente a `engine`:
   - **G-DFL1**: gana a `engine` en **≥ 6 de 7** partidos DFL en `spellF1` limpio **y** en ≥ 6 de 7
     con nuestro balón (ciclo de errores);
   - **G-DFL2**: error de bordes no peor: mediana de \|fin\| **≤** la de `engine` y mediana de
     \|inicio\| **≤** la de `engine` (DFL limpio, ciclo de errores);
   - **G1** slice: precisión de `D` **≥ 0,85**;
   - **G2** slice: Δ pareado de `spellF1` **≥ 0** y `wins_a ≤ wins_b` (motor ≤ variante);
   - **G3** banco: media de donantes **≥** la de `engine` y media con poco balón **≥** la de
     `engine` (las que dé el comando; la decisión 36 dice 0,4351 / 0,3595);
   - **G4** bloques: ningún bloque con **> 70%** de `D`, ningún bloque sin posesiones, posesiones/min
     del partido en **3,4 ± 0,5**;
   - **G5** acuerdo con el Smart Tagging **≥** el de `engine` **− 1 punto**.
2. Entre las que pasan, se recomienda la primera en este **orden de prior**, sin mirar cuál tiene
   más `spellF1`: **E3 `cut+onset` > E1 `cut` > E4 `kick+onset` > E2 `kick`**. El corte es un
   principio sin constante que DFL juzga entero; con el onset responde a los dos bordes (y el brief
   solo admite U1 dentro de una combinación que pase todo). La fecha por balón depende de una
   constante que ningún juez externo puede validar (sección 2.2), por eso va detrás.
3. Las diferencias de `spellF1` entre variantes que pasan no alteran el orden.
4. Si ninguna pasa, la recomendación es **mantener la cadena entregada** y el resultado se reporta
   como negativo, con qué compuerta falla y por cuánto.

---

*Lo que sigue se escribió después de medir. Las secciones 1–6 son las del commit `7d19f6d` sin
cambios, salvo la línea de estado.*

## 7. Cómo se reproducen los números

```bash
export MTAH_DATA_DIR=...                         # el bundle licenciado
python tools/dead_ball_edges.py --explore        # sección 2.1, sin ground truth
python tools/dead_ball_edges.py dfl              # sección 8.1 (IDSSE en MTAH_EXTERNAL_DIR)
python tools/engine.py --labels runs/d_edges/delivered.csv
for v in engine cut kick cut+onset kick+onset; do
  python tools/dead_ball_edges.py --variant "$v" --labels "runs/d_edges/$v.csv" --gt public
done
for v in cut kick cut+onset kick+onset; do
  python tools/compare_submissions.py runs/d_edges/engine.csv "runs/d_edges/$v.csv" --gt public
done
python tools/dead_ball_edges.py --bench
python tools/blocks.py runs/d_edges/engine.csv runs/d_edges/cut.csv runs/d_edges/kick.csv \
    runs/d_edges/cut+onset.csv runs/d_edges/kick+onset.csv
```

**`engine` es la cadena entregada, byte a byte:** `runs/d_edges/engine.csv` y la salida de
`tools/engine.py --labels` tienen el mismo SHA-256, `72c98ed4bb4a…` (el repro de la decisión 36), y
`tests/test_dead_ball_edges.py::test_the_engine_variant_reproduces_the_delivered_run` lo fija. Las
variantes son deterministas (solo numpy/pandas): `cut` `c88d2a97dfd1…`, `kick` `5cc814642a5a…`,
`cut+onset` `a081b5623ec8…`, `kick+onset` `3c034a093a7e…`. `runs/` está ignorado por Git. El orden
de lectura fue el del brief: DFL primero; el slice, el banco y los bloques después.

## 8. Mediciones

### 8.1 DFL (7 partidos, tags sintéticos, ciclo de errores −2..+2 s)

Bordes y tasas de frame en DFL limpio; `spellF1` limpio y con nuestro balón (media de 7 partidos;
gana/pierde = partidos con `spellF1` estrictamente mayor/menor que `engine`).

| cadena | spellF1 limpio | gana/pierde (7) | con nuestro balón | gana/pierde (7) | precisión D | recall D | F1 D | %D | inicio med. | inicio med. \|·\| | fin med. | fin med. \|·\| | fin media \|·\| | fin > 1 s tarde |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `engine` | 0,4935 | — | 0,3686 | — | 0,940 | 0,846 | 0,890 | 40,4% | -0,08 | 0,44 | 0,00 | 1,00 | 5,48 | 19,4% |
| E1 `cut` | 0,4929 | 3 / 4 | 0,3682 | 2 / 5 | 0,944 | 0,838 | 0,888 | 39,8% | -0,08 | 0,44 | -0,40 | 1,00 | 5,54 | 14,8% |
| E2 `kick` ⚠ | 0,5108 | 7 / 0 | 0,3790 | 7 / 0 | 0,962 | 0,847 | 0,901 | 39,5% | -0,08 | 0,40 | 0,00 | 0,00 | 4,94 | 4,3% |
| E3 `cut+onset` | 0,4983 | 4 / 3 | 0,3789 | 6 / 1 | 0,913 | 0,895 | 0,904 | 43,9% | -0,16 | 0,72 | -0,40 | 1,00 | 5,56 | 15,0% |
| E4 `kick+onset` ⚠ | 0,5173 | 7 / 0 | 0,3902 | 7 / 0 | 0,929 | 0,905 | 0,917 | 43,7% | -0,16 | 0,68 | 0,00 | 0,00 | 4,97 | 4,4% |

⚠ Optimista por construcción (sección 2.2): el balón de DFL salta en la reanudación verdadera y
`kick` lo encuentra ahí (\|fin\| mediano 0,00 s con cualquier error del tag). No es evidencia de la
fecha por balón; se reporta porque estaba pre-registrado.

Mediana de \|fin\| (s) con el error del tag fijo:

| cadena | error −2 s | error −1 s | error 0 s | error +1 s | error +2 s |
|---|---:|---:|---:|---:|---:|
| `engine` | 1,36 | 1,00 | 0,20 | 1,00 | 2,00 |
| E1 `cut` | 2,00 | 1,00 | 0,00 | 1,00 | 2,00 |
| E2 `kick` | 0,00 | 0,00 | 0,00 | 0,00 | 0,00 |
| E3 `cut+onset` | 2,00 | 1,00 | 0,00 | 1,00 | 2,00 |
| E4 `kick+onset` | 0,00 | 0,00 | 0,00 | 0,00 | 0,00 |

`spellF1` por partido (J03WMX, J03WN1, J03WOH, J03WOY, J03WPY, J03WQQ, J03WR9):

| cadena | limpio | con nuestro balón |
|---|---|---|
| `engine` | 0,4843 0,4493 0,5026 0,5074 0,4917 0,5022 0,5171 | 0,3616 0,3268 0,3775 0,3794 0,3660 0,3982 0,3709 |
| E1 `cut` | 0,4800 0,4501 0,5015 0,5044 0,4939 0,5016 0,5189 | 0,3586 0,3256 0,3769 0,3778 0,3677 0,3976 0,3728 |
| E2 `kick` | 0,5005 0,4690 0,5186 0,5378 0,5110 0,5072 0,5317 | 0,3699 0,3437 0,3872 0,3918 0,3819 0,3988 0,3794 |
| E3 `cut+onset` | 0,4828 0,4447 0,5097 0,5053 0,5015 0,5172 0,5265 | 0,3607 0,3284 0,3877 0,3868 0,3781 0,4219 0,3885 |
| E4 `kick+onset` | 0,5045 0,4645 0,5289 0,5382 0,5195 0,5223 0,5428 | 0,3742 0,3468 0,4006 0,4000 0,3929 0,4237 0,3932 |

### 8.2 Slice público (17 posesiones, 1.469 frames de `D`)

| cadena | `spellF1` | `macroF1` | Δ pareado | `n_discordant` (IoU 0,5) | ganadas motor/variante | jackknife Δ | posesiones pred. | `D` pred. | precisión `D` | recall `D` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `engine` (entregada) | 0,5368 | 0,8533 | — | — | — | — | 21 | 1.502 | 0,877 | 0,897 |
| E1 `cut` | **0,5474** | 0,8597 | **+0,0105** | 0 | 0 / 0 | 0,0000 .. +0,0108 | 21 | 1.461 | 0,901 | 0,897 |
| E2 `kick` | 0,5158 | 0,8613 | **−0,0211** | 1 | **1 / 0** | −0,0324 .. +0,0108 | 21 | 1.452 | 0,907 | 0,897 |
| E3 `cut+onset` | 0,5368 | 0,8649 | 0,0000 | 0 | 0 / 0 | −0,0108 .. +0,0216 | 21 | 1.541 | 0,890 | 0,933 |
| E4 `kick+onset` | 0,5053 | 0,8665 | **−0,0316** | 1 | **1 / 0** | −0,0432 .. 0,0000 | 21 | 1.532 | 0,895 | 0,933 |

| Δ `spellF1` por IoU frente a `engine` | 0,3 | 0,4 | 0,5 | 0,6 | 0,7 |
|---|---:|---:|---:|---:|---:|
| E1 `cut` | 0 | 0 | 0 | 0 | +0,0526 |
| E2 `kick` | −0,0526 | −0,0526 | −0,0526 | 0 | +0,0526 |
| E3 `cut+onset` | −0,0526 | −0,0526 | 0 | +0,0526 | +0,0526 |
| E4 `kick+onset` | −0,1053 | −0,1053 | −0,0526 | +0,0526 | +0,0526 |

Diagnóstico de agregados (no cambia la selección): `cut` quita 41 frames de `D` predicho en el slice
y los 41 eran vivos en la verdad (los aciertos de `D` siguen en 1.317; la precisión sube de 0,877 a
0,901 sin perder recall). `kick` deja 50 frames de `D` menos con los mismos aciertos, pero re-fecha la reanudación y con
ella el frame en que se fuerza la posesión: pierde una posesión larga a IoU 0,3–0,5.

### 8.3 Banco de trasplante de huecos

| banco | limpio | media de donantes (n = 19) | media con < 50% de balón (n = 6) | peor donante |
|---|---:|---:|---:|---:|
| `engine` (entregada) | 0,5368 | 0,4351 | 0,3595 | 0,2400 |
| E1 `cut` | 0,5474 | **0,4474** | **0,3730** | 0,2533 |
| E2 `kick` | 0,5158 | 0,4217 | 0,3492 | 0,2400 |
| E3 `cut+onset` | 0,5368 | **0,4419** | **0,3720** | 0,2533 |
| E4 `kick+onset` | 0,5053 | 0,4162 | 0,3481 | 0,2400 |

### 8.4 Informe de bloques (sin ground truth)

| cadena | `%D` en los medios tiempos | bloque con más `D` | posesiones (partido) | pos/min | bloque mín–máx pos/min | sin pos. | acuerdo ST |
|---|---:|---:|---:|---:|---:|---:|---:|
| `engine` (entregada) | 40,0% | 65,5% (9) | 383 | 3,62 | 1,01–6,00 | 0 | 77,1% |
| E1 `cut` | 38,4% | 63,3% (9) | 390 | 3,68 | 1,01–6,00 | 0 | 77,1% |
| E2 `kick` | 38,5% | 63,1% (9) | 389 | 3,67 | 1,01–6,00 | 0 | 77,1% |
| E3 `cut+onset` | 42,0% | 64,0% (9) | 379 | 3,58 | 0,67–5,60 | 0 | **77,9%** |
| E4 `kick+onset` | 42,1% | 63,9% (9) | 378 | 3,57 | 0,67–5,60 | 0 | **77,9%** |

| bloque | balón | pos/min `engine` | `cut` | `kick` | `cut+onset` | `kick+onset` |
|---|---:|---:|---:|---:|---:|---:|
| 1★ | 88,2% | 4,20 | 4,20 | 4,20 | 4,20 | 4,20 |
| 2 | 82,7% | 4,60 | 4,60 | 4,40 | 4,60 | 4,40 |
| 3 | 76,5% | 4,20 | 4,40 | 4,20 | 4,00 | 3,80 |
| 4 | 72,3% | 6,00 | 6,00 | 6,00 | 5,60 | 5,60 |
| 5 | 56,0% | 3,20 | 3,40 | 3,40 | 3,40 | 3,40 |
| 6 | 64,7% | 4,00 | 4,20 | 4,20 | 4,20 | 4,20 |
| 7 | 36,9% | 2,00 | 2,00 | 2,00 | 2,00 | 2,00 |
| 8 | 57,2% | 3,80 | 3,80 | 3,80 | 3,60 | 3,60 |
| 9 | 29,0% | 1,60 | 1,80 | 1,80 | 1,80 | 1,80 |
| 10 | 53,7% | 3,40 | 3,40 | 3,40 | 3,20 | 3,20 |
| 11 | 19,9% | 1,01 | 1,01 | 1,01 | 0,67 | 0,67 |
| 12 | 87,8% | 3,80 | 4,00 | 4,00 | 3,80 | 3,80 |
| 13 | 67,4% | 4,00 | 4,00 | 3,80 | 4,00 | 3,80 |
| 14 | 73,5% | 4,60 | 4,60 | 4,60 | 4,40 | 4,40 |
| 15 | 45,2% | 3,20 | 3,20 | 3,20 | 3,20 | 3,20 |
| 16 | 73,7% | 3,40 | 3,40 | 3,40 | 3,20 | 3,20 |
| 17 | 61,0% | 4,00 | 4,00 | 3,80 | 3,80 | 3,60 |
| 18 | 20,3% | 3,60 | 3,80 | 3,60 | 3,80 | 3,60 |
| 19 | 48,6% | 4,00 | 4,00 | 4,00 | 4,00 | 4,00 |
| 20 | 47,9% | 3,20 | 3,20 | 3,20 | 3,20 | 3,20 |
| 21 | 60,0% | 3,80 | 3,80 | 4,00 | 3,80 | 4,00 |
| 22 | 71,7% | 2,39 | 2,73 | 3,76 | 2,73 | 3,76 |

## 9. Recomendación: **mantener la cadena entregada** (resultado negativo)

| compuerta | E1 `cut` | E2 `kick` | E3 `cut+onset` | E4 `kick+onset` |
|---|---|---|---|---|
| G-DFL1 gana ≥ 6/7 limpio y con balón | **no (3/7; 2/7)** | sí (7/7; 7/7) ⚠ | **no (4/7; 6/7)** | sí (7/7; 7/7) ⚠ |
| G-DFL2 \|fin\| y \|inicio\| no peores | sí (1,00 / 0,44) | sí (0,00 / 0,40) ⚠ | **no (inicio 0,72 > 0,44)** | **no (inicio 0,68 > 0,44)** |
| G1 precisión `D` ≥ 0,85 | sí (0,901) | sí (0,907) | sí (0,890) | sí (0,895) |
| G2 Δ ≥ 0 y `wins_a ≤ wins_b` | sí (+0,0105; 0–0) | **no (−0,0211; 1–0)** | sí (0,0000; 0–0) | **no (−0,0316; 1–0)** |
| G3 banco ≥ 0,4351 / 0,3595 | sí (0,4474 / 0,3730) | **no (0,4217 / 0,3492)** | sí (0,4419 / 0,3720) | **no (0,4162 / 0,3481)** |
| G4 bloque ≤ 70%, sin vacíos, 3,4 ± 0,5 | sí (63,3%; 3,68) | sí (63,1%; 3,67) | sí (64,0%; 3,58) | sí (63,9%; 3,57) |
| G5 acuerdo ST ≥ 76,1% | sí (77,1%) | sí (77,1%) | sí (77,9%) | sí (77,9%) |

Ninguna pasa las siete. Por la regla de la sección 6, **la cadena entregada no cambia**.

Lo que queda como resultado:

- **El corte (`cut`) es el caso más interesante y no se adopta.** En todos los instrumentos del
  partido gana o empata: slice +0,0105 (0 discordantes, jackknife de un solo signo, 0 .. +0,0108),
  precisión de `D` 0,877 → 0,901 sin perder ni un acierto (los 41 frames quitados eran todos vivos),
  banco +0,0123 de media y +0,0135 con poco balón, acuerdo ST igual, `%D` 40,0 → 38,4%. Pero en DFL,
  el juez externo pre-registrado, **no gana**: 3 de 7 partidos limpio (−0,0006 de media) y 2 de 7
  con nuestro balón (−0,0004), con el error de bordes igual (\|fin\| mediano 1,00 s en ambos). La
  tabla de error fijo explica por qué: cortar en una estimación **temprana** quita `D` verdadero
  (con −2 s, \|fin\| 1,36 → 2,00 s); cortar en una exacta o tardía no quita nada o lo arregla; con
  un ciclo simétrico de errores, se compensa. En DFL W1 apenas sobrepasa la reanudación (0,6 s de
  mediana), así que hay poco que ganar; en el partido la sobrepasa 1,6 s de mediana y hasta 11,8 s
  (p90).
- **La fecha por balón (`kick`) es negativa en el partido**, con los tres instrumentos que sí la
  pueden juzgar: pierde una posesión en el slice (−0,0211; 1–0), baja el banco (−0,0134 / −0,0103) y
  deja igual el acuerdo ST. Sus 7/7 de DFL no valen como evidencia (balón congelado que salta en la
  reanudación). Mover el frame de la reanudación mueve también el forzado de la posesión
  (decisiones 30–32), y ahí es donde pierde: la estimación de +5 s, aun siendo "temprana" frente al
  primer balón rápido, da mejores posesiones que el balón.
- **El onset (U1) dentro de una combinación tampoco entra.** `cut+onset` empata en el slice (0,0000,
  0–0), sube el banco (+0,0068 / +0,0125) y el acuerdo ST (+0,8 puntos), pero falla las dos
  compuertas de DFL: gana 4/7 limpio y empeora el error de inicio (0,44 → 0,72 s). Esto último es
  nuevo respecto a dead-v3: con las paradas etiquetadas dentro del `D` (cuyo inicio ya da el balón
  fuera), el onset adelanta de más el inicio de algunas paradas de los jugadores.

## 10. Limitaciones y lo que queda abierto

- **DFL no puede juzgar una fecha por balón** (sección 2.2), ni las muestras abiertas de Metrica
  (2.3). Para `kick`, las compuertas de DFL eran necesarias pero no suficientes; falló en las del
  partido, así que la conclusión no depende de eso.
- **Los tags sintéticos de DFL son una suposición**: una reanudación por parada con balón fuera y un
  error de la estimación cíclico y simétrico de ±2 s. El veredicto de `cut` en DFL depende de esa
  forma: la tabla de error fijo dice que el corte gana si la estimación es exacta o tardía y pierde
  si es temprana. En el partido, el primer balón rápido cae una mediana de 1,2 s **después** de la
  estimación (sección 2.1), lo que la haría temprana y apuntaría en contra del corte; pero el slice
  dice lo contrario (los 41 frames cortados eran todos vivos). No se reinterpreta aquí: un
  pre-registro nuevo podría medir en el partido, sin ground truth, cuándo empieza el juego respecto
  a la estimación (por ejemplo con el primer control del reanudador) y fijar con eso la distribución
  de errores de los tags sintéticos de DFL antes de volver a medir `cut`.
- **El slice y el banco no ordenan esto.** El +0,0105 de `cut` es una posesión a IoU 0,7; el banco
  trasplanta huecos sobre las mismas 17 posesiones.
- **Las paradas sin tag** (W1 solo) no se tocaron: la regla de control seguido de movimiento del
  brief afecta a 7 de 76 tramos, sin juez externo (sección 2.3).
- **Las tres posesiones del slice que motivaron el carril** (#6, #14, #17 de `lane-dating.md`) no se
  miraron una a una, para no leer el slice fuera del pre-registro; la precisión de `D` de `cut` dice
  que el corte va en esa dirección.

## 11. Revisión de código (PR #57)

Correcciones posteriores a la medición, cada una con su prueba sintética; **ninguna cambia la
recomendación**:

- **Tags sintéticos de DFL antes de la parada.** Con un error de −2 s en una parada más corta, la
  estimación caía antes de que el balón saliera (1 de 464 tags). Ahora la estimación nunca es anterior
  al segundo frame de la parada; el inicio del tag sí puede caer en juego, como en los nuestros
  cuando la parada dura menos que el desfase de 5 s (41 de 464). DFL re-medido: **las victorias no
  cambian** (`cut` 3/7 y 2/7, `cut+onset` 4/7 y 6/7, `kick` y `kick+onset` 7/7 y 7/7); solo se mueven
  segundos decimales de los bordes (`cut+onset` \|inicio\| mediano 0,72 → 0,74 s; `engine` con error
  −2 s, \|fin\| 1,36 → 1,40 s).
- **`kick_restarts`.** Tags con la misma estimación se fechan juntos (siguen en un frame, así que
  `restart_controls` los sigue viendo como una reanudación, ambigua si nombran equipos distintos), y
  un frame fechado nunca queda antes del anterior. En el partido no hay tags con el mismo frame y hay
  un solo par de ventanas solapadas: las cuatro salidas tienen el mismo SHA-256 que en la sección 7.
- **`--explore`.** Emparejaba reanudaciones con sus fechas tras reordenarlas, contaba dos veces un tramo
  W1 con dos estimaciones y fallaba sin datos. Corregido (`kick_dating`, la máscara real de `cut`,
  percentiles vacíos a cero): los números de la sección 2.1 no cambian; `cut` quita 2.518 frames,
  2.511 de ellos fuera del `D` etiquetado.
- **`chain`** usa `engine.chain` en lugar de copiar su preámbulo; `engine` sigue siendo la cadena
  entregada byte a byte (la prueba con el bundle lo fija).
- **El commit del pre-registro** es `7d19f6d`: el mismo contenido que el `6324ea2` original
  (`git diff` vacío en los tres archivos), re-aplicado sobre `dev`; su fecha de autor es la original
  (21:27), la de commit es la del re-aplicado.

Deuda aceptada: `dfl()` reconstruye cada partido por cada error del ciclo y re-ejecuta las cadenas
limpias (coste, no resultado; módulo de investigación). La detección de `kick` por un solo frame de
velocidad, sin persistencia, es parte de la regla pre-registrada: cambiarla sería una variante nueva,
y `kick` ya pierde en el partido.
