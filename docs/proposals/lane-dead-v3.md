# Carril dead-v3 — dónde empieza una parada de los jugadores y quién reanuda

Estado: **medido — resultado negativo** (sección 9). Las secciones 1–6 se escribieron y commitearon
(`a27ebd6`) antes de correr ninguna variante contra el ground truth público; las 7–10 se añadieron
después, en un commit aparte, sin tocar las 1–6 salvo esta línea de estado. Todo lo que se cita aquí sale de los 7 partidos DFL/IDSSE
(estado vivo/muerto por frame) o del partido **sin** etiquetas (agregados).

## 1. Qué se propone

La cadena entregada (`engine.run()`, decisiones 30–36) marca `D` en las paradas etiquetadas (balón
fuera → reanudación del Smart Tagging) unidas a las paradas de los jugadores W1 (p90 de velocidad
de jugadores sobre ±1 s < 2 m/s, tramos ≥ 4 s). Quedaban dos preguntas abiertas:

1. **Bordes.** Una regla de velocidad dispara cuando los jugadores ya frenaron, y frenan *después*
   del pitido. ¿Cuánto llegan tarde el inicio y el final de una parada W1, y se corrige con una regla
   física fijada fuera del partido?
2. **Reanudación sin tag.** Tras una parada W1 sin reanudación etiquetada, el motor arrastra el
   equipo de antes de la parada hasta un control sin disputa del rival. El carril dead-v2 propuso
   dar el balón al **primer control tras la parada** (`model+first-control`) y nunca lo midió con
   W1.

`tools/dead_ball_v3.py` implementa las variantes sobre el motor entregado (`engine.DEFAULT`: regla
del duelo, reanudaciones etiquetadas con las decisiones 32/35) y cambia solo lo que dice cada
nombre. La variante `engine` reproduce `engine.run()` (se comprueba frame a frame al medir).

## 2. Lo que se miró antes de escribir esto

### 2.1 DFL (7 partidos, estado vivo/muerto por frame; decisión 37 lo permite para constantes físicas)

`python tools/dead_ball_v3.py dfl-edges --grid`. Cada tramo detectado se compara con el primer y el
último tramo `dead` verdadero que solapa; positivo = tarde. 645 tramos W1 emparejados.

| regla | precisión | recall | F1 | `%D` | inicio: mediana | inicio: mediana \|·\| | fin: mediana | fin: mediana \|·\| |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| W1 | 0,954 | 0,682 | 0,796 | 32,0% | **+5,36 s** | 5,44 s | **−0,68 s** | 1,08 s |
| `onset` (3,25 m/s, 40 s) | 0,919 | 0,790 | 0,849 | 38,5% | +0,52 s | 1,68 s | −0,68 s | 1,08 s |

(`dead` verdadero en DFL: 44,8% de los frames.)

**La hipótesis del brief se cumple a medias.** El inicio llega tarde, y mucho (mediana 5,4 s; p75
11 s): tras el pitido los jugadores siguen trotando varios segundos. **El final no llega tarde**: W1
termina 0,7 s *antes* de que el balón vuelva a estar vivo (los jugadores empiezan a moverse antes del
saque: carrera del lanzador, desmarques antes de un córner). Desplazar el final empeora su error
(+0,5 s: mediana −0,20 pero \|·\| 1,12 s; +1 s: \|·\| 1,52 s, exploración previa). **El final se deja
como está.**

**Regla de inicio `onset`** (inicio de la deceleración). Desde el primer frame de un tramo W1 se
camina hacia atrás mientras el p90 de ±1 s (la misma señal de W1) siga por debajo de `onset_mps`
con el p90 del frame conocido. El tramo se extiende **solo si** el camino termina en un frame donde
el campo se **vio** más rápido que eso. Si termina en otra cosa, el inicio no se observó y se queda
donde lo puso W1: en otra parada (el campo nunca aceleró entre las dos: el tramo vivo entre ellas
sigue vivo), en un frame sin cuantil (perder jugadores no es evidencia de que pararan), en una
**reanudación etiquetada** (el balón estaba en juego desde ahí: el mismo principio que
`dead_ball.stoppages`), en el borde del medio tiempo o tras `onset_cap_s`.

