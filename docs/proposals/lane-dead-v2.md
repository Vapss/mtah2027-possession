# Carril dead-v2 — balón muerto desde cómo se mueven los jugadores

Estado: **medido**. El pre-registro (secciones 1–6) se escribió y commiteó (`b0b930c`) antes de
correr ninguna variante contra el ground truth público del partido; las secciones 7–10 (medición,
recomendación y limitaciones) se añadieron después, en un commit aparte, sin tocar las 1–6.

## 1. Qué se propone

La cadena entregada (`make engine`, decisiones 30–32) marca `D` solo donde Smart Tagging etiquetó
una reanudación: 59 `SET PIECES` en un partido que tiene del orden de cien paradas. Una parada sin
tag (falta, fuera de juego, lesión, la mayoría de saques de banda) funde las dos posesiones que la
rodean; en el slice público, precisión de `D` 0,907 pero recall 0,384.

`tools/dead_ball_v2.py` añade un detector que **no mira el balón ni las identidades**: cuando el
árbitro para el juego nadie esprinta; los jugadores más rápidos bajan a paso de marcha en un
segundo y siguen así hasta la reanudación, mientras que en juego vivo siempre hay alguien
corriendo. Se calcula con cuantiles y conteos sobre los slots que haya (invariante al orden), así
que sobrevive a los cambios de identidad del tracking automático y a los huecos de balón.

Todo lo que el detector necesita (rasgos, pesos, umbral y decodificador) se fijó con **datos
etiquetados externos y públicos**, no con el slice: el dataset abierto de Sportec/DFL (Bassek et
al. 2025, *Sci. Data* 12, 195, doi 10.1038/s41597-025-04505-y, CC-BY 4.0; figshare 28196177): 7
partidos de Bundesliga con estado del balón vivo/muerto y equipo en posesión **por frame**, a
25 fps. Esos datos no se mezclan con los del partido ni entran en Git: solo entran los 88 números
del modelo y agregados.

## 2. Lo que se miró antes de escribir esto

### 2.1 En el partido, sin ground truth (solo agregados)

- **Balón parado como firma: descartado.** Rachas de balón observado a < 0,5 m/s (velocidad sobre
  ±12 frames) de ≥ 2 s: solo 23 en todo el partido, y solo 5 de 59 reanudaciones etiquetadas tienen
  una en sus primeros 10 s (el balón se ve el 56% de esos 10 s y casi nunca quieto: se lleva en la
  mano, se coloca, se lanza).
- **29 de las 59 paradas de V2 son solo los 3,5–5 s del tag** (ningún episodio de balón fuera en
  los 40 s previos): en ellas el balón se ve el 23% (mediana) de esos 40 s, y la última vez que se
  ve está a 4,9 m de una línea, 16,6 s antes del tag.
- **Paradas sin tag:** de 102 episodios de balón fuera, 59 no tienen reanudación etiquetada en 40 s;
  en 3 de cada 4 el balón se ve dentro del campo en el frame siguiente (ruido de línea, no paradas).
  **El bloque 1★ no tiene ninguno**, y tiene 3 reanudaciones etiquetadas, una de ellas el saque
  inicial. Como DECISIONS 16 documenta 4 tramos `D` en la ventana pública, al menos 2 de ellos no
  tienen ni tag ni balón fuera: ninguna regla de balón ni de tag puede verlos.
- **Velocidad del campo:** la mediana de velocidad de los jugadores en juego normal ronda
  1,3 m/s, así que el umbral de quietud de V3 (mediana < 1,5 m/s) también se cumple en juego vivo:
  por eso V3 se desbordaba. El percentil 90 separa mejor (mediana 1,6 m/s en las ventanas de tag,
  2,8 m/s en el resto del partido, que incluye paradas sin tag).

### 2.2 En los datos DFL (etiquetas externas; aquí se fijó todo)

- `dead` es el 40,7–51,7% de los frames de cada partido (media 44,9%). En bloques de 5 minutos:
  mediana 45,7%, p90 64,5%, p95 70,0%, **máximo 88,6%** (129 bloques).
