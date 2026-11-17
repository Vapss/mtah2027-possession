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

---

*Lo que sigue se escribió después de medir. Las secciones 1–6 son las del commit `375153f` sin
cambios; el código medido es el del commit `09b7b55`.*

## 7. Cómo se reproducen los números

```bash
export MTAH_DATA_DIR=...                       # el bundle licenciado
python tools/decoder.py --report               # las tablas de la sección 8, tal cual
for v in engine uncontested touch mid mid+uncontested+touch; do
  python tools/decoder.py --variant "$v" --labels "runs/decode/$(echo "$v" | tr + _).csv"
done
python tools/compare_submissions.py runs/decode/engine.csv runs/decode/uncontested.csv --gt public
python tools/blocks.py runs/decode/engine.csv runs/decode/uncontested.csv runs/decode/touch.csv \
    runs/decode/mid.csv runs/decode/mid_uncontested_touch.csv
```

`runs/` está ignorado por Git. `engine` en `tools/decoder.py` reproduce byte a byte las etiquetas
de `python tools/engine.py --labels` (comprobado con `cmp`, y en `tests/test_decoder.py`), así que
cada Δ es contra la cadena entregada. Ninguna variante cambia un solo frame `D`. Dos corridas de
`--variant uncontested` dan el mismo SHA-256 (`d4848b22ecf49424…`).

## 8. Mediciones

Salida de `python tools/decoder.py --report`, pegada sin editar:

Slice público (17 posesiones). Δ, `wins` y jackknife frente a `engine`; TP/FP/FN por IoU.

| variante | spellF1 | macroF1 | Δ | wins engine–var | jackknife Δ | TP/FP/FN 0,3 | 0,5 | 0,7 | pred | trans ±25 | \|lat\| | equipo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `engine` | 0,4585 | 0,7066 | 0,0000 | 0–0 | 0,0000 .. 0,0000 | 13/11/4 | 10/14/7 | 5/19/12 | 24 | 4/20 | 12,5 | 83,5% |
| `mid` | 0,4780 | 0,7160 | 0,0195 | 0–2 | 0,0100 .. 0,0200 | 13/11/4 | 12/12/5 | 5/19/12 | 24 | 6/20 | 11,8 | 85,0% |
| `uncontested` | 0,5189 | 0,7114 | 0,0604 | 0–0 | 0,0489 .. 0,0633 | 13/7/4 | 10/10/7 | 5/15/12 | 20 | 4/20 | 12,5 | 84,3% |
| `touch` | 0,5600 | 0,7163 | 0,1015 | 0–0 | 0,0776 .. 0,1065 | 13/5/4 | 10/8/7 | 6/12/11 | 18 | 4/20 | 12,5 | 85,1% |
| `viterbi` | 0,4114 | 0,7041 | -0,0471 | 3–1 | -0,0735 .. -0,0065 | 9/9/8 | 8/10/9 | 4/14/13 | 18 | 3/20 | 3,7 | 83,0% |
| `mid+uncontested+touch` | 0,5829 | 0,7243 | 0,1243 | 0–2 | 0,1012 .. 0,1300 | 13/5/4 | 12/6/5 | 6/12/11 | 18 | 6/20 | 11,8 | 86,3% |

Banco de trasplante (19 donantes, 6 con < 50% de balón) e informe por bloques.

