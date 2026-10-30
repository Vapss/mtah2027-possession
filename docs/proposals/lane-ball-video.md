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
