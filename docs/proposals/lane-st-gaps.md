# Lane st-gaps — el Smart Tagging dentro de los huecos largos de balón

Propuesta para la cadena entregada (`tools/engine.py`, `run()`). Código: `tools/st_gaps.py`, pruebas:
`tests/test_st_gaps.py`. Este documento no cambia el motor ni `docs/DECISIONS.md`: el coordinador
integra.

## 1. Pre-registro

Escrito y comprometido en git **antes** de medir nada contra el ground truth (slice público, banco de
trasplante o comparación pareada). Lo explorado antes, todo sin etiquetas, está declarado abajo con
sus números.

### Problema

Dentro de un hueco de balón el motor no ve controles y arrastra el equipo del último control
(decisiones 24, 29). El Smart Tagging (`smart_tagging.possession_votes`) es una opinión
independiente del tracking, y la decisión 34 midió que en el slice acierta el ~98% de los frames
vivos **sin balón** (391), frente a ~68% en el conjunto de frames vivos: es fiable justo donde el
tracking es ciego. La muestra es pequeña (391 frames de un solo bloque, el más fácil), y se dice.

**Pregunta.** ¿Una regla determinista que, dentro de un hueco largo, cambie el equipo arrastrado al
que nombra el Smart Tagging cuando la contradice durante la mayor parte del hueco, mejora la cadena
entregada?

**Consecuencia, declarada antes de medir.** Si esta regla entra, el Smart Tagging deja de ser un
validador independiente para esta componente: el acuerdo con el Smart Tagging del informe de bloques
sube por construcción en los frames que la regla cambia, y no se puede leer como evidencia a favor.
Se reporta, marcado como no independiente.

### Lo explorado antes de escribir esto (sin ground truth)

Sobre la cadena entregada (motor con duelo + reanudaciones + `D` etiquetado ∪ W1, decisiones 29–36),
el tracking y el Smart Tagging del partido entero. Scripts de exploración fuera del repositorio; los
números los reproduce `tools/st_gaps.py --explore`.

- **Huecos de balón** (`ball_gaps.ball_gaps`, rachas máximas sin balón dentro de un medio tiempo):
  150, 64.643 frames. La distribución es bimodal: 133 de 150 duran ≥ 1 s y 132 de esos ≥ 5 s;
  ≥ 10 s: 79; ≥ 20 s: 44 (43.292 frames, 67% del déficit, decisión 24).
- **W1 ya se comió la mayor parte de los huecos largos.** Solo 19.770 frames sin balón son vivos
  (no `D` en la cadena entregada). Un **hueco vivo** (racha máxima sin balón y sin `D`): 153, de los
  que 65 duran ≥ 5 s (16.667 frames), 20 ≥ 10 s y 5 ≥ 20 s.
- **Dentro de los huecos el Smart Tagging suele estar de acuerdo con el equipo arrastrado.** En los
  huecos vivos ≥ 5 s, de los frames vivos el 44,1% tiene voto de un solo equipo igual al
  arrastrado y el 13,9% al rival.
- **Cuántos huecos haría saltar la regla** (voto del rival ≥ X de los frames vivos del hueco):

  | unidad | G | X = 0,3 | X = 0,5 | X = 0,7 | en el bloque 1 (X = 0,5) | en bloques 7, 9, 11, 18 (X = 0,5) |
  |---|---:|---:|---:|---:|---:|---:|
  | hueco vivo | 1 s | 23 | 19 (2.857 fr) | 18 | 0 | 0 |
  | hueco vivo | 5 s | 14 | 11 (2.373 fr) | 10 | 0 | 0 |
  | hueco vivo | 10 s | 3 | 3 (983 fr) | 3 | 0 | 0 |
  | hueco vivo | 20 s | — | 0 | — | 0 | 0 |
  | hueco de balón | 5 s | 29 | 25 | 23 | 0 | 1 |
  | hueco de balón | 20 s | 11 | 10 | 9 | 0 | 1 |

  Meseta en X entre 0,3 y 0,7. **Con X = 0,5 la regla no salta en ningún hueco del bloque 1** con
  ninguna G, así que el slice público casi no puede juzgarla: se espera Δ = 0 exacto allí. Es un dato
  estructural (dónde actúa la regla), no una lectura del ground truth.
