# Carril m-whether — SI cambia la posesión en juego: los cambios que la cadena pierde y los que inventa, juzgados en los partidos abiertos de Metrica

Ronda 6. Código: `tools/change_whether.py`; pruebas: `tests/test_change_whether.py`. Reutiliza sin
editarlos `tools/metrica_open.py` (cargador y verdad de eventos E1–E5) y `tools/change_dating.py`
(la cadena en Metrica, el emparejamiento, la calibración `--degraded`) de la ronda 5. Este documento
no cambia el motor ni `docs/DECISIONS.md`: el coordinador integra.

Tres commits, en este orden y sin reescribir los anteriores:

1. **Anatomía** (este commit): secciones 1–4. Ninguna variante existe todavía.
2. **Pre-registro** de las variantes, con su código y sus pruebas, **antes de medir ninguna**.
3. **Resultados**, añadidos al final sin tocar lo anterior.

*Nota de procedimiento.* Una primera versión de este commit (`ad0e424`) se calculó sobre el
instrumento de la ronda 5 antes de las correcciones de la revisión de #59 (los medios tiempos
separados por `HALF_GAP`, entre otras); el coordinador había pedido no commitear números de
Metrica hasta esas correcciones. Esta versión se recalculó sobre `origin/dev` (`2d3cc3e`) antes de
escribir ninguna variante: los números con el balón limpio no cambian; los del balón con ruido se
mueven un poco porque el sorteo del ruido cubre ahora 250 frames más (σ sigue en 0,85 m).

## 1. La pregunta

La ronda 5 (lane-m-dating.md) encontró que, con el balón de Metrica, la cadena entregada fecha bien
los cambios que empareja (mediana +0,04 / +0,16 s) pero deja **un tercio de los cambios en juego
sin pareja** (81 de 251 en g1, 71 de 216 en g2) "con otros tantos sobrantes" (66, 69). Eso es una
cuestión de **si** cambia la posesión, no de **cuándo**, y la ronda 5 lo dejó para otro carril.

Primero, sin regla: **¿de qué están hechos los cambios perdidos y los sobrantes?** Y después, con
hasta cuatro variantes pre-registradas contra las categorías más grandes: ¿puede una regla
determinista, con constantes fijadas en g1 o por física, recuperar cambios perdidos o quitar
sobrantes sin mover la escala temporal de BAR-ATH fuera de 3,4 ± 0,5 posesiones/min y sin depender
del balón idealizado de Metrica?

La escala de la verdad de Metrica es comparable a la nuestra (3,65 / 3,35 posesiones/min frente a
3,4 ± 0,5; DFL: 4,58), así que, a diferencia de DFL (decisión 37), **puede** juzgar reglas que
cambian el número de posesiones. Pero su definición no es la del reto: su posesión es "quién actuó
el último" (E2), y un `RECOVERY` cuenta aunque sea un despeje o un desvío; el reto dice que la
posesión cambia cuando el rival gana posesión **controlada** y que el balón suelto se queda con el
último equipo. La sección 4 mide cuánto pesa esa diferencia.

## 2. El instrumento

### 2.1 El emparejamiento, corregido (fijado antes de cualquier variante)

La ronda 5 emparejaba los cambios **en juego** de la verdad (E5) con **todos** los cambios de la
cadena, reanudaciones incluidas. Un cambio de la cadena en una reanudación (forzado por ella, o por
el primer control de quien saca) no tiene pareja en juego por construcción, y contaba como sobrante.
Aquí cada cambio de la verdad, en juego o no, se empareja uno a uno con cada cambio de la cadena con
la regla de la ronda 5 (`change_dating.match`: mismo equipo nuevo, ±5 s, los pares más cercanos
primero):

- **perdido** = un cambio **en juego** de la verdad sin pareja;
- **sobrante** = un cambio de la cadena sin pareja de **ningún** tipo;
- la fecha de los emparejados en juego se reporta como en la ronda 5.

Los números de la ronda 5 salen al lado (línea "Ronda 5"), con el desglose de sus sobrantes, para
que las dos cuentas se puedan reconciliar.

### 2.2 Las causas (escritas antes de contarlas; `MISS_KINDS`, `EXTRA_KINDS`)

**Un cambio en juego perdido** `(t, U)` (el equipo `T` lo tenía) se mira en los frames
`[t, min(e, t + 5 s)]`, donde `e` es el fin de la posesión de `U` en la verdad (otro equipo, balón
muerto o fin de la mitad): donde tendría que estar su pareja. Gana la primera causa que aplica:

