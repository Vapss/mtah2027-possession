# Carril dating — CUÁNDO cambia la posesión, separado de SI cambia

Estado: **pre-registro** (escrito y commiteado antes de medir ninguna variante contra el ground
truth: ni `spellF1`, ni el banco, ni el pareado, ni el test de signos). Las secciones de medición,
recomendación y limitaciones se añaden después, en un commit aparte, sin tocar las secciones 1–6.

Código: `tools/dating.py`; pruebas: `tests/test_dating.py`. Este documento no cambia el motor ni
`docs/DECISIONS.md`: el coordinador integra.

## 1. Qué se propone

La cadena entregada (`tools/engine.py` `run()`, decisiones 29–36: control + regla del duelo +
paradas etiquetadas unidas a las de los jugadores W1 + reanudaciones) decide **si** la posesión
cambia con la regla del duelo: un control del rival solo la cambia si el equipo que la tiene no
tiene a nadie a ≤ 1,5 m del balón. Y **fecha** el cambio en ese mismo control sin disputa.

Un análisis por posesión del coordinador en el slice público encontró que las posesiones
emparejadas **empiezan tarde** de forma sistemática (+5,0, +7,0, +1,7, +1,1, +2,2, +1,4, +1,7, +0,6,
+3,9 s), mientras que la verdad (posesión del tracking corregido) cambia en el primer toque del
nuevo equipo. La hipótesis: mantener la decisión de la regla del duelo y mover solo la **fecha** de
cada cambio hacia atrás, dentro de su traspaso. Ninguna variante crea, borra ni reordena un cambio,
ni escribe un `D`.

**Cautela, declarada.** La hipótesis sale de mirar las latencias del slice público, así que una
ganancia en el slice está contaminada por diseño (el mismo problema que hundió V1/V6 del carril
decode, decisiones 34 y su adenda 2). Por eso la aceptación de la sección 6 es **más fuerte** que
la habitual: un test de signos por posesión con p ≤ 0,05, el banco sin bajar en media ni con poco
balón, y el informe por bloques. El corpus externo de DFL **no arbitra** la fecha: su verdad tiene
otra definición de cuándo cambia la posesión (decisión 34, adenda 2).

## 2. Exploración ya hecha (declarada)

Todo lo de esta sección se midió **sin ground truth** (el partido completo, sus propios datos) y
antes de escribir las variantes. Se reproduce con `python tools/dating.py --explore`; la tabla de
abajo es su salida, sin editar.

**Definición del traspaso.** Un cambio natural (no forzado) de la cadena entregada del equipo `o` al
`n` en el frame `c` tiene su traspaso en `(l, c]`, con `l` el último frame del tramo de `o` en que
`o` controló el balón (con o sin disputa), en que una reanudación se lo dio, o en que el balón
estaba muerto (`D` entregado), el que sea más tardío. Así una fecha nunca cruza una parada ni una
reanudación.

```
Exploración sin ground truth: los traspasos de la cadena entregada en el partido.

Cambios naturales: 301; forzados por una reanudación: 2.

| | valor |
|---|---:|
| hueco del traspaso (l, c), frames, p10/25/50/75/90 | 0 / 4 / 40 / 90 / 169 |
| frames dentro de traspasos | 19425 |
| de ellos, sin balón | 16,9% |
| balón visto, nadie a ≤ 1,5 m | 66,8% |
| balón visto, alguien a ≤ 1,5 m | 16,3% |

| variante | cambios movidos | adelanto medio | adelanto de los movidos p10/25/50/75/90 | adelanto máx. | frames reetiquetados |
|---|---:|---:|---:|---:|---:|
| `first` | 29 de 301 | 0,9 | 1 / 2 / 4 / 11 / 28 | 49 | 280 |
| `touch` | 167 de 301 | 25,6 | 1 / 4 / 21 / 54 / 122 | 470 | 7705 |

Anclas de `touch` que mueven un cambio: 167. Velocidad del balón en el ancla: desconocida 3,0%, ≤ 10 m/s 70,7%, > 10 m/s 26,3%, > 20 m/s 3,6%.
```

