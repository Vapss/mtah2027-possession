# Carril restart-team — QUÉ EQUIPO reanuda cuando el tag no lo dice

Estado: **pre-registro** (secciones 1–6), escrito y commiteado antes de correr ninguna variante
contra ninguna etiqueta (DFL, slice, banco) y antes de medir el acuerdo P-vs-L o el Smart Tagging
de ninguna variante en BAR-ATH. Pre-registro en `65274a7`; **enmienda** (sección 6 bis) en un commit
aparte, también antes de medir: la primera ejecución de DFL se detuvo sin leer su salida.

Código: `tools/restart_team.py`; pruebas: `tests/test_restart_team.py`. Este documento no cambia el
motor ni `docs/DECISIONS.md`: el coordinador integra.

## 1. Qué se propone

La cadena entregada (decisiones 30–36) fuerza la posesión al equipo que reanuda en cada `SET PIECES`
del Smart Tagging **con equipo**. De las 59 reanudaciones etiquetadas, **32 no traen equipo**: los 26
saques de banda y los 6 saques de centro (2 `Kick Off (Start)`, 4 `Kick Off (After Goal)`).
`engine.restart_controls` las salta, así que tras un saque de banda el motor arrastra al equipo que
echó el balón fuera — por reglamento, casi siempre el equivocado — hasta el siguiente control sin
disputa, y los primeros 9,2 s del partido salen `X` porque no hay estado antes del primer control.

La auditoría de la decisión 40 dice dónde está el margen: con `D` perfecto el slice va de 0,5368 a
0,6162; con el **equipo** correcto en nuestros frames vivos, a 0,8889, y 690 de los 889 frames vivos
con equipo equivocado caen a menos de 4 s de un cambio verdadero.

Se propone una regla determinista que **nombra el equipo** de cada reanudación sin equipo, para que
el motor la fuerce como las demás (con las decisiones 32/35 sin cambios: no se fuerza si el tracking
ya vio un control aceptado en la ventana del tag), y que **se abstiene** — la deja sin forzar, como
hoy — cuando la evidencia es ambigua. Dos fuentes de evidencia:

- **P (posiciones):** quién tiene el balón en las manos o a los pies mientras se prepara la
  reanudación.
- **L (reglamento):** saque de banda → el rival del equipo con la posesión cuando el balón salió;
  saque de centro tras gol → el equipo que encajó (el rival del que tenía la posesión al entrar el
  balón); saque de centro de una mitad → el rival del que sacó de centro en la otra mitad.

## 2. Lo que se miró antes de escribir esto (declarado)

### 2.1 BAR-ATH, sin ground truth

- **Reanudaciones etiquetadas por tipo y equipo** (`dead_ball.load_evidence().restarts`): córner 7
  local / 5 visitante, falta 2 / 3, saque de puerta 7 / 3, `Kick Off (After Goal)` 4 sin equipo,
  `Kick Off (Start)` 2 sin equipo, saque de banda 26 sin equipo.
- **Lo que trae el brief del coordinador** (decisión 40 y su auditoría, con la GT pública del slice
  como diagnóstico): los números de la sección 1, y agregados del tracking en los 6 saques de centro:
  el jugador más cercano de un equipo a 0,0–0,4 m del balón y el más cercano del otro a 8,9–12,7 m en
  4 de 6; uno sin balón sus primeros 2 s; uno con 4,9 m frente a 0,2 m.
- **Contaminación, declarada.** El saque de centro del inicio de la ventana pública (frame 11.185) se
  encontró mirando el slice. Cualquier ganancia pública que venga de él está contaminada por
  construcción; por eso los jueces principales son DFL y el reglamento, no el slice.
- **No se miró:** ningún P, L o acuerdo entre ellos en BAR-ATH, ni el Smart Tagging alrededor de
  ninguna reanudación sin equipo, ni el slice ni el banco de ninguna variante.

### 2.2 DFL (7 partidos), sin mirar equipos ni aciertos

- **El balón muerto de DFL está congelado y salta en la reanudación** (carril d-edges, 2.2): el 100%
  de los frames muertos tienen desplazamiento nulo del balón y en el primer frame vivo el balón se
  teletransporta: en 674 de las 696 paradas dentro de una mitad el salto es ≥ 1 m. Así que en DFL
  **el balón de la ventana del tag no es el balón real**: es el balón congelado donde quedó muerto
  (fuera del campo en 256 de los 290 saques de banda, cerca del punto de salida; en 16 de los 17
  saques de centro tras gol, donde entró el balón). Lo que dice eso de P está en 5.1.
