# Auditoría del margen: qué componente pierde el `spellF1`

Generado por `python tools/headroom.py --write docs/analysis/headroom.md` desde el commit `4ccca6ef`. No se edita a mano.
**Diagnóstico con la GT pública: no elige ninguna regla, constante ni variante**
(decisión 40). Cada fila cambia un componente de la cadena entregada por la verdad y
puntúa en el slice y en el banco de trasplante.

| cadena | slice | banco (media) | banco, poco balón | peor donante |
|---|---:|---:|---:|---:|
| delivered | 0,5368 | 0,4351 | 0,3595 | 0,2400 |
| oracle D | 0,6162 | 0,5128 | 0,4114 | 0,2933 |
| oracle D: only remove our false D | 0,5789 | 0,4649 | 0,3765 | 0,2452 |
| oracle D: only add the D we miss | 0,5730 | 0,4824 | 0,3944 | 0,2897 |
| oracle team on the live frames | 0,8889 | 0,8729 | 0,8713 | 0,8316 |

## El equipo en los frames vivos (slice limpio)

Frames vivos para nosotros y para la verdad: 5846; con el equipo equivocado: 889 (15,2%), de ellos 230 sin etiqueta (`X`): los primeros 9,2 s de la ventana, antes del primer estado.

| distancia al cambio verdadero más cercano | frames con el equipo equivocado |
|---|---:|
| 0-1 s | 318 |
| 1-2 s | 176 |
| 2-4 s | 196 |
| 4-8 s | 174 |
| 8-inf s | 25 |

## Reanudaciones sin equipo

32 de las 59 reanudaciones etiquetadas no traen equipo; `engine.restart_controls` no las fuerza.

| tipo | sin equipo |
|---|---:|
| Kick Off (After Goal) | 4 |
| Kick Off (Start) | 2 |
| Throw-in | 26 |