**Lo que dice, antes de medir nada contra la verdad:**

- **La hipótesis literal es casi un no-op.** Fechar en el primer control del nuevo equipo (con o
  sin disputa) tras el último control del anterior mueve 29 de 301 cambios, 0,9 frames de media,
  como mucho 49 frames (2 s), 280 frames en todo el partido. No puede producir correcciones de
  +5..+7 s: casi siempre el primer control del nuevo equipo **ya es** sin disputa.
- **El retraso vive en el hueco entre el último control del anterior y el primero del nuevo**:
  mediana 40 frames, p90 169 (6,8 s). En dos tercios de ese hueco el balón se ve y nadie está a
  ≤ 1,5 m: viaja.
- **Un ancla de "primer toque"** (el control del motor sin su prueba de velocidad: balón dentro del
  campo, el más cercano del nuevo equipo a ≤ 1,5 m y más cerca que el del anterior, a cualquier
  velocidad) mueve 167 de 301 cambios, mediana 21 frames entre los movidos, p90 122 (4,9 s).
- **El riesgo de ese ancla, declarado:** quitar la prueba de velocidad reintroduce el fallo que el
  motor evita, un balón en vuelo que pasa cerca de un jugador (el más cercano acierta el 39% por
  encima de 20 m/s, decisión 29). El 26,3% de las anclas va a > 10 m/s y el 3,6% a > 20 m/s. Aquí
  ese fallo solo puede adelantar la **fecha** de un cambio que la regla del duelo ya decidió, nunca
  crear uno, y por eso es aceptable probarlo.

Nota de procedimiento: un primer recuento hecho en un script aparte, sin la condición de la parada
en la definición del traspaso, daba 32 y 206 cambios movidos (hueco mediano 65 frames, 55,5% sin
balón: buena parte del hueco era tiempo de parada). Con esos números el coordinador aprobó las
variantes de abajo y pidió el diagnóstico de velocidad de la sección 5. La condición de la parada
forma parte de la definición desde el código del pre-registro; no se eligió mirando la verdad.

Exploración previa de otros carriles que toca la verdad (declarada, no hecha aquí): el carril
decode (sección 2a de `lane-decode.md`) comparó en 10 transiciones del slice el error de fecha del
primer control (motor D31), del último control anterior, del punto medio y del "primer toque" a
≤ 1,5 / 2 / 3 m: el primer toque daba mediana de |error| 36 frames frente a 38 del primer control.

## 3. Reglas comunes

- Todas las variantes son la cadena entregada (`bench.METHODS["engine"]`, `engine.chain` con
  `engine.DEFAULT` y `engine.delivered_dead`) con otra fecha: mismo `engine.control`, misma regla
  del duelo (`engine.uncontested`), mismas reanudaciones forzadas (`engine.restart_controls` sobre
  los controles aceptados), mismo `D` entregado escrito al final.
- Solo se mueven cambios **naturales**: un cambio forzado por una reanudación conserva su frame.
- Un cambio de `c` se mueve a su ancla `a ∈ (l, c]`; los frames `[a, c)` pasan al equipo nuevo. Nada
  fuera de un traspaso cambia; el número, el orden y los equipos de los cambios son los de la cadena
  entregada (lo fija un test).
- Todo ocurre dentro de cada medio tiempo. Deterministas, solo numpy y pandas, sin semilla.
  **Ninguna constante nueva**: el alcance es el 1,5 m del motor.

## 4. Variantes (tres, ni una más)

| | nombre | ancla del cambio | constantes |
|---|---|---|---|
| V-a | `first` | primer control del nuevo equipo en `(l, c]`, con o sin disputa | ninguna |
| V-b | `touch` | primer frame de `(l, c]` en que el nuevo equipo toca el balón, a cualquier velocidad | ninguna (1,5 m del motor) |
| V-c | `none` | ninguna: es la cadena entregada (control negativo) | — |

**V-a `first` — la hipótesis literal.** La regla del duelo decide el cambio; se fecha en el primer
control (`engine.control`) del nuevo equipo tras el último del anterior, aunque fuera disputado.
*Por qué:* es la carrera del nuevo equipo hacia el balón que la regla del duelo descarta como
evidencia de cambio pero que ya es el inicio del traspaso. La exploración dice que es casi un no-op;
se mide igualmente porque es la hipótesis pedida, y se espera un resultado nulo.