- **Separabilidad, rasgo a rasgo** (AUC de `dead`, un partido): p90 de velocidad de jugadores en
  `[t, t+4 s)` 0,938, en `[t−1, t+1 s)` 0,930; mediana de velocidad en `[t, t+4 s)` 0,935; jugadores
  en la banda 0,72; en las áreas 0,65; dispersión en y 0,66 (invertida). Los de "después" separan
  más que los de "antes": tras el pitido los jugadores paran.
- **Mismo dominio que nuestro tracking**, comparando distribuciones marginales (nuestro partido sin
  etiquetas frente a un partido DFL): p90 de velocidad p10/p25/p50/p75/p90 = 1,31/1,59/2,66/3,82/4,79
  frente a 1,30/1,66/2,88/3,88/4,71; la fracción de frames con p90 < 2 m/s es 37,3% frente a 33,4%
  (en DFL, el 93% de esos frames es `dead`). Jugadores en banda, en áreas y dispersión coinciden igual
  de bien. En el bloque 1★ esa fracción es 19%.
- **Modelo, dejando un partido fuera (LOMO, 7 pliegues):** regresión logística ridge sobre 29 rasgos
  (sección 3), precisión/recall/acierto por frame **0,885 / 0,884 / 0,895** (la literatura, Lang et
  al. 2022 con identidades, da 92% de acierto). La regla de un solo umbral (p90 en ±1 s < 2 m/s):
  0,929 / 0,709 / 0,846.
- **Decodificador, elegido sobre DFL con nuestro propio motor corriendo en DFL** (control +
  arrastre, decisión 29; el balón DFL está corregido y siempre presente) y puntuado con el scorer
  oficial frente a la posesión DFL (cientos de posesiones por partido). Rejilla: umbral
  {0,5; 0,6; 0,7; 0,8} × parada mínima {2; 4; 6; 8 s}, cierre de huecos vivos < 1 s (script
  exploratorio, antes de añadir la abstención de la sección 3). Con balón
  completo el mejor está en 0,6/6–8 s (0,4616) y 0,5/4 s da 0,4566; **con el patrón de balón
  perdido de nuestro partido** (59,3% de balón, superpuesto a cada partido DFL) el mejor es
  **0,5 / 4 s (0,3527)**, y es el que se fija: es el régimen del partido privado (DECISIONS 13).
- **Resultado DFL de la cadena fijada** (`python tools/dead_ball_v2.py dfl-bench --dir DFL`, y con
  `--dropout`), `spellF1` medio en 7 partidos, modelo LOMO:

| `D` sobre el motor | balón completo | balón como el nuestro |
|---|---:|---:|
| ninguno (motor solo) | 0,3761 | 0,2553 |
| `rule` | 0,4317 | 0,3216 |
| `model` | 0,4569 | 0,3528 |
| `model+first-control` | 0,4631 | 0,3529 |
| `D` verdadero (techo) | 0,5574 | 0,4449 |

  `model` gana al motor solo en los 7 partidos, con y sin balón. `model+first-control` gana a
  `model` en los 7 con balón completo (+0,0062) y empata con el balón perdido (+0,0001, gana en 4 de
  7): la regla necesita ver el primer control, y sin balón lo ve tarde.

### 2.3 En el partido con las variantes ya fijadas, sin ground truth

`python tools/dead_ball_v2.py --variant V --labels ...` y `python tools/blocks.py`:

| variante | `%D` en los medios tiempos | bloque con más `D` | pos/min |
|---|---:|---:|---:|
| motor entregado | 12,3% | 41,8% (12, antes del saque) | 3,64 |
| `rule` | 40,3% | 65,5% (9) | 3,91 |
| `model` | 48,6% | 70,8% (9) | 3,42 |
| `model+first-control` | 48,6% | 70,8% (9) | 3,35 |
| `model-only` | 45,3% | 67,0% (18) | 3,47 |

Los `%D` incluyen los ~117 s antes del saque del segundo tiempo (no graduados; DECISIONS 30). Los
bloques con más `D` son los de menos balón (7, 9, 11, 18): ahí el p90 de velocidad de jugadores
tiene mediana 1,5–1,8 m/s frente a 2,6–3,3 en el resto, y el tracking también pierde jugadores
(p10 de 2–7 jugadores seguidos en 7, 11 y 18). Por eso el detector se abstiene donde el cuantil de
velocidad es desconocido (menos de 8 jugadores): perder a los jugadores no es evidencia de que se
pararan.

