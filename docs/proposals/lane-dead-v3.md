# Carril dead-v3 — dónde empieza una parada de los jugadores y quién reanuda

Estado: **pre-registrado**. Las secciones 1–6 se escriben y commitean antes de correr ninguna
variante contra el ground truth público. Todo lo que se cita aquí sale de los 7 partidos DFL/IDSSE
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
