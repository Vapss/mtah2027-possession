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
