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

Todas las tablas completas (por partido, limpio y degradado, `spellF1` y `macroF1`, partidos ganados)
están en `docs/analysis/external.md`, generado por
`python tools/external.py --score --write docs/analysis/external.md`. La primera ejecución fue desde
el commit del pre-registro (`ba5a142`); la de `910f4fa` solo añade las tablas de escala temporal
por partido que pidió el coordinador, y reproduce todas las puntuaciones byte a byte. Una segunda
ejecución desde el mismo commit da el fichero idéntico. Aquí van los resúmenes y su lectura.

### 2.1 P1, dominio: **fuera de dominio para parámetros con escala temporal**

| | IDSSE (7 partidos) | BAR-ATH público |
|---|---:|---:|
| posesiones/min | 3,78–5,30, media **4,58** | 3,40 |
| mediana de posesión | 3,0–4,7 s (media de medianas **3,77**, agrupada 3,68, n = 3.061) | 7,6 s |
| posesiones < 1 s | 9,0–16,8% | 5,9% |
| `%D` | **40,7–51,7%** | 19,6% |
| paradas/min | 0,94–1,19 | 0,80 |
| balón fuera del campo en frames `D` / vivos | 59,0% / 0,47% | — |

La puerta falla por las dos condiciones (4,58 > 4,4; 3,77 < 3,8 s, esta por poco). Las posesiones DFL
son más cortas y más frecuentes, con más posesiones de menos de un segundo: la definición de la DFL
parece cambiar de equipo con toques que la nuestra no cuenta (despejes, rebotes, duelos), aunque con
este corpus no se puede distinguir eso de un fútbol simplemente más cortado. Y su `D` es más del
doble: cubre toda parada arbitral, desde el pitido hasta la reanudación, con el balón quieto donde
salió (59% de los frames `D` lo tienen fuera del campo). Por tanto, según la regla pre-registrada:
**este corpus no puede fijar ventanas, `dwell` ni duraciones mínimas**, y como se ve abajo, tampoco
sirve para medir reglas de `D`.

### 2.2 Puntuaciones

`spellF1` medio de los 7 partidos (el degradado ve el balón en un 60,5% de los frames de las mitades;
nuestras dos mitades donantes, 59,3% y 59,3%):

| método | público | banco: media | banco: < 50% balón | externo limpio | externo degradado |
|---|---:|---:|---:|---:|---:|
| `engine` (entregado) | 0,4585 | 0,3516 | 0,2782 | 0,3767 | 0,2631 |
| `engine-bare` | 0,4195 | 0,2959 | 0,2047 | 0,3767 | 0,2631 |
| `smooth50` | 0,3256 | 0,2150 | 0,1657 | 0,3081 | 0,2226 |
| `engine-out` | (2.3) | (2.3) | (2.3) | **0,4767** | **0,3454** |

`macroF1` medio, limpio / degradado: `engine-bare` 0,4106 / 0,3664, `engine-out` 0,7029 / 0,6151,
`smooth50` 0,3923 / 0,4772. Posesiones/min predichas, limpio / degradado (ground truth 4,58):
`engine-bare` 3,50 / 2,34, `engine-out` 4,19 / 2,91, `smooth50` 3,96 / 4,20.

Partidos ganados en `spellF1`: `engine-out` > `engine-bare` > `smooth50` en **7/7** partidos, limpio
y degradado. **Control de integridad**: `engine` da exactamente `engine-bare` en los 14 casos (sin
reanudaciones su máscara `D` es vacía y no hay control forzado), como se predijo.

### 2.3 Post hoc (NO pre-registrado): `engine-out` en nuestro banco

Para poder leer P2 sobre `engine-out`, la misma regla corrida en nuestro partido con las
reanudaciones del Smart Tagging quitadas (exactamente lo que ve en el corpus). Sin un solo parámetro
nuevo, pero no estaba en el pre-registro: se lee como pista, no como resultado.

| método | público | banco: media | banco: < 50% balón | peor donante |
|---|---:|---:|---:|---:|
| `engine-out` sin reanudaciones | 0,4381 | 0,3018 | 0,2003 | 0,1167 |
| `engine-bare` | 0,4195 | 0,2959 | 0,2047 | 0,1167 |

