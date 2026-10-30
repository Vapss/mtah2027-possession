# Lane external — corpus de validación con datos públicos etiquetados

Código: `tools/external.py`, pruebas: `tests/test_external.py`. Este documento no cambia el motor ni
`docs/DECISIONS.md`: el coordinador integra. Los datos externos viven fuera del repositorio
(`MTAH_EXTERNAL_DIR`, por defecto `~/Downloads/external-football-data`) y nunca entran en git.

## 1. Pre-registro

Escrito y comprometido en git **antes** de puntuar ningún método sobre el corpus. Antes de
escribirlo solo se midió, sin ningún método: la estructura de los ficheros (atributos, rangos de
coordenadas, conteos de `BallStatus`/`BallPossession`) de un partido, y agregados de nuestro propio
tracking (jugadores vistos por frame, balón visto en las mitades) y del ground truth público.

### 1.1 Fuente

**IDSSE** (Bassek, Rein, Weber, Memmert, *Scientific Data* 12:195, 2025,
doi:10.1038/s41597-025-04505-y): 7 partidos completos de la Bundesliga y 2. Bundesliga 2022/23,
datos oficiales de la DFL, licencia **CC-BY 4.0**. Depósito oficial: figshare,
doi:10.6084/m9.figshare.28196177. Tracking óptico TRACAB Gen5 a 25 Hz, con operadores en directo y
control de calidad posterior; el artículo no informa ninguna validación del balón ni de la posesión.

Descarga: figshare responde a clientes no navegador con un reto WAF (HTTP 202, cuerpo vacío), así que
se usó el espejo de PySport en Hugging Face (`pysport/idsse-data`, el que usa kloppy), y los 21
ficheros se verificaron contra los sha256 LFS que publica el espejo (7 de posiciones) y contra su
tamaño (14 pequeños): 21/21 correctos. Son los hashes del espejo, no de figshare: si figshare publica
otra revisión, no lo sabríamos.

kloppy 3.18.0 (grupo `starter`) **sí** tiene el lector (`kloppy.sportec.load_open_tracking_data`) y
mapea `BallStatus == 1` a `ALIVE` (si no `DEAD`) y `BallPossession == 1` a local (cualquier otro
valor, visitante). No se usa: por defecto `only_alive=True` descarta todos los frames muertos (toda
nuestra clase `D`), descarga de figshare (bloqueado), y el camino del equipo es numpy/pandas. El
lector propio lee el XML línea a línea y guarda una caché `.npz` junto a los datos.

**Metrica sample data** (`metrica-sports/sample-data`, juegos 1 y 2: tracking y eventos; el 3 en
EPTS): evaluado y **descartado** como ground truth. Los eventos (`PASS`, `BALL LOST`, `RECOVERY`,
`BALL OUT`, `SET PIECE`, `FAULT RECEIVED`) explican el 94–95% de los cambios de equipo entre eventos
consecutivos, pero no hay posesión por frame: el `D` habría que construirlo con reglas nuestras
(¿empieza en el `BALL OUT` o en el `FAULT RECEIVED`?, ¿acaba en el `SET PIECE`?). No es un detalle:
de 51 y 49 `BALL OUT`, 11 y 10 van seguidos de un `RECOVERY` y no de un `SET PIECE` (saques de
puerta sin etiqueta propia), y hay 77–80 `SET PIECE` para ~50 `BALL OUT` (las faltas paran el juego
sin balón fuera). Un ground truth hecho con las mismas reglas que queremos validar sería circular.
Conteos medidos con un script de exploración sobre los CSV de eventos; nada de ese análisis entra en
el repositorio.

### 1.2 Mapeo de etiquetas (fijo)

Por frame del balón: `D` si `BallStatus = 0`; si `BallStatus = 1`, `H` con `BallPossession = 1` y `A`
con `BallPossession = 2`; `X` si falta cualquiera de los dos. Local = `HomeTeamId` de la información
del partido. Es la estructura de nuestro ground truth: muerto donde el tracking corregido dice muerto,
si no el equipo que nombra.

### 1.3 Las entradas de nuestros métodos

- **Frames y mitades.** 25 Hz como los nuestros (el lector comprueba las marcas de tiempo). Cada mitad
  (`firstHalf`, `secondHalf`) es un tramo contiguo; se concatenan con 250 frames vacíos (`X` en el
  ground truth, sin balón ni jugadores), así el scorer oficial encuentra las mitades por las
  etiquetas, como en nuestro partido, y nada se arrastra a través del descanso.
- **Coordenadas.** DFL da metros desde el punto central; se pasan a origen en esquina, `[0, L] × [0, W]`
  con el tamaño del fichero (105 × 68 en el partido inspeccionado), y el test dentro/fuera del campo
  es el mismo rectángulo que el nuestro.
- **`engine.Features`.** Distancia del balón al jugador más cercano de cada equipo (sin árbitros),
  balón presente, velocidad del balón (`emision._ball_speed`, la nuestra), balón dentro del campo.