**V-b `touch` — el primer toque.** Igual, con el ancla en el primer frame de `(l, c]` en que el
balón está dentro del campo y el más cercano del nuevo equipo está a ≤ 1,5 m y estrictamente más
cerca que el del anterior, a cualquier velocidad (también desconocida). Es `engine.control` sin la
prueba de velocidad; todo control es un toque, así que el ancla nunca es posterior a `c`.
*Por qué:* `CHALLENGE.md` y la verdad del reto fechan el cambio cuando el nuevo equipo gana el
balón; el primer toque tras el último control del rival es la primera observación de eso (la
posesión de equipo empieza en el primer toque tras el de un rival, Link & Hoernig 2017). La prueba
de velocidad sirve para decidir **si** hay control; aquí no decide nada, solo fecha.

**V-c `none` — control negativo.** Sin redatar. Debe reproducir `bench.METHODS["engine"]` frame a
frame (lo comprueba un test con el bundle); si no lo hiciera, la medición no valdría.

## 5. Mediciones (las mismas para todas, frente a V-c)

1. **Slice público**, scorer oficial (`possession_metrics.evaluate`) y pareado
   (`compare_submissions.compare_codes`): `spellF1`, `macroF1`, Δ pareado, `wins_a` / `wins_b` a
   IoU 0,5 (emparejamiento oficial uno a uno), rango del jackknife y si contiene un signo contrario
   al Δ; TP por IoU 0,3..0,7; posesiones predichas; transiciones a ±25 frames y su |latencia|;
   desfase del inicio de la posesión predicha mejor emparejada (mediana y media de |·|, s).
2. **Test de signos por posesión** (`dating.iou_sign_test`): para cada una de las 17 posesiones
   verdaderas, la mejor IoU de cualquier posesión predicha del mismo equipo, antes (V-c) y después;
   mejoran, empeoran, empates exactos; p binomial exacto de dos colas sobre las no empatadas;
   cuántas pasan de IoU ≥ 0,5 a < 0,5.
3. **Banco de trasplante** (`bench.bench` + `bench.summary`): limpio, media de los 19 donantes,
   media de los 6 con < 50% de balón, peor donante.
4. **Informe por bloques** (`blocks.measure`, el cálculo de `tools/blocks.py`): posesiones/min del
   partido, mínimo y máximo por bloque, bloques sin posesión, bloques con menos de la mitad de la
   tasa de V-c, acuerdo con el Smart Tagging en el partido y en los bloques 7, 9, 11, 18, `%D` (debe
   ser idéntico).
5. **Diagnóstico de V-b, pedido por el coordinador (no es compuerta ni variante):** la parte de las
   anclas de `touch` con el balón a > 10 m/s y a > 20 m/s (sección 2), y el test de signos de la
   medición 2 para `touch<=10`: V-b moviendo **solo** los cambios cuya ancla tiene velocidad
   conocida ≤ 10 m/s (los demás conservan la fecha entregada). 10 m/s es la velocidad de un pase
   del comentario de `engine.Params`; 20 m/s, la fila de la decisión 29.

Todo sale de `python tools/dating.py --report`, que imprime las tablas; se pegan sin editar.

## 6. Regla de selección (pre-registrada)

**Compuertas**, todas obligatorias, cada una frente a V-c (la cadena entregada):

- **G1 slice:** Δ pareado de `spellF1` ≥ 0; en el test de signos por posesión, más mejoras que
  empeoramientos con p exacto de dos colas ≤ 0,05 (hacen falta al menos 6–0, 8–1 o 10–2); ninguna
  posesión perdida a IoU 0,5 en el emparejamiento oficial (`wins_a = 0`); y ningún pliegue del
  jackknife con signo contrario al Δ completo.
- **G2 banco:** media de donantes no más baja (Δ ≥ 0) **y** media de donantes con poco balón no más
  baja (Δ ≥ 0). Sin la tolerancia de −0,01 del carril decode.