Una primera versión que extendía también hasta la parada anterior **fundía 16 pares de paradas** en
el partido (133 → 117 tramos `D`), borrando la posesión entre ellas; se descartó por principio antes
de ver ninguna etiqueta del partido, y las constantes se volvieron a elegir con la versión final.

**Constantes, elegidas en DFL con una regla:** entre los umbrales {3,0; 3,25; 3,5; 3,75 m/s} ×
tope {10; 20; 40 s} que mantienen precisión de frame ≥ 0,90, la menor mediana de \|error de
inicio\|. Ganan 3,25 m/s con 20 o 40 s (1,68 s, empate); se toma **40 s** porque es el `lookback_s`
que `dead_ball` ya usa como alcance de una parada y da más F1 (0,849 frente a 0,845). 3,25 m/s es
un trote (11,7 km/h); el p90 de juego vivo en nuestro partido tiene mediana 2,8 m/s (dead-v2 §2.1).

### 2.2 El partido, sin ground truth (`python tools/dead_ball_v3.py --explore`)

| | W1 (entregado) | `onset` |
|---|---:|---:|
| `%D` en los medios tiempos | 40,0% | 43,5% |
| `%D` de los jugadores solos | 34,5% | 39,0% |
| tramos `D` | 133 | 133 (ninguna fusión) |
| paradas sin tag que terminan con un control después | 44 | 43 |
| … cuyo primer control es del rival del equipo arrastrado | 14 | 14 |
| … donde el primer control y el primer control sin disputa difieren | 1 | 1 |

Así que la regla de reanudación cambia el equipo tras **14 de 44** paradas sin tag; el resto solo
confirma el equipo arrastrado. "Cualquier control" frente a "control sin disputa" difiere en **un**
caso: no merece una variante propia (se descartó `first-uncontested`).

## 3. Constantes (fijas; ninguna se barre contra el partido)

| constante | valor | de dónde |
|---|---:|---|
| `onset_mps` | 3,25 m/s (p90 de ±1 s) | DFL, regla de la sección 2.1 |
| `onset_cap_s` | 40 s | `dead_ball.Params.lookback_s`; en DFL 20 y 40 s empatan |
| final de las paradas W1 | sin cambio | DFL: ya termina 0,7 s antes, no después |
| W1 (2 m/s, ≥ 4 s, huecos < 1 s, ≥ 8 jugadores) | sin cambio | decisión 36 |
| primer control tras parada sin tag | `engine.control` (con o sin disputa) | reglamento: en la reanudación el rival está a distancia |

## 4. Variantes (tres, ni una más)

- **U1 `onset`** — cadena entregada con los inicios W1 llevados a su onset (sección 2.1).
  Unión con las paradas etiquetadas igual que `engine.delivered_dead`.
- **U2 `first-control`** — cadena entregada (`D` sin cambios) y cada parada que **no** contiene una
  reanudación etiquetada da el balón al equipo del **primer control tras ella** (con o sin disputa),
  desde su primer frame vivo (`dead_ball_v2.first_control_forcing` sin cambios; no se aplica si otra
  parada empieza antes de ese control; una reanudación etiquetada en el mismo frame gana).
- **U3 `onset+first-control`** — U1 y U2 juntas.

Referencia: **`engine`** = la cadena entregada (`bench.METHODS["engine"]`, `engine.run()`).

## 5. Mediciones (todas, para cada variante y para `engine`)

1. **Slice público:** `spellF1`, `macroF1`, posesiones predichas, precisión y recall de `D`
   (`--gt public`); Δ pareado, `n_discordant`, ganadas motor/variante con
   `tools/compare_submissions.py engine.csv V.csv --gt public`.
2. **Banco** (`python tools/dead_ball_v3.py --bench`): limpio, media de donantes, media con < 50% de
   balón, peor donante.
3. **Informe de bloques** (`tools/blocks.py`): `%D` y posesiones/min por bloque y en el partido,
   acuerdo con el Smart Tagging.
