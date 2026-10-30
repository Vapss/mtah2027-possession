# Carril m-dating — CUÁNDO cambia la posesión en juego, juzgado en los partidos abiertos de Metrica

Ronda 5. Código: `tools/metrica_open.py` (cargador y verdad de eventos), `tools/change_dating.py`
(reglas y mediciones); pruebas: `tests/test_metrica_open.py`, `tests/test_change_dating.py`. Este
documento no cambia el motor ni `docs/DECISIONS.md`: el coordinador integra.

Tres commits, en este orden y sin reescribir los anteriores:

1. **Instrumento y calibración** (este commit): secciones 1–4.
2. **Pre-registro** de las variantes, con su código y sus pruebas, **antes de medir ninguna**.
3. **Resultados**, añadidos al final sin tocar lo anterior.

## 1. La pregunta

La cadena entregada (decisiones 29–36; `engine.inputs` + `engine.decode`, repro `72c98ed4bb4a…`)
decide **si** la posesión cambia con la regla del duelo y **fecha** el cambio en el primer control
sin disputa del nuevo equipo (jugador más cercano a ≤ 1,5 m, el rival no tan cerca, balón a
≤ 5 m/s, y nadie del equipo con posesión a ≤ 1,5 m). La auditoría del margen dice que el `spellF1`
se pierde en **qué equipo** tiene los frames vivos, cerca de los cambios verdaderos; en el slice
público las posesiones emparejadas empiezan tarde (+0,5 .. +5 s, mediana ~+1,4 s). Todo intento
anterior de redatar (carriles decode y dating) se juzgó solo en ese slice contaminado. Faltaba un
**juez externo de la fecha de un cambio**.

¿Dónde, en el tiempo, se fecha un cambio de posesión, y puede una regla determinista con constantes
fijadas fuera de BAR-ATH fecharlo mejor que la cadena entregada?

La decisión 37 prohíbe que un corpus externo arbitre reglas que cambian la escala temporal o el
número de posesiones. Una regla que **solo redata** los cambios que la regla del duelo ya decidió
conserva su número, y es lo que este carril puede juzgar fuera. Una regla que cambie el número
tiene que pasar además la banda del informe por bloques.

## 2. El instrumento

### 2.1 Los datos

Metrica Sports, *sample data*, partidos 1 y 2 (`metrica/g1`, `metrica/g2` bajo
`MTAH_EXTERNAL_DIR`, por defecto `~/Downloads/external-football-data`): tracking de los 22
jugadores y del balón a 25 fps en coordenadas normalizadas, y un registro de eventos anotado a mano
con frame de inicio y de fin sincronizado con ese tracking. El partido 3 trae eventos y metadatos
pero **no tracking**: no se usa. Nada de Metrica entra en git ni se cachea dentro del repositorio
(se lee del CSV cada vez: ~1 s por partido).

`metrica_open.load(game)` devuelve las formas que toma el motor: `engine.Features` en metros sobre
un campo de **105 × 68 m** (el `FieldSize` de los metadatos del partido 3; los partidos 1 y 2 no
traen), `dead_ball.Evidence` con las reanudaciones sacadas de los eventos `SET PIECE` y de los
saques de puerta (`PASS` / `GOAL KICK`) — equipo conocido, ventana como la del Smart Tagging
(`restart_s` antes de la reanudación; 3,5 s para un saque de centro) —, las dos mitades y los
jugadores en metros. El frame `i` de cada array es el frame `i + 1` de Metrica.

### 2.2 La verdad derivada de los eventos (escrita antes de mirar ninguna salida del motor)

Las reglas E1–E5 están en el docstring de `tools/metrica_open.py` y las fija
`tests/test_metrica_open.py`. En resumen:

- **E1.** Un evento **afirma** que su equipo tiene el balón en su frame de inicio: `PASS`, `SHOT`,
  `SET PIECE`, `RECOVERY`. `BALL LOST` y `BALL OUT` solo confirman al equipo que ya lo tiene (una
  entrada se anota como `RECOVERY` del que gana y, un frame después, `BALL LOST` del que pierde, que
  no debe devolverle el balón). `CHALLENGE`, `FAULT RECEIVED` y `CARD` no dicen nada del equipo.
- **E2.** En juego, el equipo en posesión en el frame `t` es el del último evento afirmativo de la
  mitad con inicio ≤ `t`. Antes del primero de una mitad, nadie.
- **E3.** Un **cambio** es un evento afirmativo del equipo `U` con `T ≠ U` en posesión, fechado en
  su frame de inicio: la primera acción anotada del nuevo equipo con el balón. El balón en vuelo
  tras un pase perdido sigue siendo del que lo perdió (la definición del propio reto).
- **E4.** **Balón muerto** desde una parada hasta el inicio del siguiente evento afirmativo.
  Paradas: el frame final de un `BALL OUT`, de un `SHOT` cuyo subtipo dice `OUT` o `GOAL`, y de un
  `BALL LOST` cuyo subtipo dice `OFFSIDE`, `HAND BALL` o `END HALF`; el frame inicial de un
  `FAULT RECEIVED` y de un `CHALLENGE` cuyo subtipo dice `FAULT` (no `ADVANTAGE`: el juego sigue).
- **E5.** Un cambio es **en juego** si su evento no es `SET PIECE` ni saque de puerta y no hay
  balón muerto entre el último evento afirmativo del equipo anterior y él. Solo esos se fechan
  aquí: un cambio en una reanudación es de la reanudación, que la cadena fuerza.

**Procedimiento, declarado.** La única salida mirada antes de fijar E1–E5 fue la de
`metrica_open.py --describe` (agregados de los eventos y del tracking; ninguna del motor). Las
pruebas sintéticas encontraron un error antes de la primera ejecución del motor en Metrica: un
`SHOT` que sale o es gol afirma el balón **y** para el juego, y el código solo hacía lo primero.
Corregido; la regla escrita no cambió.

### 2.3 El emparejamiento (fijado antes de la primera ejecución del motor en Metrica)

- **Cambio de la cadena:** un frame en que el estado decodificado pasa de un equipo al otro dentro
  de una mitad (el estado, antes de escribir `D` encima: `D` no es una regla de fecha).
- Cada cambio en juego de la verdad se empareja con como mucho un cambio de la cadena **al mismo
  equipo nuevo** a ≤ `TOLERANCE_S` = **±5 s**, uno a uno, los pares más cercanos primero (empates:
  el cambio verdadero anterior). 5 s cubre todos los inicios tardíos del slice menos uno y es menos
  que la posesión mediana de la verdad, así que un cambio no se empareja con el siguiente del
  siguiente.
