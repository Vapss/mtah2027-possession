# Posesión por frame a partir del último balón controlado

**Documento técnico — More than a Hack 2027 (Metrica Sports + FC Barcelona), Fase 1.**
Equipo: TODO (nombre del equipo; el archivo entregado debe llamarse `<equipo>.md`/`<equipo>.pdf`).

Convenciones. `Dnn` es la entrada `nn` de [`docs/DECISIONS.md`](DECISIONS.md); los carriles de
investigación están en `docs/proposals/lane-*.md` y las tablas generadas en `docs/analysis/`. Cada
número de este documento está copiado de esas fuentes, que dicen cómo regenerarlo. Los números
marcados con ⟨r2⟩ dependen de la cadena entregada final y se refrescan tras la ronda 2. "Slice"
es la ventana pública de 5 minutos con ground truth (bloque 1★, 17 posesiones); "partido" son los
dos medios tiempos (158.857 frames graduados). Los datos del partido son licenciados: aquí solo hay
agregados ya publicados en el repositorio.

---

## 1. Resumen

Etiquetamos cada frame con el equipo del **último balón controlado**: un frame es de control cuando
el balón se ve dentro del campo, va lento y tiene a un jugador a ≤ 1,5 m sin un rival igual de
cerca; entre controles el estado se arrastra. Un control del rival no cambia la posesión si el
equipo que la tiene también llega al balón (un duelo). El balón muerto (`D`) es la unión de las
paradas etiquetadas (balón fuera → reanudación del Smart Tagging) y de las paradas que se leen en
los jugadores (nadie corre durante ≥ 4 s). Cada reanudación etiquetada con equipo da el balón a quien saca,
salvo que el tracking ya haya visto el juego reanudado. No hay ventana de suavizado, ni modelo
aprendido, ni pesos: solo umbrales físicos fijados antes de medir, en numpy y pandas.

| instrumento | `smooth50` (suelo oficial) | cadena entregada | fuente |
|---|---:|---:|---|
| `spellF1` partido completo (oficial) | **0,2433** | desconocido (GT privado) | EVALUATION.md |
| `spellF1` slice público | 0,3256 | 0,5368 ⟨r2⟩ | D36, `engine-sensitivity.md` |
| `macroF1` slice público | 0,6207 | 0,8533 ⟨r2⟩ | D12, `engine-sensitivity.md` |
| banco de trasplante: media de 19 donantes | 0,2150 | 0,4351 ⟨r2⟩ | `bench.md` |
| banco: media de los 6 donantes con < 50% de balón | 0,1657 | 0,3595 ⟨r2⟩ | `bench.md` |
| banco: peor donante | 0,0842 | 0,2400 ⟨r2⟩ | `bench.md` |
| bloques: posesiones/min del partido (slice: 3,4) | 5,61 | 3,62 ⟨r2⟩ | `blocks.md` |
| bloques: acuerdo con el Smart Tagging | 67,2% | 77,1% ⟨r2⟩ | `blocks.md` |
| bloques: `%D` del partido / bloques sin posesión | 32,3% / 0 | 40,0% ⟨r2⟩ / 0 | `blocks.md`, D36 |

El banco está calibrado contra los números oficiales: para `smooth50` predice 0,2150 frente al
0,2433 oficial, algo pesimista (D33). Es la estimación más honesta que tenemos del partido completo.

## 2. El problema, y por qué `spellF1` decide todo

`spellF1` trata cada posesión (una racha máxima de `H` o de `A` con el balón vivo) como un objeto y
la empareja con la verdad por IoU temporal, promediando umbrales 0,3–0,7 (EVALUATION.md). Un
método que parpadea entre equipos puede tener buen acierto por frame y `spellF1` cercano a cero: los
cuatro baselines oficiales son el mismo algoritmo y `macroF1` se mueve 0,04 mientras `spellF1` se
mueve un factor cinco. Por eso todo criterio de aceptación es un Δ`spellF1` pareado, nunca
`macroF1` ni `f1_D` (D12): marcar los `SET PIECES` como `D` sube `macroF1` en 0,047 y **baja**
`spellF1` en 0,052.