- **Se puede saber el tipo de cada parada** con el balón del primer frame vivo de la verdad (ya
  teletransportado al punto de saque): a menos de 2 m del punto central es un saque de centro; a
  menos de 1,5 m de una banda (o fuera de ella) y a más de 3 m de las líneas de fondo, un saque de
  banda; a menos de 3 m de un banderín, un córner. Comprobado solo contra el **número** de eventos de
  los ficheros de eventos de DFL (`DFL_03_02_events_raw_*`, sin alinear tiempos ni mirar equipos):

  | partido | banda (geometría / eventos) | centro tras gol | córner |
  |---|---:|---:|---:|
  | J03WMX | 50 / 52 | 3 / 3 | 10 / 10 |
  | J03WN1 | 46 / 46 | 3 / 3 | 7 / 7 |
  | J03WOH | 37 / 36 | 4 / 4 | 6 / 6 |
  | J03WOY | 51 / 54 | 4 / 4 | 2 / 2 |
  | J03WPY | 39 / 41 | 1 / 1 | 11 / 11 |
  | J03WQQ | 33 / 42 | 0 / 1 | 10 / 15 |
  | J03WR9 | 34 / 37 | 2 / 2 | 6 / 6 |
  | total | 290 / 308 | 17 / 18 | 52 / 57 |

  (Centro tras gol = eventos `KickOff` menos los 2 de inicio de mitad.) Los umbrales de 2 / 1,5 / 3 m
  son del instrumento que clasifica DFL, fijados mirando solo estos conteos.
- **Las mitades de DFL empiezan en el saque de centro**: 11 de 14 mitades empiezan con el balón vivo
  en su primer frame, 3 con un tramo muerto corto. No hay frames antes del saque inicial.

### 2.3 Descartado sin medir

- **Alinear los eventos de DFL con el tracking por tiempo** para leer de ellos el tipo y el equipo:
  la geometría ya separa los tipos (2.2), y el equipo de la verdad es el de la posesión en el primer
  frame vivo, que es lo que el brief pide como verdad.
- **Usar la velocidad del balón en P**: un balón que se sostiene para sacar de banda puede estar
  fuera del campo o perderse en el tracking a ratos; P se queda en posiciones, sin constante nueva.

## 3. Constantes (fijas; ninguna se barre contra etiquetas)

| constante | valor | de dónde |
|---|---:|---|
| radio del que saca, `take_m` | 1,5 m | `engine.Params.radius_m`: más cerca, el jugador puede jugar el balón |
| distancia del rival, `clear_m` | 2,0 m | Regla 15: en un saque de banda los rivales a ≥ 2 m del punto del saque (en el de centro, ≥ 9,15 m: 2 m también lo separa) |
| ventana de P | `[inicio del tag, reanudación estimada)` | la ventana del propio `SET PIECES` antes del frame que el motor fuerza: 5 s; 3,5 s en un saque de centro (`dead_ball.Params`) |
| ancla de L | inicio de la parada etiquetada | `dead_ball.stoppages(..., "out")`: la última salida del balón antes del tag (en un gol, hasta 120 s antes) |
| ventana del voto del Smart Tagging | `[reanudación, + 5 s)` | solo informa; no es compuerta |
| errores de los tags sintéticos de DFL | ciclo −2, −1, 0, +1, +2 s | el del carril d-edges, sin cambios |

## 4. Variantes (cuatro, ni una más)

Las cuatro son la cadena entregada (`engine.DEFAULT`, `D` = paradas etiquetadas ∪ W1, reanudaciones
forzadas con las decisiones 32/35) y cambian **solo** el equipo de las reanudaciones etiquetadas sin
equipo de tipo saque de banda, `Kick Off (After Goal)` o `Kick Off (Start)`; las demás reanudaciones
no se tocan. Referencia: **`engine`** = `engine.run()` byte a byte (SHA-256 `72c98ed4bb4a…`, lo fija un
test con el bundle), que deja sin forzar las 32.

**P, posiciones.** En un frame con balón observado (dentro o **fuera** del campo: un saque de banda se
sostiene fuera de la línea; donde el tracking no lo ve, ese frame no dice nada), el balón lo *tiene*
un equipo si su jugador más cercano está a ≤ 1,5 m y el más cercano del otro a ≥ 2 m. P nombra el
equipo que lo tiene en la ventana de P si **todos** los frames en que alguien lo tiene son de ese
equipo; se abstiene si nadie lo tiene en ningún frame o si lo tienen los dos en frames distintos
(p. ej. un rival que devuelve el balón).