- **Retraso** = cadena − verdad, en segundos: positivo es tarde. Se reportan emparejados, perdidos
  (cambios verdaderos sin pareja), sobrantes (cambios de la cadena sin pareja), mediana con signo,
  mediana y media de |retraso|, cuantiles y la parte a ≤ 0,5 s, ≤ 1 s y > 1 s tarde, por partido y
  por mitad.
- **La cadena en Metrica** es la entregada con las mitades de Metrica: `engine.inputs` (control,
  duelo, reanudaciones) y `engine.decode`, con el `D` entregado: paradas etiquetadas
  (`dead_ball.dead_mask`, "out") unidas a las de los jugadores (W1, `dead_ball_v2.kinematic_mask`,
  "rule"). En BAR-ATH la variante de referencia `engine` (`change_dating.METHODS`) reconstruye la
  cadena entregada con estas mismas piezas y `tests/test_change_dating.py` la fija byte a byte al
  SHA-256 `72c98ed4bb4a…`.

## 3. Agregados (`python tools/metrica_open.py --describe`)

Salida sin editar:

| juego | frames | min | balón | balón vivo / muerto (verdad) | jugadores en campo | eventos | reanudaciones | cambios | en juego | en juego /min | posesiones /min | mediana s | < 1 s | %D | BALL LOST ajenos | jugador–balón en el evento: mediana m / ≤ 2 m | quiebros del balón a ±1 frame de un evento |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| g1 | 145006 | 96,7 | 60,9% | 98,2% / 7,5% | 22,0 de 28 | 1745 | 99 | 328 | 251 | 2,60 | 3,65 | 5,1 | 6,5% | 40,5% | 19 | 0,06 / 94,6% | 98,4% de 3477 |
| g2 | 141156 | 94,1 | 59,0% | 94,5% / 2,1% | 22,0 de 26 | 1935 | 96 | 292 | 216 | 2,30 | 3,35 | 6,2 | 5,4% | 38,3% | 28 | 0,06 / 96,0% | 97,4% de 3811 |

**Escala temporal: comparable.** La verdad de eventos da **3,65 y 3,35 posesiones/min** (BAR-ATH:
3,4 ± 0,5; DFL: 4,58, cuya compuerta de dominio falló), mediana de 5,1 y 6,2 s y ~39–41% de `D`
(nuestro `D` entregado: 40,0% del partido). Por la regla del brief podría usarse también para
veredictos de `spellF1`; aquí **solo fecha cambios**, que es lo que la decisión 37 deja juzgar
fuera, y el `spellF1` de Metrica, si se reporta, es informativo.

**El `D` de E4 coincide con dónde no hay balón**, sin haberlo usado: el balón está visto en el
98,2% / 94,5% de los frames vivos de la verdad y en el 7,5% / 2,1% de los muertos. El tracking de
muestra deja de seguir el balón cuando está fuera de juego.

**Limitación que hay que tener presente: el balón de muestra está sincronizado con los eventos.**
En un evento afirmativo, el jugador que actúa está a **0,06 m** del balón (mediana; ≤ 2 m en el
95–96%), y el **97–98%** de los quiebros bruscos de la velocidad del balón (> 5 cm/frame², 31 m/s²)
caen a ±1 frame del inicio o del fin de un evento. Un tracking óptico real no pone el balón a 6 cm
del pie ni quiebra solo donde un anotador marcó un evento. Así que: (a) la fecha de la verdad y la
física del balón coinciden casi al frame, lo que la hace un buen juez de *cuándo*; y (b) cerca de un
toque el balón de Metrica es **más limpio que el nuestro**, así que este instrumento mide la lógica
de fecha de la cadena con un balón idealizado en los toques, no el ruido de nuestro tracking. Para
eso la calibración añade una fila con nuestro patrón de balón perdido encima.

## 4. Calibración (`python tools/change_dating.py --calibrate --degraded`)

Salida sin editar (la parte `--degraded` lee del bundle solo la máscara de balón visto de BAR-ATH,
en memoria; se reporta agregada):

Calibración: la cadena entregada en Metrica g1 y g2 frente a la verdad de eventos (cambios en juego, E5; tolerancia ±5,0 s, mismo equipo nuevo).

Estado decodificado (antes de escribir `D`):

| tramo | cambios verdad | cambios cadena | emparejados | perdidos | sobrantes | mediana s | mediana \|·\| s | media \|·\| s | p10 / p25 / p50 / p75 / p90 s | ≤ 0,5 s | ≤ 1 s | > 1 s tarde |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| g1 | 251 | 236 | 170 | 81 | 66 | +0,04 | 0,06 | 0,60 | +0,04 / +0,04 / +0,04 / +0,64 / +1,73 | 69,4% | 77,6% | 18,8% |
| g1 mitad 1 | 140 | 133 | 91 | 49 | 42 | +0,08 | 0,08 | 0,68 | +0,04 / +0,04 / +0,08 / +0,92 / +1,80 | 64,8% | 73,6% | 22,0% |
| g1 mitad 2 | 111 | 103 | 79 | 32 | 24 | +0,04 | 0,04 | 0,50 | +0,04 / +0,04 / +0,04 / +0,44 / +1,36 | 74,7% | 82,3% | 15,2% |
| g2 | 216 | 214 | 145 | 71 | 69 | +0,16 | 0,16 | 0,78 | +0,04 / +0,04 / +0,16 / +1,08 / +2,25 | 58,6% | 72,4% | 26,2% |
| g2 mitad 1 | 122 | 124 | 87 | 35 | 37 | +0,16 | 0,16 | 0,76 | +0,04 / +0,04 / +0,16 / +1,18 / +2,23 | 58,6% | 71,3% | 28,7% |
| g2 mitad 2 | 94 | 90 | 58 | 36 | 32 | +0,08 | 0,22 | 0,80 | +0,04 / +0,04 / +0,08 / +0,95 / +2,24 | 58,6% | 74,1% | 22,4% |

Etiquetas que ve el scorer (`D` encima; diagnóstico):

| tramo | cambios verdad | cambios cadena | emparejados | perdidos | sobrantes | mediana s | mediana \|·\| s | media \|·\| s | p10 / p25 / p50 / p75 / p90 s | ≤ 0,5 s | ≤ 1 s | > 1 s tarde |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| g1 | 251 | 232 | 169 | 82 | 63 | +0,04 | 0,08 | 0,60 | +0,04 / +0,04 / +0,04 / +0,64 / +1,74 | 69,2% | 77,5% | 18,9% |
| g2 | 216 | 200 | 138 | 78 | 62 | +0,12 | 0,16 | 0,79 | +0,04 / +0,04 / +0,12 / +1,11 / +2,24 | 58,7% | 71,7% | 26,8% |