4. **DFL** (`python tools/dead_ball_v3.py dfl-score`): `spellF1` con el motor entregado y `D` de los
   jugadores, limpio y con nuestro balón. **Solo informe**: U2/U3 cambian posesión y la definición
   de DFL no es la nuestra (decisión 37); no entra en la selección.

## 6. Regla de selección (pre-registrada)

1. **Compuertas**, todas obligatorias, frente a `engine`:
   - **G1** slice: precisión de `D` **≥ 0,85**;
   - **G2** slice: Δ pareado de `spellF1` **≥ 0** y posesiones ganadas por el motor **≤** las
     ganadas por la variante (`wins_a ≤ wins_b`);
   - **G3** banco: media de donantes **≥** la de `engine` y media con poco balón **≥** la de
     `engine` (0,4351 / 0,3595 según la decisión 36; se usan las que dé el comando);
   - **G4** bloques: ningún bloque con **> 70%** de `D`, ningún bloque sin posesiones, y
     posesiones/min del partido en **3,4 ± 0,5** (referencia física; la entregada es 3,62);
   - **G5** acuerdo con el Smart Tagging del partido **≥** el de `engine` **− 1 punto**.
2. Entre las que pasan, se recomienda la primera en este **orden de prior**, sin mirar cuál tiene
   más `spellF1`: **U3 > U1 > U2**. U3 responde a las dos preguntas; U1 descansa en una constante
   física fijada fuera y con el mayor efecto medido en DFL (error de inicio 5,4 → 0,5 s); U2 descansa
   en el reglamento pero cambia el poseedor, que ningún juez externo puede validar.
3. Las diferencias de `spellF1` entre variantes que pasan no alteran el orden: 17 posesiones no
   ordenan métodos.
4. Si ninguna pasa, la recomendación es **mantener la cadena entregada** y el resultado se reporta
   como negativo.

---

*Lo que sigue se escribió después de medir. Las secciones 1–6 son las del commit `a27ebd6` sin
cambios, salvo la línea de estado.*

## 7. Cómo se reproducen los números

```bash
export MTAH_DATA_DIR=...                       # el bundle licenciado
python tools/engine.py --labels runs/dead_v3/delivered.csv
for v in engine onset first-control onset+first-control; do
  python tools/dead_ball_v3.py --variant "$v" --labels "runs/dead_v3/$v.csv" --gt public
done
for v in onset first-control onset+first-control; do
  python tools/compare_submissions.py runs/dead_v3/engine.csv "runs/dead_v3/$v.csv" --gt public
done
python tools/dead_ball_v3.py --bench
python tools/blocks.py runs/dead_v3/engine.csv runs/dead_v3/onset.csv \
    runs/dead_v3/first-control.csv runs/dead_v3/onset+first-control.csv
python tools/dead_ball_v3.py --explore         # sección 2.2, sin ground truth
# DFL (IDSSE en MTAH_EXTERNAL_DIR, la caché de tools/external.py)
python tools/dead_ball_v3.py dfl-edges --grid  # sección 2.1
python tools/dead_ball_v3.py dfl-score         # sección 8.4
```

**`engine` es la cadena entregada, byte a byte:** `runs/dead_v3/engine.csv` y la salida de
`tools/engine.py --labels` tienen el mismo SHA-256, `72c98ed4bb4a…` (el repro de la decisión 36), y
`tests/test_dead_ball_v3.py::test_the_engine_variant_reproduces_the_delivered_run` lo fija. Las
variantes son deterministas (solo numpy): `onset` `523e019e4806…`, `first-control`
`ecd6042ea9f1…`, `onset+first-control` `8202ae60ee8f…`. `runs/` está ignorado por Git.

## 8. Mediciones

### 8.1 Slice público (17 posesiones, 1.469 frames de `D`)