La segunda restricción es la muestra. El slice tiene 17 posesiones: perder una mueve `spellF1`
unos seis puntos, y el bootstrap del baseline da un intervalo 5–95 de 0,2667..0,5939 (D3). Peor
aún, el slice es la parte más fácil del partido: tiene balón detectado en el 88,2% de sus frames,
frente al 56,9% del partido y al 19,9–36,9% de los bloques 7, 9, 11 y 18 (D13, D26). Elegir con el
slice ya engañó a los organizadores con un solo parámetro: `smooth125` gana en el slice (0,4242) y
pierde en el partido (0,2242 frente a 0,2433) (EVALUATION.md). La metodología de la sección 3
existe para no repetir ese error.

## 3. Metodología de evaluación que construimos

**Comparación pareada y jackknife** (D17, D21). `tools/compare_submissions.py` puntúa dos CSV con
el scorer oficial y reporta el Δ por umbral, las posesiones ganadas y perdidas a IoU 0,5
(`n_discordant`) y un jackknife que quita una posesión verdadera cada vez. Una victoria exige ≥ 6
posesiones discordantes en el mismo sentido (test de signos p ≤ 0,031, D29); con menos, un Δ es
dirección, y un jackknife que cambia de signo lo dice.

**Informe estructural en 22 bloques** (D26, `tools/blocks.py`). Cada medio tiempo se corta en
bloques de 7.500 frames; el bloque 1 es exactamente la ventana pública. Sin ground truth, se
describe cada bloque: balón detectado, posesiones/min, duración media, la parte del bloque que
cubre la posesión más larga, `%D` y el acuerdo con el **Smart Tagging**, la única señal
independiente del tracking (una fase ofensiva vota por su equipo, una defensiva por el otro). Es
cordura, no métrica: no se optimiza, pero bloquea una configuración que deja un bloque fuera de lo
físicamente plausible. El acuerdo no es acierto: en el slice el Smart Tagging cubre el 70,5% de los
frames vivos y acierta el 68,0% (D26).

**Banco de trasplante de huecos** (D33, `tools/bench.py`). El patrón de balón ausente de cada uno
de los otros 19 bloques completos se trasplanta sobre la ventana pública y se puntúa contra su
ground truth real: mide robustez a la cantidad y longitud de balón perdido. Calibración: para los
baselines reconstruidos da 0,0345 / 0,1854 / 0,2150 con ventanas 0 / 25 / 50, frente a 0,0486 /
0,1996 / 0,2433 oficiales. No predice `smooth125` (0,2910 frente a 0,2242), porque conserva la
estructura de posesiones del bloque 1; para un método con escala temporal propia el guardarraíl
sigue siendo el informe de bloques.

**Corpus externo DFL/IDSSE** (`lane-external.md`, `docs/analysis/external*.md`). Siete partidos
abiertos de la Bundesliga con estado vivo/muerto y equipo en posesión por frame (Bassek et al.
2025, CC-BY 4.0), puntuados con el scorer oficial, limpios y con nuestro patrón de balón
trasplantado. Su compuerta de dominio **falla**: 4,58 posesiones/min, mediana de 3,8 s y 41–52% de
`D`, frente a 3,4/min, 7,6 s y 19,6% en nuestro slice. Por la regla escrita antes de puntuar, no
fija escalas de tiempo ni reglas de `D` por su puntuación; sí sirve para robustez y reglas sin
escala temporal. Reproduce la caída relativa del banco por balón perdido (−28% frente a −34% en
`smooth50`) y su orden de métodos, lo que valida el banco desde fuera.