Diagnóstico: con el balón visto de BAR-ATH por mitad encima (`external.keep_mask`, estado decodificado):

| tramo | cambios verdad | cambios cadena | emparejados | perdidos | sobrantes | mediana s | mediana \|·\| s | media \|·\| s | p10 / p25 / p50 / p75 / p90 s | ≤ 0,5 s | ≤ 1 s | > 1 s tarde |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| g1 (balón 37,1%) | 251 | 186 | 123 | 128 | 63 | +0,04 | 0,08 | 0,74 | +0,04 / +0,04 / +0,04 / +0,92 / +1,78 | 63,4% | 73,2% | 21,1% |
| g2 (balón 36,0%) | 216 | 158 | 94 | 122 | 64 | +0,30 | 0,50 | 1,01 | +0,04 / +0,04 / +0,30 / +1,52 / +2,79 | 50,0% | 62,8% | 35,1% |

### 4.1 Lectura: el instrumento **no** reproduce el síntoma del slice en la mediana; sí en la cola

- **La mediana no es tarde.** En la cadena entregada sobre Metrica limpio, el retraso mediano es
  **+0,04 s** en g1 y **+0,16 s** en g2 (1 y 4 frames), y en cada mitad entre +0,04 y +0,16 s;
  el p25 es un frame. Frente al +1,4 s de mediana del slice, **la regla de fecha de la cadena (el
  primer control sin disputa) está en el toque del nuevo equipo en la mayoría de los cambios.**
- **La cola sí es tarde.** El p75 va de +0,44 a +1,18 s y el p90 de +1,36 a +2,25 s; entre el
  15% y el 29% de los cambios emparejados llega **más de 1 s tarde**, y casi nunca antes (el p10 es
  +0,04 s). Con nuestro balón perdido encima, la cola crece (g2: p75 +1,52, p90 +2,79, 35% > 1 s
  tarde) y la mediana de g2 sube a +0,30 s, pero sigue lejos de +1,4 s.
- **Un tercio de los cambios en juego no tiene pareja a ±5 s** (81 de 251, 71 de 216) y la cadena
  tiene otros tantos sobrantes (66, 69): eso es **si** cambia, no **cuándo**, y redatar no lo toca.
- **`D` encima casi no cambia la fecha** (filas de etiquetas ≈ estado).

**Qué significa antes de seguir.**

1. Con un balón limpio en los toques, la cadena entregada **no** es sistemáticamente tarde: una
   regla que adelante todos los cambios estropeará la mayoría, que ya están a un frame. Es lo que
   le pasó a `touch` en el carril dating (−0,0526 en el slice). Una regla de fecha solo puede ganar
   si actúa **en la cola** y deja quietos los cambios que ya están en el toque.
2. El +1,4 s del slice no lo explica la regla de fecha sola: con un balón como el de Metrica la
   regla acierta la mediana. El resto tiene que venir de lo que el slice tiene y Metrica no (balón
   menos limpio en los toques y más huecos — la fila degradada lo apunta —, las colas de `D` y la
   fragmentación que encontró el carril dating, 11 posesiones de muestra). Este carril solo puede
   actuar sobre la parte que sí reproduce: **la cola tardía**.
3. Lo que hay en la cola se explora en g1 (sección 5 del pre-registro), sin mirar g2, que queda
   como partido reservado para el veredicto.

---

*Lo que sigue es el pre-registro (commit 2), escrito antes de medir ninguna variante en g2, en DFL,
en BAR-ATH, en el slice ni en el banco. Las secciones 1–4 no cambian.*

## 5. Exploración en g1 (declarada; g2 no se mira)

Todo lo de esta sección se midió en Metrica g1 y **solo ahí**: es donde se fijan las constantes. Se
reproduce con `python tools/change_dating.py --explore`; salida sin editar:

Exploración en Metrica g1 (g2 no se mira): la cola tardía de la cadena entregada.

Frames `[verdad, cadena)` de los cambios emparejados con retraso > 1 s: por qué no hubo control del nuevo equipo.

| sin balón | fuera | lejos | rival más cerca | rápido | duelo | frames |
|---:|---:|---:|---:|---:|---:|---:|
| 0,0% | 0,0% | 61,6% | 2,2% | 19,9% | 16,3% | 1543 |

| cambios | n | rival a ≤ 1,5 m en el frame verdadero |
|---|---:|---:|
| tarde > 1 s | 32 | 50,0% |
| ≤ 0,5 s | 118 | 10,2% |

Anclas probadas (retraso de los emparejados, s; temprano = antes de −0,5 s):