- **G3 bloques:** posesiones/min del partido dentro de 3,4 ± 20% (2,72 .. 4,08); ningún bloque sin
  posesiones; ningún bloque con menos de la mitad de las posesiones/min de V-c en ese bloque;
  acuerdo con el Smart Tagging del partido no más de 1,0 punto por debajo del de V-c.

**Elección:** la primera variante que pase las tres, en este orden de prior: **V-a > V-b**. V-a es
la hipótesis literal y conserva la noción de control del motor; V-b reintroduce el balón en vuelo
como evidencia de fecha. Nunca por el número más alto. Si ninguna pasa, **se mantiene la cadena
entregada** y el resultado se reporta como negativo, con qué compuerta falla y por cuánto. El
diagnóstico `touch<=10` no es elegible: si contradice a V-b, se reporta y no cambia la elección.

---

*Lo que sigue se escribió después de medir. Las secciones 1–6 son las del commit `f699965` sin
cambios.*

## 7. Cómo se reproducen los números

```bash
export MTAH_DATA_DIR=...                         # el bundle licenciado
python tools/dating.py --explore                 # sección 2 (sin ground truth)
python tools/dating.py --report                  # sección 8, tal cual
python tools/dating.py --possessions             # sección 9, diagnóstico posterior
python tools/engine.py --labels runs/dating/engine.csv
for v in none first touch; do python tools/dating.py --variant "$v" --labels "runs/dating/$v.csv"; done
python tools/dating.py --variant "touch<=10" --labels runs/dating/touchle10.csv
python tools/compare_submissions.py runs/dating/engine.csv runs/dating/touch.csv --gt public
```

`runs/` está ignorado por Git. `none` reproduce **byte a byte** `python tools/engine.py --labels`
(`cmp` sin diferencias, y `tests/test_dating.py` lo fija frente a `bench.METHODS["engine"]`), así que
cada Δ es contra la cadena entregada. Ninguna variante cambia un frame `D` ni `X` (mismo test). Dos
corridas de `--variant touch` dan el mismo SHA-256 (`cfc2c59e3a2e523b…`); `first` da
`f49f8c28eebc51dd…`. `compare_submissions.py` por la línea de comandos da los mismos Δ, `wins` y
jackknife que la tabla: `first` 0,0000, 0–0; `touch` −0,0526, 2–0 a favor de la cadena entregada,
jackknife −0,0541 .. −0,0216; `touch<=10` −0,0316, 1–0, jackknife −0,0324 .. 0,0000.

## 8. Mediciones

Salida de `python tools/dating.py --report`, pegada sin editar:

Slice público (17 posesiones). Δ, `wins` y jackknife frente a `none`; TP por IoU 0,3 / 0,4 / 0,5 / 0,6 / 0,7.