- **`dead_ball.Evidence`.** `out`/`inside` del balón observado, `still` con `dead_ball.field_speed` y
  `stillness` sobre todos los jugadores. **`restarts` vacío siempre**: no hay Smart Tagging. Toda regla
  que dependa de una reanudación etiquetada (el `D` entregado y el control en la reanudación) queda
  muda aquí.
- **Métodos sin cambios.** Un método del banco (`(features, evidence) -> labels`) corre tal cual: durante
  la llamada, `engine.halves`, `dead_ball.halves` y `ball_gaps.half_runs` devuelven las mitades del
  partido externo y se restauran después. Un método que lea otra cosa de nuestro partido (Smart
  Tagging, el tracking crudo) no es portable y no se puntúa aquí.

### 1.4 Degradación (fija)

Dos escenarios, ambos siempre informados:

- **limpio**: el tracking DFL tal cual (balón visto en ~100% de los frames);
- **degradado**: la máscara de presencia de balón de BAR-ATH (`tools/atd`, en memoria, nunca escrita)
  se trasplanta mitad sobre mitad: nuestra mitad *i* sobre la mitad *i* externa desde su primer frame,
  repetida desde su inicio si la externa es más larga. Donde nuestro tracker no vio el balón se borran
  posición, distancias, velocidad y la observación dentro/fuera, exactamente como `bench.degrade`.
  Jugadores, quietud y etiquetas no se tocan. Del patrón solo se informan agregados (cuota por mitad).

Por qué así: el patrón entero por mitad conserva la mezcla real de bloques buenos y malos (59% de
balón en las mitades, 20–37% en los peores bloques) y la longitud de nuestros huecos. Igual que en el
banco, un hueco trasplantado cae donde cayó el nuestro, no donde el balón es difícil de ver: mide
robustez a la cantidad y longitud de balón perdido, no a su ubicación.

**Jugadores sin degradar**, a propósito: nuestras features no tienen identidad (la distancia mínima
por equipo), así que anonimizar o fragmentar trayectorias no cambia nada; y nuestro ATD ve una mediana
de 22 jugadores por frame (p10 18, media 20,5), así que la pérdida de jugadores es pequeña frente a la
del balón. Queda como limitación.

### 1.5 Métodos puntuados (sin un solo parámetro nuevo)

| nombre | qué es |
|---|---|
| `engine-bare` | `engine.chain(f, engine.DEFAULT, None, None)`: control + arrastre, sin `D` |
| `engine-out` | `engine-bare` + `D` = `dead_ball.dead_mask(..., "out+still+untagged")` sin reanudaciones: la única regla de `D` que no necesita Smart Tagging (balón visto fuera ≥ 1 s, muerto hasta que se vuelve a ver dentro, como mucho 40 s; constantes de `dead_ball.DEFAULT` sin tocar) |
| `smooth50` | `bench._smooth50`: el suelo publicado reconstruido |
| `engine` | la cadena entregada; sin reanudaciones su máscara `out` es vacía y debe dar **exactamente** `engine-bare` (control de integridad, no un método más) |

Instrumentos: por partido, `spellF1` y `macroF1` del `possession_metrics.evaluate` oficial, la media
de los 7, posesiones por minuto del ground truth y de la predicción, `%D` predicho, y partidos ganados
por pares. Junto a ellos, en la misma ejecución, el público y el banco de cada método que exista en
`bench.METHODS`.

### 1.6 Preguntas y reglas de lectura

Esta línea **no elige un método**: construye un instrumento. Las reglas dicen qué uso del corpus es
legítimo, y se fijan ahora:

- **P1, dominio.** Estructura del ground truth por partido frente al slice público (3,4 posesiones/min,
  media 14,2 s, mediana 7,6 s, 19,6% `D`, 0,8 paradas/min). **Puerta**: el corpus vale para elegir un
  parámetro con **escala temporal** (ventanas, `dwell`, duraciones mínimas) solo si la media de
  posesiones/min de los 7 partidos cae en `[2,4; 4,4]` (±30% de 3,4) **y** su mediana de duración en
  `[3,8; 15,2]` s (factor 2 de 7,6). Si no, solo vale para comparar robustez al balón perdido y reglas
  sin escala temporal. El slice público es un único bloque fácil, así que la puerta es gruesa a
  propósito.
- **P2, orden.** ¿Ordena el corpus degradado los métodos como el banco? Se compara el orden de las
  medias (público, banco media, banco < 50% balón, externo limpio, externo degradado) y los partidos
  ganados. «Concuerda» si el orden de las medias degradadas es el del banco **y** cada par del orden
  gana en ≥ 5 de 7 partidos. Si no concuerda, se informa dónde y se explica, sin reajustar nada.
- **P3, calibración.** ¿Cuánto cae `smooth50` de limpio a degradado, frente al banco (0,3256 → 0,2150)
  y al oficial del partido completo (0,2433)? Descriptivo.

## 2. Resultados

(Se rellenan después de este commit, con números de `python tools/external.py`.)