| ancla | emparejados | mediana | mediana \|·\| | media \|·\| | p10 / p25 / p75 / p90 | temprano | > 1 s tarde |
|---|---:|---:|---:|---:|---|---:|---:|
| cadena entregada | 170 | +0,04 | 0,06 | 0,60 | +0,04 / +0,04 / +0,64 / +1,73 | 3,5% | 18,8% |
| toque, tras el último control del anterior (`touch` de lane-dating) | 171 | -0,12 | 0,32 | 0,80 | -2,24 / -1,10 / +0,00 / +0,08 | 41,5% | 2,3% |
| toque, tras el último toque del anterior | 171 | +0,00 | 0,12 | 0,61 | -1,56 / -0,46 / +0,00 / +0,40 | 24,6% | 6,4% |
| toque sin disputa, tras el último toque | 171 | +0,00 | 0,28 | 0,67 | -1,56 / -0,44 / +0,04 / +1,00 | 24,6% | 9,4% |
| toque sin disputa, tras el último control | 171 | -0,04 | 0,48 | 0,84 | -2,20 / -1,06 / +0,00 / +0,40 | 40,4% | 5,3% |
| control ≤ 5,0 m/s, tras el último control | 170 | +0,04 | 0,04 | 0,47 | +0,04 / +0,04 / +0,12 / +1,36 | 4,1% | 12,9% |
| control ≤ 5,0 m/s, tras el último toque | 170 | +0,04 | 0,04 | 0,52 | +0,04 / +0,04 / +0,16 / +1,61 | 3,5% | 15,9% |
| control sin disputa ≤ 5,0 m/s, tras el último control | 170 | +0,04 | 0,06 | 0,60 | +0,04 / +0,04 / +0,64 / +1,73 | 3,5% | 18,8% |
| control ≤ 7,5 m/s, tras el último control | 172 | +0,04 | 0,04 | 0,40 | +0,04 / +0,04 / +0,12 / +0,73 | 8,1% | 7,6% |
| control ≤ 7,5 m/s, tras el último toque | 172 | +0,04 | 0,04 | 0,45 | +0,04 / +0,04 / +0,12 / +1,28 | 5,8% | 11,6% |
| control sin disputa ≤ 7,5 m/s, tras el último control | 172 | +0,04 | 0,04 | 0,52 | +0,04 / +0,04 / +0,33 / +1,32 | 7,0% | 13,4% |
| control ≤ 10,0 m/s, tras el último control | 171 | +0,04 | 0,04 | 0,38 | -0,80 / +0,04 / +0,08 / +0,16 | 13,5% | 4,1% |
| control ≤ 10,0 m/s, tras el último toque | 171 | +0,04 | 0,04 | 0,40 | -0,04 / +0,04 / +0,12 / +0,48 | 8,8% | 8,2% |
| control sin disputa ≤ 10,0 m/s, tras el último control | 171 | +0,04 | 0,04 | 0,50 | -0,64 / +0,04 / +0,12 / +1,00 | 12,3% | 9,9% |
| control ≤ 15,0 m/s, tras el último control | 171 | +0,04 | 0,08 | 0,64 | -1,92 / -0,60 / +0,04 / +0,12 | 26,9% | 2,3% |
| control ≤ 15,0 m/s, tras el último toque | 171 | +0,04 | 0,04 | 0,53 | -1,44 / +0,00 / +0,08 / +0,44 | 15,8% | 7,0% |
| control sin disputa ≤ 15,0 m/s, tras el último control | 171 | +0,04 | 0,12 | 0,73 | -1,80 / -0,54 / +0,08 / +0,64 | 25,7% | 7,6% |
| recepción: aproximación mínima en los últimos 1 s | 170 | +0,00 | 0,00 | 0,50 | +0,00 / +0,00 / +0,26 / +1,56 | 3,5% | 18,2% |
| recepción: aproximación mínima en los últimos 2 s | 170 | +0,00 | 0,00 | 0,42 | +0,00 / +0,00 / +0,11 / +1,25 | 3,5% | 13,5% |
| recepción: aproximación mínima en los últimos 5 s | 171 | +0,00 | 0,00 | 0,38 | +0,00 / +0,00 / +0,08 / +1,00 | 4,1% | 9,9% |

**Lo que dice.**

- **La cola tardía es un toque del nuevo equipo que la cadena no acepta como control**: en el frame
  verdadero el nuevo equipo está en el balón (el balón de muestra está a 0 m del pie), pero el
  toque es **disputado** (rival a ≤ 1,5 m en el 50% de los cambios tardíos frente al 10% de los que
  ya están a tiempo) o **rápido**; luego el balón se va (en el 62% de los frames tardíos nadie del
  nuevo equipo está a ≤ 1,5 m) y la cadena fecha el cambio en el siguiente control lento y sin
  disputa, el de un compañero.
- **Todo ancla de "toque" sin límite de velocidad adelanta demasiado**: entre el 25% y el 41% de los
  cambios quedan más de 0,5 s **antes** de la verdad, incluso con el balón idealizado de Metrica.
  Es la causa probable de que `touch` perdiera en BAR-ATH (lane-dating), ahora vista desde fuera.
- **La familia "control" acorta la cola sin ese daño**: el primer control del nuevo equipo con o
  sin disputa (`first`, la V-a de lane-dating) baja la cola > 1 s de 18,8% a 12,9% con 4,1% de
  tempranos (3,5% la cadena); subir el límite de velocidad cambia cola por tempranos (7,5 m/s:
  7,6% / 8,1%; 10 m/s: 4,1% / 13,5%; 15 m/s: 2,3% / 26,9%).
- **La aproximación mínima del nuevo equipo** (recepción) en los últimos 5 s del traspaso baja la
  media de |retraso| de 0,60 a 0,38 s con 4,1% de tempranos. **Cautela:** en Metrica el balón está
  a 0 m exactos en los toques, así que el mínimo cae justo en el evento; con un tracking real el
  mínimo es ruidoso. DFL (tracking óptico real, sección 6.2) es el control de esto.

**Cómo se fijaron las constantes (declarado: la regla se formuló mirando esta tabla, en g1).** Entre
los valores probados se toma el de menor media de |retraso| en g1 cuya parte de tempranos no supere
la de la cadena entregada en más de 5 puntos (3,5% → ≤ 8,5%): **7,5 m/s** para `relaxed` (10 m/s
da 13,5%) y **5 s** para la ventana de `reception` (frente a 1 y 2 s). El alcance es el 1,5 m del
motor en todas. g2 entero es el juez.

## 6. Pre-registro

### 6.1 Variantes (tres, ni una más)

Todas son la cadena entregada con otra **fecha**: mismo control, misma regla del duelo, mismas
reanudaciones forzadas, mismo `D`. Solo se mueven cambios **naturales** (no forzados), cada uno a un
ancla dentro de su traspaso `(l, c]`, con `l` el último frame del tramo del equipo anterior en que
controló el balón (con o sin disputa), en que una reanudación se lo dio o en que el balón estaba
muerto — la definición de lane-dating, sección 2 —. El número, el orden y los equipos de los cambios
son los de la cadena (lo fija un test), así que la escala temporal no se mueve (decisión 37).

| | nombre | ancla | constantes nuevas |
|---|---|---|---|
| V1 | `first` | primer control (`engine.control`: 1,5 m, 5 m/s) del nuevo equipo en `(l, c]`, con o sin disputa | ninguna |
| V2 | `reception` | la aproximación mínima del nuevo equipo al balón en `(max(l, c − 5 s), c]`, entre los frames con el balón en el campo y su jugador más cercano a ≤ 1,5 m y estrictamente más cerca que el del anterior; el más temprano si empatan | `LOOKBACK_S` = 5 s (g1) |
| V3 | `relaxed` | primer control del nuevo equipo en `(l, c]` con el límite de velocidad a 7,5 m/s, con o sin disputa | `RELAXED_MPS` = 7,5 m/s (g1) |
| ref | `engine` | ninguna: la cadena entregada, byte a byte (`72c98ed4bb4a…`, fijado por un test) | — |

En todas el ancla nunca es posterior al cambio (el control del cambio cumple la condición de cada
una), así que solo se adelanta.

**Conocimiento previo, declarado.** V1 es exactamente la V-a `first` de lane-dating (misma
definición de traspaso, mismo ancla), y sus números en BAR-ATH ya se conocen: slice Δ 0,0000 (0–0),
banco igual (0,4351 / 0,3595), Smart Tagging 77,1% → 77,0%, 3,62 posesiones/min. Por eso pasará,
casi seguro, las compuertas de BAR-ATH, del slice y del banco, y su veredicto depende de Metrica
reservado y de DFL. V2 y V3 no se han medido nunca fuera de g1.