| variante | banco limpio | media | poco balón | peor | pos/min | bloque mín–máx | sin pos. | ST partido | ST bloques 7/9/11/18 | %D |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `engine` | 0,4585 | 0,3516 | 0,2782 | 0,2069 | 3,64 | 0,67–5,60 | 0 | 73,1% | 72,4% | 12,3% |
| `mid` | 0,4780 | 0,3672 | 0,2833 | 0,2069 | 3,61 | 0,67–5,40 | 0 | 72,8% | 72,3% | 12,3% |
| `uncontested` | 0,5189 | 0,3792 | 0,3021 | 0,2370 | 3,29 | 0,34–5,20 | 0 | 73,4% | 72,4% | 12,3% |
| `touch` | 0,5600 | 0,3847 | 0,3060 | 0,2462 | 2,91 | 0,67–4,40 | 0 | 73,3% | 72,5% | 12,3% |
| `viterbi` | 0,4114 | 0,3396 | 0,2355 | 0,1846 | 2,53 | 0,34–4,20 | 0 | 72,6% | 68,4% | 12,3% |
| `mid+uncontested+touch` | 0,5829 | 0,4008 | 0,3208 | 0,2615 | 2,79 | 0,34–4,40 | 0 | 73,4% | 71,8% | 12,3% |

Compuertas pre-registradas (sección 6).

| variante | G1 slice | G2 banco | G3 bloques |
|---|---|---|---|
| `mid` | pasa | pasa | pasa |
| `uncontested` | pasa | pasa | pasa |
| `touch` | pasa | pasa | pasa |
| `viterbi` | **falla** | **falla** | **falla** |
| `mid+uncontested+touch` | pasa | pasa | **falla** |

Elección por la regla: **`uncontested`**.

`compare_submissions.py` por la línea de comandos da los mismos Δ, `wins` y rangos de jackknife.
TP por IoU 0,3 / 0,4 / 0,5 / 0,6 / 0,7, cadena entregada frente a la variante, con las posesiones
predichas:

| variante | TP engine | TP variante | pred engine → variante |
|---|---|---|---:|
| `uncontested` | 13 / 12 / 10 / 7 / 5 | 13 / 12 / 10 / 8 / 5 | 24 → 20 |
| `touch` | 13 / 12 / 10 / 7 / 5 | 13 / 12 / 10 / 8 / 6 | 24 → 18 |
| `mid` | 13 / 12 / 10 / 7 / 5 | 13 / 12 / 12 / 7 / 5 | 24 → 24 |
| `mid+uncontested+touch` | 13 / 12 / 10 / 7 / 5 | 13 / 12 / 12 / 8 / 6 | 24 → 18 |

Informe por bloques (`tools/blocks.py`, extracto de la tabla de posesiones/min; el documento
completo se regenera con el comando de la sección 7). Solo los bloques que deciden G3:

| bloque | balón | `engine` | `uncontested` | `touch` | `mid` | `mid+uncontested+touch` |
|---|---:|---:|---:|---:|---:|---:|
| 1★ | 88,2% | 4,80 | 4,00 | 3,60 | 4,80 | 3,60 |
| 11 | 19,9% | 0,67 | 0,34 | 0,67 | 0,67 | 0,34 |
| 16 | 73,7% | 4,00 | 3,20 | 2,00 | 4,00 | **1,60** |
| 20 | 47,9% | 3,20 | 2,40 | 2,00 | 3,20 | 1,60 |
| **partido** | 59,3% | **3,64** | **3,29** | **2,91** | **3,61** | **2,79** |

En el bloque 16, V5 deja 8 posesiones de 30,3 s de media donde la cadena entregada tiene 20 de
14,8 s: menos de la mitad de su tasa, que es lo que G3 prohíbe. En el bloque 20 queda exactamente en
la mitad (1,60 frente a 3,20), y en el 11 `uncontested` pasa por una posesión (1 frente a 2 en un
bloque de 3 minutos: 0,34 frente al umbral 0,335).

## 9. Recomendación: **V2 `uncontested`**

Aplicando la sección 6 tal cual: V4 falla las tres compuertas; V5 pasa G1 y G2 y **falla G3**
(bloque 16), así que la regla 1 no se aplica; V1, V2 y V3 pasan las tres, y en el orden de prior
la primera es **V2**. Que V5 y V3 tengan números más altos en el slice y en el banco no cambia la
elección: es exactamente lo que el pre-registro existe para impedir.

Qué hace V2: un control del rival solo cambia la posesión si el jugador más cercano del equipo que
la tiene está a más de 1,5 m del balón; un duelo no la cambia. Frente a la cadena entregada:

