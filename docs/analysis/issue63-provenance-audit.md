# #63: auditoría documental de los tres pendientes

Fecha de auditoría: 16-nov-2026. Base: `89699073e327abd01b99e09b0fbbe7c9faffcc5b`.
No se ejecutó ninguna selección, nueva puntuación del partido ni modificación de parámetros.
Esta nota no certifica cumplimiento ni cierra #63. La reproducción real ya registrada y la
procedencia de las decisiones son comprobaciones distintas.

## Método y alcance

Se recuperaron las cabeceras originales de los PR #52, #54 y #70, además de consultar los commits
integrados. Un squash no conserva todos los pasos de investigación: la fecha de integración no
es la fecha de elección de un parámetro. Se contrastaron propuestas, D29/D34/D36/D44/D45 y código
activo; se separan texto anterior, informe posterior y declaraciones retrospectivas.

Los enlaces siguientes fijan los objetos consultados. Sus fechas de autor y el orden del Git son
evidencia documental, no una certificación independiente de cuándo se ejecutó cada experimento.
No se infiere que el historial disponible contenga toda la investigación fuera de Git.

Las cuatro capturas facilitadas por el equipo contienen la aclaración de reglas, pero no muestran
remitente ni fecha. El [resumen del texto visible](issue63-progress.md#contraste-con-las-capturas-de-la-aclaración-original)
distingue las reglas de la interpretación operativa del repositorio. No se copiaron imágenes ni
datos del partido. El equipo confirmó que no dispone de una especificación del proveedor sobre
la posición del saque dentro de las ventanas `SET PIECES`.
El equipo también confirmó que no tiene una respuesta escrita de la organización sobre cómo
subsanar la exposición al slice en control/duelo o en el cambio a W3. Las preguntas del final
siguen siendo una consulta preparada, no una autorización ni una respuesta recibida.

## 1. Control y duelo

**Método:** localizar la primera elección escrita de radio, velocidad y permanencia; confrontarla
con las exposiciones declaradas; comprobar si la literatura o un corpus externo justifica esos
valores y la aproximación al duelo. Una regla cualitativa no valida automáticamente sus umbrales.

**Evidencia comprobada:**

- El [motor inicial](https://github.com/Vapss/mtah2027-possession/commit/a38112ab245ca6a69f60e8bdd2bcbee5c5dc1266)
  ya contiene `1.5 m / 5 m/s / dwell=1`; su mensaje también reporta una puntuación pública.
- El [pre-registro de D29](https://github.com/Vapss/mtah2027-possession/commit/0dae7f9c132aec34b7ea82ae6d25ee75ee2c7e26)
  declara cinco configuraciones probadas antes de escribirlo. Dice que eligió por prior físico,
  sin escoger la puntuación máxima. Esto documenta la declaración del criterio, pero no prueba
  independencia respecto a la exploración ya conocida.
- El [pre-registro del duelo](https://github.com/Vapss/mtah2027-possession/commit/375153fe5cd0bb8f0cf5abe253381ec7952e80f0)
  incluye compuertas del slice y del banco; el [informe posterior](https://github.com/Vapss/mtah2027-possession/commit/bff16bbb2bdb4f4ea0377e6808dd675a34ea322c)
  recomienda `uncontested`. La definición del reto respalda conservar al último poseedor en
  disputa; no determina que dos jugadores a 1,5 m sean la implementación correcta.
- [Vidal-Codina et al., §2.3](https://arxiv.org/html/2202.00804v3#S2.SS3)
  distingue zonas de posesión y duelo y añade evidencia de contacto mediante cambios de dirección
  o velocidad. Es respaldo conceptual; no es una validación de la combinación de tres umbrales
  de este motor.
- El [informe ELASTIC ya versionado](elastic-feasibility.md) advierte que `receiver_id` incluye
  acciones de un toque y defensivas. No equivale a control sostenido; el protocolo anterior no
  autoriza elegir umbrales ni el duelo. No se abrió el partido reservado.
- La [publicación primaria del corpus DFL, Position data](https://pmc.ncbi.nlm.nih.gov/articles/PMC11787359/)
  define `BallPossession` por el jugador que controla el balón y declara los datos CC BY 4.0.
  Es una referencia externa de equipo más pertinente que convertir automáticamente una recepción
  ELASTIC en control. No documenta allí todos los casos de duelo; la equivalencia completa con la
  definición del reto no queda demostrada por esa frase.

**Resultado:** corregida en `engine.py` la afirmación demasiado fuerte «fixed before measuring».
Se conserva D29 como registro histórico. La justificación independiente de los valores sigue
pendiente; una comprobación externa favorable hoy no demuestra que se eligieran antes de medir.

**Ruta para resolver:** documentar un corpus externo con derechos y etiquetas cuya semántica
distinga control, toque y disputa; fijar antes de ejecutar variantes la partición, la métrica,
el criterio de elección y el tratamiento de empates. Registrar la exposición histórica a DFL.
Si se recalibra, será una decisión nueva y una candidata nueva, con su propia reproducción y hash.
La admisibilidad de sustituir decisiones históricas requiere respuesta de la organización.

**Límite:** el material comprobado no proporciona una referencia externa de control/duelo que
permita dar por superado ese paso. No se ejecuta la rejilla antigua de #63 sobre una referencia
inadecuada ni se escogen variantes por el slice.

## 2. Offsets de reanudación de 3,5 y 5 segundos

**Método:** distinguir conversión de reloj, metadatos del export y estimación del instante de saque;
buscar una especificación aplicable a este export, sin inspeccionar sus filas.

**Evidencia comprobada:**

- El [pre-registro original de lane-d](https://github.com/Vapss/mtah2027-possession/blob/8bb690a16bb8f98c3f4f8dcca09bb23c4e25ec13/docs/proposals/lane-d.md),
  §§2–3, relaciona 3,5 s con los saques iniciales y 5 s con perfiles temporales agregados del
  tracking/tags del partido. Declara no haber usado GT para fijarlos. Por tanto, su procedencia
  escrita es una estimación a partir del partido, no una especificación del proveedor.
- `dead_ball.restarts()` suma el offset a `start`; no lee una fecha de acción independiente.
  Que los tiempos compartan el reloj del vídeo no sitúa el saque dentro del clip.
- La [documentación oficial de Codeball](https://codeball.metrica-sports.com/patterns/)
  permite configurar `in_time` y `out_time`. Su [configuración fijada en Git](https://github.com/metrica-sports/codeball/blob/06161ac69f9b7b53e3820537e780ab962c4349e6/codeball/patterns/patterns_config.json)
  tiene 2 s de entrada y 2 s de salida para `SetPieces`. No se encontró en las páginas consultadas
  una vinculación entre esa configuración y el export del concurso; no se transfieren sus valores.
- La [API de patrones para Play](https://codeball.metrica-sports.com/format-for-play/)
  diferencia inicio, fecha de evento y fin en archivos `.patt` JSON. No prueba que el XML recibido
  conserve la fecha de evento ni permite reconstruirla mediante una constante universal.

**Resultado:** se aclara en el comentario del código que son estimaciones dentro del clip.
La consulta pública acotada y la respuesta del equipo no acreditan una convención de 3,5/5 s.
No se afirma que no pueda existir documentación adicional.

**Ruta para resolver:** obtener del proveedor la semántica/configuración aplicable y determinar
con la organización si la estimación documentada es admisible. Si no lo es o no se puede acreditar,
la sustitución debe prescindir de estos valores o estimarlos con datos externos del mismo tipo de
export y tiempos de acción independientes; requeriría protocolo previo y una nueva candidata.
No se cambia a 0, 2 u otro offset sin justificación escrita.

**Límite:** una reanudación etiquetada de DFL no acredita el tiempo de entrada de este export.
Sin especificación aplicable ni un export externo comparable no hay calibración equivalente
demostrada. «No usó GT» tampoco demuestra por sí solo que esto satisfaga la obligación de ajustar
parámetros con datos externos.

## 3. W3: entrenamiento externo y cambio de criterio

**Método:** comparar el pre-registro original con el primer informe de resultados; después,
reconstruir la elección de W1 y la retirada posterior de sus compuertas. Separar entrenamiento
de pesos, preferencia previa y selección final.

**Evidencia comprobada:**

1. El [pre-registro `b0b930c`](https://github.com/Vapss/mtah2027-possession/blob/b0b930cf5e6aa9f710781e98a92d3bfce5ed9a5a/docs/proposals/lane-dead-v2.md),
   §6, ya escribe `W3 > W2 > W1 > W4`, con motivación DFL y la regla de primer poseedor tras una
   parada. También exige compuertas del slice y del banco. No es un prior inventado en noviembre.
2. El [informe `4319869`](https://github.com/Vapss/mtah2027-possession/commit/431986968366dac3a10eaea09eb2c2054924ee6a)
   conserva las secciones 1–6 salvo la línea de estado y añade resultados: elige W1 porque W2/W3
   fallan la compuerta de precisión pública de `D`. Este es el mecanismo de selección escrito.
3. El [cambio posterior a W3](https://github.com/Vapss/mtah2027-possession/commit/abbafa1fb8eea4a6403a154997efb72b89c665e2)
   retira las compuertas inadmisibles y reaplica el prior. D45 declara que ya se conocían los
   resultados públicos de W1/W3. Recuperar el prior original demuestra su existencia anterior,
   pero no convierte ese cambio posterior de criterio en una selección independiente.
4. La procedencia externa del entrenamiento en siete DFL está descrita en el protocolo y el código.
   La reproducción real registrada en [reproduction-verification.json](reproduction-verification.json)
   acredita los builds del candidato y el alcance del hook de GT; no vuelve a entrenar el modelo
   ni demuestra independencia histórica de todas sus constantes o de su selección.

**Resultado:** queda resuelta la duda documental sobre si el orden de preferencia ya existía.
Permanece abierta la admisibilidad de retirar las compuertas después de conocer sus resultados.
No se sustituye W3 por W1 ni se vuelve a puntuar para decidirlo.

**Ruta para resolver:** presentar esa secuencia completa a la organización y solicitar criterio
escrito sobre la corrección mediante D44/D45. Si exige una candidata nueva, fijar un procedimiento
externo antes de cualquier medición nueva y reproducirlo como nueva entrega. La autorización
no se presume a partir de un resultado externo posterior.

**Límite:** Git demuestra qué estaba escrito en cada commit; no puede eliminar la exposición
declarada ni emitir una decisión de la organización. No se puede prometer aprobación de W3.

## Consulta preparada; no enviada

Estas preguntas no requieren adjuntar tracking, etiquetas, vídeo ni capturas con información
personal. No se ha enviado ningún mensaje a terceros durante esta auditoría.

1. D29 declara cinco configuraciones evaluadas con el slice antes de su pre-registro, y el duelo
   se adoptó con compuertas del slice/banco. ¿Qué procedimiento admitirían para sustituir esas
   decisiones por una elección exclusivamente externa? ¿Puede conservar los valores si resultan
   elegidos externamente, declarando la exposición anterior?
2. Los offsets 3,5/5 s se estimaron de agregados del tracking/tags proporcionados, sin GT. ¿Esto
   constituye ajuste que debe reemplazarse? ¿Cuál es la especificación de `SET PIECES` del export
   entregado y existe una fecha de acción o configuración oficial que resuelva el instante del saque?
3. W3 tenía prioridad escrita antes del informe de resultados, pero se descartó por una compuerta
   del slice; tras la aclaración se eliminó la compuerta y se recuperó W3 con exposición declarada.
   ¿Admiten esa corrección o exigen un procedimiento externo nuevo?

## Comprobaciones y estado final de esta auditoría

Los cambios de Python de esta auditoría solo afectan comentarios/docstrings. Se comprobó igualdad
del AST ejecutable frente a la base, retirando únicamente docstrings para la comparación; lint,
formato y el guard de datos pasaron. No se ha regenerado ni sustituido la candidata de `configs/delivery.json`.
Las cinco suites existentes de motor y balón muerto pasaron: 103 pruebas. Después se ejecutó
la suite completa desde un clon limpio de `b7cb6133d10f16a2c96dbfdc7a11cfb0db4efbbe`, usando
el bundle local: 509 pruebas pasaron, 6 se omitieron y no hubo fallos ni errores. Pasó la prueba
de reproducción real que exige dos builds idénticos al digest del manifiesto, sin intentos de
acceso al GT dentro del alcance del hook. La CI de ese commit pasó `check` y `graph`.
No hay nuevos números del partido ni evidencia externa de rendimiento en este documento.

| Pendiente | Avance comprobado | Qué impide cerrarlo |
|---|---|---|
| Control/duelo | Cronología recuperada y afirmación de premedición corregida | Referencia externa adecuada y decisión trazable; criterio sobre la exposición histórica |
| Offsets | Origen en agregados identificado; configuración pública contrastada | Semántica/configuración aplicable o sustitución externa justificada |
| W3 | Prior original verificado antes del informe posterior | Criterio sobre retirar las compuertas con los resultados ya conocidos |

Se mantiene abierto #63. La auditoría reduce incertidumbre documental; no equivale a resolver
los tres pendientes ni permite afirmar que la promoción `dev` → `main` tenga aprobación metodológica.