1. **ya del nuevo equipo**: la cadena ya tiene a `U` en `t`; nunca vio la posesión de `T` de antes
   (el reflejo de otro perdido).
2. **aceptado sin pareja**: hay un control sin disputa de `U` (sería un cambio) pero el
   emparejamiento uno a uno lo dio a otro cambio.
3. **veto del duelo**: hay controles de `U` (`engine.control`) y la regla del duelo los anula todos
   (alguien de `T` a ≤ 1,5 m).
4. **toque rápido**: ningún control de `U`, pero un jugador de `U` es el más cercano a ≤ 1,5 m de un
   balón en el campo: el balón iba a > 5 m/s (un toque de primeras, un desvío, una intercepción).
5. **rival igual de cerca**: `U` a ≤ 1,5 m pero nunca estrictamente más cerca que `T`.
6. **sin balón**: el balón falta en ≥ 50% de los frames.
7. **lejos**: nadie de `U` a ≤ 1,5 m de un balón visto (balón aéreo, error de posición).

Cruces (no excluyentes): la posesión de `U` en la verdad dura < 2 s; acaba en parada; acaba porque
`T` la recupera; ≥ 50% de sus frames en el `D` predicho; y si la cadena **sin** la regla del duelo
(`engine.D31`, mismo `D`, mismas reanudaciones) la empareja: es la respuesta a "cuántos perdidos
explica el veto del duelo".

**Un cambio sobrante** `(c, V)` de la cadena (venía de `W`):

1. **reanudación forzada**: `c` es un cambio forzado por una reanudación.
2. **balón muerto en la verdad**: la verdad tiene balón muerto (o nadie) en `c`.
3. **corrección tardía**: la verdad ya tiene a `V` en `c`: la cadena llega a la verdad más de 5 s
   tarde (o vuelve de un error).
4. **ida y vuelta**: la cadena vuelve a `W` en < 3 s (A → B → A).
5. **control del rival**: el resto; la verdad dice `W` y la cadena se queda con `V` ≥ 3 s.

### 2.3 El balón degradado (fijado en g1, sin etiquetas)

La ronda 5 midió que el balón de muestra de Metrica está sincronizado con los eventos. Aquí se mide
contra el nuestro con un estadístico que no necesita etiquetas: **la distancia de un balón lento**
(≤ 2 m/s, en el campo, fuera del `D` entregado) **a su jugador más cercano**. En Metrica g1 su
mediana es 0,05 m; en BAR-ATH, 1,02 m. Las dos distribuciones de velocidad del balón son en cambio
casi iguales (mediana ~6 m/s): nuestro error no es un temblor de frame a frame, es un
**desplazamiento del balón que varía despacio**. El juego degradado pone encima de un partido de
Metrica, en este orden:

1. **ruido de posición**: por eje, ruido gaussiano blanco suavizado con un núcleo gaussiano de 1 s
   (añade < 1 m/s de velocidad) y escalado a σ por eje; **σ se ajusta en g1** (`fit_sigma`: la σ de
   la rejilla 0,50 .. 1,50 m que deja la mediana de la distancia del balón lento más cerca de la de
   BAR-ATH) y g2 la usa sin tocarla. Semilla fija por partido (g1: 1, g2: 2).
2. **nuestro patrón de balón visto**: la máscara de balón visto de BAR-ATH, mitad sobre mitad
   (`change_dating.keep_mask`, el `--degraded` de la ronda 5). El `D` etiquetado ve el `out` del
   balón degradado; el de los jugadores (W1) no lee el balón.

`features_from` recalcula las features del motor con el balón movido copiando la aritmética de
`metrica_open.build` (que este carril no edita).

## 3. Anatomía (`python tools/change_whether.py --anatomy`)

Salida sin editar (BAR-ATH: el bundle licenciado, solo agregados; el slice público con su GT
pública; g2 no se carga):

### Metrica g1 (g2 no se carga)

Instrumento corregido (todas las verdades contra todos los cambios de la cadena) y el de la ronda 5 (solo verdades en juego):

| tramo | cambios verdad (en juego) | cambios cadena | emparejados | perdidos en juego | sobrantes | perdidos + sobrantes | mediana \|·\| s (en juego) |
|---|---:|---:|---:|---:|---:|---:|---:|
| cadena entregada | 328 (251) | 236 | 219 | 84 | 17 | 101 | 0,04 |
| sin la regla del duelo (`engine.D31`) | 328 (251) | 296 | 249 | 64 | 47 | 111 | 0,04 |

Ronda 5: 170 emparejados, 81 perdidos, 66 sobrantes. Sus sobrantes, por qué: junto a un cambio verdadero que no es en juego 18, reanudación forzada 41, sin cambio verdadero a ±5 s 7

