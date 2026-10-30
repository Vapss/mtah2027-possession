# Lane F — evidencia de formación dentro de los huecos de balón

Propuesta para el motor de posesión (#6, `tools/engine.py`). Código: `tools/formation.py`,
pruebas: `tests/test_formation.py`. Este documento no cambia el motor ni `docs/DECISIONS.md`: el
coordinador integra.

## 1. Pre-registro

Escrito y comprometido en git **antes** de leer ground truth o resultados del Smart Tagging. Lo
único medido antes de escribirlo son agregados del tracking para fijar la convención de
coordenadas: `x`, `y` normalizadas a `[0, 1]` desde una esquina (rango observado −0,04..1,04), y
el orden de los centroides de equipo por mitad (el visitante tiene el centroide en `x` mayor en el
97,6% de los frames de la 1.ª mitad y en `x` menor en el 96,6% de la 2.ª: los lados se cambian en
el descanso, como debe ser).

### Problema

El motor etiqueta cada frame con el equipo del último balón *controlado* y arrastra ese estado
entre controles. El tracker pierde el balón en el 41% de los frames puntuables, en huecos de
mediana 268 frames; los de más de 500 frames tienen el 67% del balón perdido. Dentro de un hueco el
motor no tiene evidencia. Esta propuesta le da evidencia **solo de los jugadores**: qué equipo
tiene la forma de quien tiene el balón.

### Independencia

El Smart Tagging **no es entrada** en ningún punto de esta línea: ni rasgo, ni etiqueta de
entrenamiento, ni criterio para ordenar variantes. Es la única señal independiente del tracking
para validar fuera del slice público; usarlo como entrada haría circular esa validación. Solo
aparece como compuerta de aprobado/suspenso (G2 abajo). El ground truth público tampoco se usa
para entrenar ni para elegir umbrales.

### Rasgos (por frame, solo tracking)

Coordenadas en metros (`x · 105,3`, `y · 68,0`). Para cada equipo `t` y mitad `h`, la dirección de
ataque `d_t,h ∈ {+1, −1}` sale de los datos: el equipo cuyo centroide `x` tiene la mediana más baja
en la mitad defiende la portería de `x = 0` y ataca hacia `+x`. La coordenada firmada de un jugador
es `s = d_t,h · (x − 52,65)`: positiva en campo rival, creciente hacia la portería rival.

Por equipo, sobre los jugadores presentes de ese equipo:

1. `mean_s` — media de `s` (altura del bloque);
2. `max_s` — el jugador más adelantado;
3. `deep_s` — el segundo más retrasado (la última línea sin el portero);
4. `spread_x` — desviación típica de `x`;
5. `spread_y` — desviación típica de `y` (amplitud);
6. `vel_s` — velocidad media hacia la portería rival, en m/s: por jugador, `(s_i(f) − s_i(f−25)) / 1 s`,
   solo jugadores presentes en ambos frames y sin cruzar el inicio de la mitad;
7. `opp_half` — jugadores con `s > 0`.

El modelo ve **solo las diferencias local − visitante** de los siete. Un frame con menos de 7
jugadores presentes en algún equipo, o con algún rasgo indefinido, no tiene evidencia: queda fuera
del entrenamiento y recibe `P(local) = 0,5`.

### Modelo

Regresión logística **sin intercepto** sobre las siete diferencias, cada una dividida por su RMS en
los frames de entrenamiento (sin centrar). Sin intercepto y con rasgos antisimétricos, intercambiar
los equipos invierte exactamente la probabilidad: el modelo dice qué forma parece de posesión, no
quién suele tenerla (ese prior ya lo lleva el estado arrastrado). Ajuste por Newton–Raphson,
**25 iteraciones fijas**, ridge `λ = 1e-3`, pesos iniciales cero: determinista sin semilla.

Etiquetas de entrenamiento: los frames de **control** del motor (`engine.control`, parámetros por
defecto) dentro de las mitades, `1` si controla el local. Nada de ground truth ni Smart Tagging.

`P(local)` por frame es la salida del modelo. Para la regla se suaviza con una media móvil
centrada de **125 frames (5 s)** dentro de cada mitad.

### Regla de relleno `fill_gaps`

Dentro de cada hueco de balón (corrida maximal sin balón dentro de una mitad, la misma definición
que `tools/ball_gaps.py`) de longitud `≥ L`:

1. El estado de partida es el que el motor arrastra al entrar en el hueco.
2. Se recorre el hueco con histéresis: cambia al otro equipo `u` cuando la `P(u)` suavizada es
   `≥ τ` durante **50 frames consecutivos (2 s)**, y el cambio se **fecha en el primero de ellos**
   (la misma convención que `engine.decode` con `dwell`). Puede haber más de un cambio en un hueco
   largo.
3. El estado con el que acaba el hueco se sigue arrastrando **hasta el siguiente frame de control**
   de la mitad: en esos frames el motor tampoco tiene evidencia nueva, y cortar el relleno en el
   borde del hueco crearía una posesión espuria de unos frames entre el hueco y el próximo control.
   Ningún frame de control ni ningún frame posterior a él cambia.
4. Un hueco que empieza sin estado (antes del primer control de la mitad) no se toca.

Variantes (máximo 4, fijadas aquí y no barridas):

| variante | `L` (frames) | `τ` |
|---|---:|---:|
| V1 | 125 (5 s) | 0,80 |
| V2 | 125 (5 s) | 0,90 |
| V3 | 500 (20 s) | 0,80 |
| V4 | 500 (20 s) | 0,90 |

### Mediciones

- (a) exactitud de `P(local) > 0,5` en frames de control **fuera de muestra**: entrenar en los
  bloques impares de `tools/blocks.blocks` y evaluar en los pares, y al revés; se reportan los dos
  pliegues y el conjunto, junto a la exactitud de "siempre la clase mayoritaria" y la exactitud en
  los frames con `P` suavizada `≥ 0,8` o `≤ 0,2` (lo que la regla usa).
- (b) exactitud en los frames vivos sin balón del slice público (391 frames: muestra pequeña), del
  modelo y del motor con y sin relleno.
- (c) acuerdo con el Smart Tagging en frames de hueco (sin balón, dentro de una mitad, con votos a
  un solo equipo, etiqueta `H`/`A`): motor arrastrando frente a motor + relleno, por bloque y en el
  partido; con detalle de los bloques 7, 9, 11 y 18.
- (d) `spellF1` público y Δ pareado frente al motor (`tools/compare_submissions.py`).
- (e) posesiones por minuto por bloque (`tools/blocks.py`).

### Regla de selección

Una variante se **aprueba** solo si pasa todas las compuertas:

- **G1** (vale para toda la línea): exactitud fuera de muestra del conjunto en (a) `≥ 0,70`. Si
  falla, el resultado es negativo y no se recomienda ninguna variante.
- **G2**: el acuerdo con el Smart Tagging en frames de hueco del partido sube al menos **2 puntos**
  sobre el motor, y no baja en más de uno de los bloques 7, 9, 11 y 18.
- **G3**: Δ `spellF1` pareado en el slice público `≥ −0,02` (se espera ~0: el slice casi no tiene
  huecos, decisiones 13 y 24; un Δ positivo tampoco cuenta como evidencia).
- **G4**: plausibilidad física: tasa del partido entre 2,5 y 5,0 posesiones/min, y ningún bloque
  con 0 ni con más de 8 posesiones/min.

Entre las aprobadas se recomienda la **más conservadora**, la que cambia menos frames; el Smart
Tagging no ordena variantes, solo aprueba o suspende. Si ninguna pasa, el resultado es negativo y
se reporta como tal.

---

Las secciones 2 en adelante se escribieron **después** de medir. El pre-registro de arriba está en
el commit `2ac2fb0`, anterior a cualquier lectura de ground truth o Smart Tagging.

## 2. Cómo se reproducen los números

> **Nota del coordinador.** Estos números se midieron con el motor del commit `e02437c`, antes de la
> decisión 31, que dejó de contar como control un balón fuera del campo. Como `formation.py` entrena
> con `engine.control`, el comando de abajo **ya no reproduce** esta tabla en el código actual: el
> motor desnudo pasa de 0,4390 a 0,4195 y la máscara de entrenamiento cambia. Para reproducir la
> evidencia tal como se archivó, hay que ejecutarlo sobre ese commit (`git worktree add ../lane-f
> e02437c`). La conclusión no depende de esto: el relleno de huecos no entra en la cadena.

```bash
export MTAH_DATA_DIR="<carpeta del bundle>"
uv sync --locked --inexact
mkdir -p runs/lane-f  # la redirección del shell abre el archivo antes de que Python cree la carpeta
.venv/Scripts/python tools/formation.py --measure runs/lane-f > runs/lane-f/measure.json
```

Cada número de la sección 3 es un campo de ese JSON (solo agregados; las CSV de etiquetas de
`runs/lane-f/` no se comprometen). Dos corridas seguidas dan un JSON idéntico byte a byte. Tarda
unos segundos con el tracking en caché.

## 3. Mediciones

Pesos del modelo entrenado en todos los frames de control (`weights`), sobre rasgos divididos por su
RMS: `mean_s` +2,65, `deep_s` −3,24, `spread_y` +1,25, `max_s` +0,71, `vel_s` +0,25, `spread_x`
−0,15, `opp_half` +0,04. `mean_s` y `deep_s` están muy correlacionados: los pesos individuales no
se interpretan, solo la predicción.

### (a) Exactitud fuera de muestra en frames de control (`heldout`)

| entrenar → evaluar | frames de prueba | exactitud | suavizada | mayoritaria | frames con `P` ≥ 0,8 o ≤ 0,2 | exactitud ahí |
|---|---:|---:|---:|---:|---:|---:|
| impares → pares | 14.002 | 0,808 | 0,809 | 0,636 | 50,9% | 0,883 |
| pares → impares | 13.421 | 0,801 | 0,809 | 0,587 | 56,0% | 0,896 |
| **conjunto** | 27.423 | **0,804** | | | | |

### (b) Frames vivos sin balón del slice público (`public_no_ball`), 391 frames

| | exactitud |
|---|---:|
| modelo, `P` cruda > 0,5 | 1,000 |
| modelo, `P` suavizada > 0,5 | 1,000 |
| motor | 0,944 |
| motor + V1 / V2 / V3 / V4 | 0,944 / 0,944 / 0,944 / 0,944 |

Ninguna variante toca estos frames: la evidencia no llega al umbral sostenido en los huecos del
slice. Con 391 frames, el 1,000 del modelo es una anécdota, no una medida.

### (c) Acuerdo con el Smart Tagging en frames de hueco (`smart_tagging_gap`)

Frames sin balón dentro de una mitad, con votos a un solo equipo y etiqueta `H`/`A`.

| bloque | frames | motor | V1 | V2 | V3 | V4 |
|---|---:|---:|---:|---:|---:|---:|
| **partido** | 32.233 | **0,713** | 0,709 | 0,726 | 0,706 | **0,729** |
| 7 | 681 | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 |
| 9 | 2.569 | 1,000 | 0,524 | 1,000 | 0,587 | 1,000 |
| 11 | 1.662 | 0,125 | 0,125 | 0,125 | 0,125 | 0,125 |
| 18 | 1.150 | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 |
| 1★ | 623 | 0,372 | 0,575 | 0,372 | 0,372 | 0,372 |
| 6 | 1.431 | 0,999 | 0,822 | 0,897 | 0,822 | 0,897 |
| 10 | 2.551 | 0,752 | 0,924 | 0,752 | 0,924 | 0,752 |
| 20 | 2.789 | 0,454 | 0,610 | 0,688 | 0,610 | 0,688 |

Los demás bloques no cambian en ninguna variante, salvo movimientos en 3, 5, 8, 15, 19 y 21 (V1
en los seis, V3 en el 5, V2 en el 15; todos en el JSON). Solo en los frames que cada variante cambia
(`smart_tagging_changed_frames`, incluye el arrastre tras el hueco hasta el próximo control):

| variante | frames cambiados | de ellos juzgados por el ST | acuerdo motor | acuerdo relleno |
|---|---:|---:|---:|---:|
| V1 | 12.261 | 4.837 | 0,493 | 0,507 |
| V2 | 6.143 | 1.428 | 0,340 | 0,660 |
| V3 | 10.559 | 3.791 | 0,527 | 0,473 |
| V4 | 5.931 | 1.338 | 0,296 | 0,704 |

### (d) `spellF1` público, pareado contra el motor (`public_spell_f1`)

| variante | motor | con relleno | Δ | discordantes (motor–relleno) |
|---|---:|---:|---:|---:|
| V1 | 0,4390 | 0,4098 | −0,0293 | 1 (1–0) |
| V2 | 0,4390 | 0,4390 | 0,0000 | 0 |
| V3 | 0,4390 | 0,4390 | 0,0000 | 0 |
| V4 | 0,4390 | 0,4390 | 0,0000 | 0 |

### (e) Posesiones por minuto (`possessions_per_minute`, `tools/blocks.measure`)

| | partido | bloque 7 | bloque 9 | bloque 11 | bloque 18 | mín. bloque | máx. bloque |
|---|---:|---:|---:|---:|---:|---:|---:|
| motor | 3,25 | 0,80 | 1,60 | 0,67 | 1,60 | 0,67 | 5,20 |
| V1 | 3,34 | 0,80 | 2,00 | 0,67 | 1,60 | 0,67 | 5,20 |
| V2 | 3,27 | 0,80 | 1,60 | 0,67 | 1,60 | 0,67 | 5,20 |
| V3 | 3,29 | 0,80 | 1,60 | 0,67 | 1,60 | 0,67 | 5,20 |
| V4 | 3,27 | 0,80 | 1,60 | 0,67 | 1,60 | 0,67 | 5,20 |

### Compuertas, aplicadas tal como se pre-registraron

| variante | G1 (0,804 ≥ 0,70) | G2 (≥ +2 pt, ≤ 1 bloque duro peor) | G3 (Δ ≥ −0,02) | G4 | resultado |
|---|---|---|---|---|---|
| V1 | pasa | **falla**: −0,4 pt, peor en el 9 | **falla**: −0,0293 | pasa | suspende |
| V2 | pasa | **falla**: +1,3 pt | pasa | pasa | suspende |
| V3 | pasa | **falla**: −0,7 pt, peor en el 9 | pasa | pasa | suspende |
| V4 | pasa | **falla**: +1,6 pt | pasa | pasa | suspende |

**Ninguna variante se aprueba. El resultado es negativo.**

### Diagnóstico posterior (no pre-registrado)

Leído después de las compuertas, para entender el negativo; no cambia la regla ni las variantes
(`posthoc_model_vs_smart_tagging_gap`). Acuerdo con el ST en los mismos frames de hueco:

| | frames | motor (arrastre) | modelo, `P` suavizada > 0,5 | parte con `P` ≥ 0,8 o ≤ 0,2 | modelo ahí |
|---|---:|---:|---:|---:|---:|
| partido | 32.233 | 0,713 | 0,658 | 31,1% | 0,748 |
| bloque 7 | 681 | 1,000 | 0,552 | 14,5% | 1,000 |
| bloque 9 | 2.569 | 1,000 | 0,506 | 14,7% | 0,315 |
| bloque 11 | 1.662 | 0,125 | 0,255 | 19,5% | 0,596 |
| bloque 18 | 1.150 | 1,000 | 0,637 | 7,3% | 1,000 |

## 4. Recomendación

**No integrar `fill_gaps` en el motor.** Ninguna variante pasa la compuerta pre-registrada G2, y
la regla de selección no deja elegir la que más se acerca (V4, +1,6 puntos) por estar cerca.

Por qué no funciona, según las mediciones:

- **El modelo es bueno donde no hace falta.** El 0,804 fuera de muestra es sobre frames de control:
  balón visible, lento y pegado a un jugador. En los huecos la forma del equipo dice menos: frame a
  frame, el modelo coincide con el ST en el 65,8% de los frames de hueco, por debajo del 71,3% del
  simple arrastre. Solo en el 31% de frames donde el modelo está seguro supera al arrastre (74,8%).
- **Los bloques duros no son lo que parecían.** En los bloques 7, 9 y 18, en los frames de hueco que
  el ST juzga, el arrastre del motor ya coincide con él el 100%: ahí el relleno no tiene nada que
  mejorar (lo que `docs/analysis/blocks.md` muestra para esos bloques es el respaldo y `smooth50`,
  no el motor). En el bloque 11 el arrastre
  coincide el 12,5%, pero la formación también contradice al ST (25,5%): ningún umbral sobre esta
  evidencia lo arregla. No se puede saber si ahí se equivoca el tracking o el ST.
- **Con umbral alto acierta, pero mueve poco.** Con `τ = 0,9` (V2, V4), en los frames que cambia el
  relleno coincide con el ST 2 a 1 (0,704 contra 0,296 en V4). La señal no es ruido, pero cubre
  1.338 frames juzgados de 32.233, y en el bloque 6 empeora 10 puntos. Con `τ = 0,8` (V1, V3)
  queda en 50/50 y rompe el bloque 9.

Qué queda: `tools/formation.py` con rasgos y pruebas, por si una propuesta futura quiere `P(local)`
como evidencia blanda en otro sitio (por ejemplo, desempatar *dentro* del decodificador en vez de
sobrescribir el arrastre). Cualquier cambio así necesita su propio pre-registro: V4 con otra compuerta
sería exactamente el ajuste a posteriori que este documento prohíbe.

## 5. Limitaciones

- **Acuerdo con el ST no es acierto.** Medido contra la ventana pública, el ST acierta el 68,0% de
  los frames vivos que cubre (decisión 26). Un +1,6 puntos de acuerdo está muy por debajo de lo que
  esa señal puede distinguir con confianza, que es otra razón para no leer V4 como ganadora.
- **El slice público no mide huecos** (decisiones 13 y 24): 391 frames vivos sin balón, que ninguna
  variante toca, y un Δ `spellF1` que se mueve por una sola posesión (V1). (b) y (d) son
  comprobaciones de que nada se rompe, no evidencia a favor.
- **Cambio de distribución en las etiquetas.** Los frames de control son solo los de balón visible
  y controlado; el modelo se aplica justo donde no lo hay. (a) mide el modelo en su terreno, no en
  el de uso, y el diagnóstico posterior muestra que la diferencia importa.
- **Dentro de muestra en (c)–(e).** El relleno usa el modelo entrenado en todos los frames de
  control del partido. Los frames de hueco no son de entrenamiento, y con 7 pesos el pliegue
  temporal casi no pierde exactitud (0,804), así que el optimismo debería ser pequeño. No está medido
  con predicciones cruzadas.
- **Separación temporal imperfecta.** Los bloques pares e impares son contiguos: en cada frontera
  los frames de control vecinos están correlacionados entre sí. Con bloques de 5 minutos, la parte
  afectada es pequeña.
- **Huecos de la definición.** El primer segundo de cada mitad no tiene velocidad, así que tampoco
  formación (`P = 0,5`), y un equipo con menos de 7 jugadores seguidos tampoco. Las dos cosas son
  raras en juego (mediana de 11 por equipo), pero no se midió cuántos frames de hueco afectan.
- **Un partido.** Los pesos, las direcciones de ataque y todas las cifras son de BAR–ATH. Barcelona
  domina la posesión; un modelo sin intercepto evita que eso entre como prior, pero no que la forma
  "de posesión" aprendida sea la de este partido.