Además conozco, por DECISIONS 16 y el brief, que la ventana pública tiene 19,6% de `D` en 4 tramos
y que `D` perfecto sobre el motor daría ≈ 0,53. Ninguna constante de abajo se eligió con eso.

## 3. Constantes (fijas; ninguna se barre contra el partido)

| constante | valor | de dónde |
|---|---:|---|
| velocidad de un jugador | desplazamiento en ±12 frames (0,96 s) | un segundo promedia el jitter del export automático |
| velocidad máxima creíble | 12 m/s | más rápido que un sprint es un cambio de slot: desconocido |
| jugadores mínimos para un cuantil | 8 | con menos, el cuantil no describe el campo |
| rasgos de velocidad | mediana y p90, ventanas [−1,1) [−4,0) [0,4) [−10,0) [0,10) [−30,0) [0,30) s | 14 |
| rasgos de colocación | jugador más cercano a un banderín (tope 30 m), jugadores a < 1 m de una banda, en las áreas, desviación de x e y; ventanas [−2,2) [−10,0) [0,10) s | 15 |
| modelo | logística ridge (λ = 1, Newton, 25 iteraciones), 7 partidos DFL, 1 de cada 5 frames | determinista, sin semilla; `train --check` lo comprueba |
| umbral del modelo | P(dead) > 0,5 | rejilla DFL con balón perdido (2.2) |
| regla `rule` | p90 en ±1 s < 2,0 m/s | marcha rápida; DFL: 93% `dead` |
| decodificador | huecos vivos < 1 s dentro de una parada se cierran; paradas < 4 s se eliminan | rejilla DFL (2.2) |

Reglas comunes:

- Todo se calcula medio tiempo a medio tiempo; ninguna ventana cruza el descanso y nada fuera de
  `engine.halves()` se marca.
- Donde el p90 de ±1 s es desconocido el detector nunca dice `dead`.
- El `D` de las variantes que lo unen es `dead_ball.dead_mask(..., "out")` ∪ detector; las
  reanudaciones etiquetadas se fuerzan exactamente como en la cadena entregada (decisiones 30–32).
- El motor (control, decodificación, `dwell`) no cambia.

## 4. Variantes (cuatro, ni una más)

- **W1 `rule`** — cadena entregada ∪ regla de un umbral (p90 < 2 m/s), decodificada igual.
- **W2 `model`** — cadena entregada ∪ detector logístico.
- **W3 `model+first-control`** — W2, y además cada parada que **no** contiene una reanudación
  etiquetada termina dando el balón al equipo del **primer control después de ella**, desde su
  primer frame vivo (`first_control_forcing`; no se aplica si otra parada empieza antes de ese
  control). Es la regla de `CHALLENGE.md` ("tras una parada siempre hay un poseedor claro") con la
  observación del tracking en vez de una estimación, como en la decisión 32. Sin ella, el motor
  arrastra el equipo de antes de la parada hasta ese control, y esos frames forman una posesión
  falsa del equipo anterior.
- **W4 `model-only`** — solo el detector, sin el `D` entregado (ablación: ¿aporta algo V2?). Las
  reanudaciones etiquetadas se siguen forzando.

## 5. Mediciones (todas, para cada variante y para el motor entregado)

1. **Slice público:** `spellF1`, `macroF1` (scorer oficial), posesiones predichas, TP/FP/FN a IoU
   0,5; Δ pareado y `n_discordant` / ganadas–perdidas frente al motor con
   `tools/compare_submissions.py engine.csv V.csv --gt public`; precisión y recall de `D` por frame.
2. **Banco de trasplante de huecos** (`python tools/dead_ball_v2.py --bench`): limpio, media de
   donantes, media de donantes con < 50% de balón, peor donante.
3. **Informe de bloques** (`tools/blocks.py`): `%D`, posesiones/min y acuerdo con el Smart Tagging
   por bloque y en el partido.
