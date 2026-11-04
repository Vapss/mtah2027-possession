# Revisión estricta: la regla del duelo con datos externos (decisión 44)

Generado por `python tools/readjudicate.py --write docs/analysis/readjudication.md`. No se edita a mano.
Juez: la verdad de eventos de los partidos abiertos de Metrica g1 y g2 (decisión 42); nada lee
las etiquetas de BAR-ATH. Regla pre-registrada: la regla del duelo se queda si su `spellF1`
medio degradado es ≥ el de la misma cadena sin ella.

| partido | condición | cadena | spellF1 | perdidos | sobrantes |
|---|---|---|---:|---:|---:|
| g1 | limpio | con duelo (entregada) | 0,6531 | 85 | 18 |
| g1 | limpio | sin duelo (`engine.D31`) | 0,6625 | 64 | 47 |
| g1 | degradado | con duelo (entregada) | 0,4614 | 135 | 48 |
| g1 | degradado | sin duelo (`engine.D31`) | 0,4255 | 122 | 110 |
| g2 | limpio | con duelo (entregada) | 0,6154 | 72 | 16 |
| g2 | limpio | sin duelo (`engine.D31`) | 0,6212 | 54 | 53 |
| g2 | degradado | con duelo (entregada) | 0,4215 | 130 | 55 |
| g2 | degradado | sin duelo (`engine.D31`) | 0,3880 | 121 | 103 |

| condición | con duelo | sin duelo | Δ |
|---|---:|---:|---:|
| limpio | 0,6342 | 0,6418 | -0,0076 |
| degradado (decide) | 0,4414 | 0,4067 | 0,0347 |

**Veredicto: la regla del duelo se queda.**
