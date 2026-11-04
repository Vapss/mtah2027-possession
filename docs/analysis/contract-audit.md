# Contrato a escala completa: la entrega en los 199.319 frames

Generado por `python tools/contract_audit.py --submission submissions/engine.csv --artifact runs/engine/artifacts/engine.csv --ball-artifact artifacts/possession.csv` desde el commit `80675e5`. No se edita a mano.

Pre-registro: `docs/experiments/contrato-partido-completo.md`. No lee ground truth,
video,
Smart Tagging ni coordenadas: solo la submission, el artefacto y la presencia de balón.

**Insumo:** presencia de balón desde `artifacts/possession.csv` (confidence > 0)

## Veredicto

| gate | resultado | detalle |
|---|---|---|
| T1 contrato del archivo | **falla** | 230 X dentro de una mitad |
| T2 ninguna posesión > 5 min | pasa | 0 posesiones ≥ 7500 frames; la más larga 1532 frames |
| T3 transiciones sin balón | pasa | 49 huecos ≥ 500 frames; 0 transiciones H<->A dentro; 43 D->H/A (reanudaciones) |
| T4 ningún bloque degenerado | pasa | 22 bloques; 0 fuera de gate |

**FALLA** el contrato estructural.

Una falla de T1 es mecánica: dice dónde el archivo no cumple el contrato, no que la
etiqueta
sea incorrecta. El scorer oficial rellena las `X` dentro de una mitad con la etiqueta
anterior
(y con la primera conocida al inicio), así que la métrica de ranking puede no
moverse; las
métricas por frame sí las cobran. Ningún umbral se ajusta acá: la decisión es del lead.

## Posesiones más largas

| inicio | fin | frames | segundos | equipo |
|---:|---:|---:|---:|:---:|
| 89120 | 90652 | 1532 | 61.3 | A |
| 25575 | 26904 | 1329 | 53.2 | H |
| 79615 | 80913 | 1298 | 51.9 | H |
| 75565 | 76859 | 1294 | 51.8 | H |
| 128342 | 129551 | 1209 | 48.4 | H |

## Huecos de balón

- Huecos: 186; el más largo 8689 frames.
- Huecos >= 500 frames: 49.

| inicio | fin | frames | segundos |
|---:|---:|---:|---:|
| 0 | 4192 | 4192 | 167.7 |
| 4207 | 5051 | 844 | 33.8 |
| 5108 | 10643 | 5535 | 221.4 |
| 19029 | 19772 | 743 | 29.7 |
| 29030 | 29781 | 751 | 30.0 |
| 34200 | 34827 | 627 | 25.1 |
| 36264 | 37052 | 788 | 31.5 |
| 45454 | 46197 | 743 | 29.7 |
| 46678 | 48031 | 1353 | 54.1 |
| 48078 | 48600 | 522 | 20.9 |
| ... | | | (39 mas) |

## Bloques de 5 minutos

| # | mitad | inicio | %D | posesiones |
|---:|---:|---:|---:|---:|
| 1 | 1 | 11185 | 20.0% | 21 |
| 2 | 1 | 18685 | 17.6% | 23 |
| 3 | 1 | 26185 | 34.4% | 21 |
| 4 | 1 | 33685 | 23.6% | 30 |
| 5 | 1 | 41185 | 47.5% | 16 |
| 6 | 1 | 48685 | 36.2% | 20 |
| 7 | 1 | 56185 | 50.5% | 10 |
| 8 | 1 | 63685 | 38.0% | 19 |
| 9 | 1 | 71185 | 65.5% | 8 |
| 10 | 1 | 78685 | 31.8% | 17 |
| 11 | 1 | 86185 | 50.6% | 3 |
| 12 | 2 | 110808 | 49.2% | 19 |
| 13 | 2 | 118308 | 35.6% | 20 |
| 14 | 2 | 125808 | 27.5% | 23 |
| 15 | 2 | 133308 | 52.5% | 16 |
| 16 | 2 | 140808 | 23.8% | 17 |
| 17 | 2 | 148308 | 35.8% | 20 |
| 18 | 2 | 155808 | 52.1% | 18 |
| 19 | 2 | 163308 | 47.2% | 20 |
| 20 | 2 | 170808 | 47.3% | 16 |
| 21 | 2 | 178308 | 57.9% | 19 |
| 22 | 2 | 185808 | 38.7% | 7 |
