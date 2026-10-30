# Motor (#6): mapa de sensibilidad pre-registrado, sobre la cadena entregada

Generado por `python tools/engine_sweep.py --write docs/analysis/engine-sensitivity.md` desde el commit `ffbd6de1`. No se edita a mano. Rejilla, métricas y regla de
selección: decisión 29, commiteada antes de correr esto; cada fila es la cadena entregada
(motor + reanudaciones + `D`, decisiones 30 y 31) con esos umbrales. En **negrita**, el
default, elegido por física. `gana/pierde` = posesiones del slice público cuyo estado de
acierto a IoU 0,5 cambia frente al default (test de signos; hacen falta ≥ 6 en el mismo
sentido). `ST` = acuerdo con el Smart Tagging, la única señal independiente del tracking;
`ST bajos` es su media en los bloques 7, 9, 11 y 18, los de menos balón.

| radio | vel. | dwell | spellF1 | macroF1 | gana | pierde | pos/min | ST | ST bajos |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **1,5** | **5** | **1** | **0,5368** | **0,8533** | **0** | **0** | **3,58** | **77,1%** | **85,6%** |
| 1,0 | 3 | 1 | 0,4750 | 0,8329 | 0 | 3 | 2,50 | 77,9% | 88,7% |
| 1,0 | 3 | 5 | 0,4138 | 0,8144 | 0 | 4 | 2,17 | 78,1% | 81,6% |
| 1,0 | 3 | 12 | 0,3680 | 0,8414 | 0 | 6 | 1,77 | 78,5% | 82,3% |
| 1,0 | 5 | 1 | 0,5053 | 0,8439 | 1 | 1 | 3,15 | 79,5% | 83,8% |
| 1,0 | 5 | 5 | 0,4686 | 0,8436 | 0 | 1 | 2,66 | 78,8% | 83,5% |
| 1,0 | 5 | 12 | 0,4414 | 0,8481 | 0 | 3 | 2,11 | 81,3% | 80,1% |
| 1,0 | 7 | 1 | 0,5053 | 0,8488 | 1 | 1 | 3,64 | 77,0% | 83,2% |
| 1,0 | 7 | 5 | 0,4800 | 0,8512 | 1 | 1 | 2,94 | 80,8% | 83,5% |
| 1,0 | 7 | 12 | 0,5375 | 0,8505 | 0 | 1 | 2,29 | 82,3% | 80,1% |
| 1,5 | 3 | 1 | 0,5333 | 0,8662 | 0 | 2 | 2,75 | 78,0% | 85,8% |
| 1,5 | 3 | 5 | 0,4138 | 0,8180 | 0 | 4 | 2,40 | 78,0% | 83,5% |
| 1,5 | 3 | 12 | 0,4000 | 0,8108 | 0 | 5 | 1,92 | 77,2% | 82,3% |
| 1,5 | 5 | 5 | 0,4800 | 0,8480 | 0 | 1 | 2,99 | 79,8% | 83,6% |
| 1,5 | 5 | 12 | 0,4125 | 0,8507 | 0 | 2 | 2,41 | 80,7% | 82,4% |
| 1,5 | 7 | 1 | 0,5263 | 0,8508 | 0 | 0 | 4,30 | 75,5% | 83,8% |
| 1,5 | 7 | 5 | 0,5081 | 0,8421 | 0 | 0 | 3,46 | 78,0% | 83,3% |
| 1,5 | 7 | 12 | 0,5059 | 0,8527 | 1 | 1 | 2,70 | 81,0% | 82,5% |
| 2,0 | 3 | 1 | 0,5294 | 0,8416 | 0 | 1 | 2,88 | 79,3% | 87,0% |
| 2,0 | 3 | 5 | 0,4516 | 0,8216 | 0 | 2 | 2,50 | 80,6% | 83,3% |
| 2,0 | 3 | 12 | 0,4286 | 0,7983 | 0 | 4 | 2,08 | 79,0% | 71,3% |
| 2,0 | 5 | 1 | 0,4421 | 0,8570 | 0 | 2 | 3,66 | 76,5% | 88,1% |
| 2,0 | 5 | 5 | 0,5059 | 0,8539 | 0 | 1 | 3,13 | 78,4% | 84,0% |
| 2,0 | 5 | 12 | 0,4667 | 0,8563 | 0 | 2 | 2,58 | 80,6% | 82,1% |
| 2,0 | 7 | 1 | 0,4585 | 0,8470 | 0 | 1 | 4,52 | 75,7% | 85,3% |
| 2,0 | 7 | 5 | 0,4324 | 0,8436 | 0 | 2 | 3,67 | 77,1% | 83,7% |
| 2,0 | 7 | 12 | 0,5059 | 0,8504 | 1 | 1 | 2,89 | 81,5% | 81,9% |

## Lectura según la regla de la decisión 29

- `spellF1` de las otras 26 configuraciones: 0,3680 .. 0,5375 (default 0,5368).
- Configuraciones que ganan al default según la regla (test de signos p ≤ 0,031, más ganadas que perdidas, sin empeorar el acuerdo con el Smart Tagging y sin romper un bloque): **0**.
- Acuerdo con el Smart Tagging: 75,5% .. 82,3% (default 77,1%).
