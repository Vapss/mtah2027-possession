# Lane impute — la posesión dentro de los huecos de balón, inferida desde los jugadores

Propuesta para el motor de posesión (#6, `tools/engine.py`). Código: `tools/impute.py`, pruebas:
`tests/test_impute.py`. Este documento no cambia el motor ni `docs/DECISIONS.md`: el coordinador
integra.

## 1. Pre-registro

Escrito y comprometido en git **antes** de medir nada contra el ground truth (slice público o banco
de trasplante) y antes de leer el Smart Tagging. Lo explorado antes, todo sin etiquetas humanas, está
declarado abajo con sus números.

### Problema

La cadena entregada (decisiones 29–32) etiqueta cada frame con el equipo del último control y lo
arrastra hasta el siguiente. Dentro de un hueco de balón el motor no tiene evidencia y comete dos
errores posibles:

1. **Frontera.** Si el equipo del último control antes del hueco (`antes`) y el del primero después
   (`después`) difieren, el cambio ocurrió en algún punto del hueco; el motor lo fecha en el control
   de `después`, el último momento posible.
2. **Posesión oculta.** Si `antes = después`, una posesión entera del rival dentro del hueco es
   invisible.

El banco de trasplante (`tools/bench.py`) mide justo esto contra etiquetas reales: es el
instrumento principal de esta línea.

### Lo explorado antes de escribir esto (sin ground truth, sin Smart Tagging)

- **Intervalos.** Entre anclas consecutivas de una mitad (frame de control o reanudación forzada)
  con al menos un frame sin balón: 149 en el partido; en 59 `antes ≠ después` (36.293 frames), en 90
  `antes = después` (39.912 frames).
- **Autobanco (instrumento nuevo, sin GT).** El partido entero degradado con su propio patrón de
  huecos desplazado (±2,5 y ±7,5 min dentro de cada mitad, ~37% de balón), puntuado con el
  `spellF1` oficial contra **la cadena entregada con el balón a la vista** como pseudo-verdad. Mide
  cuánto de la respuesta del motor con balón recupera cada método sin él. Hallazgo que cambió el
  diseño: en los intervalos con un solo cambio en la pseudo-verdad, ese cambio cae **exactamente
  en el control de `después`** en el 59% y el 75% de los casos (desplazamientos +2,5 y +7,5 min);
  el cuartil mediano de su posición relativa es 0,9–1,0. La frontera del motor es la respuesta
  correcta la mayoría de las veces, y un punto medio la empeora: con él la exactitud por frame
  sube y el `spellF1` baja. Por eso el modelo lleva rasgos de los anclajes (abajo) y dos variantes
  dan coste cero al cambio en el control de `después`.
- **Autocorrelación** del log-odds del modelo dentro de huecos > 500 frames: 0,95 a 1 s, 0,73 a
  5 s, 0,56 a 10 s. Frames vecinos no son observaciones independientes; de ahí el templado.
- Los números finales de esta exploración están en la sección 3 (`heldout`, `self_bench`), con el
  mismo código que se compromete aquí.

### Método (`tools/impute.py`)

**Intervalos.** Entre dos anclas consecutivas `p < q` de una mitad, con al menos un frame sin balón
estrictamente dentro. Anclas = frames de control del motor y reanudaciones que la cadena fuerza
(`engine.restart_controls`). Se excluyen los intervalos que **terminan** en una reanudación
forzada (esa entrega ya la decide la regla de las decisiones 30–32) y lo que queda antes del primer
ancla o después del último de una mitad (sin estado de partida o sin final). **Candidatos** a
cambio: los frames sin balón del intervalo que no son `D`, más `q`. Donde el balón se ve sin control,
el "todavía no cambió" del motor es observación; dentro de una parada nadie tiene el balón. Ningún
frame fuera de un intervalo cambia; `D` se escribe encima como en la cadena entregada.

**Evidencia por frame sin balón** (todas antisimétricas: local − visitante, o `±1` local/visitante):

1. Los 7 rasgos de formación del carril F (`tools/formation.py`), sin cambios.
2. `interp_d`: distancia del local más cercano menos la del visitante más cercano al balón
   **interpolado** en línea recta entre donde se vio por última vez y donde se vuelve a ver, en la
   fracción del hueco transcurrida (bidireccional: el final del hueco es observable offline).
3. `interp_d_near`: lo mismo dividido por `1 + segundos al extremo visto más cercano` (la
   interpolación vale cerca de un balón visto, no en mitad de un hueco largo).
4. `before_far`, `after_near`: el equipo del ancla anterior (`±1`) por `1 − w` y el del ancla
   siguiente por `w`, con `w` la fracción del intervalo transcurrida. Deja que el modelo aprenda de
   los datos cuán pronto dentro de un hueco tiene ya el balón el equipo de `después`.

**Modelo.** Regresión logística sin intercepto de `tools/formation.fit` (Newton, 25 iteraciones,
ridge 1e-3, sin semilla). **Autosupervisado con huecos sintéticos**: el propio patrón de huecos
del partido desplazado ±5 min (ciclico dentro de cada mitad) se superpone sobre frames con balón;
una fila es un frame vivo, con balón y con estado, que el desplazamiento oculta, y su etiqueta es el
estado de la cadena entregada **con el balón a la vista**. Los rasgos de esa fila se calculan con
el balón oculto (anclas incluidas). Ni ground truth ni Smart Tagging. El modelo se reajusta en cada
llamada sobre lo que la entrada deja ver: en el banco, sobre los rasgos degradados, así que nunca ve
el balón que el banco oculta.

**Variantes** (cinco, fijas, ninguna se barre):

| variante | regla | parámetros y por qué |
|---|---|---|
| V1 `mid` | si `antes ≠ después`, el cambio en la mediana de los candidatos | ninguno: prior uniforme. Ablación ingenua; el autobanco ya la da por peor |
| V2 `change` | si `antes ≠ después`, un único cambio en el punto que maximiza la evidencia del modelo (`antes` hasta él, `después` desde él); empates a la mediana | ninguno: el arg-máx no depende de la escala del log-odds |
| V3 `viterbi` | decodificación de 2 estados sobre los candidatos con ambos extremos fijos: 1 cambio si difieren, 0 o 2 si coinciden | coste de cada cambio `−ln(3,4 / 1.500)` = 6,09 nats (3,4 posesiones/min, la tasa física de la decisión 26); log-odds templado por 25 frames (1 s) |
| V4 `viterbi` extremo libre | V3, pero el cambio **en `q`** (la respuesta del motor) cuesta 0 | lo que el autobanco mostró: el control de `después` es el cambio la mayoría de las veces |
| V5 `viterbi` extremo libre, templado 5 s | V4 con templado de 125 frames | la autocorrelación del log-odds sigue en 0,73 a 5 s: más conservadora |

### Mediciones (todas, para todas las variantes)

1. **Banco de trasplante** (principal): `spellF1` por donante (19), media, media de donantes con
   < 50% de balón, peor donante; Δ contra el motor; donantes mejor / peor que el motor. Diagnóstico
   (no decide): exactitud de equipo en los frames vivos del GT público que el donante ocultó.
2. **Slice público**: `spellF1` oficial, Δ pareado y `n_discordant`, ganadas/perdidas contra el
   motor (`tools/compare_submissions.py`).
3. **Informe de bloques** (`tools/blocks.measure`): posesiones/min en el partido y por bloque,
   acuerdo con el Smart Tagging en el partido.
4. Sin GT: exactitud fuera de muestra del modelo (bloques pares/impares) frente a arrastrar, y el
   autobanco (`spellF1` contra la pseudo-verdad y exactitud en frames ocultos).

### Regla de selección

Una variante **pasa** si cumple todas:

- **G1 (banco)**: Δ media de donantes frente al motor **≥ +0,010** y Δ media de donantes con poco
  balón **≥ 0**.
- **G2 (banco, consistencia)**: más donantes mejor que el motor que peor (empates fuera).
- **G3 (público)**: Δ pareado de `spellF1` **≥ −0,02** (se espera ~0: el slice casi no tiene huecos).
- **G4 (estructura)**: partido entre 2,5 y 5,0 posesiones/min, ningún bloque en 0 ni por encima de
  8, y acuerdo con el Smart Tagging del partido no más de 1 punto por debajo del motor (guarda, el
  Smart Tagging no entra en nada más).

Entre las que pasan se recomienda la de mayor media de donantes en el banco, salvo que una más simple
(orden V1 < V2 < V3 < V4 < V5) quede a ≤ 0,005 de ella: entonces la más simple. Si ninguna pasa, el
resultado es **negativo**: no integrar, y se dice.

El autobanco no aprueba ni suspende nada (su verdad es el propio motor); se reporta para ver si
ordena las variantes como el banco, lo que diría si sirve para el partido entero.
