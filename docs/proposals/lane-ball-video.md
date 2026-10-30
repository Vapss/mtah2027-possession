# Lane ball-video — recuperar el balón desde el vídeo táctico donde el tracking lo pierde

Propuesta para el motor de posesión (#6, `tools/engine.py`). Código: `tools/video_ball.py`, pruebas:
`tests/test_video_ball.py`, entorno de exploración: `requirements-video.txt`. Este documento no
cambia el motor ni `docs/DECISIONS.md`: el coordinador integra.

## 0. Problema

El ATD no tiene balón en el 41% de los frames puntuables; ahí el motor no tiene evidencia y arrastra
el último estado (banco: 0,4585 limpio, 0,2782 de media en donantes con poco balón). El reglamento
permite mejorar o sustituir el tracking con detección propia, y el vídeo táctico es la autoridad de
índice: la fila `i` del envío es el frame `i` del vídeo, y la homografía por frame lleva el campo a
la imagen. Un balón en el píxel `(u, v)` del frame `i` está en `H_i⁻¹(u, v)` del campo, en las mismas
coordenadas 0-1 que el ATD.

**Datos licenciados.** El detector lee los frames de una tubería de ffmpeg en memoria; no se escribe
ningún frame, recorte ni imagen, nada se abre con una herramienta de imágenes y nada sale de la
máquina (telemetría de ultralytics desactivada: `yolo settings sync=False`). Las detecciones son
datos derivados a nivel de frame: viven en `runs/` (gitignored) y no se publican. Aquí solo hay
agregados.

## 1. Factibilidad (sin ground truth)

Medido antes de este pre-registro, solo contra el tracking. Comandos:

```bash
export MTAH_DATA_DIR="<carpeta del bundle>"
.venv/Scripts/python tools/video_ball.py sample --out runs/video_ball/sample.npz
<venv-video>/python tools/video_ball.py detect --frames runs/video_ball/sample.npz \
    --out runs/video_ball/sample_det_yolo11x.npz [--weights yolo11s.pt --batch 16]
.venv/Scripts/python tools/video_ball.py feasibility --frames runs/video_ball/sample.npz \
    --detections runs/video_ball/sample_det_yolo11x.npz
```

**Muestra.** Dentro de las dos mitades, semilla 2027: 200 tramos de 10 frames consecutivos con balón
del ATD en todos (2.000 frames, `with_ball`) y 200 tramos sin balón del ATD en ninguno (2.000, `gap`);
3.934 frames distintos (algunos tramos se solapan). Tramos y no frames sueltos: cada búsqueda en el
vídeo cuesta ~0,2 s y el filtro temporal necesita vecinos.

Los diagnósticos (desfase, oráculo, dónde caen los falsos positivos) son la clave `diagnose` de la
misma salida, con `conf ≥ 0,3`.

**Alineación.** (a) `ffmpeg -ss i/25` antes de `-i` devuelve exactamente el frame `i`: el hash del
frame buscado coincide con el de la decodificación secuencial en los frames 300, 1.237, 50.001 y
150.013 (desfase 0 en los cuatro). (b) Contra el ATD, la proporción de cajas a ≤ 1 m del balón del
ATD en el frame `i + k` es máxima en `k = 0` (0,427; 0,415 en `k = −1`, 0,421 en `k = +1`, 0,268 en
`k = −4`, 0,320 en `k = +4`): vídeo y tracking están alineados al frame.

**Escala.** Por la homografía en los frames con balón del ATD, la cámara táctica sigue el juego
(panea y hace zoom): mediana 27 px/m a lo largo del campo (p5 19,9, p95 39,9). El balón (0,22 m)
mide ~6 px; las cajas detectadas tienen mediana 8 × 8 px. Por eso se infiere a la resolución
nativa (`imgsz = 1920`): reducir la imagen borra el balón.

**Detector.** COCO `sports ball` (clase 32) de ultralytics YOLO11, pesos públicos, sin
reentrenar, fp16, hasta 5 cajas por frame con `conf ≥ 0,05`; el umbral real se aplica después, en
numpy. Se mide la mejor caja por frame proyectada al suelo.

### 1a. Posición frente al ATD (frames `with_ball`)

`encontrado`: hay caja; `recall@1 m / 2 m`: la mejor caja está a esa distancia del ATD;
`precisión@2 m`: entre los frames con caja; `hueco`: frames `gap` con caja.

| modelo | conf ≥ | encontrado | recall@1 m | recall@2 m | precisión@2 m | error mediano (m) | hueco |
|---|---:|---:|---:|---:|---:|---:|---:|
| yolo11x | 0,1 | 0,924 | 0,326 | 0,451 | 0,488 | 2,16 | 0,864 |
| yolo11x | 0,2 | 0,809 | 0,312 | 0,434 | 0,536 | 1,60 | 0,652 |
| yolo11x | 0,3 | 0,683 | 0,292 | 0,402 | 0,588 | 1,34 | 0,469 |
| yolo11x | 0,5 | 0,425 | 0,209 | 0,277 | 0,652 | 1,03 | 0,211 |
| yolo11x | 0,7 | 0,079 | 0,043 | 0,059 | 0,752 | 0,88 | 0,044 |
| yolo11s | 0,2 | 0,881 | 0,289 | 0,400 | 0,454 | 3,49 | 0,732 |
| yolo11s | 0,3 | 0,799 | 0,279 | 0,387 | 0,484 | 2,28 | 0,581 |
| yolo11s | 0,5 | 0,539 | 0,236 | 0,308 | 0,572 | 1,37 | 0,299 |

- **Como rastreador de posición, el detector COCO no es defendible.** Ni con el umbral más alto
  pasa de 0,75 de precisión a 2 m, y el techo de recall es bajo: incluso eligiendo, como oráculo,
  cualquiera de las 5 cajas con `conf ≥ 0,05`, solo hay una a ≤ 2 m del ATD en el 55,9% de los frames
  `with_ball`.
- El error es bimodal: con `conf ≥ 0,3` el 25% de las mejores cajas está a ≤ 0,53 m y el 50% a
  ≤ 1,34 m, pero el 31% está a más de 5 m (falsos positivos). No son los puntos de penalti ni el
  centro (0,2% a ≤ 1 m de ellos) y **tampoco suelen estar junto a un jugador**: distancia mediana al
  jugador más cercano 10,6 m, solo el 7,1% a ≤ 1,5 m.
- El filtro de consistencia temporal (sección 3) apenas los quita: con `conf ≥ 0,3` la precisión a
  2 m pasa de 0,588 a 0,698, porque los falsos positivos son persistentes, no parpadeos de un frame.

### 1b. Control del motor (lo que el motor realmente lee)

El motor solo usa el balón a través de los frames de **control** (jugador a ≤ 1,5 m, balón a
≤ 5 m/s, el rival no tan cerca). Un falso positivo lejos de los jugadores no crea control, así que la
pregunta útil es otra: con el balón **solo del vídeo** (el del ATD descartado, apoyo temporal solo
de otras cajas del vídeo, sin circularidad), ¿qué controles produce?

| modelo | conf ≥ | control ATD | control vídeo | otro equipo que el ATD¹ | control vídeo en hueco | acuerdo con el estado² (with_ball) | acuerdo con el estado² (hueco) |
|---|---:|---:|---:|---:|---:|---:|---:|
| yolo11x | 0,2 | 0,268 | 0,116 | 0,035 | 0,032 | 0,882 (n 221) | 0,926 (n 54) |
| yolo11x | 0,3 | 0,268 | 0,100 | 0,041 | 0,026 | 0,879 (n 190) | 0,907 (n 43) |
| yolo11x | 0,5 | 0,268 | 0,059 | 0,025 | 0,014 | 0,886 (n 114) | 0,870 (n 23) |
| yolo11s | 0,2 | 0,268 | 0,086 | 0,054 | 0,028 | 0,866 (n 157) | 0,745 (n 47) |
| yolo11s | 0,3 | 0,268 | 0,081 | 0,058 | 0,021 | 0,858 (n 148) | 0,719 (n 32) |
| yolo11s | 0,5 | 0,268 | 0,061 | 0,072 | 0,009 | 0,848 (n 112) | 0,667 (n 12) |

¹ Entre los frames donde ambos tienen control. ² Estado decodificado por el motor entregado, en
frames vivos (no `D`, con estado).

- **Como evidencia de quién controla, yolo11x es preciso**: cuando su balón crea un control, nombra
  al otro equipo que el control del ATD en el 3,5-4% de los casos.
- **La cobertura en huecos es el límite**: solo el 2,6-3,2% de los frames de hueco reciben un control
  del vídeo (contra el 26,8% de controles del ATD donde ve el balón). Y en hueco ese control coincide
  con el estado que el motor ya arrastra en ~91% de los casos: el vídeo puede cambiar la etiqueta en
  una fracción muy pequeña de los frames de hueco. **Techo de ganancia esperado: pequeño.**
- yolo11s es peor en todo (más falsos positivos, menos acuerdo en hueco).

### 1c. Velocidad

En la muestra (búsquedas incluidas, RTX 4070 Laptop 8 GB, fp16, `imgsz` 1920): yolo11x 11,0 fps de
detección (3.934 frames en 359 s) y 7,6 fps con decodificación; yolo11s 46,2 fps de detección y
19,4 fps con decodificación. Las dos mitades son 158.857 frames: con yolo11x, ~4 h solo de
detección. La decodificación secuencial (sin búsquedas) se mide en la sección 4.

### 1d. Veredicto de factibilidad

Negativo como **rastreador** (precisión de posición ≤ 0,75 a 2 m, recall ≤ 0,46), dudoso-positivo
como **fuente de controles** (equipo correcto ~96%, cobertura ~3% de los frames de hueco). No basta
para descartar sin medir, pero el techo es bajo; por eso el pre-registro de abajo es **por etapas**:
primero lo barato y con cota superior, y el partido completo solo si la cota lo justifica.

## 2. Pre-registro

Escrito y comprometido en git **antes** de leer ground truth, el banco o el Smart Tagging con
cualquier variante de esta línea. Lo medido antes de escribirlo es solo la sección 1 (tracking y
vídeo).

### Detector y filtro (fijos, no se barren)

- Detector: yolo11x COCO `sports ball`, `imgsz 1920`, fp16, 5 cajas/frame, `conf ≥ 0,05` guardado;
  salida redondeada a 0,1 px y 0,001 de confianza.
- `min_conf = 0,2`: el umbral de la tabla 1b con más cobertura en hueco cuyo control nombra al otro
  equipo que el ATD en ≤ 5% y cuyo acuerdo con el estado en `with_ball` es ≥ 0,85 (medido solo con
  el tracking). Variante estricta `min_conf = 0,5`.
- Plausibilidad: balón proyectado dentro de `[−0,05; 1,05]` en `x` e `y` (el ATD llega a −0,04..1,04:
  en el campo o justo fuera); y **apoyo temporal**: otro balón (vídeo o ATD) a ≤ 5 frames y a una
  distancia compatible con ≤ 35 m/s (el tiro más fuerte) más 1 m de ruido. Una caja aislada se
  descarta.
- Fusión: el ATD **nunca** se sobrescribe; el balón del vídeo solo rellena frames sin balón del ATD.
  Las `Features` del motor se recalculan con el balón fusionado (`engine.features` sobre un
  `atd.Tracking` con los mismos jugadores): distancias, velocidad y dentro/fuera.

### Variantes (máximo 4)

| variante | `min_conf` | qué alimenta el balón del vídeo |
|---|---:|---|
| V0 | — | el motor entregado, sin vídeo (referencia) |
| V1 | 0,2 | solo las `Features` del motor (control); la evidencia de balón muerto queda como está |
| V2 | 0,5 | como V1, estricto |
| V3 | 0,2 | como V1 y además la evidencia de balón muerto (`out`/`inside` desde el balón fusionado) |

### Banco (dos diseños)

El banco borra el balón de block 1 donde el donante no lo tenía. Rellenar esos huecos con el vídeo
de block 1 **sobrestima** la ganancia: los frames de block 1 son fáciles (el ATD veía el balón), los
huecos reales no. Por eso:

- **B-opt (cota superior)**: en el hueco trasplantado, el balón del vídeo de block 1 entra donde
  exista y pase el filtro.
- **B-joint (primario)**: se trasplanta el patrón **conjunto** del donante. En el frame `j` de la
  ventana: si el donante tenía ATD, queda el ATD de block 1; si no, entra el balón del vídeo de
  block 1 **solo si** el donante tenía en su frame `j` un balón del vídeo aceptado (en su hueco
  real); si no, nada. Así la cantidad y la longitud de la cobertura del vídeo son las de los huecos
  reales; la ubicación sigue siendo la de block 1 (la misma limitación que el banco ya declara).

### Etapas y regla de parada

1. **Etapa 1 (barata):** inferencia sobre block 1 (7.500 frames). Medir V1-V3 en B-opt y en el
   slice público. **Si ninguna variante mejora la media de B-opt sobre V0 en ≥ 0,01, se para**:
   B-joint rellena un subconjunto de los frames de B-opt, y el resultado es negativo.
2. **Etapa 2:** inferencia de las dos mitades; B-joint, informe por bloques, determinismo.

### Regla de selección

Una variante se **recomienda** solo si pasa todas:

- **G1**: media de B-joint y media de donantes con poco balón de B-joint ≥ V0 + 0,01.
- **G2**: Δ `spellF1` pareado en el slice público (`tools/compare_submissions.py`) ≥ −0,02 (dirección,
  no prueba: 17 posesiones).
- **G3**: informe por bloques: ningún bloque con 0 o más de 8 posesiones/min, y el acuerdo con el
  Smart Tagging en los bloques de poco balón 7, 9, 11 y 18 no baja más de 1 punto en ninguno.

Entre las que pasan, la que cambia menos frames (V2 antes que V1, V1 antes que V3). Si ninguna pasa,
el resultado es negativo y se reporta como tal. El Smart Tagging no es entrada en ningún punto.

---

Las secciones 3 en adelante se escribieron **después** de medir. El pre-registro de arriba está en
el commit `2364dd6`.

## 3. Resultado de la etapa 1 (detector COCO): negativo

```bash
<venv-video>/python tools/video_ball.py detect --range 11185 18685 --out runs/video_ball/det_block1.npz
.venv/Scripts/python tools/video_ball.py evaluate --detections runs/video_ball/det_block1.npz \
    --design opt --labels-dir runs/video_ball/labels_stage1
.venv/Scripts/python tools/compare_submissions.py runs/video_ball/labels_stage1/V0.csv \
    runs/video_ball/labels_stage1/V2.csv --gt public
```

Comprobación del banco reimplementado: V0 reproduce exactamente `tools/bench.py --method engine`
(0,4585 / 0,3516 / peor 0,2069 / poco balón 0,2782).

| variante | público `spellF1` | Δ pareado vs V0 | `n_discordant` | spurious@0,3 (V0: 11) | `macroF1` | B-opt limpio | B-opt media | B-opt poco balón | B-opt peor | frames rellenados en block 1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| V0 | 0,4585 | — | — | 11 | 0,7066 | 0,4585 | 0,3516 | 0,2782 | 0,2069 | 0 |
| V1 | 0,4000 | −0,0585 | 0 | 17 | 0,6979 | 0,4000 | 0,3929 | 0,3885 | 0,3478 | 393 |
| V2 | 0,4372 | −0,0213 | 0 | 13 | 0,7062 | 0,4372 | 0,4288 | 0,4208 | 0,3714 | 99 |
| V3 | 0,3915 | −0,0670 | 0 | 17 | 0,6886 | 0,3915 | 0,3930 | 0,3894 | 0,3556 | 393 |

(«B-opt limpio» es block 1 con sus huecos reales rellenados por el vídeo: el mismo número que el
público.)

**Lectura: el sesgo de selección, medido.**

- **Cota superior grande.** Cuando el vídeo rellena huecos *trasplantados* —frames donde la pelota
  se veía— el banco sube mucho (V2: media +0,077, poco balón +0,143). Si el vídeo recuperase el
  balón en los huecos reales como lo hace en los visibles, la ganancia sería la mayor de cualquier
  línea.
- **En los huecos reales, pierde.** En el slice público el vídeo rellena los huecos *reales* de
  block 1 (12% de sus frames): ninguna posesión cambia de estado de emparejamiento (`n_discordant`
  0 en las tres) y todas las pérdidas son posesiones espurias (+2 a +6): controles breves del otro
  equipo dentro de un hueco, que parten una posesión. Los huecos del ATD están donde la pelota es
  difícil de ver (aire, aglomeración, oclusión), y ahí el detector COCO encuentra otra cosa.
- **Las cuatro suspenden G2** (Δ ≥ −0,02; V2 por poco, −0,0213), así que la recomendación es
  negativa sea cual sea B-joint. Por decisión del coordinador la etapa 2 (inferencia del partido,
  ~4,5 h de GPU a 9,3 fps) **se detuvo**: solo puliría un negativo ya establecido por la regla
  pre-registrada. B-joint y el informe por bloques no se midieron para el detector COCO.

**Determinismo (COCO, GPU).** Los 500 primeros frames de block 1 inferidos dos veces (1.443 cajas):
posiciones idénticas tras redondear a 0,1 px; la confianza difiere en 2 cajas por 0,001-0,002 (un
cruce de frontera de redondeo). Casi determinista, no idéntico byte a byte.

## 4. Adenda pre-registrada: detector afinado con etiquetas del ATD

Pedido por el coordinador tras la sección 3. Escrita y comprometida **antes** de extraer datos de
entrenamiento, entrenar o medir nada con este detector.

### Datos (sin fuga al banco ni al slice público)

- **Exclusión:** block 1 (11.185..18.684) más 1 minuto a cada lado → frames 9.685..20.183 no se usan
  ni para entrenar ni para elegir umbrales. El banco y el slice público viven ahí.
- **Partición temporal:** entrenamiento en la 1.ª mitad, bloques 3-9 (26.185..78.684); selección
  del umbral en los bloques 10-11 (78.685..90.651); go/no-go en la 2.ª mitad (bloques 12-22).
- **Etiquetas:** el balón del ATD proyectado con la homografía del frame, caja de **24 × 24 px**
  centrada ahí. Motivo (sin ground truth, medido en la sección 1 con las cajas COCO a ≤ 2 m del ATD,
  n 798): la proyección del ATD queda a 8,9 px de la pelota visible en mediana, 16,1 en p75 y 25,1
  en p90 (la pelota aparece ~5,5 px más arriba: su altura). Una caja de 24 px la contiene en ~80%
  de los casos; el detector aprende «dónde está la pelota» con ~0,5 m de tolerancia, que es lo que
  el control (1,5 m) necesita.
- **Muestras:** 6.000 frames con balón del ATD en los bloques 3-9 (equiespaciados entre los frames
  con balón, sin semilla). Cada uno da un recorte de 640 × 640 a resolución nativa que contiene la
  pelota en posición aleatoria (semilla 2027) y un recorte **negativo** del mismo frame que no la
  contiene (a ≥ 48 px de su caja): el ATD dice dónde está, así que el resto del frame es sin balón.
  Los frames de hueco del ATD **no** son negativos: allí no se sabe.
- Los recortes se escriben en JPEG (calidad 95) en `runs/` (gitignored), nunca se abren con una
  herramienta de imágenes y se borran al terminar.

### Modelo y entrenamiento (fijos)

yolo11s (pesos COCO como punto de partida), una clase, `imgsz 640` sobre los recortes, 20 épocas,
`batch 16`, `seed 0`, `deterministic=True`, sin aumentos de color (`hsv_*=0`), `mosaic 0`,
`fliplr 0,5`, `scale 0` (la escala de la pelota es física). Inferencia sobre el frame completo a
`imgsz 1920` (misma escala de píxel que el entrenamiento).

### Umbral de operación (sin ground truth)

En una muestra de los bloques 10-11 (200 tramos de 10 frames con balón del ATD, semilla 2027): el
**menor** umbral de confianza, en la rejilla 0,1..0,9 de 0,05 en 0,05, con precisión a 2 m (mejor
caja frente al ATD) ≥ 0,90.

### Go / no-go (antes de cualquier inferencia del partido)

En la 2.ª mitad (200 tramos con balón y 200 sin balón del ATD, semilla 2027), al umbral de
operación:

- **GO** si la precisión a 2 m frente al ATD es **≥ 0,90**. Se reportan también el recall a 1/2 m,
  la cuota de frames de hueco con detección aceptada y la tabla de control de la sección 1b.
- Si es no-go: se para y se reporta el negativo.

### Si es GO

Variantes (las mismas reglas de filtro y fusión de la sección 2, solo cambia el detector):

| variante | umbral | qué alimenta |
|---|---|---|
| F1 | el de operación | las `Features` del motor (control), como V1 |
| F2 | el menor de la rejilla con precisión ≥ 0,95 en bloques 10-11 | ídem, estricto |

1. Inferencia en block 1 y prueba pareada **en huecos reales** (público). Compuerta: **sin
   pérdida**: `wins_a ≤ wins_b` y Δ `spellF1` ≥ −0,005. Si ninguna pasa, se para.
2. Solo si alguna pasa: inferencia del partido, B-joint, B-opt e informe por bloques, con la regla de
   selección de la sección 2 (G1-G3).
3. Determinismo: dos ejecuciones sobre una muestra con `CUBLAS_WORKSPACE_CONFIG=:4096:8`,
   algoritmos deterministas y semillas fijas; tiempo en CPU como alternativa.

## 5. Resultado de la adenda (detector afinado): no-go

```bash
<venv-video>/python tools/video_ball.py prepare --out runs/video_ball/ft_ds --span 26185 78685 --count 6000
<venv-video>/python tools/video_ball.py prepare --out runs/video_ball/ft_ds --span 78685 90652 --count 500 --split val
<venv-video>/python tools/video_ball.py train --data runs/video_ball/ft_ds --project runs/video_ball/ft_train
.venv/Scripts/python tools/video_ball.py sample --span 78685 90652 --out runs/video_ball/sample_thr.npz
.venv/Scripts/python tools/video_ball.py sample --span 110808 190198 --out runs/video_ball/sample_h2.npz
<venv-video>/python tools/video_ball.py detect --weights runs/video_ball/ft_train/ft/weights/last.pt \
    --cls 0 --batch 16 --frames runs/video_ball/sample_thr.npz --out runs/video_ball/thr_det_ft.npz
.venv/Scripts/python tools/video_ball.py feasibility --frames runs/video_ball/sample_thr.npz \
    --detections runs/video_ball/thr_det_ft.npz --thresholds 0.1 0.15 ... 0.9      # rejilla de 0,05
(lo mismo con sample_h2 / h2_det_ft y --thresholds 0.1 0.2 0.35 0.5 --control-thresholds 0.2 0.35)
```

**Datos y entrenamiento.** 6.000 recortes positivos y 6.000 negativos de los bloques 3-9, más 500 + 500
de los bloques 10-11 como validación interna del entrenador (no elige pesos: se usa `last.pt`).
20 épocas en 0,89 h (RTX 4070 Laptop). La validación interna (IoU sobre cajas de 24 px alrededor de
etiquetas ruidosas) es poco informativa: P 0,478, R 0,180, mAP50 0,177 en la última época; el
criterio pre-registrado es la distancia al ATD en frames completos. (Durante la 1.ª época un proceso
residual de la etapa 2 compitió por la GPU; solo afectó a la velocidad, no al orden de los datos.)

### 5a. Umbral de operación (bloques 10-11, 1.ª mitad, fuera del entrenamiento)

| conf ≥ | encontrado | recall@1 m | recall@2 m | precisión@2 m | error mediano (m) | hueco |
|---:|---:|---:|---:|---:|---:|---:|
| 0,10 | 0,458 | 0,312 | 0,370 | 0,808 | 0,49 | 0,332 |
| 0,15 | 0,330 | 0,259 | 0,286 | 0,869 | 0,35 | 0,201 |
| **0,20** | 0,260 | 0,221 | 0,237 | **0,913** | 0,26 | 0,121 |
| 0,25 | 0,224 | 0,196 | 0,210 | 0,938 | 0,24 | 0,087 |
| 0,30 | 0,170 | 0,148 | 0,161 | 0,944 | 0,21 | 0,058 |
| **0,35** | 0,119 | 0,110 | 0,116 | **0,971** | 0,19 | 0,044 |
| 0,50 | 0,062 | 0,062 | 0,062 | 1,000 | 0,15 | 0,013 |

Umbrales por la regla pre-registrada: **F1 = 0,20** (≥ 0,90) y **F2 = 0,35** (≥ 0,95). Dentro de la 1.ª
mitad el detector es otro animal que el COCO: error mediano 0,26 m, casi sin falsos positivos lejanos
(1,1% a más de 5 m con `conf ≥ 0,3`), pero muy poco confiado (recall a 2 m 0,24 con 0,20).

### 5b. Go / no-go (2.ª mitad, nunca vista)

| conf ≥ | encontrado | recall@1 m | recall@2 m | precisión@2 m | error mediano (m) | hueco |
|---:|---:|---:|---:|---:|---:|---:|
| 0,10 | 0,336 | 0,168 | 0,227 | 0,677 | 1,00 | 0,286 |
| **0,20** | 0,095 | 0,048 | 0,061 | **0,651** | 0,99 | 0,073 |
| 0,35 | 0,028 | 0,013 | 0,015 | 0,518 | 1,77 | 0,022 |
| 0,50 | 0,008 | 0,002 | 0,002 | 0,250 | 13,4 | 0,004 |

Control (balón solo del vídeo), 2.ª mitad, `conf ≥ 0,20`: controles del vídeo en el 1,3% de los frames
con balón (ATD 19,2%), ninguno del otro equipo que el ATD; en hueco, controles en el 0,4% de los
frames, que coinciden con el estado del motor en 4 de 9.

**NO-GO**: precisión a 2 m de **0,651 < 0,90** al umbral de operación. El detector no generaliza de
una mitad a la otra (los equipos cambian de campo y de dirección de ataque; la luz y el encuadre
cambian): en la 2.ª mitad encuentra cajas en un tercio de frames (0,095 frente a 0,260) y el error mediano sube de 0,26 a 0,99 m. Por la
regla de la adenda se para aquí: ni block 1, ni prueba pública, ni partido completo con este
detector.

### 5c. Velocidad y determinismo (para cualquier entrega futura con vídeo)

- **GPU, ajustes deterministas** (`CUBLAS_WORKSPACE_CONFIG=:4096:8`, `cudnn.benchmark=False`,
  `use_deterministic_algorithms(True)`, ya activos en `Detector`): dos ejecuciones del detector
  afinado sobre 500 frames (120.000..120.499) dan tablas **idénticas byte a byte** (1.122 cajas).
  Sin esos ajustes, el COCO yolo11x difería en 2 de 1.443 confianzas por 0,001-0,002 (sección 3).
- **CPU (fp32) frente a GPU (fp16)**: no idénticos. En 40 frames, 90 cajas frente a 89; mejor caja
  por frame a 0,30 px de mediana (máx. 0,61) y confianza a ≤ 0,008; con umbral 0,35 una caja cruza
  la frontera (3 frente a 4). Reproducir byte a byte exige fijar dispositivo, precisión, versiones
  (`requirements-video.txt`) y ffmpeg.
- **Velocidad** (1920 px): yolo11s afinado ~43 fps de detección en GPU (11,4 s / 500 frames), ~1 h
  para las dos mitades con decodificación secuencial (67 fps medida en block 1); en CPU 2,4 fps,
  ~18,5 h. yolo11x COCO: 10,7 fps, ~4,5 h.
- **Tamaño**: los pesos afinados ocupan 19 MB (> 5 MB, el límite del repositorio) y derivan del vídeo
  licenciado: no se comprometen; viven en `runs/` y los recortes de entrenamiento se borraron.

## 6. Recomendación y limitaciones

**Recomendación: no integrar.** El motor entregado (V0) sigue igual. Ninguna variante pasa su regla
pre-registrada:

| intento | qué falla | número |
|---|---|---|
| COCO yolo11x, V1-V3 | G2: prueba pareada pública en huecos reales | V1 −0,0585, V2 −0,0213, V3 −0,0670 (`n_discordant` 0; +2 a +6 espurias) |
| afinado con etiquetas del ATD, F1-F2 | go/no-go: precisión a 2 m en la 2.ª mitad | 0,651 < 0,90 |

**El hallazgo útil es el sesgo de selección, cuantificado.** El banco de trasplante con relleno de
vídeo (B-opt) promete mucho —media 0,4288 y poco balón 0,4208 frente a 0,3516 y 0,2782— porque
rellena huecos donde la pelota se veía. En los huecos reales del slice público el mismo relleno solo
añade posesiones espurias. Cualquier línea futura de imputación de balón debe medirse en huecos
reales (o con el patrón conjunto B-joint), nunca solo con el banco de trasplante.

**Qué haría falta para reabrirla** (no hecho, fuera de presupuesto): un detector que generalice
entre mitades —entrenar con las dos mitades (validando por bloques alternos, siempre lejos de
block 1), aumentos de luz y volteo vertical por el cambio de campo, o un modelo con contexto temporal
(varios frames apilados) para la pelota en el aire—, y medir primero la cuota de controles correctos
en huecos reales, que es el techo real de la ganancia.

**Limitaciones.**

- Solo 17 posesiones públicas: los Δ públicos son dirección, no prueba; aquí todos los cambios son
  posesiones espurias añadidas, sin ninguna discordante, y por eso la dirección es clara.
- B-joint y el informe por bloques **no se midieron** (la etapa 2 se detuvo por decisión del
  coordinador al quedar establecido el negativo por G2); el acuerdo con el Smart Tagging en los
  bloques 7, 9, 11 y 18 no se midió.
- Las etiquetas del ATD son ruidosas en píxeles (8,9 px de mediana, más con la pelota en el aire) y
  el ATD solo trae `z` en 9.909 de 113.488 frames con balón: no se pudo filtrar la pelota alta.
- Los diagnósticos de la sección 1 usan el ATD como referencia; un ATD equivocado cuenta como error
  del vídeo. La alineación al frame sí está comprobada (sección 1).
- La comprobación de búsqueda exacta por hash (sección 1) se hizo con un script de exploración no
  versionado; la de desfase contra el ATD sí está en `feasibility`.