| variante | spellF1 | macroF1 | Δ | wins none–var | jackknife Δ | TP | pred | trans ±25 | \|lat\| | inicio: mediana / media \|·\| (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `none` | 0,5368 | 0,8533 | 0,0000 | 0–0 | 0,0000 .. 0,0000 | 13 / 13 / 11 / 9 / 5 | 21 | 6/20 | 12,3 | 0,96 / 2,04 |
| `first` | 0,5368 | 0,8545 | 0,0000 | 0–0 | 0,0000 .. 0,0000 | 13 / 13 / 11 / 9 / 5 | 21 | 6/20 | 12,3 | 0,96 / 2,01 |
| `touch` | 0,4842 | 0,8548 | -0,0526 | 2–0 | -0,0541 .. -0,0216 | 13 / 11 / 9 / 8 / 5 | 21 | 6/20 | 8,8 | 0,48 / 1,90 |
| `touch<=10` | 0,5053 | 0,8491 | -0,0316 | 1–0 | -0,0324 .. 0,0000 | 13 / 12 / 10 / 8 / 5 | 21 | 7/20 | 10,7 | 0,52 / 1,89 |

Test de signos por posesión: mejor IoU del mismo equipo, variante frente a `none`.

| variante | mejoran | empeoran | empates | p exacto (dos colas) | pierden IoU ≥ 0,5 |
|---|---:|---:|---:|---:|---:|
| `first` | 2 | 0 | 15 | 0,5000 | 0 |
| `touch` | 7 | 5 | 5 | 0,7744 | 2 |
| `touch<=10` | 6 | 3 | 8 | 0,5078 | 1 |

Banco de trasplante (19 donantes, 6 con < 50% de balón) e informe por bloques.

| variante | banco limpio | media | poco balón | peor | pos/min | bloque mín–máx | sin pos. | ST partido | ST bloques 7/9/11/18 | %D |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `none` | 0,5368 | 0,4351 | 0,3595 | 0,2400 | 3,62 | 1,01–6,00 | 0 | 77,1% | 85,6% | 40,0% |
| `first` | 0,5368 | 0,4351 | 0,3595 | 0,2400 | 3,62 | 1,01–6,00 | 0 | 77,0% | 86,1% | 40,0% |
| `touch` | 0,4842 | 0,4182 | 0,3321 | 0,2000 | 3,61 | 1,01–6,00 | 0 | 74,2% | 79,2% | 40,0% |
| `touch<=10` | 0,5053 | 0,4299 | 0,3370 | 0,2000 | 3,61 | 1,01–6,00 | 0 | 76,8% | 79,9% | 40,0% |

Compuertas pre-registradas (sección 6), frente a `none`.

| variante | G1 slice | G2 banco | G3 bloques |
|---|---|---|---|
| `first` | **falla** | pasa | pasa |
| `touch` | **falla** | **falla** | **falla** |

Elección por la regla: **ninguna; se mantiene la cadena entregada**.

## 9. Recomendación: **ninguna variante; se mantiene la cadena entregada** (resultado negativo)

Aplicando la sección 6 tal cual:

- **V-a `first` falla G1** solo por el test de signos: mejora 2 posesiones, no empeora ninguna,
  15 empates (p = 0,50; hacían falta ≥ 6–0). En el slice el `spellF1` no cambia (Δ 0,0000, 0
  discordantes) y el banco tampoco: es el no-op que la exploración de la sección 2 anticipaba (280
  frames movidos en todo el partido). Pasa G2 y G3 porque no cambia casi nada.
- **V-b `touch` falla las tres**, y no por poco. G1: Δ −0,0526, **pierde 2 posesiones a IoU 0,5**
  (`wins` 2–0 a favor de la cadena entregada: las verdaderas #5 y #13), test de signos 7–5 (p =
  0,77), y el jackknife es negativo en todos los pliegues. G2: banco −0,0169 de media y **−0,0274
  con poco balón**, peor donante 0,2400 → 0,2000. G3: la tasa no cambia (3,61), pero el acuerdo con
  el Smart Tagging del partido cae **2,9 puntos** (77,1% → 74,2%; el límite era 1,0) y 6,4 puntos en
  los bloques de poco balón (85,6% → 79,2%). La señal independiente del tracking dice lo mismo que el
  slice y el banco: las fechas de `touch` son peores en todo el partido, no solo en estas 17.
- **El diagnóstico `touch<=10`** (solo anclas con el balón a ≤ 10 m/s) también es negativo: Δ
  −0,0316, pierde 1 posesión a IoU 0,5, test de signos 6–3 (p = 0,51), banco −0,0052 / −0,0225.
  Quitar las anclas en vuelo reduce el daño pero no lo quita: el problema no es solo el balón que
  pasa volando cerca de un jugador.

Que `touch` acerque la mediana del desfase de inicio de 0,96 a 0,48 s y aun así pierda en todos los
instrumentos es la lección: mover los cambios hacia atrás arregla unas posesiones a costa de
adelantar otras más allá de la verdad, y las que se adelantan son cortas, donde un segundo decide si
se emparejan.

### Diagnóstico posterior (no pre-registrado, no cambia la elección)

Salida de `python tools/dating.py --possessions`, pegada sin editar:

Por posesión verdadera del slice: mejor IoU del mismo equipo y desfase del inicio de esa posesión predicha (s, positivo = tarde). Diagnóstico posterior, no pre-registrado.

| # | equipo | dura (s) | IoU none | first | touch | touch<=10 | inicio none | touch | touch<=10 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | A | 6,6 | 0,568 | 0,591 | 0,591 | 0,591 | 0,00 | 0,00 | 0,00 |
| 2 | H | 8,1 | 0,214 | 0,245 | 0,245 | 0,245 | 5,04 | 4,60 | 4,60 |
| 3 | A | 2,8 | 0,000 | 0,000 | 0,000 | 0,000 | — | — | — |
| 4 | H | 41,6 | 0,618 | 0,618 | 0,611 | 0,611 | 6,96 | 6,96 | 6,96 |
| 5 | A | 7,4 | 0,640 | 0,640 | 0,301 | 0,301 | 1,68 | -1,60 | -1,60 |
| 6 | H | 28,6 | 0,916 | 0,916 | 0,916 | 0,916 | 1,08 | 1,08 | 1,08 |
| 7 | A | 3,2 | 0,479 | 0,479 | 0,479 | 0,479 | -1,32 | -1,32 | -1,32 |
| 8 | H | 42,4 | 0,919 | 0,919 | 0,947 | 0,947 | 2,20 | 2,20 | 2,20 |
| 9 | A | 20,0 | 0,910 | 0,910 | 0,975 | 0,975 | 1,36 | -0,04 | -0,04 |
| 10 | H | 0,8 | 0,113 | 0,113 | 0,149 | 0,149 | 0,48 | 0,48 | 0,48 |
| 11 | A | 16,0 | 0,613 | 0,613 | 0,643 | 0,643 | 1,72 | 1,12 | 1,12 |
| 12 | H | 1,3 | 0,076 | 0,076 | 0,000 | 0,074 | -4,48 | — | -4,60 |
| 13 | A | 3,6 | 0,517 | 0,517 | 0,369 | 0,517 | -0,88 | -3,68 | -0,88 |
| 14 | A | 35,7 | 0,961 | 0,961 | 0,961 | 0,961 | 0,84 | 0,84 | 0,84 |
| 15 | H | 3,5 | 0,402 | 0,402 | 0,485 | 0,402 | 0,56 | -0,56 | 0,56 |
| 16 | A | 7,6 | 0,974 | 0,974 | 0,974 | 0,974 | -0,12 | -0,12 | -0,12 |
| 17 | H | 11,8 | 0,672 | 0,672 | 0,672 | 0,672 | 3,88 | 3,88 | 3,88 |

Posesiones que la cadena entregada empieza tarde: frames `[inicio verdadero, inicio predicho)`.

| # | tarde (s) | `D` | otro equipo | mismo equipo | balón visto | control anterior sin disputa | control anterior disputado | control nuevo | toque nuevo sin control |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 5,04 | 0,0% | 100,0% | 0,0% | 100,0% | 46 | 5 | 11 | 0 |
| 4 | 6,96 | 0,0% | 52,9% | 47,1% | 100,0% | 16 | 0 | 68 | 0 |
| 5 | 1,68 | 0,0% | 100,0% | 0,0% | 100,0% | 0 | 0 | 0 | 0 |
| 6 | 1,08 | 100,0% | 0,0% | 0,0% | 100,0% | 0 | 0 | 12 | 5 |
| 8 | 2,20 | 0,0% | 100,0% | 0,0% | 100,0% | 0 | 0 | 0 | 0 |
| 9 | 1,36 | 0,0% | 100,0% | 0,0% | 100,0% | 0 | 0 | 0 | 6 |
| 10 | 0,48 | 0,0% | 100,0% | 0,0% | 100,0% | 4 | 0 | 0 | 0 |
| 11 | 1,72 | 0,0% | 100,0% | 0,0% | 100,0% | 0 | 0 | 0 | 15 |
| 14 | 0,84 | 100,0% | 0,0% | 0,0% | 100,0% | 0 | 0 | 0 | 0 |
| 15 | 0,56 | 0,0% | 100,0% | 0,0% | 100,0% | 0 | 0 | 0 | 0 |
| 17 | 3,88 | 100,0% | 0,0% | 0,0% | 100,0% | 0 | 0 | 48 | 11 |

**Lectura.** Las posesiones que la cadena entregada empieza tarde **no** se retrasan en el traspaso
que este carril sabe redatar. `touch` no corrige las más tardías: #4 sigue en +6,96 s, #17 en
+3,88 s y #8 en +2,20 s, y #2 solo pasa de +5,04 a +4,60 s. Lo que hay en esos frames tardíos son
cuatro mecanismos distintos:

1. **La cola de una parada** (#6, #14, #17): el 100% de los frames tardíos es `D` predicho y la
   verdad ya está en juego. En #17 el nuevo equipo tiene **48 frames de control** dentro de ese `D`, y
   en #6, 12. La parada predicha termina tarde; ninguna regla de fecha la cruza (sección 3), y no
   debe: es el borde final del `D`, que es de los carriles de balón muerto.
2. **El tracking ve al equipo anterior controlando** (#2: 46 frames de control **sin disputa** del
   equipo anterior en los 5 s tardíos; #10: 4). La verdad ya da el balón al nuevo; la evidencia dice
   otra cosa. Es un desacuerdo de evidencia, no de fecha.
3. **Fragmentación** (#4): el 47,1% de los frames tardíos ya es del mismo equipo, en una posesión
   predicha anterior que un cambio espurio separa; 68 frames de control disputado del nuevo equipo
   y 16 sin disputa del anterior entremedias. Es un problema de **si**, no de cuándo.
4. **Balón suelto sin nadie a ≤ 1,5 m** (#5, #8, #15): ningún control ni toque de nadie en los
   frames tardíos, con el balón visto el 100% del tiempo. No hay observación en la que anclar una
   fecha; `touch` encontró en #5 un toque anterior a la verdad y la adelantó 1,60 s (IoU 0,640 →
   0,301).

Solo #9 y #11 tienen en los frames tardíos toques del nuevo equipo sin control (6 y 15 frames): el
caso que la hipótesis describe, y `touch` los mejora (0,910 → 0,975, 0,613 → 0,643). Las otras
cinco mejoras del test de signos (#1, #2, #8, #10, #15) son de 0,02 a 0,08 de IoU, y la de #15
llega adelantando el inicio por delante de la verdad (+0,56 → −0,56 s). Nada de eso compensa lo
que rompe en las cortas: #5 (7,4 s), #12 (1,3 s) y #13 (3,6 s).

**Pistas para el coordinador** (no probadas, salidas de mirar el slice, contaminadas por diseño):
el borde **final** del `D` entregado (mecanismo 1: una parada que sigue mientras un equipo controla
el balón es candidata a terminar en ese control) y la fragmentación por duelos largos (mecanismo
3). Cualquiera de las dos necesita su propio pre-registro y evidencia fuera del slice.

## 10. Limitaciones

- **17 posesiones.** El negativo de V-b es robusto en el slice (todos los pliegues del jackknife
  negativos, 2 posesiones perdidas), pero descansa en las mismas 17 posesiones que el banco
  trasplanta. Lo que lo sostiene fuera de ellas es el Smart Tagging del partido (−2,9 puntos).
- **El negativo de V-a no es "la hipótesis es falsa"**, es "la hipótesis es casi vacía": con la
  regla del duelo, el primer control del nuevo equipo tras el último del anterior ya es casi siempre
  sin disputa (29 de 301 cambios se mueven). No hay nada que medir.
- **La definición del traspaso** termina en la última parada y en la última reanudación del equipo
  anterior (sección 2). Es una regla de principio, fijada antes de medir, y cambia la exploración
  (167 cambios movidos por `touch` en lugar de 206). No se midió la variante sin ella; el
  diagnóstico de arriba dice que cruzar la parada no arreglaría #6, #14 ni #17, porque ahí el
  retraso está **dentro** del `D`.
- **El corpus de DFL no arbitra la fecha** (decisión 34, adenda 2), así que no se usó.
- **El desfase de inicio** (columna de la sección 8 y tabla de arriba) usa la posesión predicha de
  mayor IoU, no el emparejamiento oficial uno a uno; es un diagnóstico, no una métrica.
