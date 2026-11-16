# Tiempo de ejecución de la cadena entregada

Medido a mano el 3 de noviembre de 2026 sobre la cadena entregada (SHA-256 `7a7f70b68d39…`, decisión 45), con el
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
| `make engine` (`tools/engine.py --build`), corrida 1 / 2 / 3 | 17,5 / 17,8 / 17,3 s |
| `make repro` (construye dos veces y compara) | 33,7 s |

Las tres salidas dieron el mismo SHA-256 que `submissions/engine.csv`.

## Por etapas, en un solo proceso

```python
import time
from tools import engine, atd, emision, dead_ball
f = engine.features(atd.load("tactical"), emision.team_slots())   # tracking y rasgos
ev = dead_ball.load_evidence()                                     # Smart Tagging
w3 = engine._players_stoppages(engine.KINEMATIC)                   # paradas de los jugadores
out = engine.chain(f, engine.DEFAULT, ev.restarts, engine.delivered_dead(ev))
```

| etapa | tiempo |
|---|---:|
| importar los módulos | 0,54 s |
| cargar el tracking y calcular los rasgos | 5,01 s |
| reanudaciones del Smart Tagging | 0,59 s |
| paradas de los jugadores (W3: 29 rasgos y el detector logístico) | 8,52 s |
| control, duelo, primer control y decodificación | 0,04 s |
| **total en proceso** | **14,70 s** |

El resto hasta los ~17,5 s de `make engine` es el subproceso que escribe el artefacto, el ensamblador
y el validador oficial. Con W1 (decisión 36) la misma medición daba 13,8 s y 11,04 s en proceso: el
detector logístico de W3 cuesta 2,5 s más que la regla de un umbral.
