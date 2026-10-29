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
