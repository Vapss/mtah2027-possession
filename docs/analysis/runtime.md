# Tiempo de ejecución de la cadena entregada

Medido a mano el 30 de octubre de 2026 sobre la cadena entregada (SHA-256 `72c98ed4bb4a…`), con el
bundle licenciado en `MTAH_DATA_DIR`. Máquina: portátil con Intel Core i9-13980HX (32 hilos),
16 GB de RAM, Windows 11, Python 3.12.3 del entorno fijado (`uv.lock`). Son tiempos de pared; otra
máquina dará otros.

## La entrega completa

```bash
# tres corridas, cada una en su directorio bajo runs/
for i in 1 2 3; do
  time python tools/engine.py --build runs/timing-$i --submission /tmp/sub$i.csv
done
time python tools/repro.py --against submissions/engine.csv
```

| comando | tiempo |
|---|---:|
| `make engine` (`tools/engine.py --build`), corrida 1 / 2 / 3 | 13,8 / 13,8 / 14,1 s |
| `make repro` (construye dos veces y compara) | 27,4 s |

Las tres salidas dieron el mismo SHA-256 que `submissions/engine.csv`.

## Por etapas, en un solo proceso

```python
import time
from tools import engine, atd, emision, dead_ball
f = engine.features(atd.load("tactical"), emision.team_slots())   # tracking y rasgos
ev = dead_ball.load_evidence()                                     # Smart Tagging
w1 = engine._players_stoppages()                                   # paradas de los jugadores
out = engine.chain(f, engine.DEFAULT, ev.restarts, engine.delivered_dead(ev))
```

| etapa | tiempo |
|---|---:|
| importar los módulos | 0,43 s |
| cargar el tracking y calcular los rasgos | 4,12 s |
| reanudaciones del Smart Tagging | 0,48 s |
| paradas de los jugadores (W1) | 5,96 s |
| control, duelo y decodificación | 0,04 s |
| **total en proceso** | **11,04 s** |

El resto hasta los ~14 s de `make engine` es el subproceso que escribe el artefacto, el ensamblador y
el validador oficial. La nota de `lane-dead-v2.md` §9 ("unos 15 s más por corrida" para W1) es de una
versión anterior del código; en esta medición W1 cuesta 6 s.
