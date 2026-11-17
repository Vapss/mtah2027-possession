# #63 — pre-registro de calibración externa de B5

> Estado tras integrar #70: protocolo histórico. La emisión B5 se retiró del código activo;
> la candidata externa no se incorpora a la entrega W3. El texto original se conserva debajo
> como registro previo a la medición, sin reinterpretar su resultado como validación del motor.

**Antes de ejecutar ninguna calibración B5 sobre DFL.** La selección no utiliza ground truth del
partido del reto, su slice ni el banco de trasplante. Los partidos DFL ya se exploraron para otras
reglas y estos dos se usaron para la auditoría descriptiva de ELASTIC; no se presentan como una
prueba ciega de todo el desarrollo. Esta prueba no lee las anotaciones ELASTIC ni datos del partido.

## Pregunta y población

¿Puede fijarse la temperatura de la emisión H/A de B5 desde una tarea externa explícita? Fuente:
IDSSE/DFL, Bassek et al., doi:10.1038/s41597-025-04505-y, CC BY 4.0; espejo
`pysport/idsse-data` revisión `a715a38dfbaf5f58e431727c2b78d174101a703c`. Los hashes de XML
están en `docs/analysis/elastic-feasibility.md`.

Entrenar en `J03WMX`, comprobar en `J03WN1`; no ajustar con el segundo. Usar todas las filas con
balón dentro del campo, ambas distancias de equipo finitas y estado DFL vivo con propietario H/A.
Contar exclusiones y clases. Un partido con menos de 1.000 filas elegibles o sin ambas clases hace
la prueba inconcluyente. Las filas consecutivas no son observaciones independientes.

La referencia es la distancia mínima balón–jugador por equipo, sin decodificador ni `D`. Evaluar
la probabilidad H/A **condicional** a balón vivo: `p(H)=sigmoid((d_A-d_H)/T)`; no confundirla con
las probabilidades finales con suelo de `D` ni con la calibración de un ensemble.

## Prior, regla y comprobación

- Prior estructural de escala: `T0 = 1 m`, una escala fija en unidades de distancia, no un ajuste
  al partido ni una afirmación de calibración. La penalización es `0,01 * log(T/T0)^2` añadida a
  la pérdida logarítmica media de entrenamiento; `0,01` es una elección previa de regularización,
  no una cantidad medida del partido.
- Una sola búsqueda áurea determinista sobre `log(T)` en `[log(0,05), log(20)]`, 80 iteraciones;
  si hay empate numérico se escoge el punto inferior. No barrer variantes ni cambiar límites tras
  observar resultados. La pérdida usa `logaddexp` para estabilidad.
- Calcular en ambos partidos log-loss sin penalización y Brier binario para la candidata y `T0`.
  En el segundo, aceptar **solo como constante de B5 para DFL** si la candidata es interior y su
  log-loss mejora estrictamente sobre `T0` por más de `1e-12`, y se cumplen los mínimos. Si no,
  declarar no concluyente y no cambiar la temperatura. No mirar el slice para desempatar.
- La temperatura aceptada se fija como constante determinista en código, redondeada a 12 decimales
  antes de evaluar la compuerta. Si se redondea fuera del intervalo, no se acepta. Comprobar que se
  preserva el orden H/A en pruebas sintéticas; las probabilidades y confianza sí pueden cambiar.

## Alcance y riesgos

El propietario DFL es un proxy externo, no necesariamente la definición de control del reto. El
tracking del balón es limpio, sin reproducir su patrón de ausencia ni ruido del partido del reto;
por eso una mejora en DFL **no demuestra calibración en el partido ni mejora de spellF1**. Esos
límites se documentarán junto a cualquier constante. No elegir ni descartar otros umbrales del
motor a partir de esta prueba. El build del motor usa etiquetas one-hot; sigue pendiente probar la
reproducción real con el bundle antes de afirmar que el CSV coincide byte a byte.