Cambios en juego perdidos (84), por la primera causa que aplica:

| causa | n | corta (< 2 s) | acaba en parada | la recupera el anterior | dentro de D predicho | la empareja la cadena sin duelo |
|---|---:|---:|---:|---:|---:|---:|
| ya del nuevo equipo | 28 (33,3%) | 12 | 7 | 21 | 1 | 6 |
| veto del duelo | 14 (16,7%) | 7 | 8 | 6 | 5 | 14 |
| toque rápido | 36 (42,9%) | 18 | 16 | 20 | 2 | 1 |
| rival igual de cerca | 2 (2,4%) | 2 | 2 | 0 | 0 | 0 |
| sin balón | 1 (1,2%) | 1 | 0 | 1 | 0 | 0 |
| lejos | 3 (3,6%) | 2 | 1 | 2 | 1 | 0 |
| total | 84 | 42 | 34 | 50 | 9 | 21 |

Cambios sobrantes de la cadena (17):

| causa | n | dentro de D predicho |
|---|---:|---:|
| reanudación forzada | 3 (17,6%) | 3 |
| balón muerto en la verdad | 1 (5,9%) | 1 |
| corrección tardía | 7 (41,2%) | 0 |
| ida y vuelta | 5 (29,4%) | 0 |
| control del rival | 1 (5,9%) | 0 |

### El balón degradado: el ruido de posición, fijado en g1

Objetivo (BAR-ATH, sin etiquetas): mediana de la distancia de un balón lento (≤ 2 m/s, en el campo, fuera del `D` entregado) a su jugador más cercano = **1,02 m**. Rejilla σ 0,50 .. 1,50 m por eje (suavizado 1 s); en g1: σ 0,50 → 0,62 m, σ 0,70 → 0,86 m, σ 0,90 → 1,09 m, σ 1,10 → 1,30 m, σ 1,30 → 1,50 m, σ 1,50 → 1,69 m. **Elegido σ = 0,85 m.**

| balón | visto (mitades vivas) | balón lento → jugador, mediana m | velocidad p25 / p50 / p75 m/s | control | control sin disputa |
|---|---:|---:|---|---:|---:|
| BAR-ATH | 79,3% | 1,02 | 3,12 / 5,84 / 10,21 | 28,5% | 26,7% |
| g1 limpio | 95,2% | 0,05 | 2,81 / 6,08 / 11,69 | 42,3% | 38,4% |
| g1 con nuestro balón visto | 60,2% | 0,05 | 2,77 / 6,02 / 11,47 | 42,5% | 38,8% |
| g1 con ruido σ 0,85 | 95,2% | 1,04 | 2,92 / 6,16 / 11,83 | 34,2% | 31,3% |
| g1 con ruido y nuestro balón visto (degradado) | 60,2% | 1,02 | 2,89 / 6,06 / 11,66 | 35,4% | 32,2% |

La cadena entregada en g1 bajo cada balón (instrumento corregido) y sus perdidos por causa:

| tramo | cambios verdad (en juego) | cambios cadena | emparejados | perdidos en juego | sobrantes | perdidos + sobrantes | mediana \|·\| s (en juego) |
|---|---:|---:|---:|---:|---:|---:|---:|
| g1 limpio | 328 (251) | 236 | 219 | 84 | 17 | 101 | 0,04 |
| g1 con nuestro balón visto | 328 (251) | 186 | 161 | 131 | 25 | 156 | 0,08 |
| g1 con ruido σ 0,85 | 328 (251) | 271 | 202 | 97 | 69 | 166 | 0,24 |
| g1 con ruido y nuestro balón visto (degradado) | 328 (251) | 205 | 157 | 135 | 48 | 183 | 0,32 |

| causa | g1 limpio | g1 con nuestro balón visto | g1 con ruido σ 0,85 | g1 con ruido y nuestro balón visto (degradado) |
|---|---:|---:|---:|---:|
| ya del nuevo equipo | 28 | 43 | 32 | 44 |
| aceptado sin pareja | 0 | 0 | 0 | 0 |
| veto del duelo | 14 | 6 | 8 | 4 |
| toque rápido | 36 | 29 | 38 | 28 |
| rival igual de cerca | 2 | 1 | 5 | 2 |
| sin balón | 1 | 50 | 1 | 48 |
| lejos | 3 | 2 | 13 | 9 |
| sobrante: reanudación forzada | 3 | 11 | 8 | 12 |
| sobrante: balón muerto en la verdad | 1 | 1 | 6 | 1 |
| sobrante: corrección tardía | 7 | 12 | 26 | 21 |
| sobrante: ida y vuelta | 5 | 1 | 19 | 10 |
| sobrante: control del rival | 1 | 0 | 10 | 4 |

