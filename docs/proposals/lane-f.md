# Lane F — evidencia de formación dentro de los huecos de balón

Propuesta para el motor de posesión (#6, `tools/engine.py`). Código: `tools/formation.py`,
pruebas: `tests/test_formation.py`. Este documento no cambia el motor ni `docs/DECISIONS.md`: el
coordinador integra.

## 1. Pre-registro

Escrito y comprometido en git **antes** de leer ground truth o resultados del Smart Tagging. Lo
único medido antes de escribirlo son agregados del tracking para fijar la convención de
coordenadas: `x`, `y` normalizadas a `[0, 1]` desde una esquina (rango observado −0,04..1,04), y
el orden de los centroides de equipo por mitad (el visitante tiene el centroide en `x` mayor en el
97,6% de los frames de la 1.ª mitad y en `x` menor en el 96,6% de la 2.ª: los lados se cambian en
el descanso, como debe ser).

### Problema

El motor etiqueta cada frame con el equipo del último balón *controlado* y arrastra ese estado
entre controles. El tracker pierde el balón en el 41% de los frames puntuables, en huecos de
mediana 268 frames; los de más de 500 frames tienen el 67% del balón perdido. Dentro de un hueco el
motor no tiene evidencia. Esta propuesta le da evidencia **solo de los jugadores**: qué equipo
tiene la forma de quien tiene el balón.

### Independencia

El Smart Tagging **no es entrada** en ningún punto de esta línea: ni rasgo, ni etiqueta de
entrenamiento, ni criterio para ordenar variantes. Es la única señal independiente del tracking
para validar fuera del slice público; usarlo como entrada haría circular esa validación. Solo
aparece como compuerta de aprobado/suspenso (G2 abajo). El ground truth público tampoco se usa
para entrenar ni para elegir umbrales.

### Rasgos (por frame, solo tracking)

Coordenadas en metros (`x · 105,3`, `y · 68,0`). Para cada equipo `t` y mitad `h`, la dirección de
ataque `d_t,h ∈ {+1, −1}` sale de los datos: el equipo cuyo centroide `x` tiene la mediana más baja
en la mitad defiende la portería de `x = 0` y ataca hacia `+x`. La coordenada firmada de un jugador
es `s = d_t,h · (x − 52,65)`: positiva en campo rival, creciente hacia la portería rival.

Por equipo, sobre los jugadores presentes de ese equipo:

1. `mean_s` — media de `s` (altura del bloque);
2. `max_s` — el jugador más adelantado;
3. `deep_s` — el segundo más retrasado (la última línea sin el portero);
4. `spread_x` — desviación típica de `x`;
5. `spread_y` — desviación típica de `y` (amplitud);
6. `vel_s` — velocidad media hacia la portería rival, en m/s: por jugador, `(s_i(f) − s_i(f−25)) / 1 s`,
   solo jugadores presentes en ambos frames y sin cruzar el inicio de la mitad;
7. `opp_half` — jugadores con `s > 0`.

El modelo ve **solo las diferencias local − visitante** de los siete. Un frame con menos de 7
jugadores presentes en algún equipo, o con algún rasgo indefinido, no tiene evidencia: queda fuera
del entrenamiento y recibe `P(local) = 0,5`.

### Modelo

Regresión logística **sin intercepto** sobre las siete diferencias, cada una dividida por su RMS en
los frames de entrenamiento (sin centrar). Sin intercepto y con rasgos antisimétricos, intercambiar
los equipos invierte exactamente la probabilidad: el modelo dice qué forma parece de posesión, no
quién suele tenerla (ese prior ya lo lleva el estado arrastrado). Ajuste por Newton–Raphson,
**25 iteraciones fijas**, ridge `λ = 1e-3`, pesos iniciales cero: determinista sin semilla.

Etiquetas de entrenamiento: los frames de **control** del motor (`engine.control`, parámetros por
defecto) dentro de las mitades, `1` si controla el local. Nada de ground truth ni Smart Tagging.

`P(local)` por frame es la salida del modelo. Para la regla se suaviza con una media móvil
centrada de **125 frames (5 s)** dentro de cada mitad.

### Regla de relleno `fill_gaps`

Dentro de cada hueco de balón (corrida maximal sin balón dentro de una mitad, la misma definición
que `tools/ball_gaps.py`) de longitud `≥ L`:

1. El estado de partida es el que el motor arrastra al entrar en el hueco.
2. Se recorre el hueco con histéresis: cambia al otro equipo `u` cuando la `P(u)` suavizada es
   `≥ τ` durante **50 frames consecutivos (2 s)**, y el cambio se **fecha en el primero de ellos**
   (la misma convención que `engine.decode` con `dwell`). Puede haber más de un cambio en un hueco
   largo.
3. El estado con el que acaba el hueco se sigue arrastrando **hasta el siguiente frame de control**
   de la mitad: en esos frames el motor tampoco tiene evidencia nueva, y cortar el relleno en el
   borde del hueco crearía una posesión espuria de unos frames entre el hueco y el próximo control.
   Ningún frame de control ni ningún frame posterior a él cambia.
4. Un hueco que empieza sin estado (antes del primer control de la mitad) no se toca.

Variantes (máximo 4, fijadas aquí y no barridas):

| variante | `L` (frames) | `τ` |
|---|---:|---:|
| V1 | 125 (5 s) | 0,80 |
| V2 | 125 (5 s) | 0,90 |
| V3 | 500 (20 s) | 0,80 |
| V4 | 500 (20 s) | 0,90 |

### Mediciones

- (a) exactitud de `P(local) > 0,5` en frames de control **fuera de muestra**: entrenar en los
  bloques impares de `tools/blocks.blocks` y evaluar en los pares, y al revés; se reportan los dos
  pliegues y el conjunto, junto a la exactitud de "siempre la clase mayoritaria" y la exactitud en
  los frames con `P` suavizada `≥ 0,8` o `≤ 0,2` (lo que la regla usa).
- (b) exactitud en los frames vivos sin balón del slice público (391 frames: muestra pequeña), del
  modelo y del motor con y sin relleno.
- (c) acuerdo con el Smart Tagging en frames de hueco (sin balón, dentro de una mitad, con votos a
  un solo equipo, etiqueta `H`/`A`): motor arrastrando frente a motor + relleno, por bloque y en el
  partido; con detalle de los bloques 7, 9, 11 y 18.
- (d) `spellF1` público y Δ pareado frente al motor (`tools/compare_submissions.py`).
- (e) posesiones por minuto por bloque (`tools/blocks.py`).

### Regla de selección

Una variante se **aprueba** solo si pasa todas las compuertas:

- **G1** (vale para toda la línea): exactitud fuera de muestra del conjunto en (a) `≥ 0,70`. Si
  falla, el resultado es negativo y no se recomienda ninguna variante.
- **G2**: el acuerdo con el Smart Tagging en frames de hueco del partido sube al menos **2 puntos**
  sobre el motor, y no baja en más de uno de los bloques 7, 9, 11 y 18.
- **G3**: Δ `spellF1` pareado en el slice público `≥ −0,02` (se espera ~0: el slice casi no tiene
  huecos, decisiones 13 y 24; un Δ positivo tampoco cuenta como evidencia).
- **G4**: plausibilidad física: tasa del partido entre 2,5 y 5,0 posesiones/min, y ningún bloque
  con 0 ni con más de 8 posesiones/min.

Entre las aprobadas se recomienda la **más conservadora**, la que cambia menos frames; el Smart
Tagging no ordena variantes, solo aprueba o suspende. Si ninguna pasa, el resultado es negativo y
se reporta como tal.

<!-- Las secciones 2 en adelante se escriben después de medir. -->