| instrumento | cadena entregada | V2 `uncontested` | Δ |
|---|---:|---:|---:|
| `spellF1` público | 0,4585 | 0,5189 | +0,0604 (0 discordantes, jackknife +0,0489 .. +0,0633) |
| `macroF1` público | 0,7066 | 0,7114 | +0,0048 |
| banco, media de 19 donantes | 0,3516 | 0,3792 | +0,0276 |
| banco, 6 donantes con < 50% de balón | 0,2782 | 0,3021 | +0,0239 |
| banco, peor donante | 0,2069 | 0,2370 | +0,0301 |
| posesiones/min del partido | 3,64 | 3,29 | más cerca de la referencia de 3,4 |
| acuerdo con el Smart Tagging | 73,1% | 73,4% | +0,3 puntos |

**Lo que esto prueba y lo que no.** En el slice el Δ sale **entero de la precisión**: V2 predice 20
posesiones en lugar de 24 y empareja las mismas (más una a IoU 0,6); ninguna posesión verdadera
cambia de estado a IoU 0,5 (`wins` 0–0). Con 0 discordantes, el pareado no puede llamarlo una
victoria (hacen falta ≥ 6 en el mismo sentido, decisión 29); es dirección. Lo que lo sostiene más
allá de las 17 posesiones es que el signo no cambia al quitar ninguna (jackknife todo positivo),
que el banco mejora en la media de los 19 donantes, en los de poco balón y en el peor, y que en el
partido la tasa baja hacia la referencia física sin que el Smart Tagging, la única señal
independiente, empeore. No añade ninguna constante.

**Integración** (para el coordinador; este carril no toca `tools/engine.py`): en `engine.chain`,
decodificar con `decoder.decode(ctrl, halves(), forced, decoder.uncontested(ctrl, f.home_m,
f.away_m, params.radius_m))` en lugar de `decode(ctrl, halves(), params.dwell, forced)`. `control`,
`restart_controls` y la máscara `D` no cambian; con `switch=None` es el decodificador actual
(`dwell = 1`) exacto. Solo numpy, determinista.

### Las demás variantes

- **V1 `mid`** pasa todo con un efecto pequeño: +0,0195, **2–0** a IoU 0,5 (con V5, las únicas
  variantes que hacen ganar estado a alguna posesión), transiciones a ±25 frames 4 → 6 de 20, banco
  +0,0156 / +0,0051. Es la única variante que mueve la fecha de los cambios. La regla que usa salió
  de mirar las latencias del slice (declarado en 2a), así que ese 2–0 se lee con esa cautela.
- **V3 `touch`** pasa todo con el mayor Δ entre las que pasan (+0,1015, 0–0, banco +0,0331 /
  +0,0278), pero es una escala de tiempo y el informe por bloques lo enseña: la tasa del partido
  cae a 2,91 y los bloques 16 y 20 quedan exactamente en la mitad de la cadena entregada, en el
  borde de G3.
- **V4 `viterbi`** es negativo en todo: −0,0471 con 3–1 en contra, banco −0,0120 / −0,0427, y el
  acuerdo con el Smart Tagging en los bloques de poco balón cae a 68,4%. Queda en 0,4114, al lado
  del 0,4138 del debate anterior, aun con la emisión del control: el problema no era la emisión. El
  control blando acumula evidencia de jugadores a ~2 m que el control duro descarta, y el coste de
  cambio retrasa o funde cambios reales (9 TP a IoU 0,3 frente a 13).
- **V5** suma los tres mecanismos y da el mejor número en todos los instrumentos con ground truth
  (+0,1243, 2–0, banco 0,4008 / 0,3208), y falla la compuerta estructural en el bloque 16.

### Diagnóstico posterior (no pre-registrado, no cambia la elección)

