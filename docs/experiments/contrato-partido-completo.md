# Pre-registro: prueba de contrato a escala completa (partido de 199.319 frames)

**Ticket:** #21 (guardián de métrica), extensión a la entrega final.
**Escrito antes de correr la prueba.** Cualquier cambio de umbral después de ver los resultados
invalida la prueba y se registra como tal.

## Qué pregunta

¿La submission entregada es estructuralmente posible en el partido completo, en los tramos donde
el slice público no puede mirar? No pregunta si acierta contra el ground truth (no se puede: solo
hay 5 minutos públicos). Pregunta si viola invariantes que cualquier etiquetado de posesión debe
cumplir, y localiza la violación en frames concretos.

Es la única medición nueva que queda con evidencia admisible: no lee ground truth, no lee vídeo, no
elige parámetros. Usa la submission, la presencia de balón del tracking (dato provisto) y las
mitades de `games.py`.

## Entradas

- `submission`: `submissions/engine.csv` (199.319 filas, `frame,label`).
- `artifact`: el artefacto del motor (`frame,p_home,p_away,p_dead,confidence`), para comprobar que
  la submission es su lectura one-hot.
- `ball`: presencia de balón por frame. Dos fuentes admitidas, en este orden:
  1. el bundle licenciado (`atd.load(...).ball()[1]`), igual que `tools/blocks.py`;
  2. un artefacto intermedio de emisión, donde `confidence = max(p_home,p_away) × ball_present`,
     así que `confidence > 0` equivale a balón observado. Se valida contra las coberturas por
     bloque ya publicadas en `docs/analysis/blocks.md`; si no coinciden, la prueba no corre.

## Pruebas y umbrales (fijados ahora)

**P0 — validación de la entrada.** Cobertura de balón del partido 56,9% ± 0,1 y cobertura por
bloque igual a `blocks.md` (redondeo). Si falla, se detiene: el problema es el insumo, no la salida.

**T1 — contrato del archivo.** 199.319 filas; frames 0..199.318, únicos y contiguos; etiquetas en
`{H,A,D,X}`; `X` exactamente en los 40.462 frames fuera de las dos mitades (20.156 de entretiempo
más los extremos); ninguna `X` dentro de una mitad; la submission coincide frame a frame con el
argmax del artefacto (`X` donde `confidence = 0`). **Pasa si las cinco condiciones se cumplen.**

**T2 — ninguna posesión de más de 300 s.** Una posesión es un tramo maximal de `H` o `A` del mismo
equipo. Ningún tramo puede durar ≥ 7.500 frames. Justificación: una posesión real dura segundos o
un par de minutos; 5 minutos es 2,5–5× el máximo plausible y, en esta cadena, solo se puede
sostener arrastrando estado a través de un hueco de balón. Es la prueba que ataca directamente la
política de huecos > 500 frames, que el slice no puede medir. **Pasa si no hay ningún tramo ≥ 7.500
frames**; cada violación se reporta con inicio, fin, duración y cobertura de balón.

**T3 — ninguna transición de equipo sin balón.** Un hueco es un tramo maximal con
`ball_present = False`. Para cada hueco de ≥ 500 frames (la banda que concentra el 67% del déficit de
balón), se cuentan las transiciones directas `H↔A` estrictamente dentro del hueco. Deben ser 0: un
cambio exige un control, y un control exige balón observado; la reanudación entra por `D`, no por un
`H→A` directo. Se reportan aparte las transiciones `D→H/A` dentro de huecos largos, que sí pueden
ser reanudaciones forzadas. **Pasa si no hay ninguna transición directa `H↔A` dentro de un hueco
≥ 500 frames.**

**T4 — ningún bloque degenerado.** En los 22 bloques de 5 minutos de `games.py`: `%D ≤ 85` y al
menos una posesión por bloque. Justificación: el máximo publicado es 65,5%; un bloque casi todo `D`
o sin posesiones indica una regla disparada de más. **Pasa si los 22 bloques cumplen.**

## Regla de decisión

- **Las cuatro pasan:** la entrega es estructuralmente válida a escala completa; el resultado entra
  en el documento técnico como certificado sin ground truth y el archivo se puede congelar.
- **Alguna falla:** se reportan los frames y el hueco exacto; **no se cambia nada en silencio**. La
  decisión es del lead antes del freeze, y cualquier cambio vuelve a pasar por esta prueba, `make
  repro` y el validador oficial.

## Fuera de alcance (declarado)

Acierto contra el ground truth del partido completo; etiquetas del Smart Tagging; coordenadas del
balón y del campo; vídeo. Nada de eso se lee.

## Por qué este experimento y no los otros

| candidato | veredicto | motivo |
|---|---|---|
| Rejilla de 27 en DFL | descartado | D37: el corpus cambia la definición (4,58 pos/min, 41–52% `D`); todos los decodificadores pierden 7/7 por escala, no por la regla |
| Re-arbitrar el duelo en DFL | descartado | mismo sesgo: DFL marca por toque, `CHALLENGE.md` por control |
| Re-arbitrar umbrales 1,5/5 en DFL | descartado | son umbrales de *nuestro* sensor (balón con ruido); el balón de DFL es limpio |
| Barrido de estabilidad sin GT | descartado como selección | mide robustez, no corrección; su referencia de 3,4 pos/min sale del GT público |
| U1 `onset` | no es experimento | decisión sobre evidencia externa ya medida (DFL 7/7); la decide el lead |
| Más variantes de slice o banco | descartado | n=17, in-sample, y ahora prohibido como selección |
| Vídeo / imputación | descartado | negativos cerrados (D38, D34) |
| Pregunta a la organización | no es experimento | máxima prioridad, pero no produce una medición |

Lo que queda sin resolver después de esta prueba: si la política de huecos largos es *correcta*
(no solo plausible). No hay corpus admisible que lo diga; el certificado solo descarta lo imposible.