En nuestro partido la regla casi no hace nada (+0,019 público, ruido; +0,006 banco; −0,004 con poco
balón). En el corpus vale +0,10 limpio y +0,08 degradado. Una regla de `D` ganará mucho más en
IDSSE que en BAR-ATH, porque allí el `D` es el doble y el balón se queda fuera durante la parada.

### 2.4 P2, orden: **concuerda en lo que no depende del Smart Tagging, y en nada más**

- `engine-bare` > `smooth50`: el mismo orden en público, banco (media y poco balón), externo limpio y
  degradado, y **7/7** partidos en los dos escenarios externos. Concuerda.
- `engine` > `engine-bare` (banco +0,056): el corpus no lo puede ver, empatan 0/7, porque toda la
  diferencia viene de las reanudaciones etiquetadas. Por la regla pre-registrada, **no concuerda** en
  ese par; lo esperado, no un fallo del corpus, pero sí un límite: lo mejor de nuestra cadena es
  invisible aquí.
- `engine-out` > `engine-bare`: el mismo signo en las medias, pero de un tamaño que no se parece en
  nada (2.3), y el signo se invierte en los donantes con poco balón de nuestro banco. Mide el dominio,
  no el método.

### 2.5 P3, calibración de la degradación: **reproduce la pérdida del banco**

| | limpio → degradado | caída |
|---|---|---:|
| `smooth50`, corpus | 0,3081 → 0,2226 | −28% |
| `smooth50`, banco (público → media) | 0,3256 → 0,2150 | −34% |
| `smooth50`, oficial (público → partido completo) | 0,3256 → 0,2433 | −25% |
| `engine-bare`, corpus | 0,3767 → 0,2631 | −30% |
| `engine-bare`, banco | 0,4195 → 0,2959 | −29% |

La degradación transplantada cuesta en el corpus lo mismo, en relativo, que en nuestro banco, y el
`smooth50` degradado (0,2226) cae entre el banco (0,2150) y el oficial (0,2433). El trasplante se
comporta igual sobre otros partidos: es una buena señal para el banco, porque ya no depende solo de
las 17 posesiones del bloque 1.

### 2.6 Arbitraje de los decodificadores del carril decode (post hoc, a petición del coordinador)

No pre-registrado aquí: el coordinador pidió usar el corpus como árbitro de las variantes de
`tools/decoder.py` (rama `research-decode-lane` en `1974f54`), retenidas porque cambian la escala
temporal de la posesión. El fichero se copió sin commitear y se corrió
`python tools/external.py --score --extra tools.decoder:METHODS` (sin cambiar nada del corpus, que
ya estaba comprometido); el `engine` del decodificador sale como `decoder.engine` y da exactamente
nuestro `engine`. Sin Smart Tagging, el `D` y el control en la reanudación de esas variantes están
mudos, igual que en `engine`: la comparación aísla la parte de decodificación.

| método | público | banco: media | banco: < 50% balón | ext. limpio | ext. degradado | /min degradado | gana a `engine`, degradado |
|---|---:|---:|---:|---:|---:|---:|---:|
| `engine` | 0,4585 | 0,3516 | 0,2782 | 0,3767 | 0,2631 | 2,34 | — |
| `mid` | 0,4780 | 0,3672 | 0,2833 | 0,3533 | 0,2443 | 2,34 | 0/7 |
| `uncontested` | 0,5189 | 0,3792 | 0,3021 | 0,3495 | 0,2394 | 1,81 | 0/7 |
| `touch` | 0,5600 | 0,3847 | 0,3060 | 0,3303 | 0,2185 | 1,62 | 0/7 |
| `viterbi` | 0,4114 | 0,3396 | 0,2355 | 0,2633 | 0,1740 | 1,41 | 0/7 |
| `mid+uncontested+touch` | 0,5829 | 0,4008 | 0,3208 | 0,3055 | 0,2051 | 1,45 | 0/7 |

(ground truth: 4,58 posesiones/min.) En el corpus degradado **todas las variantes pierden contra
`engine` en 7/7 partidos**; en el limpio también, salvo `uncontested`, que gana uno (J03WQQ). Es
justo al revés que en público y banco. La tabla de escala temporal lo explica: degradadas, las
variantes que fusionan posesiones predicen medianas de 12–33 s y 1,2–2,0 posesiones/min por
partido, frente a una verdad de 3,0–4,7 s y 3,8–5,3/min. `mid` no cambia el ritmo (solo re-data el
cambio) y también pierde 7/7, lo que sugiere (sin verificarlo) que la DFL fecha el cambio en el
primer control del nuevo equipo, como `engine`.