En el bloque 16 de V5 el acuerdo con el Smart Tagging **sube** de 72,3% a 79,4% (cobertura 93,7%),
y en el partido queda en 73,4%. La señal independiente no dice que esas fusiones sean errores; G3
es una guarda gruesa (la mitad de la tasa) y la fijó el pre-registro. Si el coordinador quiere V5 o
V3, es una variante nueva con otra compuerta y necesita su propio pre-registro; elegirla ahora sería
el ajuste a posteriori que este documento prohíbe. La combinación sin escala de tiempo (V1 + V2) no
se midió.

## 10. Limitaciones

- **17 posesiones, 0 discordantes.** Todo el Δ de V2 en el slice son 4 posesiones espurias menos.
  El banco no añade ground truth: trasplanta huecos sobre las mismas 17.
- **Bloque 11.** Con V2, una sola posesión cubre el 91,4% del bloque (cadena entregada: 47,5%) y
  `%H` pasa de 52,5% a 8,6%; el acuerdo con el Smart Tagging no cambia (29,0%, sobre el 47,3% de
  frames que cubre). Es un bloque de 3 minutos con 19,9% de balón: un duelo que ya no cambia la
  posesión deja el estado arrastrado por un hueco largo. Pasa G3 por una posesión; conviene mirarlo
  antes de integrar.
- **El radio del duelo es el del motor (1,5 m)**, no el de 0,5–1 m de la literatura. Se reusó para
  no añadir una constante; con un radio menor, V2 filtraría menos duelos.
- **El banco no ve escalas de tiempo** (sus propios límites, `tools/bench.py`): para V3 y V5 un
  banco favorable no dice nada de los bloques con otra estructura de posesión; por eso decide G3.
- **La fecha de los cambios sigue mal.** Ninguna variante resuelve la latencia: la mejor (V1)
  empareja 6 de 20 transiciones a ±1 s. Los errores grandes (±110 frames) son cambios equivocados,
  no mal fechados, y una regla de fecha no los arregla.
- **Exploración declarada.** La regla de V1 y el descarte de la "recepción" salieron de mirar
  latencias del slice antes del pre-registro (sección 2a).

---

## 11. Seguimiento: V6 `mid+uncontested` frente a V2 (pre-registro)

*Escrito y commiteado antes de medir V6 en ningún instrumento. Las secciones 1–10 no cambian.*

**Contexto.** El coordinador reprodujo la sección 8 y acepta V2 `uncontested` como candidata de
integración. V3 y V5 quedan aplazadas al corpus de validación externo (su riesgo es una escala de
tiempo que el banco no juzga). Lo único medible ahora sin escala de tiempo es la combinación que la
sección 9 dejó sin medir: V1 + V2.

**V6 `mid+uncontested`.** Decodifica con V2 (un cambio necesita un control sin disputa) y fecha cada
cambio natural con V1 (punto medio del traspaso, con el tope de 2 s). Es V5 sin `touch`: mismas
funciones, mismas constantes (1,5 m, 50 frames), ninguna nueva. El último control del equipo
anterior que usa V1 sale del control sin modificar, como en V5.

**Cautela declarada.** La regla de V1 salió de mirar las latencias del slice público antes del
primer pre-registro (sección 2a): el punto medio fue la regla que mejor fechaba esas 10
transiciones. Cualquier ganancia de V6 sobre V2 en el slice se lee con esa cautela; por eso la
regla de abajo pide además que el banco con poco balón no baje.

**Compuertas**, las de la sección 6, pero medidas **frente a V2** (no frente al motor):

- **G1 slice:** Δ pareado de `spellF1` (V6 − V2) ≥ 0; `wins` de V6 ≥ `wins` de V2 a IoU 0,5; y
  ningún pliegue del jackknife con signo contrario al Δ completo.
- **G2 banco:** Δ de la media de donantes ≥ 0 y Δ de la media de donantes con poco balón ≥ −0,01.
- **G3 bloques:** posesiones/min del partido en 2,72 .. 4,08; ningún bloque sin posesiones; ningún
  bloque con menos de la mitad de las posesiones/min de V2 en ese bloque; acuerdo con el Smart
  Tagging del partido no más de 1,0 punto por debajo del de V2.

