# Motor (#6): mapa de sensibilidad pre-registrado

Generado por `python tools/engine_sweep.py --write docs/analysis/engine-sensitivity.md` desde el commit `3d63ba56`. No se edita a mano. Rejilla, métricas y regla de
selección: decisión 29, commiteada antes de correr esto. La fila **en negrita** es el
default, elegido por física. `gana/pierde` = posesiones del slice público cuyo estado de
acierto a IoU 0,5 cambia frente al default (test de signos; hacen falta ≥ 6 en el mismo
sentido). `ST` = acuerdo con el Smart Tagging, la única señal independiente del tracking;
`ST bajos` es su media en los bloques 7, 9, 11 y 18, los de menos balón.

| radio | vel. | dwell | spellF1 | macroF1 | gana | pierde | pos/min | ST | ST bajos |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **1,5** | **5** | **1** | **0,4390** | **0,5113** | **0** | **0** | **3,25** | **74,0%** | **75,0%** |
| 1,0 | 3 | 1 | 0,4875 | 0,4818 | 0 | 2 | 1,84 | 75,7% | 93,6% |
| 1,0 | 3 | 5 | 0,2615 | 0,4707 | 0 | 6 | 1,43 | 75,8% | 88,3% |
| 1,0 | 3 | 12 | 0,1455 | 0,4943 | 0 | 9 | 0,90 | 76,2% | 91,4% |
| 1,0 | 5 | 1 | 0,4410 | 0,5054 | 1 | 1 | 2,61 | 77,3% | 87,6% |
| 1,0 | 5 | 5 | 0,4649 | 0,5082 | 0 | 0 | 2,06 | 77,1% | 90,0% |
| 1,0 | 5 | 12 | 0,3724 | 0,4990 | 0 | 4 | 1,27 | 79,4% | 89,5% |
| 1,0 | 7 | 1 | 0,4410 | 0,5098 | 1 | 1 | 3,13 | 75,0% | 84,5% |
| 1,0 | 7 | 5 | 0,4757 | 0,5151 | 1 | 0 | 2,44 | 77,1% | 86,5% |
| 1,0 | 7 | 12 | 0,4364 | 0,5026 | 0 | 3 | 1,54 | 80,2% | 89,6% |
| 1,5 | 3 | 1 | 0,4667 | 0,4963 | 0 | 2 | 2,29 | 74,4% | 75,7% |
| 1,5 | 3 | 5 | 0,2769 | 0,4872 | 0 | 6 | 1,78 | 73,6% | 71,2% |
| 1,5 | 3 | 12 | 0,2462 | 0,4673 | 0 | 7 | 1,12 | 77,2% | 91,4% |
| 1,5 | 5 | 5 | 0,4615 | 0,5143 | 0 | 0 | 2,59 | 77,0% | 71,3% |
| 1,5 | 5 | 12 | 0,3152 | 0,5038 | 0 | 4 | 1,75 | 77,8% | 70,4% |
| 1,5 | 7 | 1 | 0,4293 | 0,5091 | 0 | 0 | 4,06 | 70,8% | 67,9% |
| 1,5 | 7 | 5 | 0,4293 | 0,5091 | 0 | 0 | 3,32 | 72,4% | 64,2% |
| 1,5 | 7 | 12 | 0,4114 | 0,5057 | 1 | 3 | 2,05 | 77,9% | 70,5% |
| 2,0 | 3 | 1 | 0,4973 | 0,5018 | 0 | 1 | 2,70 | 73,6% | 76,0% |
| 2,0 | 3 | 5 | 0,3613 | 0,4999 | 0 | 4 | 2,08 | 75,1% | 75,7% |
| 2,0 | 3 | 12 | 0,2222 | 0,4655 | 0 | 8 | 1,38 | 78,4% | 83,6% |
| 2,0 | 5 | 1 | 0,3721 | 0,5036 | 0 | 2 | 3,78 | 74,2% | 75,7% |
| 2,0 | 5 | 5 | 0,4615 | 0,5184 | 0 | 1 | 3,02 | 75,3% | 73,9% |
| 2,0 | 5 | 12 | 0,3771 | 0,5148 | 0 | 3 | 2,11 | 77,1% | 70,3% |
| 2,0 | 7 | 1 | 0,3535 | 0,5013 | 0 | 2 | 4,70 | 73,1% | 71,2% |
| 2,0 | 7 | 5 | 0,4000 | 0,5085 | 0 | 1 | 3,93 | 71,1% | 66,5% |
| 2,0 | 7 | 12 | 0,4432 | 0,5066 | 1 | 2 | 2,54 | 78,0% | 66,9% |

## Lectura según la regla de la decisión 29

- `spellF1` de las otras 26 configuraciones: 0,1455 .. 0,4973 (default 0,4390).
- Configuraciones que ganan al default con ≥ 6 posesiones discordantes en el mismo sentido: **0**.
- Acuerdo con el Smart Tagging: 70,8% .. 80,2% (default 74,0%).