**Cómo leerlo.** P1 ya dijo que el corpus no puede fijar escalas temporales, y el sesgo tiene un
sentido conocido: su verdad es *más fina* que la nuestra (4,58 frente a 3,4/min), así que castiga
fusionar posesiones más de lo que lo haría BAR-ATH. El corpus no demuestra que las variantes sean
peores en nuestro partido. Sí demuestra dos cosas: su ganancia en público y banco **no es una
propiedad general de la posesión**, sino que depende de la definición del ground truth; y bajo
nuestro patrón de balón las que fusionan llevan el ritmo predicho de 2,34/min (el de `engine`, ya
corto frente a 4,58) a 1,4–1,8/min de media. Antes de entregar una de ellas, la prueba que falta es
la de nuestro partido: posesiones por minuto por bloque en `tools/blocks.py` frente a ~3,4.

## 3. Recomendación

1. **Usar el corpus degradado** (`external.score(method, external.load_all(), degraded=True)`) como
   segunda opinión, con 7 partidos y ~3.000 posesiones, para decisiones sobre **el equipo y el
   arrastre bajo balón perdido**: reglas de control, de arrastre en huecos, imputación de balón,
   evidencia de formación. Leer los partidos ganados por pares, no solo la media; un cambio que no gane
   en ≥ 5/7 no está demostrado.
2. **No usarlo para fijar parámetros con escala temporal** (P1 falla) **ni para medir reglas de `D`**
   (2.3: su `D` es otra cosa). Si un método mejora por su `D` en el corpus, eso no dice nada de BAR-ATH.
   Para los decodificadores (2.6) el corpus es una **alarma, no un veredicto**: pierden 7/7, pero
   el sesgo del dominio va contra ellos. La decisión debe salir del informe de bloques de nuestro
   partido.
3. **No usarlo para nada que necesite el Smart Tagging** (reanudaciones): ahí el corpus es ciego, y
   la cadena entregada se reduce a `engine-bare`.
4. El limpio sirve de techo: cuánto pierde un método por el balón que no vemos (−28/−30% aquí).
5. **Cómo enchufar un método**: cualquier función del banco, `(features, evidence) -> H/A/D/X`, sin
   tocar este módulo: `python tools/external.py --score --extra tools.<módulo>:METHODS`. Da público,
   banco y corpus (limpio y degradado) en la misma ejecución, con escala temporal por partido.
   Requisitos: las mitades se piden a `engine.halves`, `dead_ball.halves` o `ball_gaps.half_runs`
   (se sustituyen también si se importaron por nombre); nada de Smart Tagging ni del tracking crudo.
   Datos: `MTAH_EXTERNAL_DIR/idsse/` con los 21 ficheros del espejo (§1.1); la primera carga
   construye la caché en ~70 s y luego tarda unos segundos.

## 4. Limitaciones

- La definición de posesión y de `D` de la DFL no es la de Metrica (2.1); ninguna de las dos está
  documentada en detalle, y el corpus no es el ground truth de la competición.
- Los huecos trasplantados no caen donde el balón es difícil de ver (aire, área llena), igual que en el
  banco; y los jugadores no se degradan (1.4).
- Las reanudaciones no existen. Los eventos DFL (saques, faltas, córners) podrían hacer de Smart
  Tagging, pero tienen otra semántica (instantes exactos, no ventanas de 35 s); no se intentó.
- `macroF1` degradado de `smooth50` sube sobre el limpio (0,3923 → 0,4772): con un 41–52% de `D` en el
  ground truth, el `D` que `smooth50` escribe en los huecos acierta por volumen. Otro efecto del
  dominio; el `macroF1` del corpus no se debe leer para `D`.
- 7 partidos, 5 de ellos de Fortuna Düsseldorf en casa (2. Bundesliga), más Köln–Bayern y
  Bochum–Leverkusen: pocos estilos de juego, y los 7 «partidos ganados» no son 7 muestras
  independientes de estilo.
- Las sumas de hash son las del espejo de Hugging Face, no las de figshare (1.1).
- Metrica sample data descartado como ground truth (1.1).
