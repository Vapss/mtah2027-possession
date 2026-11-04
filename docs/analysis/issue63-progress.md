# #63: evidencia y pendientes de procedencia

Esta nota distingue pruebas con datos sintéticos de una reproducción real. No es una decisión de
freeze ni justifica elegir parámetros con el slice. La referencia es `dev` en `ebec47f`.

## Prior de duración

El `355` de `postprocess.py` se obtenía de la duración media del slice (D20). Se elimina, sin
sustituirlo por otro valor: la primera clave del desempate maximiza la duración original del vecino.
Si las duraciones difieren, esa clave ya decide; si son iguales, ambas distancias a cualquier prior
son iguales. Por tanto la segunda clave no podía cambiar la elección. Se conserva el desempate al
vecino anterior. Este postproceso no está en la cadena `make repro`; sus otros umbrales siguen
necesitando procedencia admisible si se propone incorporarlo.

## Temperatura de emisión

La temperatura `2,857386876102962` se calibró con el GT público (D18). La función `engine.run`
calcula rasgos y control, y el build convierte etiquetas con `onehot`: no llama a `emision.emit`.
Una prueba sintética modifica la temperatura y hace fallar una llamada a `emit`, y comprueba la
salida del motor en ambos casos. Eso no sustituye la reproducción del CSV real. B5 sí usa esa
temperatura en probabilidades y confianza: no se debe afirmar que cambiarla deja inalterado un
ensemble. Se reemplazó por `2,864606845062 m` conforme al protocolo externo pre-registrado de
`docs/proposals/b5-external-calibration.md`. Resultados reproducibles en `b5-external.json`:
log-loss condicional en el segundo partido DFL 0,5347 frente a 0,7437 con el prior de 1 m.
Esto demuestra la compuerta DFL especificada, no calibración en el partido de competición.
El manifiesto histórico B6 fija el hash del artefacto con la temperatura anterior: generar B5 con
la nueva temperatura cambia sus probabilidades y no puede satisfacer ese hash. `make verify-b6`
solo puede comprobar esa evidencia con el artefacto histórico correspondiente; queda por preparar
una ruta reproducible para conservarla sin devolver la temperatura anterior al flujo actual. No se
actualiza el manifiesto sin regeneración y auditoría con el bundle. Se propone comprobar la evidencia
histórica en un checkout aislado del commit anterior al cambio, sin usarla para generar la entrega:

```bash
git worktree add --detach runs/b6-historical ebec47f9267edae2089389dd845ac4340bdb1a53
cd runs/b6-historical
uv sync --locked
# MTAH_DATA_DIR debe apuntar al bundle licenciado, fuera del repositorio.
.venv/bin/python tools/emision.py --output artifacts/possession.csv
make verify-b6
```

En Windows se usa `.venv/Scripts/python`. El commit conserva la emisión histórica; la auditoría no
vuelve a adoptar su temperatura para el modelo actual. **Ruta propuesta, no verificada:** aquí no hay
bundle y no se ha comprobado el hash antiguo ni el resultado de `make verify-b6` en ese checkout.

## Constantes activas identificadas en la ruta del motor

Inventario estático inicial; la fecha es la de incorporación del carril en la historia consultada,
no necesariamente la fecha en que cada valor se eligió. Las fuentes son referencias, no una
certificación de que la regla 11 se haya cumplido.

| Elemento | Valores activos | Procedencia y estado |
|---|---|---|
| Control y duelo | 1,5 m; 5 m/s; `dwell=1`; `duel=True` | D29 y D34: adopción con comparación en el slice. Pendiente justificación externa. |
| Fecha de reanudación | +3,5 s en saques de centro; +5 s en otros tags | `lane-d.md` §2–3, incorporado el 29-oct: se eligieron usando agregados del tracking y tags del partido. Bajo la regla 11 actual no basta con que no usaran GT; necesitan procedencia externa y prior admisible. |
| Episodios fuera | fusión de huecos de hasta 1 s; retrospección de 40 s, o 120 s tras gol | `lane-d.md` §3, 29-oct; prior físico descrito allí. La selección de la variante `out` y los criterios de D30–D31 también consultaron el slice; evaluar la cadena y su procedencia completa. |
| Fuera breve | sin mínimo para episodios vinculados a una reanudación | D31: regla física, con referencia además al slice. Pendiente separar justificación del uso histórico de GT. |
| Parada W1 | velocidad ±12 frames, máximo 12 m/s, al menos 8 jugadores, p90 en ±1 s < 2 m/s; cerrar huecos vivos < 1 s y descartar paradas < 4 s | `lane-dead-v2.md` §2–3, 29-oct; DFL y prior físico, con selección del decodificador usando DFL y patrón de huecos del partido. Auditar independencia y selección de W1 antes de afirmar cumplimiento. |
| Reanudación | forzar equipo conocido salvo control previo aceptado; empate entre equipos se ignora | D30, D32 y D35; reglas de estado. Auditar si la elección entre variantes y sus límites dependió del slice. |
| Geometría y reloj | FPS, dimensiones y mitades proceden de `games.py` | Metadatos de alineación del organizador, no umbrales elegidos para optimizar; verificar versión de las entradas al reproducir. |

`still_mps`, `still_window_s` y el mínimo de salida sin tag se calculan o existen en `dead_ball`,
pero la variante final `out` no consulta esas señales para decidir sus paradas. El modelo logístico
de `dead_ball_v2` y sus umbrales de modelo tampoco se usan en W1. Este inventario no pretende cubrir
cada constante de bibliotecas o validadores; faltan auditorías de dependencias y fechas precisas.

## Control de acceso al GT

`tests/test_gt_guard.py` activa un audit hook de Python en el proceso y en procesos Python hijos.
Los controles negativos comprueban que un acceso prohibido deja evidencia incluso si se captura la
excepción. La prueba sintética ejecuta la cadena de reproducción real sustituyendo los lectores y
detectores cuyos datos licenciados no están disponibles. Una prueba separada, marcada para cuando
exista el bundle, ejecuta la reproducción con entradas reales y la misma vigilancia. Se exige que
el hook se haya iniciado en al menos siete procesos: `repro` y los tres pasos de cada build.

Alcance: los hooks de auditoría no son un sandbox del sistema operativo. Cubren eventos `open` de
procesos Python que heredan el entorno; no demuestran ausencia de lecturas mediante procesos nativos,
extensiones que eviten esos eventos, intérpretes aislados o rutas sustituidas por el propio código.
La prueba sintética tampoco cubre el interior de las funciones de entrada sustituidas. La evidencia
real y una revisión de esas rutas siguen siendo necesarias antes de certificar el build completo.

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

1. Reproducir y revisar la calibración externa B5 y verificar sus consumidores reales.
2. Para 1,5 m / 5 m/s / `dwell` 1 y la regla del duelo, producir una decisión justificada por
   corpus externo adecuado y prior escrito antes de medir; declarar un conflicto no es por sí solo
   una justificación de los valores actuales. Inventariar además el resto de constantes activas.
3. Reproducir dos veces con el bundle licenciado, comparar con el archivo candidato, pasar el
   validador y ejecutar la prueba de GT real. El bundle no está en esta copia.
4. Revisar y registrar la decisión final antes de cerrar el issue y congelar la entrega.