4. **DFL** (sección 2.2), ya medido.

## 6. Regla de selección (pre-registrada)

1. **Compuertas**, todas obligatorias:
   - **G1** slice público: Δ pareado de `spellF1` frente al motor **≥ 0** y posesiones ganadas
     **≥** perdidas (dirección, no prueba);
   - **G2** slice público: precisión de `D` **≥ 0,80** (la de DFL LOMO es 0,885; por debajo de 0,80
     la transferencia habría fallado) y recall de `D` **> 0,384** (el del motor; si no sube, el
     carril no hizo nada);
   - **G3** banco: media de donantes **≥ 0,3516** y media de donantes con poco balón **≥ 0,2782**
     (las del motor entregado);
   - **G4** bloques: `%D` del partido contado desde el saque de cada medio tiempo **≤ 51,7%** (el
     partido DFL con más `dead`), **ningún bloque > 88,6%** (el bloque DFL con más `dead`) y ningún
     bloque sin posesiones.
2. Entre las que pasan, se recomienda la primera en este **orden de prior**, sin mirar cuál tiene el
   `spellF1` más alto: **W3 > W2 > W1 > W4**. W3 es el modelo completo (la parada y el poseedor que
   la reanuda; gana a W2 en los 7 partidos DFL con balón y empata sin él); W2 es su ablación; W1 es el detector de
   un umbral, peor en DFL; W4 descarta la evidencia de tag y balón fuera, que en el slice tiene
   precisión 0,907.
3. Una diferencia de `spellF1` entre variantes que pasan no altera el orden, sea del tamaño que sea:
   17 posesiones no ordenan métodos.
4. Si ninguna pasa, la recomendación es **mantener la cadena entregada** y el resultado se reporta
   como negativo.

---

*Lo que sigue se escribió después de medir. Las secciones 1–6 son las del commit `b0b930c` sin
cambios, salvo la línea de estado.*

## 7. Cómo se reproducen los números

```bash
export MTAH_DATA_DIR=...                       # el bundle licenciado
python tools/engine.py --labels runs/dead_v2/engine.csv
for v in rule model model+first-control model-only; do
  python tools/dead_ball_v2.py --variant "$v" --labels "runs/dead_v2/$v.csv" --gt public
  python tools/compare_submissions.py runs/dead_v2/engine.csv "runs/dead_v2/$v.csv" --gt public
done
python tools/dead_ball_v2.py --bench           # banco: motor + las cuatro variantes
python tools/blocks.py runs/dead_v2/engine.csv runs/dead_v2/rule.csv runs/dead_v2/model.csv \
    runs/dead_v2/model+first-control.csv runs/dead_v2/model-only.csv

# DFL, offline (kloppy, grupo `starter`): bajar meta_<id>.xml y pos_<id>.xml de DFL_FILES a DFL/
python tools/dead_ball_v2.py dfl-convert --dir DFL
python tools/dead_ball_v2.py train --dir DFL --check     # MODEL es exactamente el ajuste
python tools/dead_ball_v2.py dfl-bench --dir DFL         # y con --dropout
```

`runs/` está ignorado por Git y ninguna salida frame a frame sale del disco. Las etiquetas son
deterministas: dos corridas de `--variant rule` dan el mismo SHA-256 (`5b5c37175ad5bff9…`).

## 8. Mediciones

### 8.1 Slice público (17 posesiones, 1.469 frames de `D` en 4 tramos)

| cadena | `spellF1` | `macroF1` | Δ pareado | `n_discordant` | ganadas motor/variante | TP / FP / FN @ 0,5 | posesiones pred. | precisión `D` | recall `D` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| motor entregado | 0,4585 | 0,7066 | — | — | — | 10 / 14 / 7 | 24 | 0,907 | 0,384 |
| W1 `rule` | 0,4762 | 0,8480 | +0,0177 | 1 | 0 / 1 | 11 / 14 / 6 | 25 | 0,877 | 0,897 |
| W2 `model` | 0,5026 | 0,8201 | +0,0440 | 1 | 0 / 1 | 11 / 11 / 6 | 22 | 0,787 | 0,890 |
| W3 `model+first-control` | 0,5026 | 0,8201 | +0,0440 | 1 | 0 / 1 | 11 / 11 / 6 | 22 | 0,787 | 0,890 |
| W4 `model-only` | 0,4718 | 0,7860 | +0,0133 | 2 | 1 / 1 | 10 / 12 / 7 | 22 | 0,761 | 0,763 |

