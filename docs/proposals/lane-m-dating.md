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
