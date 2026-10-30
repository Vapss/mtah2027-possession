# Lane impute — la posesión dentro de los huecos de balón, inferida desde los jugadores

Propuesta para el motor de posesión (#6, `tools/engine.py`). Código: `tools/impute.py`, pruebas:
`tests/test_impute.py`. Este documento no cambia el motor ni `docs/DECISIONS.md`: el coordinador
integra.

## 1. Pre-registro

Escrito y comprometido en git **antes** de medir nada contra el ground truth (slice público o banco
de trasplante) y antes de leer el Smart Tagging. Lo explorado antes, todo sin etiquetas humanas, está
declarado abajo con sus números.

### Problema

La cadena entregada (decisiones 29–32) etiqueta cada frame con el equipo del último control y lo
arrastra hasta el siguiente. Dentro de un hueco de balón el motor no tiene evidencia y comete dos
errores posibles:

1. **Frontera.** Si el equipo del último control antes del hueco (`antes`) y el del primero después
   (`después`) difieren, el cambio ocurrió en algún punto del hueco; el motor lo fecha en el control
   de `después`, el último momento posible.
2. **Posesión oculta.** Si `antes = después`, una posesión entera del rival dentro del hueco es
   invisible.

El banco de trasplante (`tools/bench.py`) mide justo esto contra etiquetas reales: es el
instrumento principal de esta línea.

### Lo explorado antes de escribir esto (sin ground truth, sin Smart Tagging)

- **Intervalos.** Entre anclas consecutivas de una mitad (frame de control o reanudación forzada)
  con al menos un frame sin balón: 149 en el partido; en 59 `antes ≠ después` (36.293 frames), en 90
  `antes = después` (39.912 frames).
- **Autobanco (instrumento nuevo, sin GT).** El partido entero degradado con su propio patrón de
  huecos desplazado (±2,5 y ±7,5 min dentro de cada mitad, ~37% de balón), puntuado con el
  `spellF1` oficial contra **la cadena entregada con el balón a la vista** como pseudo-verdad. Mide
  cuánto de la respuesta del motor con balón recupera cada método sin él. Hallazgo que cambió el
  diseño: en los intervalos con un solo cambio en la pseudo-verdad, ese cambio cae **exactamente
  en el control de `después`** en el 59% y el 75% de los casos (desplazamientos +2,5 y +7,5 min);
  el cuartil mediano de su posición relativa es 0,9–1,0. La frontera del motor es la respuesta
  correcta la mayoría de las veces, y un punto medio la empeora: con él la exactitud por frame
  sube y el `spellF1` baja. Por eso el modelo lleva rasgos de los anclajes (abajo) y dos variantes
  dan coste cero al cambio en el control de `después`.
- **Autocorrelación** del log-odds del modelo dentro de huecos > 500 frames: 0,95 a 1 s, 0,73 a
  5 s, 0,56 a 10 s. Frames vecinos no son observaciones independientes; de ahí el templado.
- Los números finales de esta exploración están en la sección 3 (`heldout`, `self_bench`), con el
  mismo código que se compromete aquí.

### Método (`tools/impute.py`)

**Intervalos.** Entre dos anclas consecutivas `p < q` de una mitad, con al menos un frame sin balón
estrictamente dentro. Anclas = frames de control del motor y reanudaciones que la cadena fuerza
(`engine.restart_controls`). Se excluyen los intervalos que **terminan** en una reanudación
forzada (esa entrega ya la decide la regla de las decisiones 30–32) y lo que queda antes del primer
ancla o después del último de una mitad (sin estado de partida o sin final). **Candidatos** a
cambio: los frames sin balón del intervalo que no son `D`, más `q`. Donde el balón se ve sin control,
el "todavía no cambió" del motor es observación; dentro de una parada nadie tiene el balón. Ningún
frame fuera de un intervalo cambia; `D` se escribe encima como en la cadena entregada.

**Evidencia por frame sin balón** (todas antisimétricas: local − visitante, o `±1` local/visitante):

1. Los 7 rasgos de formación del carril F (`tools/formation.py`), sin cambios.
2. `interp_d`: distancia del local más cercano menos la del visitante más cercano al balón
   **interpolado** en línea recta entre donde se vio por última vez y donde se vuelve a ver, en la
   fracción del hueco transcurrida (bidireccional: el final del hueco es observable offline).
3. `interp_d_near`: lo mismo dividido por `1 + segundos al extremo visto más cercano` (la
   interpolación vale cerca de un balón visto, no en mitad de un hueco largo).
4. `before_far`, `after_near`: el equipo del ancla anterior (`±1`) por `1 − w` y el del ancla
   siguiente por `w`, con `w` la fracción del intervalo transcurrida. Deja que el modelo aprenda de
   los datos cuán pronto dentro de un hueco tiene ya el balón el equipo de `después`.

**Modelo.** Regresión logística sin intercepto de `tools/formation.fit` (Newton, 25 iteraciones,
ridge 1e-3, sin semilla). **Autosupervisado con huecos sintéticos**: el propio patrón de huecos
del partido desplazado ±5 min (ciclico dentro de cada mitad) se superpone sobre frames con balón;
una fila es un frame vivo, con balón y con estado, que el desplazamiento oculta, y su etiqueta es el
estado de la cadena entregada **con el balón a la vista**. Los rasgos de esa fila se calculan con
el balón oculto (anclas incluidas). Ni ground truth ni Smart Tagging. El modelo se reajusta en cada
llamada sobre lo que la entrada deja ver: en el banco, sobre los rasgos degradados, así que nunca ve
el balón que el banco oculta.

**Variantes** (cinco, fijas, ninguna se barre):

| variante | regla | parámetros y por qué |
|---|---|---|
| V1 `mid` | si `antes ≠ después`, el cambio en la mediana de los candidatos | ninguno: prior uniforme. Ablación ingenua; el autobanco ya la da por peor |
| V2 `change` | si `antes ≠ después`, un único cambio en el punto que maximiza la evidencia del modelo (`antes` hasta él, `después` desde él); empates a la mediana | ninguno: el arg-máx no depende de la escala del log-odds |
| V3 `viterbi` | decodificación de 2 estados sobre los candidatos con ambos extremos fijos: 1 cambio si difieren, 0 o 2 si coinciden | coste de cada cambio `−ln(3,4 / 1.500)` = 6,09 nats (3,4 posesiones/min, la tasa física de la decisión 26); log-odds templado por 25 frames (1 s) |
| V4 `viterbi` extremo libre | V3, pero el cambio **en `q`** (la respuesta del motor) cuesta 0 | lo que el autobanco mostró: el control de `después` es el cambio la mayoría de las veces |
| V5 `viterbi` extremo libre, templado 5 s | V4 con templado de 125 frames | la autocorrelación del log-odds sigue en 0,73 a 5 s: más conservadora |

### Mediciones (todas, para todas las variantes)

1. **Banco de trasplante** (principal): `spellF1` por donante (19), media, media de donantes con
   < 50% de balón, peor donante; Δ contra el motor; donantes mejor / peor que el motor. Diagnóstico
   (no decide): exactitud de equipo en los frames vivos del GT público que el donante ocultó.
2. **Slice público**: `spellF1` oficial, Δ pareado y `n_discordant`, ganadas/perdidas contra el
   motor (`tools/compare_submissions.py`).
3. **Informe de bloques** (`tools/blocks.measure`): posesiones/min en el partido y por bloque,
   acuerdo con el Smart Tagging en el partido.
4. Sin GT: exactitud fuera de muestra del modelo (bloques pares/impares) frente a arrastrar, y el
   autobanco (`spellF1` contra la pseudo-verdad y exactitud en frames ocultos).

### Regla de selección

Una variante **pasa** si cumple todas:

- **G1 (banco)**: Δ media de donantes frente al motor **≥ +0,010** y Δ media de donantes con poco
  balón **≥ 0**.
- **G2 (banco, consistencia)**: más donantes mejor que el motor que peor (empates fuera).
- **G3 (público)**: Δ pareado de `spellF1` **≥ −0,02** (se espera ~0: el slice casi no tiene huecos).
- **G4 (estructura)**: partido entre 2,5 y 5,0 posesiones/min, ningún bloque en 0 ni por encima de
  8, y acuerdo con el Smart Tagging del partido no más de 1 punto por debajo del motor (guarda, el
  Smart Tagging no entra en nada más).

Entre las que pasan se recomienda la de mayor media de donantes en el banco, salvo que una más simple
(orden V1 < V2 < V3 < V4 < V5) quede a ≤ 0,005 de ella: entonces la más simple. Si ninguna pasa, el
resultado es **negativo**: no integrar, y se dice.

El autobanco no aprueba ni suspende nada (su verdad es el propio motor); se reporta para ver si
ordena las variantes como el banco, lo que diría si sirve para el partido entero.

---

Las secciones 2 en adelante se escribieron **después** de medir. El pre-registro de arriba está en
el commit `62f07b1`, anterior a cualquier lectura de ground truth o Smart Tagging.

**Desviación declarada.** Las pruebas sintéticas (commit `cb6dde6`) encontraron que en un empate
exacto (frames con log-odds 0, p. ej. sin formación definida) el Viterbi adelantaba el cambio al
primer candidato, al revés de lo que decía su propia documentación ("sin evidencia no se mueve").
Se corrigió para que un empate ponga el cambio lo más tarde posible (la respuesta del motor). La
primera corrida de la medición se detuvo antes de escribir ningún resultado (archivo vacío, nada
leído) y todos los números de abajo son del código de `cb6dde6`. La corrección solo puede afectar a
V3–V5.

## 2. Cómo se reproducen los números

```bash
export MTAH_DATA_DIR="<carpeta del bundle>"
uv sync --locked --inexact
mkdir -p runs/impute
.venv/Scripts/python tools/impute.py --measure runs/impute > runs/impute/measure.json
```

Cada número de la sección 3 es un campo de ese JSON (solo agregados; las CSV de etiquetas de
`runs/impute/` no se comprometen). Tarda unos 4 minutos con el tracking en caché. La regla es
determinista (sin semilla, Newton con iteraciones fijas):
`tests/test_impute.py::test_the_rewrite_is_deterministic_and_stays_inside_the_gap_intervals` corre
la cadena dos veces y comprueba que es idéntica y que no cambia ningún frame fuera de un intervalo.

**Honestidad del banco.** Cada variante es un método `(features, evidence) -> labels` que recibe
los rasgos ya degradados por `bench.degrade`: el balón solo se lee donde `f.present` es verdadero,
las anclas salen del control degradado, y el modelo se **reajusta en cada donante** sobre los
huecos sintéticos de lo que queda visible. Los frames del bloque 1 que el donante ocultó nunca son
filas de entrenamiento ni aportan una posición del balón.

## 3. Mediciones

### (1) Banco de trasplante (`bench`), instrumento principal

`spellF1` público con el patrón de balón de cada donante.

| donante | balón | motor | V1 | V2 | V3 | V4 | V5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1★ (sin trasplante) | 88,2% | 0,4585 | 0,4390 | 0,4585 | 0,4585 | 0,4585 | 0,4585 |
| 2 | 82,7% | 0,5143 | 0,4914 | 0,5143 | 0,5143 | 0,5143 | 0,5143 |
| 3 | 76,5% | 0,4800 | 0,4457 | 0,4800 | 0,4800 | 0,4800 | 0,4800 |
| 4 | 72,3% | 0,3667 | 0,4000 | 0,4556 | 0,4556 | 0,4556 | 0,3667 |
| 5 | 56,0% | 0,4333 | 0,4444 | 0,4000 | 0,4000 | 0,4000 | 0,4333 |
| 6 | 64,7% | 0,3086 | 0,4229 | 0,4800 | 0,4800 | 0,4800 | 0,4000 |
| 7 | 36,9% | 0,3692 | 0,3692 | 0,3538 | 0,3538 | 0,3538 | 0,3385 |
| 8 | 57,2% | 0,3200 | 0,3900 | 0,4000 | 0,4000 | 0,4000 | 0,3200 |
| 9 | 29,0% | 0,2462 | 0,2462 | 0,2615 | 0,2615 | 0,2615 | 0,2615 |
| 10 | 53,7% | 0,3152 | 0,3636 | 0,3758 | 0,3758 | 0,3758 | 0,3152 |
| 12 | 87,8% | 0,3892 | 0,4108 | 0,4324 | 0,4324 | 0,3892 | 0,3892 |
| 13 | 67,4% | 0,4606 | 0,5333 | 0,5212 | 0,5212 | 0,4914 | 0,4606 |
| 14 | 73,5% | 0,3172 | 0,2897 | 0,3172 | 0,3172 | 0,3172 | 0,3172 |
| 15 | 45,2% | 0,2875 | 0,3152 | 0,3273 | 0,3273 | 0,3375 | 0,2875 |
| 16 | 73,7% | 0,4488 | 0,3810 | 0,4095 | 0,4095 | 0,4488 | 0,4488 |
| 17 | 61,0% | 0,3200 | 0,3657 | 0,3886 | 0,3886 | 0,3771 | 0,3200 |
| 18 | 20,3% | 0,2069 | 0,2069 | 0,2069 | 0,2069 | 0,2069 | 0,2069 |
| 19 | 48,6% | 0,2769 | 0,2370 | 0,2370 | 0,2370 | 0,2769 | 0,2769 |
| 20 | 47,9% | 0,2824 | 0,3176 | 0,3765 | 0,3765 | 0,3765 | 0,3294 |
| 21 | 60,0% | 0,3375 | 0,4000 | 0,4250 | 0,4250 | 0,4125 | 0,3500 |

| resumen | motor | V1 | V2 | V3 | V4 | V5 |
|---|---:|---:|---:|---:|---:|---:|
| media de donantes | 0,3516 | 0,3700 | **0,3875** | **0,3875** | 0,3871 | 0,3587 |
| Δ media frente al motor | | +0,0184 | **+0,0359** | +0,0359 | +0,0355 | +0,0071 |
| media de donantes con < 50% de balón (6) | 0,2782 | 0,2820 | 0,2938 | 0,2938 | **0,3022** | 0,2835 |
| Δ poco balón | | +0,0038 | +0,0157 | +0,0157 | **+0,0240** | +0,0053 |
| peor donante | 0,2069 | 0,2069 | 0,2069 | 0,2069 | 0,2069 | 0,2069 |
| donantes mejor / peor que el motor | | 11 / 5 | 11 / 4 | 11 / 4 | **10 / 2** | 4 / 1 |
| test de signos unilateral (diagnóstico) | | 0,105 | 0,059 | 0,059 | 0,019 | 0,188 |
| acierto de equipo en frames ocultos (diagnóstico) | 0,607 | 0,702 | 0,774 | 0,774 | 0,769 | 0,658 |
| ídem, donantes con < 50% de balón | 0,598 | 0,697 | 0,740 | 0,740 | 0,748 | 0,693 |

`acierto` = exactitud de equipo en los frames vivos del GT público que el donante ocultó; no decide
nada. V2 y V3 dan el mismo `spellF1` en los 20 casos: con un solo cambio obligado y el mismo coste
en cualquier sitio, el Viterbi se reduce al punto de cambio de V2, y en el bloque 1 nunca encontró
evidencia suficiente (12,2 nats templados) para insertar una posesión oculta.

### (2) Slice público, sin degradar, pareado contra el motor (`full_match`)

| variante | `spellF1` | Δ | discordantes (motor–variante) | frames cambiados en el partido |
|---|---:|---:|---:|---:|
| motor | 0,4585 | | | |
| V1 | 0,4390 | −0,0195 | 0 (0–0) | 18.168 |
| V2 | 0,4585 | 0,0000 | 0 | 17.038 |
| V3 | 0,4585 | 0,0000 | 0 | 17.032 |
| V4 | 0,4585 | 0,0000 | 0 | 10.968 |
| V5 | 0,4585 | 0,0000 | 0 | 6.586 |

132 intervalos en el partido. Como se esperaba, el slice limpio apenas tiene huecos: V2–V5 no
mueven ni una posesión; V1 mueve bordes (Δ −0,0195 sin discordantes).

### (3) Informe de bloques (`tools/blocks.measure`), partido entero

| | motor | V1 | V2 | V3 | V4 | V5 |
|---|---:|---:|---:|---:|---:|---:|
| posesiones/min, partido | 3,64 | 3,67 | 3,64 | 3,64 | 3,65 | 3,64 |
| mín. / máx. bloque | 0,67 / 5,60 | 0,67 / 5,60 | 0,67 / 5,60 | 0,67 / 5,60 | 0,67 / 5,60 | 0,67 / 5,60 |
| acuerdo con el Smart Tagging | 73,1% | 70,8% | 72,2% | 72,2% | 72,8% | 74,0% |

Por bloque solo cambian 8, 9, 10, 16 y 22, en ±0,2–0,35 posesiones/min (todo en el JSON). El 0,67
del bloque 11 es del propio motor (decisión 26) y no lo toca ninguna variante.

### (4) Sin ground truth

Modelo fuera de muestra (bloques impares → pares y al revés, filas de huecos sintéticos), frente a
arrastrar el estado del motor con los mismos huecos:

| pliegue | filas | modelo | arrastrar |
|---|---:|---:|---:|
| impares → pares, +5 min | 20.774 | 0,745 | 0,619 |
| impares → pares, −5 min | 18.689 | 0,760 | 0,760 |
| pares → impares, +5 min | 14.567 | 0,743 | 0,642 |
| pares → impares, −5 min | 16.788 | 0,728 | 0,674 |
| **conjunto** | 70.818 | **0,744** | **0,674** |

Pesos sobre rasgos divididos por su RMS: `deep_s` −2,27, `mean_s` +1,07, `spread_y` +0,82,
`opp_half` +0,67, `before_far` +0,56, `interp_d_near` −0,56, `max_s` +0,50, `vel_s` +0,31,
`interp_d` +0,16, `after_near` +0,11, `spread_x` +0,05. Formación y balón cercano dominan; el
balón interpolado lejos de un extremo apenas cuenta.

Autobanco (`self_bench`; verdad = la cadena entregada con balón, así que el motor no es un techo):
`spellF1` / acierto en frames ocultos.

| desplazamiento | balón | motor | V1 | V2 | V3 | V4 | V5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| +2,5 min | 35,9% | 0,6758 / 0,612 | 0,6382 / 0,639 | 0,6679 / 0,696 | 0,6900 / 0,765 | 0,6945 / 0,740 | 0,6697 / 0,631 |
| +7,5 min | 37,2% | 0,7133 / 0,641 | 0,6322 / 0,685 | 0,6683 / 0,734 | 0,6772 / 0,775 | 0,6942 / 0,765 | 0,7128 / 0,703 |
| −2,5 min | 35,9% | 0,7217 / 0,685 | 0,6513 / 0,655 | 0,6892 / 0,729 | 0,7009 / 0,767 | 0,7073 / 0,773 | 0,7243 / 0,715 |
| −7,5 min | 37,2% | 0,7143 / 0,670 | 0,6727 / 0,689 | 0,7205 / 0,753 | 0,7414 / 0,823 | 0,7551 / 0,826 | 0,7281 / 0,742 |
| media | | 0,7063 / 0,652 | 0,6486 / 0,667 | 0,6865 / 0,728 | 0,7024 / 0,783 | 0,7128 / 0,776 | 0,7087 / 0,698 |

**El autobanco no ordena las variantes como el banco.** En exactitud por frame sí (todas suben,
V3/V4 lo que más), pero en `spellF1` da a V1 y V2 por peores que el motor y el banco las da por
mejores. La lectura más simple: su verdad es el propio motor, que fecha el cambio en el primer
control del rival; el ground truth humano parece fecharlo antes, al ganar el balón, y entonces
adelantar la frontera dentro del hueco acierta contra el GT y "falla" contra el motor. Es una
hipótesis, no está medida. Como instrumento para el partido entero, el autobanco vale para la
exactitud de equipo, no para `spellF1`.

### Compuertas, aplicadas tal como se pre-registraron

| variante | G1 (Δ ≥ +0,010; Δ poco balón ≥ 0) | G2 (mejor > peor) | G3 (Δ público ≥ −0,02) | G4 (estructura, ST ≥ −1 pt) | resultado |
|---|---|---|---|---|---|
| V1 | pasa (+0,0184; +0,0038) | pasa (11–5) | pasa (−0,0195) | **falla**: ST −2,4 pt | suspende |
| V2 | pasa (+0,0359; +0,0157) | pasa (11–4) | pasa (0) | pasa (−0,9 pt) | **aprueba** |
| V3 | pasa (+0,0359; +0,0157) | pasa (11–4) | pasa (0) | pasa (−0,9 pt) | aprueba |
| V4 | pasa (+0,0355; +0,0240) | pasa (10–2) | pasa (0) | pasa (−0,3 pt) | aprueba |
| V5 | **falla**: +0,0071 | pasa (4–1) | pasa (0) | pasa (+0,8 pt) | suspende |

Mayor media de donantes entre las aprobadas: V2 = V3 (0,3875); V4 queda a 0,0004. V2 es la más
simple de las tres. **Por la regla se recomienda V2.**

## 4. Recomendación

**Integrar V2 (`change`) en la cadena entregada**: dentro de cada hueco de balón cuyo equipo antes
y después difiere, un único cambio en el punto que mejor reparte la evidencia del modelo
autosupervisado; los huecos con el mismo equipo a los dos lados no se tocan. En el banco sube la
media de donantes de 0,3516 a **0,3875 (+0,036)** y la de poco balón de 0,2782 a 0,2938 (+0,016);
gana en 11 donantes y pierde en 4, y sube el acierto en frames ocultos de 0,61 a 0,77. En el slice
limpio es neutra (0,4585, 0 discordantes) y no cambia la estructura (3,64 posesiones/min). No
tiene parámetros propios: el arg-máx no depende de ningún umbral ni templado.

Lo que la regla no decide pero el coordinador debe saber:

- **V4 es casi un empate y es más prudente.** 0,0004 menos de media, pero mejor en poco balón
  (+0,024), menos donantes perdidos (10–2, el único con test de signos < 0,05), menos frames
  cambiados (10.968 frente a 17.038) y menos coste en el Smart Tagging (−0,3 frente a −0,9 pt). Un
  coordinador que quiera minimizar el riesgo en los bloques sin GT puede preferirla; sería una
  elección por prior, a declarar como tal, no por el número.
- **La ganancia está en la frontera, no en las posesiones ocultas.** V3 nunca insertó una posesión
  en el banco; V5, que casi nunca mueve la frontera, apenas gana. Lo que suma es fechar el cambio
  antes del primer control del rival.
- **Un `X` no lo arreglaría.** El scorer rellena `X` con la etiqueta previa, así que abstenerse en
  el hueco es el arrastre del motor (decisión 24).

Para integrarlo: `impute.impute(f, ev, VARIANTS["V2"])` devuelve el estado y las etiquetas sobre la
cadena de `engine.chain` con los mismos `D`. Solo numpy y pandas, determinista, ~1 s sobre el
partido. Necesita una entrada en `docs/DECISIONS.md` y que `tools/repro.py` lo construya en su
propio proceso (decisión 28); no lo he tocado, es del coordinador.

## 5. Limitaciones

- **Mismas 17 posesiones.** El banco mide 19 patrones de huecos sobre la misma ventana: los
  donantes no son independientes y un +0,036 se mueve con pocas posesiones. Es dirección
  consistente (11–4), no una medida del partido completo.
- **Huecos trasplantados, no reales.** En el banco los huecos caen sobre juego donde el balón se
  veía; los reales se concentran donde no se ve (en el aire, en el área). El modelo se entrena con
  el mismo truco (huecos desplazados sobre frames con balón), así que en el banco juega en su
  distribución; en los huecos reales puede rendir menos, como le pasó al carril F. Sin GT en esos
  bloques no se puede comprobar: el acuerdo con el Smart Tagging baja 0,9 puntos con V2, poco y
  dentro de la guarda, pero no sube.
- **Pseudo-etiquetas.** El modelo aprende a imitar al motor con balón (86% de acierto de equipo en
  frames vivos), no al GT; y el autobanco sugiere que el motor y el GT fechan los cambios distinto.
- **Compuerta casi empatada.** V2/V3 y V4 están a 0,0004; la regla elige por simplicidad, y otra
  regla razonable elegiría V4.
- **Exploración previa sin GT.** El diseño (rasgos de anclaje, extremo libre) se cambió tras mirar
  el autobanco, lo que está declarado en la sección 1. No se miró el banco ni el slice antes del
  pre-registro.
- **Sin datos externos.** No se usaron los partidos públicos de Metrica ni DFL para preentrenar.
  La nota del coordinador estimaba ~84% de acierto para el estado del arte en huecos de 10 s; aquí
  V2 llega al 77% en los frames ocultos del banco.
- **Un partido.** Pesos, direcciones de ataque y cifras son de BAR–ATH.
