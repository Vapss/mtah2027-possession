# A0 — Qué es `D`, medido

Generado por `python tools/characterize_d.py --write docs/analysis/d-characterization.md` desde el commit `6b97b538`.

Ventana pública: frames **11185..18684** (7.500 frames, 5,0 min de juego). El ground truth del partido es privado, así que nada de esto describe el partido entero.

## 1. Cuánto es `D` y cuánto dura

- Frames `D`: **1.469 / 7.500 (19,6%)**.
- Tramos: **4** en 300 s de juego.

| tramo | frames | duración | % de la ventana |
|---|---|---|---|
| 1 | 138 | 5,52 s | 1,8% |
| 2 | 511 | 20,44 s | 6,8% |
| 3 | 458 | 18,32 s | 6,1% |
| 4 | 362 | 14,48 s | 4,8% |

La duración mediana de un tramo de `D` es **16,40 s**, y el más largo 20,44 s.

## 2. Qué señal separa `D` de juego vivo

Tasa base a batir: **19,6%** de los frames son `D`. `P(D | señal)` es lo que la señal promete; `P(señal | D)` es cuánto de `D` cubre; `lift` es la primera dividida por la base.

| señal | frames | P(D | señal) | P(señal | D) | lift |
|---|---:|---:|---:|---:|
| balón ausente | 885 | 55,8% | 33,6% | 2,85 |
| balón fuera del campo | 106 | 98,1% | 7,1% | 5,01 |
| balón lento (<1 m/s) | 510 | 19,4% | 6,7% | 0,99 |
| balón a >5 m del jugador más cercano | 1.270 | 27,3% | 23,6% | 1,39 |
| SET PIECES | 1.189 | 56,1% | 45,4% | 2,86 |
| GOALS | 0 | 0,0% | 0,0% | 0,00 |
| BUILD UP | 326 | 9,2% | 2,0% | 0,47 |

## 3. El balón dentro de `D`

- `P(sin balón | D)` = **33,6%**; `P(D | sin balón)` = **55,8%**. Es decir, `D` **no** es un problema de balón perdido.
- Velocidad mediana del balón: **2,70 m/s dentro de `D`** frente a **5,74 m/s** con balón vivo.
- Distancia mediana al jugador más cercano: **2,89 m** en `D` frente a **1,65 m** en juego vivo.
- Balón fuera del rectángulo del campo: **106** frames, de los cuales 98,1% son `D`.

## 4. Lectura

- **`D` son tramos, no frames.** La mediana dura 16,40 s: un umbral por frame, sin estado, no puede reconstruir esa estructura.
- **La premisa del stream A no se sostiene.** `P(sin balón | D)` = 33,6% y `P(D | sin balón)` = 55,8%: el balón perdido explica un tercio de `D` y acierta la mitad de las veces que dispara.
- **La única señal de balón casi perfecta es el fuera de campo:** precisión 98,1%, cobertura 7,1%. Dispara `D`; no lo detecta.
- **El balón no se queda quieto.** Velocidad menor que 1 m/s tiene lift 0,99: dentro de `D` el balón rueda a 2,70 m/s de mediana. Y estar a más de 5 m del jugador más cercano da lift 1,39, pese a que la distancia mediana en `D` (2,89 m) duplique la de juego vivo (1,65 m).
- **`SET PIECES` es la mejor señal contextual y no basta:** lift 2,86, cubre 45,4% de `D` con precisión 56,1%. `BUILD UP` baja de 1 (lift 0,47), que es el control funcionando: se dispara con balón vivo.
- **Consecuencia para #5, #6 y #16:** `D` se decide por estado y contexto (reanudación, saque, fuera de juego, celebración), no por un umbral del track del balón. Las señales de balón entran como disparadores de precisión dentro de un modelo con memoria, nunca como detector.

## 5. Lo que esta muestra no puede decir

- 1.469 frames y 4 tramos de `D`: los intervalos de confianza son anchos y cualquier umbral elegido aquí es una hipótesis, no un resultado.
- La ventana pública es la parte del partido con más balón detectado (88,2% frente a 56,9% global), así que la cobertura de las señales de balón está **sobrestimada**.
- El `D` del partido completo es privado: lo único observable ahí son las señales estructurales (Smart Tagging, huecos del tracker, saques), no la etiqueta.