**Regla.** V6 sustituye a V2 solo si pasa G1, G2 y G3 frente a V2 **y** el Δ de la media del banco
con poco balón es ≥ 0 (más estricto que G2). Si no, se queda V2. Se reporta qué falla y por cuánto.

**Diagnóstico aparte (no es una variante ni una regla).** La sección 10 señaló el bloque 11: con V2
una sola posesión cubre el 91,4% del bloque. Se reporta, solo con agregados, cuánto tiempo falta el
balón dentro de esa posesión y si los duelos que V2 ignora ahí (los cambios de la cadena entregada
que V2 no hace) ocurren dentro o al lado de huecos largos de balón. No sale ninguna regla de esto.

### 11.1 Resultado de V6 (escrito después de medir)

*El pre-registro de arriba es el del commit `1974f54`, sin cambios. Reproducible con
`python tools/decoder.py --report` (la parte "V6 frente a V2", pegada sin editar; la parte de la
sección 6 sale idéntica a la de la sección 8).*

Slice público (17 posesiones). Δ, `wins` y jackknife frente a `uncontested`; TP/FP/FN por IoU.

| variante | spellF1 | macroF1 | Δ | wins uncontested–var | jackknife Δ | TP/FP/FN 0,3 | 0,5 | 0,7 | pred | trans ±25 | \|lat\| | equipo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `uncontested` | 0,5189 | 0,7114 | 0,0000 | 0–0 | 0,0000 .. 0,0000 | 13/7/4 | 10/10/7 | 5/15/12 | 20 | 4/20 | 12,5 | 84,3% |
| `mid+uncontested` | 0,5405 | 0,7200 | 0,0216 | 0–2 | 0,0111 .. 0,0222 | 13/7/4 | 12/8/5 | 5/15/12 | 20 | 6/20 | 11,8 | 85,6% |

Banco de trasplante (19 donantes, 6 con < 50% de balón) e informe por bloques.

| variante | banco limpio | media | poco balón | peor | pos/min | bloque mín–máx | sin pos. | ST partido | ST bloques 7/9/11/18 | %D |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `uncontested` | 0,5189 | 0,3792 | 0,3021 | 0,2370 | 3,29 | 0,34–5,20 | 0 | 73,4% | 72,4% | 12,3% |
| `mid+uncontested` | 0,5405 | 0,3944 | 0,3072 | 0,2370 | 3,25 | 0,34–5,20 | 0 | 73,1% | 72,1% | 12,3% |

Compuertas de la sección 6, frente a `uncontested` (sección 11).

| variante | G1 slice | G2 banco | G3 bloques |
|---|---|---|---|
| `mid+uncontested` | pasa | pasa | pasa |

Δ banco con poco balón (V6 − V2): 0,0051.
Decisión por la regla: **`mid+uncontested`**.

`compare_submissions.py runs/decode/uncontested.csv runs/decode/mid_uncontested.csv --gt public`
da lo mismo: Δ +0,0216, `wins` 0–2, jackknife +0,0111 .. +0,0222; TP por IoU 0,3 / 0,4 / 0,5 /
0,6 / 0,7 de 13 / 12 / 10 / 8 / 5 (V2) a 13 / 12 / 12 / 8 / 5 (V6). Dos corridas de
`--variant mid+uncontested` dan el mismo SHA-256 (`405763bc1f064a10…`).

**Decisión por la regla: V6 `mid+uncontested` sustituye a V2.** Pasa G1 (Δ +0,0216, 2–0, ningún
pliegue con signo contrario), G2 (banco +0,0152 de media, +0,0051 con poco balón, peor donante
igual) y G3 (3,25 posesiones/min, ningún bloque vacío ni a menos de la mitad de V2, acuerdo con el
Smart Tagging 73,1% frente a 73,4%, dentro del punto de margen), y el banco con poco balón no baja.