- **La fase rival ya estaba en curso antes del hueco** en 23 de los 25 huecos de balón ≥ 5 s que
  saltan: el Smart Tagging decía "rival" mientras el balón aún se veía y el motor mantenía al equipo
  arrastrado. Fechar el cambio "al inicio de la fase" y "al inicio del hueco" solo difieren cuando la
  fase empezó después del último control observado del equipo arrastrado (2 de 11 huecos vivos ≥ 5 s,
  1,1 s y 2,5 s antes).
- **Muchos huecos de balón que saltan son casi todo `D`**: en 12 de 25 quedan menos de 3 s vivos.
  Esa franja viva es donde la unidad "hueco de balón" y la unidad "hueco vivo" difieren.
- **La premisa del bloque 11 cambió con W1.** Con la cadena entregada hoy, la posesión más larga
  cubre el 34,3% del bloque 11 (no el ~91% anterior a W1), y su único hueco largo (69,5 s) es `D` en
  el 99%. El acuerdo con el Smart Tagging de los bloques 7, 9, 11 y 18 ya es 73,1 / 89,4 / 89,4 /
  90,4%.

Lectura antes de medir: la regla tiene poco sobre lo que actuar. Se mide igual, con las variantes
fijadas abajo, y un resultado neutro o negativo es un resultado.

### La regla (`tools/st_gaps.py`)

Para cada frame, `lado` = el equipo al que votan **todas** las fases del Smart Tagging que lo
cubren (`possession_votes`, un solo equipo con votos; si no, ninguno), como en el informe de bloques.

1. **Unidad.** Según la variante: un *hueco de balón* (racha máxima sin balón observado dentro de un
   medio tiempo, `ball_gaps.ball_gaps`), o un *hueco vivo* (racha máxima sin balón **y** sin `D`
   entregado). Solo cuentan las unidades de al menos `G` segundos. Los *frames vivos* de la unidad
   son los que no son `D` en la cadena entregada; una unidad sin frames vivos no hace nada.
2. **Equipo arrastrado** `c`: el estado decodificado en el primer frame vivo de la unidad, con los
   cambios de las unidades anteriores ya aplicados (se procesan en orden temporal). Si `c` es
   ninguno, o el estado no es constante sobre los frames vivos de la unidad (una reanudación forzada
   dentro; la decide su propia regla), la unidad no hace nada.
3. **Salta** si la proporción de frames vivos de la unidad con `lado = rival de c` es **≥ X**.
4. **Cambio.** Se fuerza el estado al rival en el frame de cambio, con el mismo mecanismo que una
   reanudación (`engine.decode(forced=…)`): desde ahí manda el rival hasta el siguiente control que
   el decodificador acepte (con la regla del duelo). El tracking, al volver el balón, decide como
   siempre. Si una reanudación cae en el mismo frame, gana la reanudación (reglamento sobre
   anotador).
5. **Fecha del cambio**, según la variante:
   - `hueco`: el primer frame vivo de la unidad.
   - `fase`: el inicio de la racha de `lado = rival` que contiene el primer frame vivo de la unidad
     votado por el rival, caminando hacia atrás por frames contiguos con ese voto; pero nunca antes
     del frame siguiente a la última **observación** del equipo arrastrado antes de la unidad (un
     control suyo, `ctrl = c`, o una reanudación forzada a su favor), ni antes del inicio del medio
     tiempo. Es el principio de las decisiones 32 y 35: una observación del tracking vale más que una
     estimación.
6. `D` se escribe encima, como en la cadena entregada. Fuera de las unidades que saltan y de su
   arrastre posterior no cambia ningún frame; sin unidades que salten la salida es idéntica a
   `engine.chain` frame a frame (lo fija una prueba).

### Variantes (cuatro, fijas; ninguna se barre)