| Δ `spellF1` por IoU frente al motor | 0,3 | 0,4 | 0,5 | 0,6 | 0,7 |
|---|---:|---:|---:|---:|---:|
| W1 `rule` | −0,0151 | +0,0337 | +0,0360 | +0,0395 | −0,0058 |
| W2 `model` | −0,0188 | +0,0300 | +0,0763 | +0,1201 | +0,0125 |
| W3 `model+first-control` | −0,0188 | +0,0300 | +0,0763 | +0,1201 | +0,0125 |
| W4 `model-only` | −0,0188 | +0,0300 | +0,0250 | +0,0688 | −0,0388 |

Diagnóstico posterior (agregados; no cambia la selección): ninguna variante crea un tramo `D`
falso en el slice; **todo su falso `D` es desborde en los bordes de paradas reales**. W1 toca los
4 tramos verdaderos (185 frames de desborde, 152 sin cubrir); W2 toca 3 de 4 (355 de desborde, 161
sin cubrir): funde dos paradas cercanas por encima de la posesión corta que hay entre ellas. El
motor toca 2 de 4. W3 da exactamente las mismas etiquetas que W2 en el slice.

### 8.2 Banco de trasplante de huecos

| banco | limpio | media de donantes | media con < 50% de balón | peor donante |
|---|---:|---:|---:|---:|
| motor entregado | 0,4585 | 0,3516 | 0,2782 | 0,2069 |
| W1 `rule` | 0,4762 | 0,4024 | 0,3344 | 0,2125 |
| W2 `model` | 0,5026 | 0,3920 | 0,3142 | 0,2267 |
| W3 `model+first-control` | 0,5026 | 0,3976 | 0,3192 | 0,2267 |
| W4 `model-only` | 0,4718 | 0,3720 | 0,2923 | 0,2267 |

El detector no usa el balón, así que el banco solo le quita el balón al motor y al `D` de V2: la
ganancia de `D` se conserva en todos los donantes, y crece donde hay menos balón (W1: +0,051 en la
media, +0,056 en la media con poco balón).

### 8.3 Informe de bloques (sin ground truth)

| bloque | balón | `%D` motor | `%D` W1 | `%D` W2 | pos/min motor | pos/min W1 | pos/min W2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1★ | 88,2% | 8,3% | 20,0% | 22,2% | 4,80 | 5,00 | 4,40 |
| 2 | 82,7% | 9,5% | 17,6% | 18,9% | 4,60 | 5,00 | 3,40 |
| 3 | 76,5% | 13,3% | 34,4% | 39,1% | 5,60 | 5,00 | 4,60 |
| 4 | 72,3% | 9,4% | 23,6% | 41,2% | 5,20 | 6,00 | 5,60 |
| 5 | 56,0% | 6,0% | 47,5% | 60,7% | 4,20 | 3,60 | 3,40 |
| 6 | 64,7% | 14,3% | 36,2% | 49,0% | 4,40 | 4,40 | 3,80 |
| 7 | 36,9% | 11,6% | 53,0% | 58,3% | 1,20 | 2,00 | 1,80 |
| 8 | 57,2% | 9,2% | 38,0% | 42,9% | 3,60 | 4,20 | 3,60 |
| 9 | 29,0% | 22,9% | 65,5% | 70,8% | 2,00 | 2,00 | 1,80 |
| 10 | 53,7% | 5,0% | 31,8% | 55,3% | 2,60 | 3,40 | 2,80 |
| 11 | 19,9% | 0,0% | 51,2% | 54,6% | 0,67 | 1,34 | 0,67 |
| 12 | 87,8% | 41,8% | 49,2% | 43,0% | 4,40 | 4,20 | 4,40 |
| 13 | 67,4% | 9,9% | 35,6% | 35,8% | 3,20 | 4,00 | 3,40 |
| 14 | 73,5% | 8,9% | 27,5% | 38,9% | 4,60 | 5,00 | 4,40 |
| 15 | 45,2% | 15,8% | 52,5% | 57,1% | 3,20 | 3,60 | 2,80 |
| 16 | 73,7% | 4,9% | 23,8% | 39,1% | 4,00 | 4,00 | 3,80 |
| 17 | 61,0% | 8,8% | 35,8% | 45,9% | 3,80 | 4,40 | 3,20 |
| 18 | 20,3% | 4,4% | 55,1% | 67,0% | 2,20 | 3,00 | 2,40 |
| 19 | 48,6% | 28,1% | 47,2% | 56,4% | 4,00 | 4,00 | 3,80 |
| 20 | 47,9% | 0,0% | 47,3% | 62,4% | 3,20 | 4,00 | 3,40 |
| 21 | 60,0% | 14,9% | 57,9% | 63,3% | 4,40 | 3,80 | 3,40 |
| 22 | 71,7% | 23,1% | 39,0% | 50,2% | 2,73 | 2,39 | 3,08 |
| partido | 59,3% | 12,3% | 40,3% | 48,6% | 3,64 | 3,91 | 3,42 |

