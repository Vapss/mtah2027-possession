# ELASTIC: factibilidad de recepciones externas para #63

Auditoría descriptiva de los partidos de desarrollo; no puntúa ni elige una variante.
Protocolo previo: `docs/proposals/elastic-feasibility.md`. `J03WPY` sigue reservado.
Los eventos ELASTIC y el dataset DFL se distribuyen bajo CC BY 4.0: citar Kim et al.,
ELASTIC (CIKM 2026, doi:10.1145/3799682.3841035) y Bassek et al. (Scientific Data 12:195,
doi:10.1038/s41597-025-04505-y). El código ELASTIC no se incorpora.

| Medida | J03WMX | J03WN1 |
|---|---:|---:|
| Eventos totales | 1329 | 1030 |
| Eventos sin recepción | 226 | 197 |
| Periodo o frame inválido | 0 | 0 |
| Destinos terminales fuera / gol | 52 / 3 | 51 / 3 |
| Receptores no presentes o ambiguos en plantel | 0 | 0 |
| Recepciones elegibles | 1048 | 779 |
| Frame de balón presente | 1048 | 779 |
| Balón en juego según DFL | 1048 | 779 |
| Frame de receptor presente | 1047 | 779 |
| Receptor del equipo rival al actor | 227 | 240 |
| Frames con receptores de ambos equipos | 4 | 2 |
| Equipo receptor distinto al propietario DFL | 134 | 138 |

La coincidencia de receptor y propietario DFL es una descripción entre fuentes, no
exactitud: pueden diferir por balón suelto, acciones de un toque, convenciones o fechas.
ELASTIC asigna `receiver_id` al colapsar acciones finales, incluidas acciones de un toque
y algunas acciones defensivas; no equivale automáticamente a control sostenido (ver
`sync/utils.py` en la revisión de ELASTIC citada abajo).
El origen de las fechas en animaciones del mismo tracking introduce dependencia. Los
eventos no constituyen automáticamente posesiones. Distinguir contacto de control sigue
pendiente; esta auditoría no autoriza elegir umbrales ni la regla del duelo.

Reproducir con el entorno fijado del proyecto más `pyarrow==26.0.1` (solo exploración)
y los archivos externos en `runs/external/`:
`python tools/elastic_audit.py all --write docs/analysis/elastic-feasibility.md`.
El script no lee datos del partido de competición.

Fuente: ELASTIC `e245224aad7450961eca40954ae2bc85e1e6e696`; espejo DFL
`pysport/idsse-data` revisión `a715a38dfbaf5f58e431727c2b78d174101a703c`.
Hashes SHA-256 de los archivos leídos:

- `J03WMX` anotaciones: `3bf246033e8df7028563f8b90ecf338212063b6aed9ac6772741d429feded52b`
- `J03WMX` metadatos: `a884728647a564cf8b20e5223a1d04a5da6f6725e1e506c8651505327c197ba9`
- `J03WMX` tracking: `d3dd92e509421a6466acb0a083c009035f1751bc5fd9ef42ffa8f20d01cf7d49`
- `J03WN1` anotaciones: `20cf64b5169099ed3577c30a6bf23eda316fea6f5927e1061496f5f6dccf7681`
- `J03WN1` metadatos: `5490286436c86e6f80a538d2b1b379d0efd016e0defcaf594bc59d9ef5079f4c`
- `J03WN1` tracking: `56ef948961a18e150dba0b7b16869d0008ff66f3050a0c355d31fa5b8ec2fcec`
