# Carril dead-v2 — balón muerto desde cómo se mueven los jugadores

Estado: **pre-registro** (escrito y commiteado antes de correr ninguna variante contra el ground
truth público del partido). Las secciones de medición, recomendación y limitaciones se añaden
después, en un commit aparte, sin tocar las secciones 1–6.

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