| cadena | `spellF1` | `macroF1` | Δ pareado | `n_discordant` (IoU 0,5) | ganadas motor/variante | posesiones pred. | precisión `D` | recall `D` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `engine` (entregada) | 0,5368 | 0,8533 | — | — | — | 21 | 0,877 | 0,897 |
| U1 `onset` | 0,5263 | 0,8585 | **−0,0105** | 0 | 0 / 0 | 21 | 0,867 | 0,933 |
| U2 `first-control` | 0,5368 | 0,8533 | 0,0000 | 0 | 0 / 0 | 21 | 0,877 | 0,897 |
| U3 `onset+first-control` | 0,5263 | 0,8585 | **−0,0105** | 0 | 0 / 0 | 21 | 0,867 | 0,933 |

| Δ `spellF1` por IoU frente a `engine` | 0,3 | 0,4 | 0,5 | 0,6 | 0,7 |
|---|---:|---:|---:|---:|---:|
| U1 `onset` / U3 | −0,0526 | −0,0526 | 0 | +0,0526 | 0 |
| U2 `first-control` | 0 | 0 | 0 | 0 | 0 |

U2 no cambia ni un frame graduado del slice: ninguna parada sin tag del bloque 1★ termina con un
primer control distinto del equipo arrastrado. U3 = U1 en el slice por lo mismo. El jackknife de
U1 contiene deltas de los dos signos (−0,022 .. +0,011): dirección, no prueba.

Diagnóstico posterior (agregados; no cambia la selección): U1 añade 80 frames de `D` predicho en el
slice, **54 de ellos `D` verdadero** (68%): también en la verdad de Metrica la parada empieza antes
de lo que dice W1. El Δ negativo es una posesión corta que deja de emparejarse a IoU 0,3–0,4, y otra
que pasa a emparejarse a IoU 0,6.

### 8.2 Banco de trasplante de huecos

| banco | limpio | media de donantes (n = 19) | media con < 50% de balón (n = 6) | peor donante |
|---|---:|---:|---:|---:|
| `engine` (entregada) | 0,5368 | 0,4351 | 0,3595 | 0,2400 |
| U1 `onset` | 0,5263 | **0,4296** | **0,3585** | 0,2400 |
| U2 `first-control` | 0,5368 | 0,4397 | **0,3592** | 0,2400 |
| U3 `onset+first-control` | 0,5263 | 0,4355 | 0,3606 | 0,2400 |

### 8.3 Informe de bloques (sin ground truth)

| cadena | `%D` en los medios tiempos | bloque con más `D` | posesiones (partido) | pos/min | acuerdo ST |
|---|---:|---:|---:|---:|---:|
| `engine` (entregada) | 40,0% | 65,5% (9) | 383 | 3,62 | 77,1% |
| U1 `onset` | 43,5% | 66,3% (9) | 372 | 3,51 | **77,8%** |
| U2 `first-control` | 40,0% | 65,5% (9) | 369 | 3,48 | **75,9%** |
| U3 `onset+first-control` | 43,5% | 66,3% (9) | 358 | 3,38 | 76,6% |