### Estructura sin verdad: Metrica g1 frente a BAR-ATH

Por minuto de las mitades. Un veto es un tramo de frames seguidos en que el rival del equipo en posesión controla el balón (`engine.control`) y la regla del duelo lo anula; un toque rápido, uno en que el rival es el más cercano a ≤ 1,5 m de un balón en el campo, el equipo en posesión está fuera de alcance y el balón va a > 5 m/s. El juez independiente es la verdad de eventos en g1 y el Smart Tagging en BAR-ATH (un solo equipo votado).

| partido | min | cambios /min | forzados | vetos por cambio natural | vetos del duelo /min | veto p25 / p50 / p75 / p90 s | vetos ≥ 0,2 / 0,4 / 1 s | tras el veto, cambia a ±5 s | toques rápidos del rival /min | tras el toque, cambia a ±5 s | idas y vueltas < 3 s /min | juez independiente: dice rival en el veto / en el toque rápido / acuerdo con el estado |
|---|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---|
| Metrica g1 | 96,7 | 2,44 | 44 | 0,36 | 0,72 | 0,04 / 0,08 / 0,23 / 0,52 | 25 / 10 / 5 | 61,4% | 6,07 | 58,8% | 0,38 | eventos: 87,6% / 39,1% / 93,5% |
| BAR-ATH | 105,9 | 2,86 | 2 | 0,18 | 0,50 | 0,08 / 0,20 / 0,32 / 0,51 | 28 / 11 / 2 | 71,7% | 4,13 | 58,8% | 0,46 | Smart Tagging: 65,5% / 34,0% / 77,0% |

### Slice público (CONTAMINADO: sus 17 posesiones eligieron reglas anteriores)

Instrumento corregido (todas las verdades contra todos los cambios de la cadena) y el de la ronda 5 (solo verdades en juego):

| tramo | cambios verdad (en juego) | cambios cadena | emparejados | perdidos en juego | sobrantes | perdidos + sobrantes | mediana \|·\| s (en juego) |
|---|---:|---:|---:|---:|---:|---:|---:|
| cadena entregada | 15 (12) | 19 | 9 | 3 | 10 | 13 | 1,36 |
| sin la regla del duelo (`engine.D31`) | 15 (12) | 23 | 10 | 2 | 13 | 15 | 1,52 |

Ronda 5: 9 emparejados, 3 perdidos, 10 sobrantes. Sus sobrantes, por qué: reanudación forzada 1, sin cambio verdadero a ±5 s 9

Cambios en juego perdidos (3), por la primera causa que aplica:

| causa | n | corta (< 2 s) | acaba en parada | la recupera el anterior | dentro de D predicho | la empareja la cadena sin duelo |
|---|---:|---:|---:|---:|---:|---:|
| ya del nuevo equipo | 1 (33,3%) | 0 | 0 | 1 | 0 | 0 |
| veto del duelo | 1 (33,3%) | 0 | 0 | 1 | 0 | 1 |
| toque rápido | 1 (33,3%) | 0 | 0 | 1 | 0 | 0 |
| total | 3 | 0 | 0 | 3 | 0 | 1 |

Cambios sobrantes de la cadena (10):

| causa | n | dentro de D predicho |
|---|---:|---:|
| reanudación forzada | 1 (10,0%) | 0 |
| balón muerto en la verdad | 3 (30,0%) | 3 |
| corrección tardía | 3 (30,0%) | 0 |
| ida y vuelta | 1 (10,0%) | 0 |
| control del rival | 2 (20,0%) | 0 |

## 4. Lectura (antes de escribir ninguna variante)

**4.1 El tercio "sobrante" de la ronda 5 era casi todo del instrumento.** De sus 66 sobrantes en
g1, 41 son cambios forzados por una reanudación y 18 están junto a un cambio de la verdad que no es
en juego (una reanudación en la que el primer control de quien saca llega antes que el forzado);
solo **7** no tienen ningún cambio verdadero a ±5 s. Con el emparejamiento corregido la cadena
entregada en g1 limpio tiene **84 perdidos y 17 sobrantes**: con el balón de Metrica, su problema
es de **perdidos**, no de inventados.

**4.2 Los perdidos (g1 limpio, 84).**

