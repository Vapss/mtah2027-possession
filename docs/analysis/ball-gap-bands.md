# A2 — Estructura de los 150 huecos de balón

Generado por `python tools/band_gaps.py --ship artifacts/possession.csv --write docs/analysis/ball-gap-bands.md` desde el commit `b1c8e0b5`. No se edita a mano.

Ventana pública: frames **11.185..18.684** (7.500 frames). Base: `evaluation/results/baseline_smooth50.csv`.

## 1. Estructura

Medido sobre los frames en juego (los dos bloques de `games.half_video_blocks`), no sobre los 199.319: fuera de los medios tiempos hay huecos de 1–2 frames que no se rellenan, y contarlos inflaba el tramo ≤25 de 17 a 43.

- Huecos en juego: **150 huecos**, **64.643 frames sin balón** de 158.857 (40,7%).
- Sin balón en todo el partido: 85.831 frames (43,1%).

## 2. Tabla por tramo, sobre el ancla

Δ pareado de `spellF1` contra la base sin tocar. `disc` = posesiones verdaderas que pasan de emparejada a no emparejada o al revés (base/política). `jackknife` quita una posesión verdadera por vez. `macroF1` se reporta y no decide.

### ≤25 frames — 17 huecos / 75 frames (2 en la ventana, 7 puntuados)

| política | spellF1 | macroF1 | Δ pareado | disc | jackknife |
|---|---:|---:|---:|---:|---|
| fill | 0,3256 | 0,6207 | +0,00000 | 0 (0/0) | 0,0000..0,0000 |
| D | 0,3182 | 0,6199 | -0,00740 | 0 (0/0) | -0,0078..-0,0066 |
| X | 0,3256 | 0,6205 | +0,00000 | 0 (0/0) | 0,0000..0,0000 |

**no medible localmente** — ninguna transición y 0 discordancias en 7 frames puntuados; el relleno no puede mover ninguna posesión.

### 26–125 frames — 1 hueco / 122 frames (0 en la ventana, 0 puntuados)

| política | spellF1 | macroF1 | Δ pareado | disc | jackknife |
|---|---:|---:|---:|---:|---|
| fill | 0,3256 | 0,6207 | +0,00000 | 0 (0/0) | 0,0000..0,0000 |
| D | 0,3256 | 0,6207 | +0,00000 | 0 (0/0) | 0,0000..0,0000 |
| X | 0,3256 | 0,6207 | +0,00000 | 0 (0/0) | 0,0000..0,0000 |

**no medible localmente** — los huecos del tramo no tocan ningún frame puntuado.

### 126–500 frames — 88 huecos / 21.154 frames (4 en la ventana, 878 puntuados)

| política | spellF1 | macroF1 | Δ pareado | disc | jackknife |
|---|---:|---:|---:|---:|---|
| fill | 0,3805 | 0,5105 | +0,05491 | 2 (0/2) | 0,0357..0,0567 |
| D | 0,3524 | 0,6533 | +0,02680 | 1 (0/1) | 0,0077..0,0369 |
| X | 0,3805 | 0,5130 | +0,05491 | 2 (0/2) | 0,0357..0,0567 |

**no medible localmente** — el efecto depende de un hueco: quitando [17.047, 17.279) queda Δ +0,01588 con 0 discordante(s).

| hueco quitado | Δ pareado | disc | jackknife |
|---|---:|---:|---|
| [12.831, 12.979) (148 frames) | +0,04585 | 2 | 0,0272..0,0472 |
| [16.646, 16.778) (132 frames) | +0,05537 | 2 | 0,0369..0,0569 |
| [17.047, 17.279) (232 frames) | +0,01588 | 0 | 0,0048..0,0257 |
| [17.460, 17.826) (366 frames) | +0,04515 | 2 | 0,0257..0,0467 |

### >500 frames — 44 huecos / 43.292 frames (0 en la ventana, 0 puntuados)

| política | spellF1 | macroF1 | Δ pareado | disc | jackknife |
|---|---:|---:|---:|---:|---|
| fill | 0,3256 | 0,6207 | +0,00000 | 0 (0/0) | 0,0000..0,0000 |
| D | 0,3256 | 0,6207 | +0,00000 | 0 (0/0) | 0,0000..0,0000 |
| X | 0,3256 | 0,6207 | +0,00000 | 0 (0/0) | 0,0000..0,0000 |