| bloque | balón | `%D` `engine` | `%D` U1 | pos/min `engine` | U1 | U2 | U3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1★ | 88,2% | 20,0% | 21,1% | 4,20 | 4,20 | 4,20 | 4,20 |
| 2 | 82,7% | 17,6% | 21,9% | 4,60 | 4,60 | 4,40 | 4,40 |
| 3 | 76,5% | 34,4% | 41,4% | 4,20 | 3,80 | 4,00 | 3,60 |
| 4 | 72,3% | 23,6% | 32,4% | 6,00 | 5,60 | 6,00 | 5,60 |
| 5 | 56,0% | 47,5% | 52,5% | 3,20 | 3,20 | 3,20 | 3,20 |
| 6 | 64,7% | 36,2% | 38,3% | 4,00 | 4,00 | 3,80 | 3,80 |
| 7 | 36,9% | 50,5% | 51,7% | 2,00 | 2,00 | 2,00 | 2,00 |
| 8 | 57,2% | 38,0% | 40,4% | 3,80 | 3,60 | 3,40 | 3,20 |
| 9 | 29,0% | 65,5% | 66,3% | 1,60 | 1,60 | 1,60 | 1,60 |
| 10 | 53,7% | 31,8% | 34,0% | 3,40 | 3,20 | 3,20 | 3,00 |
| 11 | 19,9% | 50,6% | 54,1% | 1,01 | 0,67 | 1,01 | 0,67 |
| 12 | 87,8% | 49,2% | 51,1% | 3,80 | 3,60 | 3,60 | 3,40 |
| 13 | 67,4% | 35,6% | 40,2% | 4,00 | 4,00 | 3,40 | 3,40 |
| 14 | 73,5% | 27,5% | 31,5% | 4,60 | 4,40 | 4,20 | 4,00 |
| 15 | 45,2% | 52,5% | 55,7% | 3,20 | 3,20 | 3,20 | 3,20 |
| 16 | 73,7% | 23,8% | 28,3% | 3,40 | 3,20 | 3,40 | 3,20 |
| 17 | 61,0% | 35,8% | 37,6% | 4,00 | 3,80 | 3,80 | 3,60 |
| 18 | 20,3% | 52,1% | 54,5% | 3,60 | 3,60 | 3,60 | 3,60 |
| 19 | 48,6% | 47,2% | 50,4% | 4,00 | 4,00 | 4,00 | 4,00 |
| 20 | 47,9% | 47,3% | 56,1% | 3,20 | 3,20 | 3,00 | 3,00 |
| 21 | 60,0% | 57,9% | 61,5% | 3,80 | 3,80 | 3,80 | 3,80 |
| 22 | 71,7% | 38,7% | 39,3% | 2,39 | 2,39 | 2,39 | 2,39 |

U2 tiene el `%D` de `engine` en todos los bloques. Ningún bloque queda sin posesiones.

### 8.4 DFL (7 partidos, motor entregado, `D` solo de los jugadores; solo informe)

| cadena | `spellF1` limpio | partidos que gana a `engine` | con nuestro balón | partidos que gana | pos/min (verdad 4,58) |
|---|---:|---:|---:|---:|---:|
| `engine` (W1) | 0,4172 | — | 0,3062 | — | 3,49 |
| U1 `onset` | **0,4354** | **7 de 7** | **0,3251** | **7 de 7** | 3,32 |
| U2 `first-control` | 0,4172 | 2 de 7 | 0,3016 | 1 de 7 | 3,24 |
| U3 `onset+first-control` | 0,4373 | 7 de 7 | 0,3223 | 7 de 7 | 3,08 |

## 9. Recomendación: **mantener la cadena entregada** (resultado negativo)

| compuerta | U1 `onset` | U2 `first-control` | U3 `onset+first-control` |
|---|---|---|---|
| G1 precisión `D` ≥ 0,85 | sí (0,867) | sí (0,877) | sí (0,867) |
| G2 Δ ≥ 0 y `wins_a ≤ wins_b` | **no (−0,0105; 0–0)** | sí (0,0000; 0–0) | **no (−0,0105; 0–0)** |
| G3 banco ≥ 0,4351 / 0,3595 | **no (0,4296 / 0,3585)** | **no (0,4397 / 0,3592)** | sí (0,4355 / 0,3606) |
| G4 bloque ≤ 70%, sin vacíos, 3,4 ± 0,5 pos/min | sí (66,3%, 3,51) | sí (65,5%, 3,48) | sí (66,3%, 3,38) |
| G5 acuerdo ST ≥ 76,1% | sí (77,8%) | **no (75,9%)** | sí (76,6%) |

Ninguna pasa las cinco. Por la regla de la sección 6, **la cadena entregada no cambia**.

Lo que queda como resultado, y vale más que la recomendación:

