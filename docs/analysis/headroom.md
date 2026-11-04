# Auditoría del margen: qué componente pierde el `spellF1`

Generado por `python tools/headroom.py --write docs/analysis/headroom.md` desde el commit `abbafa1f`. No se edita a mano.
**Diagnóstico con la GT pública: no elige ninguna regla, constante ni variante**
(decisión 40). Cada fila cambia un componente de la cadena entregada por la verdad y
puntúa en el slice y en el banco de trasplante.

| cadena | slice | banco (media) | banco, poco balón | peor donante |
|---|---:|---:|---:|---:|
| delivered | 0,5714 | 0,4326 | 0,3454 | 0,2571 |
| oracle D | 0,6162 | 0,5142 | 0,4114 | 0,2933 |
| oracle D: only remove our false D | 0,6222 | 0,4761 | 0,3743 | 0,2759 |
| oracle D: only add the D we miss | 0,5667 | 0,4801 | 0,3942 | 0,2897 |
| oracle team on the live frames | 0,9000 | 0,8689 | 0,8599 | 0,7867 |

## El equipo en los frames vivos (slice limpio)

Contado sobre las etiquetas que ve el `spellF1` oficial: las `X` rellenadas como hace
`fill_abstentions` (hacia delante, y hacia atrás al inicio de la ventana).

Frames vivos para nosotros y para la verdad: 5676; con el equipo equivocado: 709 (12,5%). Dejamos 230 frames de la ventana en `X`; empieza con 9,2 s sin estado, que el scorer rellena con la primera etiqueta: 64 de esos frames quedan con el equipo equivocado.

| distancia al cambio verdadero más cercano | frames con el equipo equivocado |
|---|---:|
| 0-1 s | 280 |
| 1-2 s | 151 |
| 2-4 s | 146 |
| 4-8 s | 107 |
| 8-inf s | 25 |

## Reanudaciones sin equipo

32 de las 59 reanudaciones etiquetadas no traen equipo; `engine.restart_controls` no las fuerza.

| tipo | sin equipo |
|---|---:|
| Kick Off (After Goal) | 4 |
| Kick Off (Start) | 2 |
| Throw-in | 26 |