| cadena | `%D` en los medios tiempos | `%D` desde cada saque (G4) | bloque con más `D` (G4) | pos/min | acuerdo ST |
|---|---:|---:|---:|---:|---:|
| motor entregado | 12,3% | 10,7% | 41,8% | 3,64 | 73,1% |
| W1 `rule` | 40,3% | 39,1% | 65,5% | 3,91 | 76,9% |
| W2 `model` | 48,6% | 47,6% | 70,8% | 3,42 | 78,1% |
| W3 `model+first-control` | 48,6% | 47,6% | 70,8% | 3,35 | 77,5% |
| W4 `model-only` | 45,3% | 44,5% | 67,0% | 3,47 | 77,9% |

Ninguna variante deja un bloque sin posesiones. El acuerdo con el Smart Tagging (independiente del
tracking; el detector no lo lee) sube en todas: 73,1% → 76,9% (W1) y 78,1% (W2). El bloque 12 lleva
los ~117 s anteriores al saque del segundo tiempo (no graduados).

## 9. Recomendación: **W1 `rule`**

Aplicando la regla de la sección 6 tal cual:

| compuerta | W1 `rule` | W2 `model` | W3 `model+first-control` | W4 `model-only` |
|---|---|---|---|---|
| G1 Δ ≥ 0 y ganadas ≥ perdidas | sí (+0,0177; 1–0) | sí (+0,0440; 1–0) | sí (+0,0440; 1–0) | sí (+0,0133; 1–1) |
| G2 precisión `D` ≥ 0,80 | sí (0,877) | **no (0,787)** | **no (0,787)** | **no (0,761)** |
| G2 recall `D` > 0,384 | sí (0,897) | sí (0,890) | sí (0,890) | sí (0,763) |
| G3 banco ≥ 0,3516 / 0,2782 | sí (0,4024 / 0,3344) | sí (0,3920 / 0,3142) | sí (0,3976 / 0,3192) | sí (0,3720 / 0,2923) |
| G4 `%D` ≤ 51,7%, bloque ≤ 88,6%, sin bloques vacíos | sí (39,1%, 65,5%) | sí (47,6%, 70,8%) | sí (47,6%, 70,8%) | sí (44,5%, 67,0%) |

W3, W2 y W4 caen por la precisión de `D`; en el orden de prior (W3 > W2 > W1 > W4) la primera que
pasa es **W1**. Que W2/W3 tengan el `spellF1` público más alto (0,5026 frente a 0,4762) no la
cambia: es justo la elección a posteriori que el pre-registro impide, y con `n_discordant = 1` las
diferencias frente al motor y entre ellas son dirección, no prueba.

