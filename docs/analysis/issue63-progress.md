# #63: evidencia y pendientes de procedencia

Esta nota distingue pruebas sintéticas de reproducción real. No decide un freeze ni justifica
seleccionar parámetros con el slice. Se actualiza al integrar `dev` en `b3d7ed4` (#70 y #71).
La referencia de entrega es `configs/delivery.json`; no se vuelve a medir ni a elegir el candidato.

## Estado tras retirar B5 y el postproceso

#70 retiró la emisión B5, su temperatura y su interfaz de generación. `tools/emision.py` conserva
solo la identidad de equipos del XML y el cálculo de velocidad que utiliza el motor. También se
retiraron `tools/postprocess.py`, sus pruebas y el verificador/manifiesto B6. La resolución de los
conflictos de #69 conserva esas retiradas; no reintroduce una emisión o un postproceso inactivo.

El prior de duración de 355 frames procedía del slice (D20) y era redundante en su desempate,
pero ya no existe en el código actual. La candidata de temperatura externa de 2,864606845062 m
se obtuvo antes de integrar #70 mediante `docs/proposals/b5-external-calibration.md`; su evidencia
está en `docs/analysis/b5-external.json` y su programa es `tools/calibrate_b5_external.py`.
Se conserva como investigación histórica sin consumidor en la entrega. Una mejora de log-loss
en DFL no demuestra calibración en el partido del reto ni mejora de `spellF1`.

Los programas aceptan datos externos fuera del repositorio, sin copiarlos a la entrega:

```bash
python tools/calibrate_b5_external.py --dir /path/to/external/idsse --write runs/b5-check.json
python tools/elastic_audit.py all --dir /path/to/external --write runs/elastic-check.md
```

El segundo comando requiere `pyarrow==26.0.1` únicamente para exploración. Ambos verifican
las huellas de entrada registradas; no descargan datos ni seleccionan parámetros del motor W3.
Al adaptar #69 se ejecutaron ambos comandos sobre la copia externa local ya disponible: los
resultados fueron byte-idénticos a los blobs versionados de `b5-external.json` y
`elastic-feasibility.md`. Es una comprobación de reproducción de evidencia histórica, no una
evaluación nueva ni una validación del candidato W3.

La prueba sintética del motor comprueba que B5 sigue ausente y que inyectar las antiguas interfaces
no cambia su salida. No sustituye la comparación de los bytes reales. Para reproducir el antiguo
artefacto B6 habría que usar un checkout histórico aislado, por ejemplo `ebec47f`, con el bundle
autorizado. Esa ruta no se ejecutó aquí y no forma parte de la entrega; no se restaura el manifiesto
antiguo ni se modifica el hash de referencia actual.

## Constantes activas identificadas en la ruta W3

Inventario estático inicial: las referencias no certifican independencia de selección. La fecha de
incorporación no necesariamente coincide con la elección de cada valor. D44–D45 siguen abiertos.

| Elemento | Valores o reglas activos | Procedencia y estado |
|---|---|---|
| Control y duelo | 1,5 m; 5 m/s; `dwell=1`; `duel=True` | D29 y D34: adopción con comparación en el slice. Pendiente justificación independiente. |
| Fecha de reanudación | +3,5 s en saques de centro; +5 s en otros tags | `lane-d.md` §2–3: agregados del tracking y tags del partido. Auditar procedencia y selección bajo D44–D45. |
| Episodios fuera | fusionar huecos de hasta 1 s; buscar 40 s hacia atrás, o 120 s tras gol; sin mínimo para salida vinculada a tag | D30–D31; la selección y la reversión de episodios cortos consultaron el slice. Separar justificación del historial. |
| Detector W3 | `KINEMATIC=model`; regresión logística de 29 rasgos, medias/escalas/pesos incrustados; umbral >0,5 | `dead_ball_v2.MODEL`, D36 y D45: entrenado en siete DFL. La reselección W3 ocurrió con resultados públicos ya conocidos; no es evidencia independiente. |
| Rasgos de jugadores y decodificación W3 | desplazamiento ±12 frames; descartar velocidades >12 m/s; al menos 8 velocidades válidas; cerrar huecos vivos <1 s y descartar paradas <4 s | `dead_ball_v2.Params`: protocolo DFL y ventanas temporales del módulo. Inventariar y justificar cada constante, incluidas geometría de rasgos y ventanas. |
| Reanudación con tag | equipo conocido salvo control previo no disputado; conflictos de equipos no fuerzan estado | D30, D32 y D35. Cancelar el forzado no acorta la máscara D; auditar selección histórica. |
| Reanudación sin tag | primer control aceptado posterior asignado desde el primer frame vivo, sin cruzar otra parada ni mitad | D45; interpretación del reinicio con poseedor claro. Auditar la selección de W3 y la aproximación operacional. |
| Geometría y reloj | FPS, dimensiones y mitades de `games.py`; geometría de áreas en rasgos | Metadatos y reglas de campo; verificar versión de entradas y distinguir de umbrales elegidos. |

W1 (`rule_mps=2`) es una variante histórica: ese umbral no decide las paradas del detector `model`.
`still_mps`, `still_window_s` y el mínimo de salida sin tag tampoco deciden las paradas etiquetadas
de la variante `out`. Esta distinción no elimina la necesidad de auditar todas las constantes activas.

## Control de acceso al GT

`tests/test_gt_guard.py` activa un audit hook de Python en el proceso y en procesos Python hijos.
Los controles negativos usan rutas inexistentes o módulos de GT sintéticos, sin leer etiquetas
del partido. Registran la tentativa incluso si el código captura la excepción.

La prueba sintética ejecuta la reproducción real con lectores y detectores licenciados sustituidos;
exige que la vigilancia haya arrancado en al menos siete procesos: `repro` y los tres pasos de
cada build. No comprueba el interior de las funciones sustituidas ni el hash real de entrega.
La prueba separada con bundle ejecuta la misma cadena W3 con entradas reales, comprueba ausencia
de intentos de lectura y exige igualdad entre los dos hashes y el digest completo del manifiesto.
Sin bundle se omite, no se considera superada. El 16-nov-2026 se ejecutó con el bundle real en
`4146b2453b2bd4618549077182bc640a8ae69cae`: dos builds idénticos byte a byte, validador oficial
correcto, digest completo igual al manifiesto, siete procesos vigilados y cero intentos registrados.
La suite desde clon limpio pasó 509 pruebas con 6 omitidas y ningún fallo/error. El registro
sanitizado está en `docs/analysis/reproduction-verification.json`; no contiene datos del partido.

Alcance: los hooks no son un sandbox del sistema operativo. Cubren eventos `open` de procesos
Python que heredan el entorno; no descartan accesos mediante programas nativos, extensiones que
eludan esos eventos, intérpretes aislados o rutas deliberadamente sustituidas. La ejecución real
acredita ese alcance observado; no demuestra aislamiento de sistema ni procedencia independiente.

## Evidencia externa candidata

El repositorio [SkillCorner/opendata](https://github.com/SkillCorner/opendata/tree/4340d274572876239c154c90bc507a9b3250a656)
documenta tracking extrapolado a 10 Hz y un campo de posesión por frame. Su [licencia MIT](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/LICENSE)
aparece en el repositorio; debe comprobarse su alcance sobre los archivos concretos y cumplir la
atribución. El README no especifica cómo se obtiene la posesión ni si es independiente del tracking.
La diferencia de dominio, la interpolación y una posible dependencia entre etiqueta y rasgos pueden
sesgar la evaluación: no se acepta todavía como verdad ni se han medido variantes. Antes de cualquier
evaluación se necesita verificar derechos y definición, fijar un prior y protocolo de separación
desarrollo/evaluación, y dejar constancia de qué evidencia externa ya se había observado.

Otro candidato es [SoccerTrack v2](https://huggingface.co/datasets/atomscott/soccertrack-v2): la
[licencia de datos CC BY 4.0](https://github.com/AtomScott/SoccerTrack-v2/blob/main/LICENSE-DATA)
cubre las anotaciones y exige atribución. Su ficha describe acciones de balón con equipo y jugador,
pero el propio balón se reconstruye interpolando entre eventos anotados: usa la fecha de la etiqueta.
No es un árbitro independiente del error de fecha o de distancia balón-jugador sin estudiar esa
dependencia. Además, los partidos son universitarios y el acceso a los archivos exige aceptar sus
condiciones en Hugging Face. No se descargó ni midió; su posible uso requiere fijar versión, permiso
y un protocolo acorde con esos límites antes de observar resultados.

Una tercera posibilidad es el [benchmark de ELASTIC](https://github.com/hyunsungkim-ds/elastic/tree/e245224aad7450961eca40954ae2bc85e1e6e696):
su README publica, bajo CC BY 4.0, eventos corregidos y tiempos de acción y recepción reanotados
para tres partidos DFL (`J03WMX`, `J03WN1`, `J03WPY`). El [artículo](https://arxiv.org/abs/2608.30227)
indica que tres analistas fijaron los tiempos observando animaciones del tracking. Es una posible
referencia externa para estudiar contactos y recepciones, no una verdad completa de spells: el
origen en el mismo tracking introduce dependencia, los tres partidos DFL ya se exploraron en el
proyecto y el balón es más limpio que el de la competición. Se registró primero el protocolo de
factibilidad y después se auditaron dos partidos de desarrollo; el resultado agregado está en
`docs/analysis/elastic-feasibility.md`. No se ha medido ninguna variante ni abierto el partido
reservado. Sigue pendiente distinguir las acciones que implican control. La licencia del código
ELASTIC es MPL-2.0 y es distinta de la licencia de las anotaciones; este proyecto no lo incorpora.

## Pendiente para cerrar #63

1. **Verificado:** reproducción W3 con bundle real bajo vigilancia, comparación de bytes y hash
   completo. B5 ya no tiene consumidor activo; su calibración queda como investigación separada.
2. Para 1,5 m / 5 m/s / `dwell` 1 y la regla del duelo, producir una decisión justificada por
   corpus externo adecuado y prior escrito antes de medir; declarar un conflicto no es por sí solo
   una justificación de los valores actuales. Inventariar además el resto de constantes activas.
3. **Verificado para el candidato:** dos builds, validador y prueba de GT real. Falta comparar
   directamente con una copia preservada o realmente enviada del CSV de entrega, cuando exista.
4. Revisar y registrar la decisión final antes de cerrar el issue y congelar la entrega.

El #69 prepara estas comprobaciones y conserva la evidencia histórica; no cierra #63 ni acredita
por sí solo el cumplimiento del concurso.