| variante | unidad | G | X | fecha | por qué |
|---|---|---:|---:|---|---|
| V1 | hueco de balón | 5 s | 0,5 | `hueco` | la regla tal como la plantea el carril. G = 5 s es el corte de 126 frames de la decisión 24 (no una constante nueva): más largo que el vuelo de cualquier pase o pelotazo (60 m a 15 m/s = 4 s), así que un hueco así puede esconder un cambio, y son ≥ 5 veces la resolución de ~1 s del Smart Tagging. X = 0,5: el anotador nombra al rival durante la mayor parte del hueco |
| V2 | hueco de balón | 5 s | 0,5 | `fase` | V1 fechando al inicio de la fase del Smart Tagging, acotado por la última observación del tracking |
| V3 | hueco vivo | 5 s | 0,5 | `hueco` | la posesión solo existe con balón vivo: la unidad y su longitud se miden sobre los frames no `D`, y no se crean franjas vivas de ~1 s entre paradas |
| V4 | hueco de balón | 20 s | 0,5 | `hueco` | solo los huecos más largos (corte de 500 frames de la decisión 24, 67% del déficit de balón): más largos que la posesión media del partido (14,2 s), donde arrastrar un solo equipo es lo menos plausible |

X no varía: la exploración muestra una meseta entre 0,3 y 0,7, y 0,5 es la mayoría. Una G de 20 s
sobre huecos vivos no salta nunca (exploración), así que no es una variante.

### Mediciones (todas, para todas las variantes, contra la cadena entregada `engine.run()`)

(a) **Slice público, huecos reales.** `spellF1` oficial (`possession_metrics.evaluate`); pareado con
`tools/compare_submissions.py` (Δ, `n_discordant`, posesiones ganadas/perdidas a IoU 0,5, rango del
jackknife); **acierto de equipo en los frames vivos sin balón** del GT público (frames con GT `H`/`A`
y sin balón observado; ~391), antes y después, con las abstenciones rellenadas como el scorer; y
frames cambiados en la ventana.

(b) **Banco de trasplante** (`bench.bench` + `bench.summary`): limpio, media de donantes, media de
donantes con < 50% de balón, peor donante; Δ frente al motor y donantes mejor / peor. Diagnóstico:
en los frames de la ventana que la regla cambia en cada donante, la proporción en que la nueva
etiqueta coincide con el GT. **Sesgo declarado: pesimista para esta regla** — el banco trasplanta
huecos sobre jugadas donde el balón se veía, donde el Smart Tagging acierta ~68%, no ~98%; es el
sesgo opuesto al de la imputación y el vídeo (decisiones 34, 38).

(c) **Informe de bloques** (`blocks.measure`): posesiones/min del partido y por bloque, en especial
7, 9, 11 y 18, y `larga` (la parte del bloque que cubre la posesión más larga). Acuerdo con el Smart
Tagging, marcado como no independiente.

(d) **Honestidad.** Cuántos frames del partido cambia cada variante (dentro de las unidades y por
el arrastre posterior), cuántas unidades saltan, y cuántos de esos frames caen en los 4 bloques con
poco balón (7, 9, 11, 18).

### Regla de selección

Una variante **es integrable** si cumple las tres:

- **Ga (slice, huecos reales).** Ninguna posesión perdida: en el pareado a IoU 0,5 frente a la
  cadena entregada, 0 posesiones del GT que la cadena empareja y la variante no; **y** el acierto de
  equipo en los frames vivos sin balón no baja.
- **Gc (estructura).** Partido entre 2,5 y 5,0 posesiones/min; ningún bloque con 0 posesiones ni
  por encima de 8/min; ningún bloque por debajo de la mitad de su tasa con la cadena entregada.
- **E (evidencia a favor).** Al menos una señal con ground truth a favor: Δ pareado de `spellF1`
  > 0, o acierto en los frames vivos sin balón estrictamente mayor, o Δ media de donantes del banco
  > 0. Sin esto la regla no tiene evidencia y no entra, aunque no rompa nada: el slice no la ve (no
  salta en el bloque 1) y el Smart Tagging, que es su entrada, ya no puede validarla.

El banco **no veta solo** (su sesgo es pesimista aquí): entra en E y en el desempate. Entre las
integrables se recomienda la de mayor media de donantes en el banco; si otra queda a ≤ 0,005 y
cambia menos frames del partido, la más conservadora. Si ninguna es integrable el resultado es
**negativo o no demostrado**, se dice cuál, y se recomienda no integrar.