- **Pregunta 1, bordes: la mitad de la hipótesis era falsa.** En DFL un tramo W1 empieza 5,4 s tarde
  (mediana) y **termina 0,7 s antes**, no tarde. El final no hay que moverlo. El inicio se corrige
  con una regla física fijada fuera (`onset`, 3,25 m/s): error mediano 5,4 → 0,5 s, precisión de
  frame 0,954 → 0,919, recall 0,682 → 0,790. En el partido, el 68% del `D` que añade en el slice es
  `D` verdadero, sube el acuerdo con el Smart Tagging (+0,7 puntos) y gana en los 7 partidos DFL con
  y sin balón. Pero pierde en el slice (−0,0105, una posesión corta a IoU 0,3–0,4, 0 discordantes a
  0,5) y en el banco (−0,005 / −0,001), y el pre-registro exige no bajar. **Se reporta como no
  adoptado, no como refutado**: el banco y el slice usan las mismas 17 posesiones, y su pérdida es
  del tamaño de una posesión.
- **Pregunta 2, reanudación sin tag: negativa.** Cambia el poseedor tras 14 de 44 paradas sin tag,
  no toca el slice, sube la media del banco (+0,005) pero baja la de poco balón (−0,0003) y **baja el
  acuerdo con el Smart Tagging 1,2 puntos**: el único juez independiente del tracking dice que el
  primer control tras una parada sin tag nombra al equipo equivocado más a menudo que el arrastre.
  En DFL tampoco gana (2 y 1 de 7). La explicación probable (no comprobada) es que, sin balón visible
  en la reanudación (el bloque medio tiene 59% de balón), el primer control *observado* no es el
  saque sino un toque posterior, a menudo del rival.
- **U3** pasa G3 y G5 (el `onset` compensa lo que U2 quita) pero hereda la pérdida del slice de U1.

## 10. Limitaciones y lo que queda abierto

- **El slice no puede ordenar esto.** Los Δ son de una posesión (`n_discordant` 0 a IoU 0,5,
  jackknife de dos signos). La regla exigía "no bajar" y U1 bajó una posesión corta; con otra regla
  (por ejemplo "no bajar más de una posesión y ganar en DFL") U1 entraría. Esa sería una decisión
  **nueva**, pre-registrada antes de mirar nada más; aquí no se reinterpreta.
- **Lo que sí apoya a U1 fuera del slice:** DFL 7 de 7 (+0,018 limpio, +0,019 con nuestro balón),
  el acuerdo con el Smart Tagging (+0,7) y que el 68% del `D` añadido en el slice es verdadero. Lo
  que la contradice: el banco (−0,005), que trasplanta huecos sobre las mismas 17 posesiones.
- **`%D` 43,5%** con U1, frente a 40,0%: dentro del rango de la verdad DFL (41–52%) y por debajo del
  70% en todos los bloques (máximo 66,3%), pero el `%D` verdadero de Metrica fuera del slice no se
  conoce.
- **El final de las paradas** no se tocó porque DFL dice que no llega tarde. Los "3,9 s de `D` al
  inicio de una posesión" del slice que citaba el brief no son, por tanto, un final W1 tardío por
  esta vía; pueden venir de una reanudación etiquetada (frame estimado como inicio del tag + 5 s,
  decisión 30). No se investigó, para no leer el slice fuera del pre-registro.
- **U2 depende del balón visible en la reanudación.** Una versión que solo fuerce cuando el primer
  control llega pronto tras la parada (el saque, no un toque posterior) es la candidata natural; no
  se midió y necesitaría su propio pre-registro.
- **DFL** es Bundesliga con tracking corregido; la regla `onset` usa solo la velocidad de los
  jugadores, cuya distribución coincide con la nuestra (dead-v2 §2.2), pero el umbral es un único
  número sin validar frame a frame en Metrica.

## Revisión de código (PR #56)

- **"Difieren" contaba la ausencia (corregido).** `first_control_differs_from_first_accepted`
  contaba como "otro equipo" una parada sin ningún control sin disputa antes de la siguiente.
  Ahora se cuentan aparte (`first_control_vs_accepted`: `..._differs_...` y
  `first_control_without_uncontested_control`). Re-medido con `--explore`: W1 1 que difiere y 0
  sin control sin disputa de 44; `onset` 1 y 0 de 43. **La cifra "1 de 44" no cambia** y la
  sección 2.2 sigue valiendo.
