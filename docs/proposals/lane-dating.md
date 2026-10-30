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