- **Toque rápido, 36 (43%)**: el nuevo equipo toca el balón, pero a > 5 m/s, y nunca lo controla
  en los 5 s siguientes. La mitad (18) son posesiones de < 2 s en la verdad; 20 acaban porque el
  equipo anterior la recupera y 16 en una parada. Es el despeje, el desvío, la intercepción que
  sale rebotada: lo que la verdad de eventos cuenta como `RECOVERY` y el reto, si no hay control,
  como balón suelto que se queda con el último equipo.
- **Ya del nuevo equipo, 28 (33%)**: la cadena nunca vio la posesión anterior del equipo que la
  pierde (21 de las 28 "la recupera el anterior": son la vuelta de una posesión corta que la cadena
  no vio). Son **reflejos** de otros perdidos, no una causa propia.
- **Veto del duelo, 14 (17%)**: controles del nuevo equipo con un rival a ≤ 1,5 m. La cadena sin la
  regla del duelo empareja los 14 y 6 de los "ya del nuevo equipo": **el veto explica 21 de los 84
  perdidos**. Pero esa cadena tiene 30 sobrantes más (17 → 47): 111 errores frente a 101. La regla
  del duelo, en conjunto, también gana en Metrica.
- Sin balón, lejos, rival igual de cerca: 6 entre las tres.
- La mitad de todos los perdidos (42 de 84) son posesiones de < 2 s en la verdad, y 50 acaban
  porque el equipo anterior la recupera: **son idas y vueltas de balones sueltos**.

**4.3 Lo que hace el balón ruidoso (g1, mismo partido, misma verdad).** El ruido de posición
(σ = 0,85 m, el que pone el balón lento a 1,04 m del jugador, como en BAR-ATH; la velocidad no se
mueve y la parte de frames con control baja de 42,3% a 34,2%, hacia el 28,5% de BAR-ATH) **cambia
el tipo de error**: los sobrantes pasan de 17 a **69** (correcciones tardías 26, idas y vueltas 19,
controles del rival 10) y los perdidos de 84 a 97. Nuestro patrón de balón visto, solo, sube los
perdidos (84 → 131, "sin balón" 50). Las dos cosas juntas: 135 perdidos y 48 sobrantes, 183 errores
frente a 101. **Con un balón como el nuestro, inventar cambios pesa casi tanto como perderlos.**

**4.4 BAR-ATH, sin verdad.** La estructura es la de g1: 0,50 vetos del duelo por minuto (g1: 0,72),
cortos (mediana 0,20 s; ≥ 0,4 s solo 11 en el partido, ≥ 1 s 2), y tras el 72% la cadena cambia al
rival en los 5 s siguientes de todos modos. El Smart Tagging dice "rival" en el 65,5% de los frames
vetados (frente al 77,0% de acuerdo con el estado en general): el veto no es claramente correcto,
pero casi siempre es solo un retraso. Los toques rápidos del rival son 4,1 por minuto (g1: 6,1) y
solo son un cambio en una minoría: la verdad dice "rival" en el 39% en g1 y el Smart Tagging en el
34% en BAR-ATH. **Un toque rápido solo no es evidencia de cambio**: casi dos de cada tres son un
balón que pasa cerca de un rival. Idas y vueltas < 3 s: 0,46 por minuto (g1 limpio: 0,38).

**4.5 El slice público (contaminado).** 15 cambios en la GT (12 en juego), 19 en la cadena: 3
perdidos y **10 sobrantes** (3 en balón muerto de la GT y dentro del `D` predicho, 3 correcciones
tardías, 2 controles del rival, 1 ida y vuelta, 1 reanudación forzada). Con nuestro balón, el slice
se parece a g1 degradado (dominan los sobrantes), no a g1 limpio. Se reporta; no elige nada.

**Qué implica para las variantes.**

1. Las categorías más grandes en g1 limpio (toque rápido y sus reflejos) son balones sueltos que la
   verdad de eventos cuenta y la definición del reto no: recuperarlos en Metrica es **contar
   posesiones** que nuestra GT probablemente no tiene, y la banda de 3,4 ± 0,5 de BAR-ATH lo vigila
   (la cadena ya está en 3,62).
2. Un toque rápido aislado es demasiado impreciso (34–39%) para cambiar la posesión. Si una variante
   lo usa, necesita una confirmación que no dependa de la precisión del balón en el toque.
3. Con el balón degradado los sobrantes (correcciones tardías, idas y vueltas) pesan casi tanto
   como los perdidos: una variante que solo añade cambios puede ganar en Metrica limpio y perder en
   el degradado. La compuerta exige las dos.
4. El veto del duelo es una categoría pequeña (14) de tramos cortos; levantarlo entero cuesta más
   de lo que da. Solo un veto **sostenido** es candidato.

---

