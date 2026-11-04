# Carril loo-dead-v3 — ¿la regla que fijó las constantes de `onset` sobrevive a un partido que no vio?

Estado: **pre-registrado — pendiente de correr**. Las secciones 1–6 se commitean antes de la primera
medición. La sección 7 se añade después, en un commit aparte, sin tocar las anteriores.

## 1. Qué se pregunta

`lane-dead-v3.md` §2.1 elige `onset_mps = 3,25` y `onset_cap_s = 40` sobre los **siete** partidos
DFL, con una regla escrita (precisión de frame ≥ 0,90 y luego la menor mediana de |error de inicio|).
El resultado que se publica después —precisión 0,919, recall 0,790, F1 0,849, inicio 5,4 → 0,5 s y
«gana 7 de 7»— se mide **sobre esos mismos siete partidos**.

Eso no es un defecto del carril: la aclaración del 3-nov permite ajustar en datos externos, y DFL lo
es. Pero significa que el 7/7 es **in-sample sobre el corpus externo**, igual que el 0,5368 lo es
sobre el slice. Y es la evidencia con la que se propone adoptar U1 `onset` y con la que se declara que
el `D` entregado (W1, 40 % de los frames) está «fijado fuera del partido».

La pregunta de este carril es una sola: **¿la regla de selección, aplicada a seis partidos, elige
una constante que sigue ganando en el séptimo?**

## 2. Por qué esta y no otra

De las propuestas sobre la mesa, esta es la única que (a) produce una estimación **fuera de muestra**,
(b) usa solo datos admisibles (DFL, CC-BY 4.0; ni ground truth ni vídeo ni el bundle licenciado), y
(c) puede cambiar una decisión del contrato final: si la evidencia de DFL es fuera de muestra, U1 se
puede adoptar citándola; si no, hay que dejar de llamarla independiente.

Las demás no pasan ese filtro: la rejilla de 27 sobre DFL tiene sesgo de escala (4,58 posesiones/min
frente a 3,62; D37), el duelo no es identificable allí (DFL da la posesión a quien toca), Metrica no
declara licencia, y la temperatura y el prior 355 no llegan al CSV.

## 3. Datos

Los siete partidos DFL/IDSSE ya usados por el carril (`tools/external.py`, `MATCHES`), con su estado
vivo/muerto por frame. Se leen de `MTAH_EXTERNAL_DIR`; nunca entran al repositorio. No se descarga
nada en tiempo de ejecución del build ni de `make repro`.

## 4. Protocolo

- **Unidad de validación:** el partido. Siete pliegues; en cada uno se entrena con seis y se evalúa
  con el que quedó fuera. Ningún partido se usa para elegir su propia constante.
- **Candidatos:** exactamente los mismos doce del pre-registro original (`lane-dead-v3.md` §2.1):
  `{3,0; 3,25; 3,5; 3,75} m/s × {10; 20; 40} s`. W1 no es candidato: es la referencia.
- **Regla de selección:** idéntica a la publicada. Entre los candidatos con precisión de frame
  ≥ 0,90 en los seis partidos de entrenamiento, el de menor mediana de |error de inicio|; empate a
  error → mayor F1; empate a F1 → el tope más corto.
- **Métricas en el partido de prueba:** precisión, recall y F1 de frame; mediana de |error de
  inicio|; y el Δ pareado de F1 frente a W1 en ese mismo partido.
- **Determinismo:** sin semillas ni orden aleatorio; el orden de los pliegues es el de `MATCHES`.

## 5. Criterio de decisión (escrito antes de correr)

La evidencia de DFL para `onset` se declara **fuera de muestra** si y solo si:

1. gana a W1 en F1 en **≥ 6 de 7** pliegues (test de signos bilateral, p ≤ 0,062), **y**
2. la constante elegida es la misma en **≥ 5 de 7** pliegues.

Si falla cualquiera de las dos, el 7/7 publicado se declara **ajuste in-sample sobre siete partidos**
y no se cita como validación independiente.

## 6. Qué no hace

- No adopta U1 ni cambia ninguna constante: el resultado va al lead, que decide. Si se adopta, la
  entrega se re-corre con `make repro` y el validador oficial, y el slice se reporta una vez.
- No toca el `D` entregado ni el motor: mide la regla de borde sobre el corpus, no la cadena.
- No usa el ground truth público ni el vídeo en ningún punto.
- No generaliza a los umbrales del motor (`1,5 m / 5 m/s / dwell 1`): esos dependen del ruido de
  nuestro balón y este corpus no lo tiene. Quedan como prior declarado.

## 7. Límites

- n = 7. El test de signos no baja de p = 0,016 con siete pliegues; es dirección fuerte, no prueba
  estadística en el sentido estricto.
- La definición de `D` de DFL no es la del reto (decisión 37). Aquí solo se usa para lo que el carril
  ya usó: el estado vivo/muerto por frame, que es físico y no depende de la definición de posesión.
- El resultado habla de la regla de inicio de las paradas, no de la escala temporal ni del `D`
  completo.

## 8. Reproducción

```bash
export MTAH_EXTERNAL_DIR=...   # idsse/ con los 21 ficheros del espejo
python tools/loo_dead_ball.py --json runs/loo_dead_ball/result.json \
    --write docs/analysis/loo-dead-ball.md
```

Sale con 0 e imprime la tabla por pliegue. El JSON y el markdown son deterministas.
