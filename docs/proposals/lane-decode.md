# Carril decode — mejor decodificación y bordes de posesión sobre la regla de control

Estado: **pre-registro** (escrito y commiteado antes de medir ninguna variante contra el ground
truth: ni `spellF1`, ni el banco, ni el pareado). Las secciones de medición, recomendación y
limitaciones se añaden después, en un commit aparte, sin tocar las secciones 1–6.

Código: `tools/decoder.py`; pruebas: `tests/test_decoder.py`. Este documento no cambia el motor ni
`docs/DECISIONS.md`: el coordinador integra.

## 1. Qué se propone

La cadena entregada (`tools/engine.py`, decisiones 29–32) decide **qué** frames son evidencia
(control: balón visto dentro del campo, jugador más cercano a ≤ 1,5 m, el rival no igual de cerca,
balón a ≤ 5 m/s) y luego **decodifica** con la regla más simple posible: el primer control rival
cambia la posesión y el cambio se fecha en ese primer control. Este carril deja intacta la
evidencia (mismo `control`, mismas reanudaciones forzadas, misma máscara `D` variante `out`) y
cambia solo la decodificación, en dos frentes:

- **Fecha del cambio** (idea a del brief). `spellF1` promedia IoU 0,3..0,7; a 0,6 y 0,7 un borde
  tardío de 1–2 s tumba una posesión corta.
- **Cambios espurios** (ideas b, c, d). En el slice el motor predice 24 posesiones contra 17
  verdaderas; balones disputados, desvíos y toques sin control abren posesiones que no existen.

## 2. Exploración ya hecha (declarada)

Todo lo de esta sección se miró **antes** de escribir las variantes. Solo (a) toca el ground
truth, y solo para latencias de transición, como permite el brief; ningún `spellF1` de ninguna
variante se ha calculado.

**(a) Latencia de transición del motor en el slice público** (scorer oficial,
`evaluate(...)["transitions"]` y `match_transitions`): de 20 transiciones verdaderas, el motor
empareja **2 a ±12 frames y 4 a ±25**. Los errores tienen los dos signos (−75 .. +56 frames entre
los emparejados a ±75), así que no hay un sesgo único que desplazar. De las 12 transiciones `H↔A`,
10 tienen un cambio del motor con el mismo destino a ≤ 6 s; para esas 10 se comparó dónde habría
fechado el cambio cada regla (frames respecto a la transición verdadera):

| regla de fecha | mediana de \|error\| | media de \|error\| | a ≤ 25 frames |
|---|---:|---:|---:|
| primer control del nuevo equipo (motor) | 38 | 48,2 | 3 |
| último control del equipo anterior | 84 | 85,3 | 3 |
| punto medio entre los dos (sin tope) | 27 | 54,4 | 5 |
| primer toque del nuevo equipo (≤ 1,5 / 2 / 3 m, cualquier velocidad) | 36 | 50,0–50,5 | 3–4 |

El intervalo entre el último control del equipo anterior y el primero del nuevo es en esas 10:
1, 2, 9, 41, 42, 48, 99, 124, 140 y 261 frames. El punto medio gana cuando el intervalo es corto
(un pase) y pierde cuando es largo (balón perdido): de ahí el tope de la variante V1.

**(b) Estructura del motor en el partido completo, sin ground truth:**

- 342 cambios de estado `H↔A`, 340 naturales y 2 forzados por una reanudación.
- Intervalo último control anterior → primer control nuevo: percentiles 10/25/50/75/90 =
  1 / 18 / 55 / 165 / 336 frames (media 175,5).
- La "recepción" (retroceder desde el primer control mientras el nuevo equipo sigue a ≤ 1,5 m y
  más cerca, a cualquier velocidad) mueve el borde 0 frames en la mediana y 7 en el p90
  (34,7% de los cambios se mueven, 2,3 frames de media): casi un no-op, **descartada** como
  variante.
- El 5,9% de los 27.504 frames de control son disputados (el rival también a ≤ 1,5 m). **63 de los
  340 cambios naturales empiezan en un control disputado.** La racha de control rival que abre un
  cambio dura 3 / 6 / 13 / 24 / 48 frames (p10..p90); 15 duran un solo frame.
- 386 posesiones (con `D`), mediana 8,2 s; 34 duran < 1 s, 72 < 2 s. 276 están "emparedadas"
  (el mismo equipo antes y después, sin `D` entre medias): 22 duran < 1 s y 54 < 2 s.

