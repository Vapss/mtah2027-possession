# Motor (#6): mapa de sensibilidad pre-registrado, sobre la cadena entregada

Generado por `python tools/engine_sweep.py --write docs/analysis/engine-sensitivity.md` desde el commit `80c4e968`. No se edita a mano. Rejilla, métricas y regla de
selección: decisión 29, commiteada antes de correr esto; cada fila es la cadena entregada
(motor + reanudaciones + `D`, decisiones 30 y 31) con esos umbrales. En **negrita**, el
default, elegido por física. `gana/pierde` = posesiones del slice público cuyo estado de
acierto a IoU 0,5 cambia frente al default (test de signos; hacen falta ≥ 6 en el mismo
sentido). `ST` = acuerdo con el Smart Tagging, la única señal independiente del tracking;
`ST bajos` es su media en los bloques 7, 9, 11 y 18, los de menos balón.

| radio | vel. | dwell | spellF1 | macroF1 | gana | pierde | pos/min | ST | ST bajos |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **1,5** | **5** | **1** | **0,4585** | **0,7066** | **0** | **0** | **3,64** | **73,1%** | **72,4%** |
| 1,0 | 3 | 1 | 0,5250 | 0,6750 | 0 | 2 | 2,25 | 76,6% | 91,0% |
| 1,0 | 3 | 5 | 0,3704 | 0,6682 | 0 | 4 | 1,87 | 76,7% | 85,3% |
| 1,0 | 3 | 12 | 0,2609 | 0,6957 | 0 | 7 | 1,34 | 76,9% | 88,9% |
| 1,0 | 5 | 1 | 0,4718 | 0,7006 | 1 | 1 | 2,99 | 77,3% | 86,0% |
| 1,0 | 5 | 5 | 0,4973 | 0,7039 | 0 | 0 | 2,47 | 76,4% | 87,2% |
| 1,0 | 5 | 12 | 0,4667 | 0,6981 | 0 | 2 | 1,72 | 79,8% | 86,7% |
| 1,0 | 7 | 1 | 0,4718 | 0,7052 | 1 | 1 | 3,51 | 75,0% | 85,9% |
| 1,0 | 7 | 5 | 0,5081 | 0,7109 | 1 | 0 | 2,83 | 77,1% | 86,6% |
| 1,0 | 7 | 12 | 0,5176 | 0,7014 | 0 | 1 | 1,96 | 80,2% | 86,8% |
| 1,5 | 3 | 1 | 0,4889 | 0,6912 | 0 | 2 | 2,67 | 74,7% | 73,1% |
| 1,5 | 3 | 5 | 0,3852 | 0,6856 | 0 | 4 | 2,19 | 74,3% | 69,8% |
| 1,5 | 3 | 12 | 0,3556 | 0,6647 | 0 | 5 | 1,55 | 77,4% | 88,9% |
| 1,5 | 5 | 5 | 0,4821 | 0,7098 | 0 | 0 | 2,99 | 76,2% | 69,9% |
| 1,5 | 5 | 12 | 0,4000 | 0,7027 | 0 | 2 | 2,17 | 77,3% | 68,8% |
| 1,5 | 7 | 1 | 0,4488 | 0,7042 | 0 | 0 | 4,41 | 70,4% | 71,2% |
| 1,5 | 7 | 5 | 0,4488 | 0,7042 | 0 | 0 | 3,70 | 72,2% | 68,9% |
| 1,5 | 7 | 12 | 0,4889 | 0,7047 | 1 | 1 | 2,48 | 76,6% | 68,9% |
| 2,0 | 3 | 1 | 0,5297 | 0,6973 | 0 | 0 | 3,01 | 73,7% | 73,5% |
| 2,0 | 3 | 5 | 0,4000 | 0,6966 | 0 | 3 | 2,41 | 76,5% | 73,1% |
| 2,0 | 3 | 12 | 0,3429 | 0,6625 | 0 | 5 | 1,78 | 78,7% | 81,7% |
| 2,0 | 5 | 1 | 0,4182 | 0,7026 | 0 | 0 | 4,08 | 72,5% | 73,3% |
| 2,0 | 5 | 5 | 0,4923 | 0,7138 | 0 | 0 | 3,36 | 74,9% | 73,7% |
| 2,0 | 5 | 12 | 0,4114 | 0,7110 | 0 | 2 | 2,48 | 76,6% | 68,7% |
| 2,0 | 7 | 1 | 0,4000 | 0,7001 | 0 | 0 | 5,00 | 71,9% | 71,5% |
| 2,0 | 7 | 5 | 0,4279 | 0,7035 | 0 | 0 | 4,26 | 71,1% | 72,1% |
| 2,0 | 7 | 12 | 0,4757 | 0,7014 | 1 | 1 | 2,91 | 77,8% | 68,4% |

## Lectura según la regla de la decisión 29

- `spellF1` de las otras 26 configuraciones: 0,2609 .. 0,5297 (default 0,4585).
- Configuraciones que ganan al default según la regla (test de signos p ≤ 0,031, más ganadas que perdidas, sin empeorar el acuerdo con el Smart Tagging y sin romper un bloque): **0**.
- Acuerdo con el Smart Tagging: 70,4% .. 80,2% (default 73,1%).