*Lo que sigue es el pre-registro (commit 2), escrito antes de medir ninguna variante en g2, en DFL,
en BAR-ATH, en el slice ni en el banco. Las secciones 1–4 no cambian.*

## 5. Exploración en g1 (declarada; g2 no se carga)

**Qué se miró antes de escribir las reglas.** La anatomía (secciones 3 y 4) y, durante ella, dos
prototipos en g1 limpio fuera del repositorio: un veto sostenido y un "dos toques del mismo equipo",
con números del mismo orden que los de la tabla de abajo. Nada de g2, DFL, BAR-ATH, el slice ni el
banco se midió con ninguna regla.

**Cómo se fija cada constante (escrito en el código, `choose`, antes de correr la rejilla).** En
cada rejilla se toma el valor con **menos perdidos + sobrantes sumados en g1 limpio y g1
degradado** (instrumento corregido); en un empate, el que menos cambia la cadena (la persistencia
más larga, las ventanas de `settle` y `relay` más cortas). La V4 combina las dos reglas con las
constantes que cada una tiene sola: sin ajuste conjunto.

Salida sin editar de `python tools/change_whether.py --explore`:

Exploración en Metrica g1, limpio y degradado (g2 no se carga).

| regla | constante s | condición | cambios cadena | perdidos | sobrantes | perdidos + sobrantes | spellF1 (eventos) |
|---|---:|---|---:|---:|---:|---:|---:|
| `engine` | — | limpio | 236 | 84 | 17 | 101 | 0,6812 |
| `engine` | — | degradado | 205 | 135 | 48 | 183 | 0,4743 |
| `persist` | 0,2 | limpio | 254 | 78 | 29 | 107 | 0,6968 |
| `persist` | 0,2 | degradado | 255 | 128 | 91 | 219 | 0,4424 |
| `persist` | 0,4 | limpio | 240 | 82 | 19 | 101 | 0,6992 |
| `persist` | 0,4 | degradado | 227 | 131 | 66 | 197 | 0,4587 |
| `persist` | 0,6 | limpio | 238 | 82 | 17 | 99 | 0,6964 |
| `persist` | 0,6 | degradado | 215 | 133 | 57 | 190 | 0,4571 |
| `persist` | 0,8 | limpio | 238 | 82 | 17 | 99 | 0,6958 |
| `persist` | 0,8 | degradado | 211 | 132 | 51 | 183 | 0,4679 |
| `persist` | 1,0 | limpio | 238 | 82 | 17 | 99 | 0,6958 |
| `persist` | 1,0 | degradado | 209 | 133 | 50 | 183 | 0,4733 |
| `settle` | 0,5 | limpio | 226 | 88 | 11 | 99 | 0,6812 |
| `settle` | 0,5 | degradado | 199 | 139 | 47 | 186 | 0,4743 |
| `settle` | 1,0 | limpio | 218 | 94 | 9 | 103 | 0,6790 |
| `settle` | 1,0 | degradado | 187 | 145 | 41 | 186 | 0,4705 |
| `settle` | 2,0 | limpio | 196 | 114 | 7 | 121 | 0,6477 |
| `settle` | 2,0 | degradado | 169 | 157 | 35 | 192 | 0,4547 |
| `settle` | 3,0 | limpio | 180 | 130 | 7 | 137 | 0,6102 |
| `settle` | 3,0 | degradado | 157 | 165 | 31 | 196 | 0,4481 |
| `relay` | 0,5 | limpio | 270 | 66 | 29 | 95 | 0,6766 |
| `relay` | 0,5 | degradado | 226 | 122 | 56 | 178 | 0,4805 |
| `relay` | 1,0 | limpio | 276 | 63 | 35 | 98 | 0,6591 |
| `relay` | 1,0 | degradado | 236 | 115 | 58 | 173 | 0,4769 |
| `relay` | 2,0 | limpio | 290 | 57 | 42 | 99 | 0,6476 |
| `relay` | 2,0 | degradado | 246 | 109 | 59 | 168 | 0,4761 |
| `relay` | 3,0 | limpio | 290 | 56 | 41 | 97 | 0,6418 |
| `relay` | 3,0 | degradado | 246 | 107 | 57 | 164 | 0,4796 |
| `relay+settle` | 3,0 + 0,5 | limpio | 278 | 60 | 33 | 93 | 0,6455 |
| `relay+settle` | 3,0 + 0,5 | degradado | 238 | 113 | 56 | 169 | 0,4769 |

Precisión de la evidencia que añade cada regla en g1 limpio:

| evidencia | n | la verdad dice el equipo nuevo al final |
|---|---:|---:|
| tramo vetado ≥ 0,2 s | 25 | 76,0% |
| tramo vetado ≥ 0,4 s | 10 | 100,0% |
| tramo vetado ≥ 0,6 s | 7 | 100,0% |
| tramo vetado ≥ 0,8 s | 7 | 100,0% |
| tramo vetado ≥ 1,0 s | 5 | 100,0% |
| toque confirmado del rival a ≤ 0,5 s | 102 | 70,6% |
| toque confirmado del rival a ≤ 1,0 s | 168 | 63,1% |
| toque confirmado del rival a ≤ 2,0 s | 222 | 62,6% |
| toque confirmado del rival a ≤ 3,0 s | 233 | 62,7% |

Constantes que fija la regla declarada: `persist` 1,0 s, `settle` 0,5 s, `relay` 3,0 s.

**Lo que dice (g1, donde se fijaron las constantes).**

- **El veto sostenido es preciso pero raro.** Los tramos vetados de ≥ 0,4 s son un cambio en la
  verdad el 100% de las veces (10 de 10), pero los de ≥ 0,2 s solo el 76%. Con el balón ruidoso,
  aceptar duelos cuesta: por debajo de 0,8 s los sobrantes del degradado suben de 48 a 57–91 (a 0,8
  y 1,0 s, a 51 y 50).
  La regla elige 1,0 s: 2 perdidos menos en limpio (84 → 82), los mismos errores en el degradado.
- **`settle` cambia errores de sitio, no el `spellF1`.** Quitar idas y vueltas < 0,5 s baja los
  sobrantes (17 → 11, 48 → 47) y sube los perdidos (84 → 88): las posesiones de < 0,5 s que quita son
  verdaderas casi tantas veces como falsas. El `spellF1` contra los eventos no se mueve (0,6812 y
  0,4743, iguales a la referencia): a IoU 0,5 una posesión de medio segundo casi nunca empareja.
- **`relay` recupera perdidos con un toque confirmado del 63–71% de precisión** (frente al 39% del
  toque rápido solo, sección 4.4) y es la que más baja los errores: 101 → 97 en limpio, 183 → 164 en
  el degradado con 3 s. Pero **añade cambios** (236 → 290 en g1 limpio, +23%) y **baja el `spellF1`
  limpio** (0,6812 → 0,6418), mientras sube el degradado (0,4743 → 0,4796): los cambios que recupera
  parten posesiones largas que la cadena ya emparejaba.
- **Ninguna regla sube el `spellF1` en limpio y en degradado a la vez en g1**: `persist` sube el
  limpio (0,6958) y baja el degradado (0,4733); `relay` y `relay+settle`, al revés; `settle` empata
  en los dos. Es la tensión de la sección 4.3: un balón limpio pide más cambios y uno ruidoso pide
  menos. **Predicción declarada antes de medir: el carril es probablemente negativo**, porque la
  compuerta M (abajo) exige las dos cosas en g2.

## 6. Pre-registro

### 6.1 Variantes (cuatro, ni una más)

Todas son la cadena entregada (control, regla del duelo, reanudaciones forzadas con la cancelación
de la decisión 35 por los controles que la variante acepta, el `D` entregado) con **un** cambio en
*si* hay cambio. La fecha de los cambios que conservan es la de la cadena.

| | nombre | regla | constante (g1, sección 5) | categoría que ataca |
|---|---|---|---|---|
| V1 | `persist` | un tramo de ≥ `PERSIST_S` frames seguidos de control de un equipo (`engine.control`, con o sin disputa) se acepta entero: un duelo que el rival sigue ganando tanto tiempo está ganado; el cambio se fecha al inicio del tramo | `PERSIST_S` = 1,0 s | veto del duelo (y sus reflejos) |
| V2 | `settle` | se borra todo A → B → A natural cuya B dure < `SETTLE_S`, sin parada dentro y sin que ninguno de los dos cambios lo fuerce una reanudación (B vuelve a A); de izquierda a derecha, un par borrado no crea otro | `SETTLE_S` = 0,5 s | ida y vuelta (sobrantes con el balón ruidoso) |
| V3 | `relay` | un toque (el equipo más cercano a ≤ 1,5 m, a cualquier velocidad, en el campo) con el otro equipo fuera de alcance se vuelve control si el **siguiente** toque de la mitad, a ≤ `RELAY_S` del final de este, es del mismo equipo: tocó dos veces sin que nadie más tocara entre medias; se acepta en su primer frame sin disputa | `RELAY_S` = 3,0 s | toque rápido (y sus reflejos) |
| V4 | `relay+settle` | V3 y luego V2, con sus constantes | 3,0 s + 0,5 s | los dos lados a la vez |
| ref | `engine` | ninguna: la cadena entregada, byte a byte (`72c98ed4bb4a…`, fijado por un test) | — | — |