- **Preámbulo compartido.** `chain` usa `engine.inputs` y sigue `params.duel` (antes también; ahora
  sin copia); `explore` también. Prueba sintética con `engine.DEFAULT` y `engine.D31`. La entrega
  sigue byte a byte igual (sha256 `72c98ed4bb4a…`).
- **Tipos.** `p90_window` y `dfl_players` anotados.
- **Deuda aceptada (8).** `speed_quantiles` se calcula dos veces por segmento y `floor_at` es un
  bucle O(n × barreras): rendimiento de un módulo de investigación.
- **Deuda aceptada (9).** Constantes y formateadores duplicados entre los módulos de la ronda 2.

## 10. Re-decisión bajo la aclaración del 3 de noviembre

La organización precisó el 3-nov-2026 que el ajuste debe hacerse con datos externos y que el ground
truth público no puede usarse para elegir (D44, regla 11 de AGENTS.md). Las compuertas **G2** (Δ del
slice) y **G3** (banco, que son las mismas 17 posesiones) de la §6 dejan de vetar: leer el slice para
rechazar también es elegir con el ground truth. **G1** se degrada a línea de reporte por la misma
razón. Quedan como compuertas las que no leen verdad del partido:

| compuerta admisible | qué exige | `engine` | U1 `onset` |
|---|---|---:|---:|
| **E1** DFL (CC-BY, 7 partidos) | gana 7/7 en F1 de `D`; constantes fijadas allí | 0,796 | **0,849** |
| **E2** estructura de bloques, sin GT | ningún bloque > 70% de `D`, 3,4 ± 0,5 pos/min | 65,5% / 3,62 | **66,3% / 3,51** |
| **E3** Smart Tagging (dato generado, no GT) | acuerdo ≥ `engine` − 1 punto | 77,1% | **77,8%** |
| **E4** precio del tiempo añadido, sin GT | cero fusiones; segmentos cortos | — | **0 fusiones, mediana 41 frames** |

Las tres primeras venían del carril; la cuarta es nueva (`tools/dead_price.py`,
`docs/analysis/dead-price.md`). U1 añade **5.646 frames** (3,55% de los medios tiempos) en **83
segmentos**, mediana **41 frames** (1,6 s), máximo 322 (12,9 s), y **ninguna fusión**: no borra la
posesión entre dos paradas, que era el motivo por el que la §2.1 descartó la primera versión de la
regla. En esos frames el balón se ve en el 46% (29% en el `D` de `engine`, 59% en juego) y rueda a
3,07 m/s de mediana (2,13 en `D`, 5,08 en juego): son frames de trote, no de juego.

**Veredicto.** Se recomienda **adoptar U1**, no U3. U2 falla E3 por sí sola (75,9%, por debajo de
`engine` − 1) y U3 la arrastra: su mitad de reanudación no está corroborada por ningún juez
admissible. U1 es la única variante que gana el árbitro externo (7/7), pasa las tres compuertas sin
ground truth y no tiene evidencia local en contra (Δ del slice −0,0105 con **0** posesiones
discordantes a IoU 0,5; 54 de los 80 frames añadidos al slice eran `D` verdadero).

**Cómo se entrega.** El cambio no se aplica por defecto en este documento: mueve el CSV enviado
(5.646 frames) y el SHA de la cadena. La secuencia, con la aprobación del lead:

```bash
export MTAH_DATA_DIR=...                   # bundle licenciado
python tools/dead_ball_v3.py --variant onset --labels submissions/engine.csv
make repro                                 # dos builds desde cero, byte a byte
python evaluation/validate_submission.py submissions/engine.csv
python tools/score.py --results submissions --note "u1"   # una sola vez, in-sample
```

**Riesgo que queda.** El precio del tiempo añadido no demuestra que esos frames sean `D`: el balón
se ve en casi la mitad y la proximidad a un `SET PIECES` (37% de los segmentos a ≤ 30 s, frente a una
tasa base de ~28%) apenas distingue. Lo que sostiene la decisión es el corpus externo —donde el
inicio de W1 llega 5,4 s tarde y `onset` lo lleva a 0,5 s— y la física: W1 solo puede dispararse
después de que el campo haya dejado de correr.