**(c) Literatura** (nota del coordinador; hipótesis, no órdenes): zona de posesión de 0,5–1 m y
"duelo" (rivales dentro de 1 m) que anula la posesión (Vidal-Codina et al. 2022); la posesión de
equipo empieza en el primer toque tras el de un rival (Link & Hoernig 2017); decodificación de
Viterbi con restricciones (PathCRF 2026). Nuestro radio de 1,5 m es holgado según esa literatura,
pero aquí **no se toca**: cambiarlo es cambiar la evidencia, y el barrido de la decisión 29 ya
mostró que 17 posesiones no lo ordenan.

## 3. Reglas comunes

- Todas las variantes son la cadena entregada con otra decodificación: mismos `engine.control`
  (`radius_m = 1,5`, `speed_mps = 5`), mismas reanudaciones forzadas
  (`engine.restart_controls`, decidido con el control sin modificar) y misma máscara `D` `out`
  escrita al final. Ninguna variante escribe ni borra un `D`.
- Todo ocurre dentro de cada medio tiempo (`engine.halves()`); antes del primer control o
  reanudación forzada de un medio tiempo, `X`, como el motor.
- Un frame forzado por una reanudación nunca se reescribe, y ningún borde se mueve a través de él.
- Deterministas, numpy y pandas solamente, sin semilla. Ninguna constante se barre.

## 4. Variantes (cinco, ni una más)

| | nombre | idea | qué cambia | constantes nuevas |
|---|---|---|---|---|
| V1 | `mid` | a | fecha de cada cambio natural | tope 2 s |
| V2 | `uncontested` | b | qué control puede abrir un cambio | ninguna (reusa 1,5 m) |
| V3 | `touch` | d | deshace posesiones rivales emparedadas cortas | 2 s |
| V4 | `viterbi` | c | decodificador probabilístico con coste de cambio | 4, de física y priors |
| V5 | `mid+uncontested+touch` | a+b+d | V2, luego V3, luego V1 | las de sus partes |

**V1 `mid` — fecha en el punto medio del traspaso.** Cada cambio natural (no forzado) del equipo
`o` al `n`, que el motor fecha en el primer control `c` de `n`, se fecha en
`c − ⌊min(c − l, 50) / 2⌋`, donde `l` es el último frame de control de `o` antes de `c` en el mismo
medio tiempo (o el frame forzado que dio el balón a `o`, si no hubo control de `o` después). Los
frames movidos pasan a `n`.
*Por qué:* el traspaso real ocurre en algún punto de `(l, c]` (el balón viaja o está disputado);
el motor elige siempre el extremo más tardío, así que su error es tardío por la mitad del
intervalo en promedio, y el punto medio minimiza el peor error si no se sabe más. El tope: un pase
de 30–40 m a 15–20 m/s vuela ≤ 2 s (50 frames); con un intervalo más largo el último control de
`o` ya no marca el inicio del traspaso (balón perdido, hueco del tracker) y el desplazamiento se
limita a 25 frames. Es la regla que la exploración 2(a) señaló; queda declarado.

**V2 `uncontested` — un cambio necesita un control sin disputa.** Un frame de control del rival
solo puede abrir un cambio si el jugador más cercano del equipo en posesión está a **más** de
`radius_m` (1,5 m) del balón. Un control disputado no cambia la posesión, ni la mantiene: para el
decodificador es un frame sin evidencia de cambio. El estado inicial de un medio tiempo y la regla
de las reanudaciones (decisión 32) siguen usando el control sin modificar.
*Por qué:* `CHALLENGE.md` — "en fases de balón disputado o suelto, la posesión se queda con el
último equipo que la tuvo"; si los dos equipos alcanzan el balón, es un duelo, no un control. Es el
"duelo anula la posesión" de Vidal-Codina et al. con el radio que ya usa el motor, no uno nuevo.

**V3 `touch` — un toque no es una posesión.** Tras decodificar, toda posesión del equipo `n` que
dure menos de **50 frames (2 s)** y esté emparedada entre posesiones del otro equipo `o` (contiguas,
en el mismo medio tiempo, sin ningún `D` entre ellas) se reescribe como `o`, salvo que empiece en un
frame forzado o que la posesión siguiente de `o` empiece en uno. Una sola pasada de izquierda a
derecha sobre las posesiones originales; lo fusionado no se reconsidera.
*Por qué:* `CHALLENGE.md` excluye "un simple toque sin control" y "el desvío de un pase que no lo
intercepta", y propone como señal de control "un jugador conserva el balón unos segundos". Una
posesión rival de menos de 2 s que termina con el equipo anterior controlando de nuevo no cumple
ninguna de las dos señales. Es una escala de tiempo: el banco no la juzga, el informe por bloques sí
(decisión 26).

