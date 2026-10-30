# Banco de trasplante de huecos

Generado por `python tools/bench.py --method engine --method smooth50 --write docs/analysis/bench.md` desde el commit `8c58268d`. No se edita a mano. Cada fila es un bloque donante: su
patrón de balón ausente se trasplanta sobre la ventana pública (bloque 1★), y se puntúa
contra su ground truth: robustez a la cantidad y longitud de balón perdido, no al lugar.

| donante | balón | `engine` | `smooth50` |
|---|---:|---:|---:|
| 1★ (sin trasplante) | 88,2% | 0,5189 | 0,3256 |
| 2 | 70,9% | 0,5455 | 0,2583 |
| 3 | 64,7% | 0,5091 | 0,2348 |
| 4 | 61,5% | 0,3882 | 0,2667 |
| 5 | 53,5% | 0,5000 | 0,2341 |
| 6 | 54,9% | 0,3086 | 0,1923 |
| 7 | 28,4% | 0,3692 | 0,1600 |
| 8 | 52,9% | 0,3667 | 0,1727 |
| 9 | 21,1% | 0,2462 | 0,0842 |
| 10 | 50,4% | 0,3152 | 0,2000 |
| 12 | 76,0% | 0,4485 | 0,3024 |
| 13 | 57,6% | 0,5161 | 0,2927 |
| 14 | 61,7% | 0,3407 | 0,2545 |
| 15 | 41,6% | 0,3600 | 0,2333 |
| 16 | 68,8% | 0,5189 | 0,2182 |
| 17 | 51,0% | 0,2968 | 0,2419 |
| 18 | 19,0% | 0,2370 | 0,1067 |
| 19 | 44,8% | 0,3000 | 0,1854 |
| 20 | 45,6% | 0,3000 | 0,2244 |
| 21 | 52,1% | 0,3375 | 0,2222 |

| resumen | `engine` | `smooth50` |
|---|---:|---:|
| sin trasplante | 0,5189 | 0,3256 |
| media de donantes (n=19) | 0,3792 | 0,2150 |
| media de donantes con < 50% de balón (n=6) | 0,3021 | 0,1657 |
| peor donante | 0,2370 | 0,0842 |