**Sin variante de "si".** El brief permite una que cambie si hay cambio; no se registra. La única
señal externa de "si" sería la verdad de eventos, cuya posesión es "quién actuó el último", y
juzgar con ella una regla que cambia el número de cambios es justo lo que la decisión 37 prohíbe.
El tercio de cambios sin pareja (sección 4) queda como pista para otro carril, con la banda del
informe por bloques.

### 6.2 Mediciones, en este orden (`python tools/change_dating.py --measure`)

1. **Metrica**, retraso de los cambios en juego (sección 2.3), por variante: **g2 entero, g2 mitad 1,
   g2 mitad 2** (reservado); g1 informativo.
2. **DFL, eventos crudos** (secundario), los 7 partidos, reglas D1–D4 del código
   (`tools/change_dating.py`, sección "DFL events"): afirman `Play`, `ShotAtGoal`,
   `OtherBallAction`, `BallClaiming` y las reanudaciones (el saque de centro, por el `Play` de quien
   lo saca); el reloj por los `CalculatedFrame` de los tiros; un desplazamiento por partido elegido
   **solo** por la distancia del equipo que actúa al balón (sin el motor); en juego si no es
   reanudación y el `BallStatus` de DFL está vivo desde el evento anterior. La cadena en DFL usa las
   reanudaciones de los eventos y el `D` entregado (`out` ∪ W1), como en Metrica. Instrumento y
   referencia, medidos antes de las variantes (`python tools/change_dating.py --dfl`), salida sin
   editar:

DFL, eventos crudos: instrumento y cadena entregada (solo la referencia).

| partido | desplazamiento (frames) | eventos afirmativos | equipo que actúa: mediana m / ≤ 1,5 m | cambios en juego | /min | reanudaciones |
|---|---:|---:|---:|---:|---:|---:|
| J03WMX | -17 | 1219 | 1,35 / 52,1% | 281 | 2,89 | 100 |
| J03WN1 | -42 | 919 | 1,41 / 51,8% | 283 | 3,00 | 101 |
| J03WOH | +34 | 969 | 1,44 / 51,2% | 242 | 2,65 | 97 |
| J03WOY | +34 | 1052 | 1,48 / 50,3% | 283 | 2,98 | 106 |
| J03WPY | +0 | 1088 | 1,54 / 49,2% | 245 | 2,51 | 91 |
| J03WQQ | +10 | 1147 | 1,40 / 51,1% | 257 | 2,71 | 96 |
| J03WR9 | -19 | 1055 | 1,38 / 52,2% | 220 | 2,25 | 89 |

Cadena entregada frente a los cambios de los eventos:

| tramo | cambios verdad | cambios cadena | emparejados | perdidos | sobrantes | mediana s | mediana \|·\| s | media \|·\| s | p10 / p25 / p50 / p75 / p90 s | ≤ 0,5 s | ≤ 1 s | > 1 s tarde |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| J03WMX | 281 | 289 | 168 | 113 | 121 | -0,28 | 0,94 | 1,33 | -2,69 / -1,15 / -0,28 / +0,76 / +1,96 | 26,8% | 53,0% | 19,6% |
| J03WN1 | 283 | 309 | 169 | 114 | 140 | -0,52 | 1,00 | 1,30 | -2,30 / -1,44 / -0,52 / +0,56 / +1,60 | 23,7% | 50,3% | 14,8% |
| J03WOH | 242 | 261 | 137 | 105 | 124 | -0,64 | 1,28 | 1,55 | -3,26 / -1,80 / -0,64 / +0,36 / +1,89 | 23,4% | 42,3% | 17,5% |
| J03WOY | 283 | 276 | 170 | 113 | 106 | -0,60 | 1,08 | 1,42 | -2,68 / -1,47 / -0,60 / +0,50 / +1,56 | 21,2% | 47,1% | 16,5% |
| J03WPY | 245 | 247 | 140 | 105 | 107 | -0,14 | 1,38 | 1,64 | -2,49 / -1,41 / -0,14 / +1,28 / +2,45 | 11,4% | 37,9% | 28,6% |
| J03WQQ | 257 | 270 | 158 | 99 | 112 | -0,06 | 1,26 | 1,51 | -2,73 / -1,48 / -0,06 / +1,08 / +2,01 | 19,0% | 39,2% | 27,2% |
| J03WR9 | 220 | 248 | 125 | 95 | 123 | +0,36 | 1,56 | 1,77 | -2,32 / -1,44 / +0,36 / +1,72 / +3,10 | 15,2% | 34,4% | 36,0% |
| todos | | | 1067 | | | -0,28 | 1,16 | 1,49 | -2,72 / -1,48 / -0,28 / +0,88 / +2,02 | 20,4% | 44,0% | 22,3% |

   **DFL es un juez grueso, declarado antes de medir.** Tras el desplazamiento, el jugador más
   cercano del equipo que actúa solo está a ≤ 1,5 m del balón en ~51% de los eventos (Metrica: 95%):
   los `EventTime` de DFL se anotan en vivo, con retraso variable (en los tiros, de −2,5 a +18 s
   frente a su tiempo calculado). El retraso mediano |·| de la referencia es 1,16 s, frente a
   0,06–0,16 s en Metrica. Sirve para detectar una variante que empeore claramente con un tracking
   real, no para ordenar diferencias finas: por eso su compuerta es "no peor", no "mejor".
3. **BAR-ATH sin GT:** acuerdo con el Smart Tagging (partido y bloques 7/9/11/18), posesiones/min,
   bloque mín–máx, bloques sin posesión, `%D` máximo por bloque, frames movidos.
4. **Slice público**, pareado con `compare_submissions.compare_codes` frente a `engine`: `spellF1`,
   `macroF1`, Δ, `wins` a IoU 0,5 (emparejamiento oficial uno a uno), jackknife.
5. **Banco de trasplante:** media de los donantes, media con < 50% de balón, peor donante.

### 6.3 Compuertas (todas obligatorias, frente a `engine`)

| | compuerta |
|---|---|
| M | **Metrica reservado:** en g2, g2 mitad 1 y g2 mitad 2, la mediana de \|retraso\| **estrictamente menor** **y** la mediana con signo **estrictamente más cerca de 0**. Un empate falla. |
| E | **DFL eventos** (los 7 juntos): mediana de \|retraso\| no mayor **y** \|mediana con signo\| no mayor. |
| B | **BAR-ATH sin GT:** Smart Tagging del partido no más de 1,0 punto por debajo; ningún bloque con > 70% de `D`; posesiones/min del partido en 3,4 ± 0,5 (2,9 .. 3,9); ningún bloque sin posesiones. |
| P | **Slice público:** Δ pareado ≥ 0; `wins_a` ≤ `wins_b`; ninguna posesión perdida a IoU 0,5 (`wins_a` = 0). |
| C | **Banco:** media de donantes y media con poco balón, ambas no más bajas. |