---

Las secciones 2 en adelante se escribieron **después** de medir. El pre-registro de arriba está en el
commit `b71360c` (empujado antes de cualquier lectura del ground truth, del banco o del pareado); el
código medido, en `d7c7dbb`. Sin desviaciones del pre-registro.

## 2. Cómo se reproducen los números

```bash
export MTAH_DATA_DIR="<carpeta del bundle>"
uv sync --locked --inexact
.venv/Scripts/python tools/st_gaps.py --explore                     # sin GT: dónde actúa la regla
mkdir -p runs/st_gaps
.venv/Scripts/python tools/st_gaps.py --measure runs/st_gaps > runs/st_gaps/measure.json
.venv/Scripts/python tools/compare_submissions.py runs/st_gaps/engine.csv runs/st_gaps/V3.csv --gt public
```

Cada número de la sección 3 es un campo de `measure.json` (solo agregados; las CSV de etiquetas de
`runs/st_gaps/` no se comprometen). Tarda ~80 s. Las tablas se generaron desde ese JSON, no a mano.
`engine` es la cadena entregada tal como la registra el banco (`bench.METHODS["engine"]`, la misma
que `engine.run()`).

## 3. Mediciones

### (a) Slice público, huecos reales

| | spellF1 | macroF1 | Δ pareado | discordantes (cadena–variante) | jackknife | acierto en frames vivos sin balón (391) | frames cambiados en la ventana |
|---|---:|---:|---:|---:|---:|---:|---:|
| cadena entregada | 0,5368 | 0,8533 | | | | 94,9% | |
| V1 | 0,5368 | 0,8533 | 0,0000 | 0 (0–0) | 0,0000 .. 0,0000 | 94,9% | 0 |
| V2 | 0,5368 | 0,8533 | 0,0000 | 0 (0–0) | 0,0000 .. 0,0000 | 94,9% | 0 |
| V3 | 0,5368 | 0,8533 | 0,0000 | 0 (0–0) | 0,0000 .. 0,0000 | 94,9% | 0 |
| V4 | 0,5368 | 0,8533 | 0,0000 | 0 (0–0) | 0,0000 .. 0,0000 | 94,9% | 0 |

### (b) Banco de trasplante

| donante | balón | cadena | V1 | V2 | V3 | V4 |
|---|---:|---:|---:|---:|---:|---:|
| 1★ (sin trasplante) | 88,2% | 0,5368 | 0,5368 | 0,5368 | 0,5368 | 0,5368 |
| 2 | 70,9% | 0,5647 | 0,4889 | 0,4889 | 0,4889 | 0,4889 |
| 3 | 64,7% | 0,5529 | 0,5263 | 0,5263 | 0,5263 | 0,5529 |
| 4 | 61,5% | 0,4229 | 0,4842 | 0,4526 | 0,4842 | 0,4432 |
| 5 | 53,5% | 0,5212 | 0,4588 | 0,4588 | 0,4588 | 0,4588 |
| 6 | 54,9% | 0,3667 | 0,3667 | 0,3667 | 0,3667 | 0,3667 |
| 7 | 28,4% | 0,3586 | 0,3586 | 0,3586 | 0,3586 | 0,3586 |
| 8 | 52,9% | 0,4432 | 0,3619 | 0,3429 | 0,4400 | 0,4432 |
| 9 | 21,1% | 0,3704 | 0,3704 | 0,3704 | 0,4000 | 0,3704 |
| 10 | 50,4% | 0,4118 | 0,4118 | 0,4118 | 0,4343 | 0,4118 |
| 12 | 76,0% | 0,5000 | 0,5189 | 0,5405 | 0,5189 | 0,5000 |
| 13 | 57,6% | 0,5212 | 0,4000 | 0,4000 | 0,4000 | 0,5212 |
| 14 | 61,7% | 0,4933 | 0,4375 | 0,4875 | 0,4375 | 0,4375 |
| 15 | 41,6% | 0,3871 | 0,3294 | 0,3294 | 0,3294 | 0,3294 |
| 16 | 68,8% | 0,5368 | 0,5368 | 0,5368 | 0,5368 | 0,5368 |
| 17 | 51,0% | 0,4000 | 0,3778 | 0,3889 | 0,3778 | 0,3778 |
| 18 | 19,0% | 0,2400 | 0,2400 | 0,2400 | 0,3067 | 0,2400 |
| 19 | 44,8% | 0,5037 | 0,4516 | 0,4387 | 0,4516 | 0,5037 |
| 20 | 45,6% | 0,2971 | 0,4108 | 0,3579 | 0,4108 | 0,4108 |
| 21 | 52,1% | 0,3750 | 0,3543 | 0,3771 | 0,3543 | 0,3750 |