Qué hace W1: a las paradas de la cadena entregada (balón fuera → reanudación etiquetada) une cada
tramo de ≥ 4 s en que el segundo jugador más rápido de ~21 (p90 de velocidades sobre ±1 s) va por
debajo de 2 m/s, cerrando huecos vivos de < 1 s, medio tiempo a medio tiempo, y nunca donde hay
menos de 8 jugadores seguidos. Una constante física fijada en datos externos, sin modelo ni pesos.

Números de la recomendada, todos de los comandos de la sección 7:

- slice público: `spellF1` **0,4585 → 0,4762** (Δ pareado +0,0177, `n_discordant` 1, 1–0 a favor),
  `macroF1` 0,7066 → 0,8480, precisión de `D` 0,907 → 0,877, **recall 0,384 → 0,897**;
- banco: media de donantes **0,3516 → 0,4024**, con poco balón **0,2782 → 0,3344**, peor donante
  0,2069 → 0,2125;
- bloques: 40,3% de `D` en los medios tiempos (39,1% desde los saques), máximo 65,5% (bloque 9, uno
  de los de menos balón), 3,91 posesiones/min, acuerdo ST 76,9%;
- DFL (7 partidos, motor propio): 0,3761 → 0,4317 con balón y 0,2553 → 0,3216 con el balón perdido
  de nuestro partido.

**Integración** (el coordinador es dueño de `tools/engine.py`): en `engine.run`, la máscara pasa a
ser `dead_ball.dead_mask(evidence, halves(), "out") | dead_ball_v2.kinematic_mask(players_m,
PITCH_M, halves(), "rule")` con `players_m = tracking.players_array[:, :, :2] * PITCH_M`. Solo
numpy; ninguna dependencia nueva, ningún archivo de pesos (W1 no usa `MODEL`); unos 15 s más por corrida.

## 10. Limitaciones y lo que queda abierto

- **El Δ público es pequeño frente al ruido** (AGENTS.md pide ~0,3 para leerlo como algo más que
  dirección). Los argumentos fuertes son estructurales y externos: recall de `D` ×2,3 con precisión
  0,877, los 4 tramos tocados sin ningún tramo falso, el banco +0,051, DFL +0,056 en 7 de 7
  partidos, y el acuerdo con el Smart Tagging +3,8 puntos.
- **W2 pierde la compuerta por 0,013 de precisión**, y es la mejor en DFL y en el `spellF1` público.
  La compuerta mide desborde en los bordes (todo su falso `D` lo es), no particiones falsas. Si el
  equipo quiere el modelo, es una decisión **nueva**: hay que pre-registrar otra compuerta antes de
  mirar nada más, no reinterpretar esta.
- **W3 = W2 en el slice**: en la ventana pública ninguna parada sin tag termina con un primer control
  distinto del estado arrastrado. En el banco suma +0,006 sobre W2 y en DFL +0,006 con balón y +0,000
  sin él. Sobre W1 no se midió (no estaba pre-registrada); una `rule+first-control` sería la
  candidata natural de una siguiente ronda.
- **`%D` de 40%** está dentro de lo que muestran los 7 partidos DFL (40,7–51,7%), pero el `D` del
  ground truth de Metrica podría definir la parada de otra forma; el slice (19,6% de `D`, W1 20,0%)
  es consistente, el resto del partido no se puede comprobar.
- **El acierto de equipo en vivo baja** (0,835 → 0,814 en W1): el desborde en los bordes marca `D`
  en frames vivos. Es el precio de los bordes, y `macroF1` sube igualmente (+0,14).
- **Los bloques de menos balón** son también los de más `D` (51–66% en 7, 9, 11, 18): ahí el tracking
  pierde también jugadores, y la abstención (< 8 jugadores) solo cubre la pérdida total. Están dentro
  del rango DFL (p95 70,0%), pero son los que menos se pueden verificar.
- **Datos externos**: DFL es Bundesliga 2022/23 con tracking corregido; el dominio coincide en las
  distribuciones marginales (sección 2.2), no está probado frame a frame. W1 depende de un solo
  umbral, que es lo que menos sufre con un cambio de dominio.
- **No se tocó**: el tope de la retrospección tras gol (la unión no cambia las paradas V2) ni el
  inicio de las 29 paradas "solo tag", que el detector ya extiende por su cuenta.