### 6.4 Regla de selección

**Orden previo, escrito antes de medir: V1 `first` > V2 `reception` > V3 `relaxed`.** V1 no añade
ninguna constante y conserva la noción de control del motor; V2 añade una (la ventana) y una noción
nueva (la aproximación mínima), sensible al ruido del balón en los toques; V3 cambia una constante
física del motor, el límite de velocidad, para la fecha, y en g1 ya cambia cola tardía por
tempranos. Se elige **la primera de ese orden que pase las cinco compuertas**; las diferencias de
`spellF1` entre variantes que pasan no reordenan nada. Si ninguna pasa, el resultado es
**negativo y se mantiene la cadena entregada**, con qué compuerta falla y por cuánto.

Todo sale de `python tools/change_dating.py --measure` y se pega sin editar en la sección 7, que
se añade en el commit 3 sin tocar lo anterior.

---

*Lo que sigue se escribió después de medir (commit 3). Las secciones 1–6 son las de los commits
`8c3fb91` (instrumento y calibración) y `7cec615` (pre-registro), sin cambios.*

## 7. Mediciones

Salida de `python tools/change_dating.py --measure`, pegada sin editar:

### Metrica (g2 reservado; g1, donde se fijaron las constantes, informativo)

**g2**

| tramo | cambios verdad | cambios cadena | emparejados | perdidos | sobrantes | mediana s | mediana \|·\| s | media \|·\| s | p10 / p25 / p50 / p75 / p90 s | ≤ 0,5 s | ≤ 1 s | > 1 s tarde |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| `engine` | 216 | 214 | 145 | 71 | 69 | +0,16 | 0,16 | 0,78 | +0,04 / +0,04 / +0,16 / +1,08 / +2,25 | 58,6% | 72,4% | 26,2% |
| `first` | 216 | 214 | 146 | 70 | 68 | +0,04 | 0,04 | 0,54 | +0,04 / +0,04 / +0,04 / +0,36 / +1,96 | 74,0% | 82,2% | 16,4% |
| `reception` | 216 | 214 | 145 | 71 | 69 | +0,00 | 0,00 | 0,41 | +0,00 / +0,00 / +0,00 / +0,08 / +1,27 | 80,0% | 86,2% | 11,0% |
| `relaxed` | 216 | 214 | 147 | 69 | 67 | +0,04 | 0,04 | 0,44 | -0,14 / +0,04 / +0,04 / +0,12 / +0,94 | 78,2% | 85,0% | 8,8% |

**g2 mitad 1**

| tramo | cambios verdad | cambios cadena | emparejados | perdidos | sobrantes | mediana s | mediana \|·\| s | media \|·\| s | p10 / p25 / p50 / p75 / p90 s | ≤ 0,5 s | ≤ 1 s | > 1 s tarde |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| `engine` | 122 | 124 | 87 | 35 | 37 | +0,16 | 0,16 | 0,76 | +0,04 / +0,04 / +0,16 / +1,18 / +2,23 | 58,6% | 71,3% | 28,7% |
| `first` | 122 | 124 | 88 | 34 | 36 | +0,04 | 0,04 | 0,48 | +0,04 / +0,04 / +0,04 / +0,24 / +1,75 | 77,3% | 83,0% | 17,0% |
| `reception` | 122 | 124 | 87 | 35 | 37 | +0,00 | 0,00 | 0,34 | +0,00 / +0,00 / +0,00 / +0,10 / +1,28 | 83,9% | 88,5% | 11,5% |
| `relaxed` | 122 | 124 | 89 | 33 | 35 | +0,04 | 0,04 | 0,46 | -0,01 / +0,04 / +0,04 / +0,12 / +1,32 | 78,7% | 83,1% | 11,2% |

**g2 mitad 2**

| tramo | cambios verdad | cambios cadena | emparejados | perdidos | sobrantes | mediana s | mediana \|·\| s | media \|·\| s | p10 / p25 / p50 / p75 / p90 s | ≤ 0,5 s | ≤ 1 s | > 1 s tarde |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| `engine` | 94 | 90 | 58 | 36 | 32 | +0,08 | 0,22 | 0,80 | +0,04 / +0,04 / +0,08 / +0,95 / +2,24 | 58,6% | 74,1% | 22,4% |
| `first` | 94 | 90 | 58 | 36 | 32 | +0,04 | 0,04 | 0,63 | +0,04 / +0,04 / +0,04 / +0,54 / +2,09 | 69,0% | 81,0% | 15,5% |
| `reception` | 94 | 90 | 58 | 36 | 32 | +0,00 | 0,00 | 0,52 | +0,00 / +0,00 / +0,00 / +0,04 / +1,04 | 74,1% | 82,8% | 10,3% |
| `relaxed` | 94 | 90 | 58 | 36 | 32 | +0,04 | 0,04 | 0,43 | -0,52 / +0,04 / +0,04 / +0,11 / +0,60 | 77,6% | 87,9% | 5,2% |

**g1**

| tramo | cambios verdad | cambios cadena | emparejados | perdidos | sobrantes | mediana s | mediana \|·\| s | media \|·\| s | p10 / p25 / p50 / p75 / p90 s | ≤ 0,5 s | ≤ 1 s | > 1 s tarde |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| `engine` | 251 | 236 | 170 | 81 | 66 | +0,04 | 0,06 | 0,60 | +0,04 / +0,04 / +0,04 / +0,64 / +1,73 | 69,4% | 77,6% | 18,8% |
| `first` | 251 | 236 | 170 | 81 | 66 | +0,04 | 0,04 | 0,47 | +0,04 / +0,04 / +0,04 / +0,12 / +1,36 | 78,2% | 82,9% | 12,9% |
| `reception` | 251 | 236 | 171 | 80 | 65 | +0,00 | 0,00 | 0,38 | +0,00 / +0,00 / +0,00 / +0,08 / +1,00 | 82,5% | 86,0% | 9,9% |
| `relaxed` | 251 | 236 | 172 | 79 | 64 | +0,04 | 0,04 | 0,40 | +0,04 / +0,04 / +0,04 / +0,12 / +0,73 | 81,4% | 86,0% | 7,6% |

### DFL, eventos (7 partidos)