**V4 `viterbi` — control blando y coste de cambio.** Dos estados (`H`, `A`) por medio tiempo. Para
cada equipo `k`, control blando por frame
`s_k = σ((1,5 − d_k) / 0,25) · σ((5 − v) / 1,0)` si el balón está visto dentro del campo y con
velocidad conocida, y `0` si no (falla cerrado, como el motor). Emisión
`log P(obs | H) − log P(obs | A) = β (s_H − s_A)`; coste de cambio por frame `C = ln((1 − p) / p)`.
Viterbi exacto, empezando en el primer control (o frame forzado) del medio tiempo con el estado de
ese control; un frame forzado fija su estado. En un empate entre cambiar antes o después, el cambio
se fecha lo **más tarde** posible (la convención del motor: el cambio empieza con la evidencia del
nuevo equipo), para que V4 mida el decodificador y no otra regla de fecha.
*Constantes, ninguna libre:* 1,5 m y 5 m/s son los umbrales del motor; 0,25 m es el ruido de
posición del tracking y 1 m/s el de velocidad que ese ruido produce a 25 fps (0,04 m por frame);
`β = ln(0,911 / 0,089) = 2,33`, la razón de momios de que el jugador más cercano con el balón lento
sea del equipo en posesión (decisión 29, 91,1%); `p = 3,4 / (60 · 25)`, el prior físico de 3,4
cambios de posesión por minuto (decisión 26), que da `C = 6,09`: hacen falta ~3 frames de control
pleno para cambiar. El debate anterior midió un Viterbi de 2 estados sobre la emisión `argmin` en
0,4138; esta variante usa la emisión del control, que es lo que el brief pide comprobar.

**V5 `mid+uncontested+touch`.** Decodifica con V2, aplica V3 y fecha con V1. Son tres mecanismos
ortogonales (qué evidencia abre un cambio, qué cambios sobreviven, dónde se fechan); V5 mide si se
suman.

## 5. Mediciones (las mismas para todas, frente a la cadena entregada)

1. **Slice público**, scorer oficial (`possession_metrics.evaluate`) y pareado
   (`compare_submissions.compare_codes`): `spellF1`, `macroF1`, Δ pareado, `wins_a` / `wins_b` /
   `n_discordant` a IoU 0,5, rango del jackknife (dejar fuera una posesión verdadera) y si contiene
   un signo distinto del Δ completo; TP / FP / FN a IoU 0,3, 0,5 y 0,7; posesiones predichas;
   transiciones emparejadas a ±25 frames y su media de |latencia|; acierto de equipo en vivos.
2. **Banco de trasplante** (`bench.bench` + `bench.summary`): sin trasplante, media de donantes,
   media de donantes con < 50% de balón, peor donante.
3. **Informe por bloques** (`blocks.measure`, mismo cálculo que `tools/blocks.py`): posesiones/min
   del partido, mínimo y máximo por bloque, bloques sin posesión, acuerdo con el Smart Tagging en el
   partido y en los bloques de menos balón (7, 9, 11, 18), `%D` del partido (debe ser idéntico).

Todo sale de `python tools/decoder.py --report`, que imprime las tablas; aquí se pegan sin editar.

## 6. Regla de selección (pre-registrada)

**Compuertas**, todas obligatorias, cada una frente a la cadena entregada:

- **G1 slice:** Δ pareado de `spellF1` ≥ 0; `wins_b ≥ wins_a` a IoU 0,5 (no pierde posesiones); y
  ningún pliegue del jackknife con signo contrario al Δ completo (estable al quitar una posesión).
- **G2 banco:** Δ de la media de donantes ≥ 0 y Δ de la media de donantes con poco balón ≥ −0,01.
- **G3 bloques:** posesiones/min del partido dentro de 3,4 ± 20% (2,72 .. 4,08); ningún bloque sin
  posesiones; ningún bloque con menos de la mitad de las posesiones/min que la cadena entregada en
  ese bloque; acuerdo con el Smart Tagging del partido no más de 1,0 punto por debajo.

**Elección entre las que pasan**, por orden de prior y nunca por el `spellF1` más alto (17
posesiones no ordenan métodos):

1. Si V5 pasa **y** al menos dos de V1, V2, V3 pasan por separado, se recomienda V5.
2. Si no, la primera que pase en este orden: **V2 > V1 > V3 > V4**. V2 no añade ninguna constante y
   es la definición del reto; V1 añade un tope físico; V3 añade una escala de tiempo; V4 tiene la
   mayor libertad de modelo.
3. Si ninguna pasa, la recomendación es **mantener el decodificador del motor** y el resultado se
   reporta como negativo.

Además de la regla, se reporta para cada variante qué compuerta falla y por cuánto: un negativo
con su motivo vale tanto como un positivo.