Con constantes neutras (`persist` infinito, `settle` y `relay` 0) cada variante es la referencia
frame a frame (test). Ninguna mueve un frame `D`; `settle` solo quita cambios.

**Conocimiento previo, declarado.** Los números de g1 de la sección 5, y con ellos la predicción
de que ninguna pasa M. Además, sin medirlo: `relay` añade un 23% de cambios en g1 y la cadena ya
está en 3,62 posesiones/min en BAR-ATH, con la banda en 3,9; si en BAR-ATH añade lo mismo, se sale.
`persist` a 1,0 s afectará a muy pocos tramos en BAR-ATH (la anatomía cuenta 2 vetos de ≥ 1 s en el
partido).

### 6.2 Mediciones, en este orden (`python tools/change_whether.py --measure`)

1. **Metrica g2 (reservado), limpio y degradado** (σ = 0,85 m, semilla 2, nuestro balón visto): por
   variante, cambios de la cadena, emparejados, perdidos en juego, sobrantes y su suma (instrumento
   corregido), la mediana de |retraso| de los emparejados en juego y el `spellF1` oficial contra la
   verdad de eventos (`H`/`A`/`D` de E1–E5, graduado donde no es `X`). g1, informativo.
2. **DFL** (secundario): `spellF1` oficial de cada variante contra la verdad por frame de los 7
   partidos (la cadena con las reanudaciones de los eventos y el `D` entregado, como
   `change_dating.dfl_inputs`), limpio y con nuestro balón visto (`external.keep_mask`); victorias,
   empates y derrotas frente a `engine` sobre 7. **Se reporta, no es compuerta** (decisión 37: DFL
   cuenta 4,58 posesiones/min y no puede vetar sola un cambio de número). Una variante que pierda
   ≥ 6 de 7 con los dos balones necesita una explicación escrita en la sección 8.
3. **BAR-ATH sin GT**: informe por bloques (posesiones/min del partido, mín–máx por bloque y la
   razón de cada bloque frente a la referencia), la posesión más larga (partido y bloque máximo),
   `%D` máximo por bloque, acuerdo con el Smart Tagging (partido y bloques 7/9/11/18), frames
   movidos y cambios.
4. **Slice público**, pareado con `compare_submissions.compare_codes` frente a `engine`: `spellF1`,
   `macroF1`, Δ, `wins` a IoU 0,5, jackknife.
5. **Banco de trasplante**: media de los donantes, media con < 50% de balón, peor donante.

### 6.3 Compuertas (todas obligatorias, frente a `engine`)

| | compuerta |
|---|---|
| M | **Metrica g2 reservado, limpio Y degradado:** `spellF1` contra la verdad de eventos **estrictamente mayor** y perdidos + sobrantes (instrumento corregido) **estrictamente menos**, en los dos balones. Un empate falla. |
| B | **BAR-ATH sin GT:** posesiones/min del partido en 3,4 ± 0,5 (2,9 .. 3,9); ningún bloque con sus posesiones/min a la mitad o al doble de las de la referencia (razón estrictamente dentro de (0,5; 2)); acuerdo con el Smart Tagging del partido no más de 1,0 punto por debajo; ningún bloque con > 70% de `D`. |
| P | **Slice público:** Δ pareado ≥ 0 y `wins_a` ≤ `wins_b`. |
| C | **Banco:** media de donantes y media con poco balón, ambas no más bajas. |

DFL (6.2.2) se reporta junto a las compuertas sin serlo.

### 6.4 Regla de selección

**Orden previo, escrito antes de medir: V1 `persist` > V2 `settle` > V3 `relay` > V4
`relay+settle`.** V1 toca solo la regla del duelo, la que más ganó en la historia de la cadena, en
su caso más claro (un duelo largo) y con una constante física; V2 no añade ningún cambio, solo
quita, así que no puede inflar la escala; V3 añade evidencia nueva (el toque a cualquier velocidad)
que es ruidosa en el toque, justo lo que la ronda 5 encontró frágil; V4 son dos reglas y dos
constantes. Se elige **la primera de ese orden que pase las cuatro compuertas**; las diferencias de
`spellF1` entre variantes que pasan no reordenan nada. Si ninguna pasa, el resultado es **negativo
y se mantiene la cadena entregada**, con qué compuerta falla y por cuánto.

Todo sale de `python tools/change_whether.py --measure` y se pega sin editar en la sección 7, que se
añade en el commit 3 sin tocar lo anterior.