| tramo | cambios verdad | cambios cadena | emparejados | perdidos | sobrantes | mediana s | mediana \|·\| s | media \|·\| s | p10 / p25 / p50 / p75 / p90 s | ≤ 0,5 s | ≤ 1 s | > 1 s tarde |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| `engine` | 1811 | 1900 | 1067 | 744 | 833 | -0,28 | 1,16 | 1,49 | -2,72 / -1,48 / -0,28 / +0,88 / +2,02 | 20,4% | 44,0% | 22,3% |
| `first` | 1811 | 1900 | 1064 | 747 | 836 | -0,40 | 1,20 | 1,51 | -2,83 / -1,57 / -0,40 / +0,80 / +1,96 | 20,1% | 43,4% | 20,6% |
| `reception` | 1811 | 1900 | 1050 | 761 | 850 | -0,66 | 1,24 | 1,58 | -3,16 / -2,00 / -0,66 / +0,56 / +1,60 | 19,9% | 43,5% | 15,3% |
| `relaxed` | 1811 | 1900 | 1071 | 740 | 829 | -0,60 | 1,12 | 1,51 | -3,00 / -1,76 / -0,60 / +0,56 / +1,64 | 20,7% | 45,2% | 16,1% |

Desplazamiento D2 por partido (frames): J03WMX -17, J03WN1 -42, J03WOH +34, J03WOY +34, J03WPY +0, J03WQQ +10, J03WR9 -19

Mediana \|·\| por partido (s):

| variante | J03WMX | J03WN1 | J03WOH | J03WOY | J03WPY | J03WQQ | J03WR9 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `engine` | 0,94 | 1,00 | 1,28 | 1,08 | 1,38 | 1,26 | 1,56 |
| `first` | 0,96 | 1,04 | 1,26 | 1,12 | 1,20 | 1,36 | 1,56 |
| `reception` | 0,92 | 1,12 | 1,82 | 1,26 | 1,24 | 1,24 | 1,50 |
| `relaxed` | 0,84 | 1,00 | 1,52 | 1,16 | 1,28 | 1,12 | 1,48 |

### BAR-ATH: sin GT, slice público (pareado con `engine`) y banco

| variante | frames movidos | ST partido | ST bloques 7/9/11/18 | pos/min | bloque mín–máx | sin pos. | %D máx. bloque | spellF1 | macroF1 | Δ | wins ref–var | jackknife Δ | banco media | poco balón | peor |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `engine` | 0 | 77,1% | 85,6% | 3,62 | 1,01–6,00 | 0 | 65,5% | 0,5368 | 0,8533 | +0,0000 | 0–0 | +0,0000 .. +0,0000 | 0,4351 | 0,3595 | 0,2400 |
| `first` | 280 | 77,0% | 86,1% | 3,62 | 1,01–6,00 | 0 | 65,5% | 0,5368 | 0,8545 | +0,0000 | 0–0 | +0,0000 .. +0,0000 | 0,4351 | 0,3595 | 0,2400 |
| `reception` | 2949 | 76,7% | 85,3% | 3,61 | 1,01–6,00 | 0 | 65,5% | 0,5263 | 0,8650 | -0,0105 | 1–0 | -0,0216 .. +0,0108 | 0,4285 | 0,3612 | 0,2533 |
| `relaxed` | 3388 | 77,1% | 85,9% | 3,61 | 1,01–6,00 | 0 | 65,5% | 0,5158 | 0,8520 | -0,0211 | 1–0 | -0,0216 .. +0,0000 | 0,4290 | 0,3437 | 0,2133 |

### Compuertas (frente a `engine`)

| variante | Metrica g2 | Metrica g2 mitad 1 | Metrica g2 mitad 2 | DFL eventos (7 partidos) | BAR-ATH sin GT | slice público (pareado) | banco |
|---|---|---|---|---|---|---|---|
| `first` | pasa (mediana \|·\| 0,16 → 0,04; mediana +0,16 → +0,04) | pasa (mediana \|·\| 0,16 → 0,04; mediana +0,16 → +0,04) | pasa (mediana \|·\| 0,22 → 0,04; mediana +0,08 → +0,04) | **falla** (mediana \|·\| 1,16 → 1,20; mediana -0,28 → -0,40) | pasa (ST 77,1% → 77,0%; %D máx. por bloque 65,5%; 3,62 pos/min; bloques sin posesión 0) | pasa (Δ +0,0000; wins ref–var 0–0) | pasa (media 0,4351 → 0,4351; poco balón 0,3595 → 0,3595) |
| `reception` | pasa (mediana \|·\| 0,16 → 0,00; mediana +0,16 → +0,00) | pasa (mediana \|·\| 0,16 → 0,00; mediana +0,16 → +0,00) | pasa (mediana \|·\| 0,22 → 0,00; mediana +0,08 → +0,00) | **falla** (mediana \|·\| 1,16 → 1,24; mediana -0,28 → -0,66) | pasa (ST 77,1% → 76,7%; %D máx. por bloque 65,5%; 3,61 pos/min; bloques sin posesión 0) | **falla** (Δ -0,0105; wins ref–var 1–0) | **falla** (media 0,4351 → 0,4285; poco balón 0,3595 → 0,3612) |
| `relaxed` | pasa (mediana \|·\| 0,16 → 0,04; mediana +0,16 → +0,04) | pasa (mediana \|·\| 0,16 → 0,04; mediana +0,16 → +0,04) | pasa (mediana \|·\| 0,22 → 0,04; mediana +0,08 → +0,04) | **falla** (mediana \|·\| 1,16 → 1,12; mediana -0,28 → -0,60) | pasa (ST 77,1% → 77,1%; %D máx. por bloque 65,5%; 3,61 pos/min; bloques sin posesión 0) | **falla** (Δ -0,0211; wins ref–var 1–0) | **falla** (media 0,4351 → 0,4290; poco balón 0,3595 → 0,3437) |

Elección por la regla (orden previo `first` > `reception` > `relaxed`): **ninguna; se mantiene la cadena entregada**.

**Reproducción.** Las etiquetas de cada variante en BAR-ATH son deterministas (dos corridas, mismo
SHA-256 del CSV `frame,label`): `engine` `72c98ed4bb4af230…` (la cadena entregada, como fija el
test), `first` `f49f8c28eebc51dd…` (**el mismo fichero** que la `first` de lane-dating: la misma
regla, confirmado), `reception` `99c85d74df19c278…`, `relaxed` `34f5cff3abd2f506…`. Ninguna
variante mueve un frame `D` ni `X` (test con el bundle).