| resumen | cadena | V1 | V2 | V3 | V4 |
|---|---:|---:|---:|---:|---:|
| media de donantes (19) | 0,4351 | 0,4150 | 0,4144 | 0,4253 | 0,4277 |
| Δ media frente a la cadena | | −0,0201 | −0,0207 | −0,0097 | −0,0074 |
| media con < 50% de balón (6) | 0,3595 | 0,3601 | 0,3492 | 0,3762 | 0,3688 |
| Δ poco balón | | +0,0006 | −0,0103 | +0,0167 | +0,0093 |
| peor donante | 0,2400 | 0,2400 | 0,2400 | 0,3067 | 0,2400 |
| donantes mejor / peor que la cadena | | 3 / 10 | 4 / 9 | 6 / 10 | 2 / 5 |
| frames de la ventana que cambia (suma de donantes) | | 10822 | 10076 | 12853 | 7264 |
| … de ellos acierta la variante / la cadena | | 3633 / 6644 | 3217 / 6314 | 5428 / 6868 | 2582 / 4397 |

### (c) Informe de bloques

| | cadena | V1 | V2 | V3 | V4 |
|---|---:|---:|---:|---:|---:|
| posesiones/min, partido | 3,62 | 3,85 | 3,85 | 3,78 | 3,68 |
| mín. / máx. bloque | 1,01 / 6,00 | 1,34 / 6,20 | 1,34 / 6,20 | 1,01 / 6,00 | 1,34 / 6,00 |
| bloques sin posesiones | 0 | 0 | 0 | 0 | 0 |
| bloques por debajo de la mitad de su tasa con la cadena | 0 | 0 | 0 | 0 | 0 |
| bloque 7: pos/min · `larga` | 2,00 · 12,2% | 2,00 · 12,2% | 2,00 · 12,2% | 2,00 · 12,2% | 2,00 · 12,2% |
| bloque 9: pos/min · `larga` | 1,60 · 17,3% | 1,60 · 17,3% | 1,60 · 17,3% | 1,60 · 17,3% | 1,60 · 17,3% |
| bloque 11: pos/min · `larga` | 1,01 · 34,3% | 1,34 · 34,3% | 1,34 · 34,3% | 1,01 · 34,3% | 1,34 · 34,3% |
| bloque 18: pos/min · `larga` | 3,60 · 9,4% | 3,60 · 9,4% | 3,60 · 9,4% | 3,60 · 9,4% | 3,60 · 9,4% |
| acuerdo con el Smart Tagging (no independiente) | 77,1% | 81,9% | 82,5% | 80,6% | 79,1% |
| bloques cuya tasa cambia | — | 2 (+0,60), 4 (+0,20), 5 (+0,20), 10 (+0,40), 11 (+0,34), 14 (+0,20), 15 (+0,40), 16 (+1,60), 19 (+0,80), 20 (+0,20), 21 (+0,20) | 2 (+0,60), 4 (+0,20), 5 (+0,20), 10 (+0,40), 11 (+0,34), 14 (+0,20), 15 (+0,40), 16 (+1,60), 19 (+0,80), 20 (+0,20), 21 (+0,20) | 2 (+0,60), 10 (+0,20), 13 (+0,20), 14 (+0,20), 16 (+1,20), 19 (+0,80), 20 (+0,20) | 5 (+0,20), 10 (+0,20), 11 (+0,34), 14 (+0,20), 15 (+0,40), 20 (+0,20) |

### (d) Honestidad

