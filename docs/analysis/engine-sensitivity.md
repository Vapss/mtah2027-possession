# Motor (#6): mapa de sensibilidad pre-registrado, sobre la cadena entregada

Generado por `python tools/engine_sweep.py --write docs/analysis/engine-sensitivity.md` desde el commit `8c58268d`. No se edita a mano. Rejilla, métricas y regla de
selección: decisión 29, commiteada antes de correr esto; cada fila es la cadena entregada
(motor + reanudaciones + `D`, decisiones 30 y 31) con esos umbrales. En **negrita**, el
default, elegido por física. `gana/pierde` = posesiones del slice público cuyo estado de
acierto a IoU 0,5 cambia frente al default (test de signos; hacen falta ≥ 6 en el mismo
sentido). `ST` = acuerdo con el Smart Tagging, la única señal independiente del tracking;
`ST bajos` es su media en los bloques 7, 9, 11 y 18, los de menos balón.

| radio | vel. | dwell | spellF1 | macroF1 | gana | pierde | pos/min | ST | ST bajos |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **1,5** | **5** | **1** | **0,5189** | **0,7114** | **0** | **0** | **3,29** | **73,4%** | **72,4%** |
| 1,0 | 3 | 1 | 0,5067 | 0,6934 | 0 | 2 | 2,10 | 76,4% | 90,5% |
| 1,0 | 3 | 5 | 0,3704 | 0,6682 | 0 | 4 | 1,76 | 76,9% | 87,5% |
| 1,0 | 3 | 12 | 0,2609 | 0,6957 | 0 | 7 | 1,32 | 76,8% | 88,9% |
| 1,0 | 5 | 1 | 0,4973 | 0,7027 | 1 | 1 | 2,82 | 77,7% | 86,2% |
| 1,0 | 5 | 5 | 0,4471 | 0,6984 | 0 | 1 | 2,29 | 77,0% | 88,0% |
| 1,0 | 5 | 12 | 0,4143 | 0,7002 | 0 | 3 | 1,68 | 79,4% | 86,6% |
| 1,0 | 7 | 1 | 0,4973 | 0,7073 | 1 | 1 | 3,30 | 74,9% | 85,8% |
| 1,0 | 7 | 5 | 0,4588 | 0,7053 | 1 | 1 | 2,57 | 78,9% | 87,9% |
| 1,0 | 7 | 12 | 0,4750 | 0,7034 | 0 | 2 | 1,93 | 80,1% | 86,6% |
| 1,5 | 3 | 1 | 0,5125 | 0,7233 | 0 | 2 | 2,36 | 74,8% | 72,5% |
| 1,5 | 3 | 5 | 0,3704 | 0,6715 | 0 | 4 | 1,99 | 75,7% | 70,5% |
| 1,5 | 3 | 12 | 0,3556 | 0,6647 | 0 | 5 | 1,44 | 75,8% | 88,9% |
| 1,5 | 5 | 5 | 0,4588 | 0,7025 | 0 | 1 | 2,64 | 76,3% | 70,6% |
| 1,5 | 5 | 12 | 0,3500 | 0,7029 | 0 | 3 | 2,03 | 77,6% | 68,8% |
| 1,5 | 7 | 1 | 0,5081 | 0,7091 | 0 | 0 | 3,97 | 71,3% | 70,9% |
| 1,5 | 7 | 5 | 0,4889 | 0,6969 | 0 | 0 | 3,09 | 74,3% | 70,4% |
| 1,5 | 7 | 12 | 0,4471 | 0,7057 | 1 | 2 | 2,32 | 77,2% | 68,9% |
| 2,0 | 3 | 1 | 0,4606 | 0,6979 | 0 | 2 | 2,54 | 75,0% | 73,7% |
| 2,0 | 3 | 5 | 0,3733 | 0,6755 | 0 | 3 | 2,14 | 77,4% | 70,4% |
| 2,0 | 3 | 12 | 0,3846 | 0,6528 | 0 | 4 | 1,63 | 77,8% | 79,4% |
| 2,0 | 5 | 1 | 0,3895 | 0,7091 | 0 | 2 | 3,37 | 72,6% | 74,5% |
| 2,0 | 5 | 5 | 0,4471 | 0,7063 | 0 | 2 | 2,83 | 74,7% | 71,1% |
| 2,0 | 5 | 12 | 0,4000 | 0,7081 | 0 | 3 | 2,25 | 77,3% | 68,7% |
| 2,0 | 7 | 1 | 0,4400 | 0,7016 | 0 | 0 | 4,19 | 72,1% | 72,0% |
| 2,0 | 7 | 5 | 0,4111 | 0,6985 | 0 | 1 | 3,36 | 73,1% | 70,8% |
| 2,0 | 7 | 12 | 0,4471 | 0,7039 | 1 | 2 | 2,60 | 78,4% | 68,5% |

## Lectura según la regla de la decisión 29

- `spellF1` de las otras 26 configuraciones: 0,2609 .. 0,5125 (default 0,5189).
- Configuraciones que ganan al default según la regla (test de signos p ≤ 0,031, más ganadas que perdidas, sin empeorar el acuerdo con el Smart Tagging y sin romper un bloque): **0**.
- Acuerdo con el Smart Tagging: 71,3% .. 80,1% (default 73,4%).