**Pre-registro.** Cada carril escribió y commiteó sus variantes, compuertas y regla de elección
antes de medir, y las secciones de resultados se añadieron después sin tocar las anteriores. La
regla se aplica aunque elija un número menor: entregamos I1 (0,4585) en vez de I0 (0,4667) (D30),
la regla del duelo en vez de la combinación con mejor slice (0,5829) (`lane-decode.md` §9) y el
detector de una sola regla en vez del modelo logístico (0,4762 frente a 0,5026)
(`lane-dead-v2.md` §9). Cuando una premisa resultó falsa al medir, se declaró la desviación (D31).

## 4. El método

La verdad se deriva mecánicamente del tracking corregido: `D` donde marca el balón muerto y, si no,
el equipo que nombra como poseedor (CHALLENGE.md). La pregunta es qué significa ahí "poseer"; la
respuesta del reto es *control*: la posesión cambia cuando el rival gana el balón controlado, y en
balones disputados o sueltos se queda con el último equipo. El motor (`tools/engine.py`) implementa
esa frase, sin ventana ni prior de duración.

### 4a. Control y arrastre (D29)

Un frame es de **control** para un equipo cuando el balón está observado y dentro del campo, el
jugador más cercano de ese equipo está a ≤ 1,5 m, el rival no está igual de cerca y el balón va a
≤ 5 m/s. La posesión es el equipo del último control, arrastrada dentro de cada medio tiempo; un
cambio se fecha en el primer frame de control rival (`dwell = 1`). Antes del primer control de un
medio tiempo se escribe `X`, que el scorer rellena.

Las razones son físicas y se fijaron antes del barrido: 1,5 m es alcance más ruido del tracking (la
distancia mediana balón→jugador es 1,84 m); 5 m/s es una conducción rápida, mientras un pase va a
10 m/s o más. El filtro de velocidad ataca la raíz del parpadeo: en el slice el jugador más cercano
es del equipo correcto en el 91,1% de los frames con el balón a < 2 m/s, en el 66,4% a 10–20 m/s y
en el 38,8% a > 20 m/s; con el balón en vuelo el más cercano suele ser un rival que pasa cerca
(D29). Un balón fuera del campo no se controla (D31): no está en juego. El barrido pre-registrado de
27 configuraciones (radio 1,0/1,5/2,0 × velocidad 3/5/7 × `dwell` 1/5/12) sobre la cadena entregada
no encuentra **ninguna** que gane al default por la regla: `spellF1` 0,3680..0,5375 frente a
0,5368 ⟨r2⟩ (`engine-sensitivity.md`).

### 4b. La regla del duelo (D34)

Un control del rival solo cambia la posesión si el jugador más cercano del equipo que la tiene está
a **más** de 1,5 m del balón. Si los dos equipos alcanzan el balón es un duelo, y por la definición
del reto la posesión se queda donde estaba. Es la regla de que un duelo anula la posesión de
Vidal-Codina et al. (2022), con el radio que ya usa el motor y sin constante nueva. Antes de
adoptarla, el 5,9% de los frames de control eran disputados y 63 de los 340 cambios naturales del
partido empezaban en uno (`lane-decode.md` §2b). Efecto medido sobre la cadena de entonces: slice
0,4585 → 0,5189 (0 discordantes, jackknife todo positivo), banco 0,3516 → 0,3792 (poco balón
0,2782 → 0,3021), acuerdo con el Smart Tagging 73,4% (D34).

### 4c. Balón muerto: paradas etiquetadas ∪ paradas de los jugadores

`D` no se detecta con un umbral sobre el balón (D16): en el slice el balón está ausente en el 33,6%
de los frames `D` y se ve fuera del campo solo en el 7,1%; dentro de `D` rueda a 2,70 m/s de mediana y está
a 2,89 m del jugador, así que ni está quieto ni está solo. Una parada es un **intervalo**.

- **Paradas etiquetadas** (D30, `lane-d.md`, variante `out`). Cada `SET PIECES` del Smart Tagging
  es una ventana fija de 35 s (5 s en los saques de centro) alrededor de la reanudación, que
  estimamos en el inicio del tag + 5 s (+ 3,5 s en un saque de centro, medido en los dos saques de
  inicio: 3,52 y 3,28 s). La parada empieza en el último episodio de balón visto fuera del campo
  en los 40 s anteriores (120 s tras un gol) y termina en la reanudación. En el slice: precisión de
  `D` 0,907, recall 0,384. Una salida de menos de 1 s también abre parada: el 55% de las salidas
  dura menos de un segundo porque la cámara táctica ve el balón fuera solo un instante (D31).