**L, reglamento.** Saque de banda y saque de centro tras gol: el rival del equipo que la cadena tiene
en posesión el frame anterior al ancla (la salida del balón); se abstiene si en ese frame no hay
estado o si el ancla es el inicio de la mitad. L se lee **en la cadena de la propia variante**, en
orden de frame: una reanudación que la variante ya nombró y forzó cuenta para la siguiente (dos
saques de banda seguidos sin control entre medias). `Kick Off (Start)`: el rival del equipo que P
nombra en el saque de centro de la otra mitad (exactamente uno por mitad; si no, se abstiene).

- **V1 `law`** — L. En los saques de centro de inicio de mitad se abstiene: el reglamento no dice
  quién sacó primero (sorteo), y su L necesita P.
- **V2 `pos`** — P.
- **V3 `pos+law`** — P; donde P se abstiene, L.
- **V4 `agree`** — se fuerza solo si P y L nombran el mismo equipo. En los dos saques de centro de
  inicio de mitad eso es: P decide en las dos mitades y nombra equipos distintos.

**El inicio de una mitad (decidido aquí).** Un `Kick Off (Start)` nombrado se fuerza como cualquier
reanudación: en su frame estimado (inicio del tag + 3,5 s), y no se fuerza si el tracking ya vio un
control aceptado en `[inicio del tag, frame)` (decisiones 32/35: entonces el motor ya arranca con ese
control). Los frames desde ese frame hasta el primer control pasan de `X` al equipo que saca. El `D`
de antes (por reglamento, antes del primer toque el balón no está en juego) no cambia, y no se
rellena nada hacia atrás.

## 5. Mediciones (todas, para cada variante y para `engine`), en este orden

1. **DFL** (`python tools/restart_team.py dfl`), con tags sintéticos (`dfl_tags`): un tag por parada
   verdadera estrictamente dentro de una mitad cuyo balón congelado esté fuera del campo (la regla de
   d-edges), más todo saque de banda y todo saque de centro tras gol según la geometría de 2.2, más
   un `Kick Off (Start)` por mitad en su primer frame vivo. Saques de banda y de centro **sin
   equipo** (como en BAR-ATH); los demás con el equipo de la verdad. Estimación desplazada de la
   reanudación verdadera por el ciclo de errores (dentro de la mitad); tag 5 s antes (3,5 s en un
   saque de centro). Verdad = el equipo que la verdad de DFL nombra en el primer frame vivo de la
   parada. Se informa:
   - por tipo (banda / centro tras gol / centro de inicio) y en total, para cada variante y para P y
     L por separado: cuántas hay, cobertura (parte decidida) y acierto en las decididas; limpio y con
     nuestro balón (ciclo de errores); y limpio con el error fijo en cada valor del ciclo;
   - `spellF1` oficial por partido de la cadena con los equipos inferidos forzados frente a `engine`
     (mismos tags, sin forzar las sin equipo), limpio y con nuestro balón (`external.score`), y
     partidos ganados (estrictamente mayor).

   **Cómo afecta a P el balón congelado de DFL.** En DFL, P solo ve en la ventana el balón congelado
   donde quedó muerto, y el balón real solo en los frames posteriores a la reanudación verdadera que
   caigan dentro (con error +1 / +2 s). Para un saque de banda el balón congelado está cerca del punto
   del saque (se saca donde salió), así que P mide algo parecido a lo nuestro, pero no lo mismo: no hay
   balón llevado por nadie hasta la línea. Para un saque de centro tras gol, el balón congelado está
   donde entró y P verá a quien esté junto a la portería, no al que saca: **P no puede
   juzgarse en DFL en los saques de centro tras gol**. En los de inicio de mitad, DFL no tiene frames
   antes del saque: la ventana de P está vacía salvo con error positivo. Se reportan igual, pero el
   juicio de P en DFL descansa en los saques de banda, y la tabla de error fijo dice cuánto depende
   de la estimación.
2. **BAR-ATH, sin ground truth** (`python tools/restart_team.py --match`): por tipo, cobertura de P y
   de L, cuántas decide cada variante y cuántas fuerza de verdad (tras la cancelación de la decisión
   32/35); acuerdo P-vs-L en los saques de banda en que los dos deciden; voto de fase del Smart
   Tagging en `[reanudación, + 5 s)` tras cada reanudación recién forzada (frames con voto de un solo
   lado que coinciden con el equipo forzado, y reanudaciones cuyo voto mayoritario coincide); acuerdo
   con el Smart Tagging y el informe de bloques de `tools/blocks.py`.