**no medible localmente** — los huecos del tramo no tocan ningún frame puntuado.

## 3. La cadena que se entrega

La misma tabla sobre `artifacts/possession.csv` decodificado como en DECISIONS 20 (`confidence = 0` → `X`). Acá `D` es un contrafáctico: el decodificador no lo produce, se mide para saber qué se perdería emitiéndolo.

| tramo | fill Δ | X Δ | D Δ | disc fill/X/D |
|---|---:|---:|---:|---|
| ≤25 | +0,00000 | +0,00000 | -0,00304 | 0/0/0 |
| 26–125 | +0,00000 | +0,00000 | +0,00000 | 0/0/0 |
| 126–500 | +0,00000 | +0,00000 | -0,00332 | 0/0/0 |
| >500 | +0,00000 | +0,00000 | +0,00000 | 0/0/0 |

En esta base `fill` y `X` empatan exactamente en `spellF1`: el scorer oficial ya rellena `X` con la etiqueta previa del medio tiempo. La única diferencia entre las dos es `macroF1`, y `D` pierde o empata en todos los tramos.

## 4. Lo que hay dentro de cada hueco puntuado

| hueco | frames | tramo | GT dentro | transiciones | posesiones GT |
|---|---:|---|---|---:|---|
| [11.185, 11.187) | 2 | ≤25 | A 2 | 0 | #1 |
| [11.508, 11.513) | 5 | ≤25 | H 5 | 0 | #2 |
| [12.831, 12.979) | 148 | 126–500 | A 20, D 128 | 1 | #5 |
| [16.646, 16.778) | 132 | 126–500 | A 132 | 0 | #14 |
| [17.047, 17.279) | 232 | 126–500 | A 232 | 0 | #14 |
| [17.460, 17.826) | 366 | 126–500 | D 366 | 0 | — |

## 5. Decisión por tramo

La regla es la misma en los cuatro tramos y no depende de la longitud: **arrastrar el estado, nunca `D` por ausencia de balón** (DECISIONS 16). Lo que cambia por tramo es cuánta evidencia local hay para decirlo, y eso se escribe:

| tramo | % del déficit de balón | evidencia | decisión |
|---|---:|---|---|
| ≤25 | 0,1% | no medible localmente: ninguna transición y 0 discordancias en 7 frames puntuados; el relleno no puede mover ninguna posesión | arrastrar estado; `D` no |
| 26–125 | 0,2% | no medible localmente: los huecos del tramo no tocan ningún frame puntuado | arrastrar estado; `D` no |
| 126–500 | 32,7% | no medible localmente: el efecto depende de un hueco: quitando [17.047, 17.279) queda Δ +0,01588 con 0 discordante(s) | arrastrar estado; `D` no |
| >500 | 67,0% | no medible localmente: los huecos del tramo no tocan ningún frame puntuado | arrastrar estado; `D` no |

Ningún tramo justifica un umbral propio: el único que mueve `spellF1` en el slice lo hace por un solo hueco, y el que más frames aporta no tiene un solo frame puntuado adentro. Una política distinta por tramo sería una decisión sobre 4 posesiones repartidas en 2 tramos, y en el tramo grande sobre ninguna.

## 6. Lo que esta muestra no puede decir

- La ventana cubre 11.185..18.684: **ningún hueco de más de 500 frames** cae adentro, y ese tramo concentra la mayor parte del déficit de balón. Su política no se mide acá; se decide por principio (DECISIONS 16), no por dato.
- Bandas de ruido: 0,04 en el partido completo y 0,33 en el slice. Un Δ local por debajo de la primera no es un resultado ni en la dirección.
- Toda la evidencia local descansa en 4 posesiones GT (#1, #2, #5, #14) de las 17 del slice, y el Δ del tramo 126–500 se cae a +0,016 con 0 discordancias si se quita uno de sus cuatro huecos.
- La ventana pública es la parte del partido con más balón detectado (88,2% frente a 56,9%), así que mide el régimen fácil de este problema.
- El ground truth del partido completo es privado: lo único observable ahí es la estructura del hueco, no la etiqueta.