```bash
export MTAH_DATA_DIR=...                                   # el bundle licenciado (BAR-ATH)
export MTAH_EXTERNAL_DIR=...                               # metrica/ e idsse/ (por defecto ~/Downloads/external-football-data)
python tools/metrica_open.py --describe                    # sección 3
python tools/change_dating.py --calibrate --degraded       # sección 4
python tools/change_dating.py --explore                    # sección 5 (solo g1)
python tools/change_dating.py --dfl                        # sección 6.2 (instrumento DFL, solo la referencia)
python tools/change_dating.py --measure                    # sección 7
```

## 8. Resultado: **negativo; se mantiene la cadena entregada**

Aplicando la sección 6 tal cual: **ninguna variante pasa las cinco compuertas.**

| variante | M (Metrica reservado) | E (DFL) | B (BAR-ATH sin GT) | P (slice) | C (banco) |
|---|---|---|---|---|---|
| `first` | pasa en g2 y en las dos mitades | **falla**: mediana \|·\| 1,16 → 1,20 s, mediana −0,28 → −0,40 s | pasa | pasa (Δ 0, 0–0) | pasa (igual) |
| `reception` | pasa | **falla**: 1,16 → 1,24 s, −0,28 → −0,66 s | pasa (ST −0,4) | **falla**: Δ −0,0105, pierde 1 posesión | **falla**: media −0,0066 |
| `relaxed` | pasa | **falla** en el signo: 1,16 → 1,12 s, pero −0,28 → −0,60 s | pasa | **falla**: Δ −0,0211, pierde 1 posesión | **falla**: media −0,0061, poco balón −0,0158 |

### Lectura

1. **Con el balón de Metrica, redatar funciona, y mucho.** En el partido reservado, las tres bajan
   la mediana de |retraso| de 0,16 a 0,00–0,04 s y la cola > 1 s tarde de 26,2% a 8,8–16,4%, en
   las dos mitades, sin cambiar el número de cambios emparejados (145 → 145–147). `first` sola
   lleva el p75 de +1,08 a +0,36 s. La respuesta a "¿dónde se fecha un cambio?" que da el juez
   externo es clara: **en el toque del nuevo equipo, aunque sea disputado o rápido**, no en su
   primer control lento y sin disputa.
2. **Con tracking real, no.** En DFL ninguna mejora: la mediana con signo se aleja de 0 en las tres
   (todas adelantan cambios que los eventos de DFL ya fechan después que la cadena) y la mediana de
   |·| solo baja en `relaxed`, 0,04 s. Por partido, `first` es peor en 4 de 7, mejor en 2 e igual
   en 1. Es un juez grueso (sección 6.2: 1,16 s de suelo), así que no dice que redatar sea malo con
   tracking real; dice que **no se ve ninguna mejora** fuera del balón idealizado.
3. **En BAR-ATH, lo mismo que DFL.** `first` es casi un no-op (280 frames, el mismo resultado que
   lane-dating). Las dos que sí mueven fechas (`reception` 2.949 frames, `relaxed` 3.388) **pierden
   una posesión** en el slice y bajan el banco. El acuerdo con el Smart Tagging no las distingue
   (76,7% y 77,1% frente a 77,1%).
4. **La explicación más simple de 1–3 es el balón.** En Metrica el balón está a 0,06 m del pie en
   cada evento y quiebra justo donde se anota un toque (sección 3); ahí un toque disputado o rápido
   **se ve** y redatar acierta. En DFL el equipo que actúa está a ≤ 1,5 m solo en la mitad de los
   eventos, y en nuestro tracking peor (la calibración degradada ya ensanchaba la cola). Con un balón
   ruidoso en los toques, el ancla temprana es tan a menudo un falso toque como el verdadero. Es la
   misma conclusión que `touch` en lane-dating, ahora vista desde dos jueces externos: **el límite
   no es la regla de fecha, es la precisión del balón en el toque.**

**No se reinterpreta la regla.** `first` falla E por 0,04 s de mediana \|·\| y 0,12 s de signo,
dentro del ruido declarado de DFL, y pasa todo lo demás. La compuerta estaba escrita y dice "no
peor"; se cumple la regla. Aunque se hubiera adoptado, su efecto en la entrega sería de 280 frames
y Δ 0 en el slice: no cambia nada que el `spellF1` vea.

## 9. Recomendación

- **Se mantiene la cadena entregada** (`72c98ed4bb4a…`). Ninguna variante de fecha entra.
- **El instrumento sí queda**: `tools/metrica_open.py` es el primer juez externo de *cuándo* cambia
  la posesión, con una verdad de escala comparable a la nuestra (3,35–3,65 posesiones/min). Su
  límite está escrito: el balón de muestra está sincronizado con los eventos y es más limpio que el
  nuestro en los toques.
- **Lo que dice para la ronda siguiente**, sin probarlo aquí:
  - Con la regla de fecha actual, la mediana ya está en el toque (1–4 frames). El síntoma del slice
    (+1,4 s de mediana) no se reproduce fuera: tiene que venir de lo que el slice tiene y Metrica
    no — balón perdido y ruidoso en los toques, colas de `D` y fragmentación (lane-dating, sección 9).
  - **El tercio de cambios sin pareja** (sección 4: 81 de 251 y 71 de 216 cambios en juego sin
    cambio de la cadena a ±5 s, con otros tantos sobrantes) pesa más que la fecha. Es una cuestión
    de **si**, y necesita su propio carril con la banda del informe por bloques (decisión 37).
  - Una regla de fecha solo valdrá la pena con un balón mejor en el toque (el vídeo ya no entra,
    decisión 38). Hasta entonces, cualquier variante que adelante cambios está expuesta al falso
    toque.

## 10. Limitaciones

- **Dos partidos de Metrica**, uno para fijar constantes y otro reservado: ~145 cambios emparejados
  en el reservado. Las mejoras en g2 son grandes y coherentes por mitades, pero vienen de un balón
  idealizado (sección 3).
- **La verdad de eventos fecha cada cambio en la primera acción anotada del nuevo equipo** (E3).
  Otra definición (por ejemplo, el primer control) daría otra mediana; esta es la que más se
  parece a la del reto ("el nuevo equipo gana el balón").
- **DFL** fecha con `EventTime` anotados en vivo; el desplazamiento por partido corrige el retraso
  medio, no la dispersión (sección 6.2). Su compuerta es la más débil de las cinco, y es la única
  que decide `first`.
- **No se probó ninguna regla de "si"** (sección 6.1). El brief la permitía; el motivo de no hacerlo
  está escrito antes de medir.
- **Deuda aceptada.** `LOW_BALL_BLOCKS` y los formateadores (`_dec`, `_abs`, `_pct`) se repiten
  entre los módulos de las rondas 2–5; el traspaso (`handovers`) es el de `tools/dating.py`,
  reescrito aquí para no importar un módulo de otro carril.