- **Paradas de los jugadores** (D36, regla W1 de `lane-dead-v2.md`). Cuando el árbitro para el
  juego nadie esprinta. Se marca cada tramo de ≥ 4 s en que el percentil 90 de las velocidades de
  los jugadores (el segundo más rápido de ~21), promediado sobre ±1 s, va por debajo de 2 m/s;
  cerrando huecos vivos de < 1 s, medio tiempo a medio tiempo, y nunca con menos de 8 jugadores
  seguidos (perder jugadores no es evidencia de que se pararan). No mira el balón ni las
  identidades, así que sobrevive a los huecos de balón y a los cambios de slot. **Todas las
  constantes se fijaron en los 7 partidos DFL**, no en nuestro slice: allí el 93% de los frames con
  ese p90 < 2 m/s es `dead`, y el decodificador (cerrar huecos vivos de < 1 s, descartar paradas de
  < 4 s) salió de una rejilla sobre DFL con nuestro patrón de balón perdido superpuesto. Lang et al.
  (2022), con identidades de jugador, reportan un 92% de acierto en esta tarea; la regla no usa
  identidades (`lane-dead-v2.md` §2.2).

Resultado de la unión (D36): recall de `D` en el slice 0,384 → 0,897 ⟨r2⟩ con precisión 0,877 ⟨r2⟩;
banco 0,3792 → 0,4351 ⟨r2⟩ (poco balón 0,3021 → 0,3595 ⟨r2⟩); acuerdo con el Smart Tagging 73,4% →
77,1% ⟨r2⟩; en DFL, sobre el motor anterior, 0,376 → 0,432 en los 7 de 7 partidos. El slice da
0,5189 → 0,5368 ⟨r2⟩ con una sola posesión discordante: la evidencia fuerte son las tres fuentes
independientes del slice.

### 4d. Reanudaciones (D30, D32, D35)

Tras una parada siempre hay un poseedor claro (CHALLENGE.md): quien saca un lateral, un córner, una
falta o un saque de puerta tiene el balón. En el frame de reanudación de cada `SET PIECES` con
`Team` conocido, el decodificador **fuerza** la posesión de ese equipo. Como ese frame es una
estimación, solo se fuerza si en la ventana `[inicio del tag, reanudación)` el tracking no ha visto
ya un control que el decodificador acepta (no un duelo): una observación vale más que una
estimación (D32, D35). En el partido, 10 de las 27 reanudaciones con equipo conocido ya tenían un
control en su ventana, en 2 de ellas del rival, y se fuerzan 17 (D32). Si dos reanudaciones caen en
el mismo frame con equipos distintos, no se fuerza ninguna.

## 5. Activos: cuáles usamos, cómo, y cuáles descartamos

| activo | uso | por qué |
|---|---|---|
| Tracking ATD táctico | **usado**: control, duelo, paradas de los jugadores | La pertenencia a equipo sale del XML (24 slots locales, 22 visitantes; D18). El balón se lee del último campo de cada línea: 113.488 de 199.319 frames (56,9%) (D14). |
| Smart Tagging | **usado**: `SET PIECES` (inicio de la reanudación y `Team`) | 59 reanudaciones etiquetadas: 26 saques de banda, 12 córners, 10 saques de puerta, 5 tiros libres, 4 saques de centro tras gol y 2 de inicio (`lane-d.md` §2). Intervalos semiabiertos (D8). |
| Smart Tagging, fases de juego | **solo validación** | Votos de equipo en el informe de bloques (D26). Nunca entran como rasgo ni como etiqueta, para que la validación no sea circular (`lane-f.md`). |
| Homografía táctica | **usada por el carril de vídeo** | Proyecta las detecciones del vídeo al campo (`lane-ball-video.md`). La cadena entregada no la necesita: el ATD ya viene en coordenadas de campo. |
| Vídeo táctico | **probado; detector COCO negativo** | Ver abajo. |
| Vídeo y tracking broadcast | **no usado** | Ver abajo. |
| Datos externos DFL/IDSSE | **usado** para fijar las constantes de W1 y como árbitro | Sección 3; revirtió V6 y confirmó la alarma de escala temporal de `touch` (sección 6). |
| Metrica sample data | **descartado como ground truth** | Solo eventos: el `D` habría que construirlo con nuestras propias reglas, y validar con ellas sería circular (`lane-external.md` §1.1). |