**Con la cautela declarada.** Todo el Δ en el slice son dos posesiones que pasan a emparejarse a
IoU 0,5 (10 → 12) y nada más se mueve: son las mismas 2–0 que V1 ganaba sobre el motor (sección
8), y la regla de V1 salió de mirar las latencias de esas transiciones (sección 2a). Dos
discordantes no son evidencia (hacen falta ≥ 6). Lo que el slice no pudo elegir lo sostienen el
banco, que mejora en media y con poco balón sin empeorar el peor donante, y que V1 no añade ninguna
escala de tiempo: mueve bordes ≤ 1 s, no crea ni borra posesiones (20 predichas en las dos). El
precio es 0,3 puntos de acuerdo con el Smart Tagging.

**Integración** (para el coordinador): la de la sección 9 más la fecha,
`redate_mid(decode(ctrl, halves(), forced, uncontested(...)), ctrl, halves(), forced)`, que es
`decoder._mid_uncontested`. Solo numpy, determinista, sin constantes nuevas.

### 11.2 Diagnóstico del bloque 11 (agregados, sin regla)

Salida de `python tools/decoder.py --block 11`, pegada sin editar:

Bloque 11, posesión más larga de `uncontested` que lo toca: equipo `A`, 163,3 s, 91,4% del bloque.

| balón en la posesión | sin balón | huecos | hueco más largo | huecos > 20 s | parte del déficit en ellos | controles rivales sin disputa |
|---:|---:|---:|---:|---:|---:|---:|
| 17,5% | 134,8 s | 4 | 69,5 s | 2 | 79,1% | 0 |

Duelos que la variante ignora dentro de esa posesión (controles rivales disputados, unidos si distan ≤ 1 s), con la isla de balón visible que los contiene y los huecos a cada lado:

| duelo | frames | disputados | isla visible | hueco antes | hueco después |
|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 5 | 13,8 s | 69,5 s | 10,9 s |

La cadena entregada etiqueta 48,0% de esa posesión con el otro equipo (número de cambios: 1). Smart Tagging: cubre 42,3% de la posesión y, de eso, vota `A` en 13,2%.

| tramo de la posesión | cobertura del Smart Tagging | de lo cubierto, vota `A` |
|---|---:|---:|
| las dos cadenas dicen `A` | 81,4% | 13,2% |
| solo la variante dice `A` | 0,0% | — |

**Lectura.** La posesión de 163 s que V2 da a `A` tiene balón en el 17,5% de sus frames; el 79,1%
de lo que falta está en dos huecos de más de 20 s, el mayor de 69,5 s. Dentro no hay **ningún**
control rival sin disputa, y V2 ignora **un solo duelo**: 5 frames (0,2 s) de control disputado
de `H`, en una isla visible de 13,8 s entre un hueco de 69,5 s antes y uno de 10,9 s después. La
cadena entregada cambia la posesión en ese duelo y etiqueta `H` el 48,0% de la posesión; V2 la
deja en `A`. Así que la pregunta del coordinador tiene respuesta: sí, el duelo que V2 ignora está
pegado a huecos largos, y de esos 5 frames depende la etiqueta de ~78 s.

**Ni el balón ni el Smart Tagging deciden ese tramo.** El Smart Tagging no cubre **ningún** frame
del tramo donde solo V2 dice `A` (el posterior al duelo), así que no arbitra el duelo. Donde las dos
cadenas dicen `A`, cubre el 81,4% y vota `A` solo en el 13,2%: contradice a las dos por igual, que
es el 29,0% de acuerdo del bloque en ambas (sección 10). Es un problema de hueco de balón, no de
decodificación: con la evidencia de este carril, la cadena entregada y V2 apuestan los mismos ~78 s
a una observación de 0,2 s, en sentidos contrarios. No sale ninguna regla de aquí; si algo puede
decidirlo es una evidencia nueva dentro de los huecos (carril de imputación o el corpus externo).
