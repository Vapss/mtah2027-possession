# Carril d-edges — dónde TERMINA una parada

Estado: **pre-registro** (secciones 1–6, escritas y commiteadas antes de correr ninguna variante
contra ninguna etiqueta: ni DFL, ni el slice público, ni el banco). Las secciones de medición,
recomendación y limitaciones se añaden después, en un commit aparte, sin tocar las 1–6 salvo esta
línea de estado.

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