**Vídeo táctico.** El carril ball-video intentó recuperar el balón donde el ATD lo pierde, con
YOLO11x COCO `sports ball` a resolución nativa (el balón mide ~6 px). Como rastreador de posición
no es defendible: precisión ≤ 0,75 a 2 m del ATD y recall ≤ 0,46. La etapa 1 pre-registrada lo
cerró: rellenando huecos *trasplantados* el banco sube mucho (+0,077 de media en la variante
estricta), pero rellenando los huecos *reales* del slice las tres variantes pierden
(Δ −0,0585 / −0,0213 / −0,0670, todas bajo la compuerta Δ ≥ −0,02), porque los huecos del ATD
están donde el balón es difícil de ver y ahí el detector encuentra otra cosa
(`lane-ball-video.md` §3, rama `research-ball-video-lane`). Detector afinado con etiquetas del
ATD: **[pendiente ronda 2]**.

**Broadcast.** No está sincronizado con el táctico (su propia línea de tiempo, con cortes y
repeticiones) y su homografía solo es utilizable en el 65,8% de los frames (DATA.md). La fusión solo
actúa donde el táctico no ve el balón, que es justo el régimen que el slice no muestrea; el backlog
decidió no tomar ninguna decisión de fusión con evidencia del slice y dejar el artefacto con peso 0
(D13).

## 6. Lo que probamos y rechazamos

| intento | qué era | el número que lo rechazó | fuente |
|---|---|---|---|
| Ventanas de suavizado | voto mayoritario del jugador más cercano | `smooth125` gana en el slice (0,4242) y pierde en el partido (0,2242) | EVALUATION.md |
| Respaldo `smooth50` + arrastre en huecos | la entrega de seguridad | 0,3805 en el slice pero 0% de `D`, acuerdo ST 62,2% y una posesión que cubre el 77,2% del bloque 18; el motor la supera (0,4585, ST 73,1%) | D25, D26, D30 |
| `D` en los huecos de balón | hueco = parada | pierde o empata en cada tramo medible: −0,00740 (≤ 25 frames); +0,02680 frente a +0,05491 del arrastre (126–500) | D24 |
| Emisión B5 por voto suave | voto top-5 gaussiano + contexto | ninguna variante mejora al `argmin` calibrado: log-loss 0,5228 frente a 0,4705 | D19 |
| Post-proceso B6 | absorber segmentos de 1–14 frames | +0,14094 sobre su baseline, pero la cadena B5 + B6 queda en 0,1851, bajo el respaldo | D20, D25 |
| Relleno por formación (carril F) | forma del equipo dentro de los huecos | acuerdo ST en huecos 71,3% → 72,9%, bajo la compuerta de +2 puntos; una variante −0,029 en el slice | D30, `lane-f.md` |
| Imputación V2 en huecos | un cambio dentro del hueco, por modelo autosupervisado | banco 0,3516 → 0,3875, pero el ST coincide con el nuevo equipo en el 43% de los frames cambiados y su acuerdo en los bloques 7/9/11/18 cae de 72,4% a 66,0%; fuera, sin declararla negativa | D34, `lane-impute.md` |
| Viterbi (V4) | control blando + coste de cambio | −0,0471 en el slice (3–1 en contra), banco 0,3396; falla las tres compuertas; DFL degradado 0,1740 frente a 0,2631 | `lane-decode.md` §8, `external-decoder.md` |
| `touch` (V3) y V5 | deshacer posesiones rivales < 2 s | V5 falla la compuerta de bloques (bloque 16: 1,60 frente a 4,00 pos/min); en DFL ambos pierden 7/7 contra su referencia con el ritmo más lejos de la verdad | `lane-decode.md` §9, `lane-external.md` §6 |
| V6 = duelo + fecha en el punto medio | redatar cada cambio | slice 0,5405 y banco 0,3944, pero en DFL degradado 0,2319 frente a 0,2394 y V2 gana 6 de 7: revertida | D34 |
| Modelos aprendidos de balón muerto (W2–W4) | logística ridge sobre 29 rasgos, fijada en DFL | 0,5026 en el slice, pero precisión de `D` 0,787 < 0,80 (W4: 0,761) por desborde en los bordes | D36, `lane-dead-v2.md` §9 |
| Quietud hacia atrás tras gol (`out+still`) | extender la parada mientras el campo está quieto | el bloque 7 llega a 50,4% de `D` (compuerta: < 50%): la quietud antes del saque tras un gol se estira hasta el tope de 120 s | `lane-d.md` §9–10 |
| Mínimo de 1 s fuera para abrir parada | filtrar "ruido de línea" | los 77 frames eliminados en el slice eran `D` real; revertida | D31 |