3. **Slice público (contaminado, declarado)**: `spellF1`, `macroF1`, posesiones predichas, precisión
   de `D`; Δ pareado, `n_discordant`, ganadas motor/variante con
   `tools/compare_submissions.py engine.csv V.csv --gt public`. **Banco**
   (`python tools/restart_team.py --bench`): limpio, media de donantes, media con poco balón, peor
   donante.

## 6. Regla de selección (pre-registrada)

1. **Compuertas**, todas obligatorias, frente a `engine`:
   - **G-DFL1**: acierto de las reanudaciones sin equipo que la variante decide, todas juntas, con el
     ciclo de errores, **≥ 0,95 limpio y ≥ 0,95 con nuestro balón**;
   - **G-DFL2**: gana a `engine` en `spellF1` en **≥ 6 de 7** partidos limpio **y** en **≥ 6 de 7** con
     nuestro balón;
   - **G-PL** (solo `pos+law` y `agree`, que usan las dos): acuerdo P-vs-L **≥ 0,90** en los saques de
     banda de BAR-ATH en que P y L deciden los dos (si no hay ninguno, la compuerta falla: no hay
     evidencia de acuerdo);
   - **G-ST**: acuerdo con el Smart Tagging del partido (`tools/blocks.py`) **no más bajo** que el de
     `engine`, por ninguna cantidad;
   - **G-B**: ningún bloque con **> 70%** de `D`, ningún bloque sin posesiones, posesiones/min del
     partido en **3,4 ± 0,5**;
   - **G-PUB**: Δ pareado de `spellF1` **≥ 0**, `wins_a ≤ wins_b` (motor ≤ variante), precisión de `D`
     **≥ 0,85**;
   - **G-BENCH**: media de donantes **≥** la de `engine` y media con poco balón **≥** la de `engine`
     (las que dé el comando; la decisión 36 dice 0,4351 / 0,3595).
2. Entre las que pasan, se recomienda la primera en este **orden de prior**, sin mirar cuál tiene
   más `spellF1`: **V4 `agree` > V3 `pos+law` > V2 `pos` > V1 `law`**. Forzar un equipo equivocado crea
   una posesión falsa, abstenerse deja la cadena como hoy: dos evidencias independientes que coinciden
   van primero; la que cubre más con las dos, después; la observación sola (que en los saques de centro
   descansa además en la geometría del reglamento) antes que el reglamento solo, que hereda el error de
   la cadena justo donde más falla (cerca de un cambio verdadero, decisión 40).
3. Las diferencias de `spellF1` entre variantes que pasan no alteran el orden.
4. Si ninguna pasa, el resultado es **negativo**, la cadena entregada se mantiene, y se reporta qué
   compuerta falla y por cuánto.

## 6 bis. Enmienda antes de medir (declarada)

Tras commitear el pre-registro, el coordinador avisó de un fallo de la revisión de #57 en los tags
sintéticos de d-edges que este carril reproducía: la estimación se recortaba a la mitad pero no al
inicio de la parada, así que con −2 s en una parada corta **la reanudación caía antes de que el balón
saliera** (y el tag empieza antes de la salida en el 8,8% de los tags de d-edges). La ejecución de DFL
ya lanzada se detuvo y se borró **sin leer nada de su salida**; ninguna otra medición había corrido.
Dos cambios, y nada más:

1. **Tags sintéticos de DFL:** la estimación nunca cae antes del primer frame muerto + 1 de su parada
   (en el `Kick Off (Start)`, del inicio de la mitad). El inicio del tag sigue a 5 s (3,5 s) de la
   estimación, recortado solo a la mitad: puede empezar antes de la salida, como un tag real de 5 s
   tras una parada corta.
2. **P no mira antes de la salida del balón:** su ventana pasa a ser
   `[max(inicio del tag, ancla), reanudación estimada)`, con el ancla de L (inicio de la parada
   etiquetada). Antes del ancla el balón estaba en juego y quien lo tenía es la jugada anterior, que
   en un saque de banda suele ser el rival del que saca. En los `Kick Off (Start)` el ancla es el
   inicio de la mitad y no cambia nada.

Las constantes, las variantes, las mediciones, las compuertas y el orden de prior no cambian.