| | V1 | V2 | V3 | V4 |
|---|---:|---:|---:|---:|
| unidades que saltan | 25 | 25 | 11 | 10 |
| … en el bloque 1 | 0 | 0 | 0 | 0 |
| … en los bloques 7, 9, 11, 18 | 1 | 1 | 0 | 1 |
| frames cambiados en el partido | 3882 | 4225 | 2722 | 1460 |
| … de ellos sin balón | 3049 | 3049 | 2376 | 1194 |
| … en los bloques 7, 9, 11, 18 | 24 | 56 | 0 | 24 |

`frames de la ventana que cambia` suma los 19 donantes: en el banco la regla sí actúa sobre el bloque
1, porque los huecos trasplantados caen donde el balón se veía. En esos frames la nueva etiqueta
acierta menos que la de la cadena en las cuatro variantes (V3: 5.428 frente a 6.868 de 12.853). Es
el sesgo declarado en el pre-registro, medido: fuera de los huecos reales el Smart Tagging que
contradice a la cadena se equivoca más que ella.

**Diagnóstico a posteriori (no decide nada, no cambia la regla).** En los 391 frames vivos sin balón
del slice, la cadena ya acierta 371 (94,9%) y ninguno es `D`. El Smart Tagging vota por un solo
equipo en 259 y acierta 254 (98,1%, la cifra de la decisión 34). Solo **contradice a la cadena en 25
frames** (acierta en 20). Esos 25 están en huecos vivos cortos o con mayoría del equipo arrastrado:
el bloque 1 tiene 6 huecos vivos, el más largo de 9,3 s, y ninguno salta con X = 0,5. Aunque la regla
se siguiera en todos, el techo en ese slice sería +15 frames de acierto (≈ +3,8 puntos) sin que haya
evidencia de que moviera una posesión. Bajar G o X para que la regla salte ahí sería ajustarla al
slice, y no se hace.

## 4. Compuertas, aplicadas tal como se pre-registraron

| variante | Ga (0 perdidas; acierto sin balón no baja) | Gc (estructura) | E (alguna señal con GT a favor) | resultado |
|---|---|---|---|---|
| V1 | pasa (0–0; 94,9% = 94,9%) | pasa (3,85/min; bloques 1,34 .. 6,20; ninguno a la mitad) | **falla**: Δ pareado 0; acierto igual; banco −0,0201 | no integrable |
| V2 | pasa (0–0; igual) | pasa (3,85/min; 1,34 .. 6,20) | **falla**: 0; igual; banco −0,0207 | no integrable |
| V3 | pasa (0–0; igual) | pasa (3,78/min; 1,01 .. 6,00) | **falla**: 0; igual; banco −0,0097 | no integrable |
| V4 | pasa (0–0; igual) | pasa (3,68/min; 1,34 .. 6,00) | **falla**: 0; igual; banco −0,0074 | no integrable |

Ninguna variante es integrable. Ga y Gc se pasan por la razón menos informativa posible: la regla no
toca el bloque 1, y en el resto del partido mueve como mucho 0,2–1,6 posesiones/min en unos pocos
bloques. **Resultado: no demostrado**, con el banco en contra en las cuatro medias.

## 5. Recomendación

**No integrar ninguna variante.** La regla no tiene evidencia a favor en ningún instrumento con ground
truth, y su coste es real: el Smart Tagging dejaría de ser un validador independiente de la cadena,
justo el único que hay fuera del slice (su acuerdo subiría 2–5 puntos por construcción, 77,1% →
79,1–82,5%, sin que eso diga nada).

Lo que el coordinador debe saber:

- **La premisa del carril cambió con W1.** La regla se pensó para la posesión arrastrada a través de
  huecos largos (bloque 11, ~91% de un bloque con 20% de balón). Con la cadena entregada hoy, los
  huecos largos son casi todo `D` (solo 19.770 de 64.643 frames sin balón son vivos), la posesión
  más larga del bloque 11 cubre el 34,3%, y en los huecos vivos ≥ 5 s el Smart Tagging está de
  acuerdo con el equipo arrastrado tres veces más que en contra (44,1% frente a 13,9% de los frames).
  La regla salta en 11–25 huecos del partido; **ninguno en el bloque 1 y como mucho uno en los
  bloques 7, 9, 11 y 18**.