## 7. Limitaciones, y qué haríamos con más tiempo

- **Bloque 11.** Con 19,9% de balón, una posesión de 163 s tiene balón en el 17,5% de sus frames y
  ~78 s dependen de un duelo de 0,2 s justo tras un hueco de 69,5 s (D34). Ni la decodificación ni
  el Smart Tagging deciden ese tramo; es un problema de huecos de balón.
- **Los huecos trasplantados no son huecos reales.** El banco quita el balón donde se veía; los
  huecos reales ocurren en balones aéreos, pelotazos y áreas llenas. Por eso la imputación gana en
  el banco y el Smart Tagging la contradice (D34), y por eso el detector COCO sube el banco y pierde
  en el slice (sección 5).
- **Los bordes de `D`.** Todo el `D` falso de W1 en el slice es desborde en los bordes de paradas
  reales (185 frames de desborde, 152 sin cubrir), y el acierto de equipo en vivo baja de 0,835 a
  0,814 (`lane-dead-v2.md` §8, §10). El 40,0% ⟨r2⟩ de `D` del partido, con máximo de 65,5% ⟨r2⟩ en
  el bloque 9 (D36), está dentro del rango DFL (40,7–51,7%) pero muy por encima del 19,6% del slice; la
  definición de parada de Metrica podría ser otra, y fuera del slice no se puede comprobar. Siguen
  abiertos: un parpadeo de balón fuera hasta 40 s antes de una falta sin salida real (D31), las 29
  paradas que son solo los 3,5–5 s del tag y los tiros libres, cuyo golpeo cae cerca de +10 s y no
  +5 s (`lane-d.md` §10).
- **17 posesiones.** Casi todos los Δ del slice tienen 0–2 posesiones discordantes; ninguno llega a
  las 6 que pide una victoria. Las decisiones descansan en el banco, el Smart Tagging y DFL.
- **El Smart Tagging no es un árbitro.** Acierta el 68,0% de los frames vivos que cubre en el slice
  (D26), aunque el 98% de los 391 frames vivos **sin balón** (D34): dentro de un hueco real es fiable,
  en general no.
- **El duelo no se generaliza a DFL.** Allí la regla del duelo queda por debajo de la regla de
  control desnuda (0,2394 frente a 0,2631 degradado, 0 de 7 partidos) y baja el ritmo degradado a
  1,81 posesiones/min, frente a 2,34 de la regla desnuda y 4,58 de la verdad (`external-decoder.md`). El corpus castiga fusionar
  posesiones porque su verdad es más fina que la nuestra, así que es una alarma y no un veredicto
  (`lane-external.md` §2.6); el radio del duelo (1,5 m) es además holgado frente a los 0,5–1 m de la
  literatura (`lane-decode.md` §10).
