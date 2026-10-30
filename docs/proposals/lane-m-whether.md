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