- **El slice no puede juzgarla y el banco la juzga con sesgo en contra.** El slice tiene 391 frames de
  hueco real, la cadena ya acierta el 94,9% de ellos y la regla no salta allí. El banco sí la hace
  saltar, pero sobre juego con balón visible, donde el Smart Tagging que contradice a la cadena
  acierta menos que ella (sección 3). Ninguno de los dos mide lo que la regla pretende.
- **V3 (hueco vivo, 5 s) es la menos mala** y la única que no toca los bloques con poco balón: −0,0097
  de media pero +0,0167 en poco balón y sube el peor donante (0,2400 → 0,3067). No basta según la
  regla escrita (E mira la media) y no se reinterpreta.
- **Para reabrirlo** haría falta ground truth sobre huecos vivos largos reales, que el slice no tiene
  (su hueco vivo más largo dura 9,3 s). Sin eso, cualquier umbral que la haga saltar más es un ajuste
  sin juez.

## 6. Limitaciones

- **El slice no ve la regla.** Ga se pasa trivialmente (0 frames cambiados en la ventana): no es
  evidencia de inocuidad en el resto del partido, solo de que el slice no la ve.
- **Mismas 17 posesiones en el banco**, y su sesgo aquí es pesimista por construcción (declarado
  antes de medir); por eso no veta solo. Pero el pre-registro exigía alguna señal a favor y no hay
  ninguna.
- **El 98% del Smart Tagging sin balón es una muestra pequeña** (259 frames votados de un solo bloque,
  el más fácil); la regla nunca llegó a apoyarse en ella.
- **Exploración previa sin GT.** La unidad "hueco vivo" y la fecha acotada por la última observación
  se diseñaron después de ver dónde actuaría la regla (sección 1, declarado); no se miró el GT, el
  banco ni el pareado antes de `b71360c`.
- **Un partido.** Cifras de BAR–ATH.

## Revisión de código (PR #56)

- **Reanudación dentro de la unidad (corregido).** Una reanudación forzada al equipo arrastrado
  dentro de una unidad no cambiaba el estado, así que la unidad saltaba y el decodificador deshacía
  el cambio en la reanudación; y la fecha `phase` podía retroceder por encima de ella, porque
  `last_observation` solo mira `[inicio de la mitad, inicio de la unidad)`. Ahora **una unidad con
  una reanudación forzada dentro (de cualquier equipo) no hace nada** (regla 2 de `st_gaps.py`): se
  descarta entera en vez de partirse, porque partirla crearía unidades más cortas que el
  pre-registro no nombra. Con eso ningún cambio se fecha antes de una reanudación de su unidad.
  Pruebas sintéticas en `tests/test_st_gaps.py`.
- **Re-medición.** `--measure` y `--explore` dan un JSON **idéntico byte a byte** al de antes de la
  corrección: 14 de las 132 unidades de V1/V2 (≥ 5 s), 2 de las 65 de V3 y 11 de las 44 de V4
  contienen una reanudación forzada, pero ninguna saltaba. Las tablas de la sección 3 no cambian y
  **la conclusión negativa se mantiene**: ninguna variante es integrable.
- **Preámbulo compartido.** `chain` usa `engine.inputs` (control → sin disputa → aceptado →
  reanudaciones) en vez de copiarlo; la entrega sigue byte a byte igual (sha256 `72c98ed4bb4a…`).
- **Deuda aceptada (5).** `_redecode` vuelve a decodificar hasta el final de la mitad por cada
  cambio y `chain` decodifica otra vez el partido: O(cambios × mitad) por llamada. Es un módulo de
  investigación; ~60 s por medición completa.
- **Deuda aceptada (6).** `_bench_changed` copia el bucle de donantes de `bench.bench` y recalcula
  ambas cadenas, y `explore` recalcula la base dentro del bucle de variantes; riesgo de deriva si
  cambia la selección de donantes de `bench.bench`.
- **Deuda aceptada (9).** `LOW_BALL_BLOCKS`, el binomial exacto y los formateadores están
  duplicados entre los módulos de la ronda 2.