- **La fecha de los cambios.** La mejor regla de fecha empareja 6 de 20 transiciones del slice a
  ±1 s; los errores grandes son cambios equivocados, no mal fechados (`lane-decode.md` §10).

Con más tiempo: el detector de balón afinado con etiquetas del ATD (ronda 2) y, si recupera balón
en huecos reales, reevaluar la imputación con verdad física (D34); `rule+first-control`, la
candidata natural para dar el balón tras una parada sin tag (`lane-dead-v2.md` §10); una quietud
tras gol con tope de 40 s y el modelo de `D` con otra compuerta, cada uno con su propio
pre-registro (`lane-d.md` §10, `lane-dead-v2.md` §10).

## 8. Reproducción

**Entorno.** Python 3.12.3, numpy 2.5.4 y pandas 3.0.6, fijados en `pyproject.toml`,
`.python-version` y `uv.lock` (D27). El camino que genera el archivo solo usa numpy y pandas: sin
red, sin semillas, sin pesos aprendidos (AGENTS.md, regla 8).

```bash
uv sync --locked --no-dev --inexact          # = make install
```

**Datos.** El bundle licenciado no está en el repositorio. Se descomprime en `./data` o se apunta
`MTAH_DATA_DIR` a donde esté (`games.py`, DATA.md):

```bash
export MTAH_DATA_DIR=/ruta/al/bundle         # PowerShell: $env:MTAH_DATA_DIR = "D:\mtah2027"
```

**Generar la entrega** (artefacto → ensamblador → validador oficial):

```bash
make engine
# equivale a (el build ya pasa el validador oficial; se repite sobre el archivo exacto que se sube):
python tools/engine.py --build runs/engine --submission submissions/engine.csv
python evaluation/validate_submission.py submissions/engine.csv
```

**Comprobar que se reproduce.** `tools/repro.py` construye la cadena dos veces desde cero, cada una
en su directorio borrado, y compara los bytes entre sí y con el archivo entregado (D28):

```bash
python tools/repro.py --against submissions/engine.csv       # = make repro
```

Sale con 0 e imprime un único SHA-256 si coinciden; el de la cadena actual empieza por
`72c98ed4bb4a` ⟨r2⟩ (D36). La cadena vive en Python, no solo en el Makefile, porque `make` no viene
en un Windows de serie (D28).

**Tiempo de ejecución.** TODO: no hay una medición publicada de la cadena completa. Lo medido: la
primera carga del tracking cuesta 3 s y 230 MB por proceso (D14) y las paradas de los jugadores
añaden unos 15 s por corrida (`lane-dead-v2.md` §9); `make repro` cuesta el doble porque construye
dos veces (D28).

## Referencias

- Bassek, M., Rein, R., Weber, H., Memmert, D. (2025). *Scientific Data* 12:195,
  doi:10.1038/s41597-025-04505-y. Datos IDSSE/DFL, CC-BY 4.0; depósito figshare
  doi:10.6084/m9.figshare.28196177 (usamos el espejo `pysport/idsse-data`, `lane-external.md` §1.1).
- Vidal-Codina, F. et al. (2022): el duelo anula la posesión. TODO: referencia bibliográfica
  completa (en las fuentes solo aparece citada por autor y año, `lane-decode.md` §2c).
- Lang, S. et al. (2022): detección de paradas desde el tracking. TODO: referencia bibliográfica
  completa (`lane-dead-v2.md` §2.2).
- Kim et al. (2023). TODO: ninguna fuente del repositorio cita este trabajo; falta indicar qué
  aporta y su referencia completa antes de mantenerlo aquí.
- Link, D., Hoernig, M. (2017): la posesión de equipo empieza en el primer toque tras el de un
  rival; contexto del carril decode, no usado en la entrega (`lane-decode.md` §2c).
