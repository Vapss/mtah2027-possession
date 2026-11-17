# #63 — factibilidad de usar las recepciones de ELASTIC

**Pre-registro de una comprobación de factibilidad, no de selección del modelo.** Este documento
se escribe antes de leer los eventos de `benchmark/gt` o medir una variante con ellos. Se inspeccionó
el esquema Parquet y el número de filas de un archivo; no se leyeron sus filas. Las variantes y números del proyecto sobre los
siete partidos DFL ya se conocen, de modo que estos partidos no constituyen un test virgen del
proceso de desarrollo, aunque estas anotaciones de evento no se hayan analizado aquí.

## Fuente y límites conocidos

- [ELASTIC, commit `e245224`](https://github.com/hyunsungkim-ds/elastic/tree/e245224aad7450961eca40954ae2bc85e1e6e696),
  `benchmark/gt/{match}.parquet`: `period_id`, `player_id`, `spadl_type`, `frame_id`,
  `receiver_id`, `receive_frame_id` y timestamps. La fuente declara las anotaciones CC BY 4.0;
  el código tiene licencia MPL-2.0 y no se copia. Atribuir también el corpus DFL original.
- Tres partidos DFL, 25 fps. El tiempo de evento y recepción se anotó por tres expertos mirando
  animaciones de las trayectorias, no vídeo independiente; el consenso no corrige el posible sesgo
  compartido respecto a la geometría del tracking. El balón DFL es más limpio y la definición de
  posesión puede diferir del reto. Una recepción no implica necesariamente control según el reto.
- La extracción propone usar únicamente datos externos con derechos de uso; nunca lee ni envía los
  datos, etiquetas o vídeo del partido de competición. Todos los archivos externos permanecen en
  `runs/` u otro directorio ignorado, no en Git.

## Partición y preguntas fijadas antes de inspeccionar resultados

1. `J03WMX` y `J03WN1` son **desarrollo** del lector y comprobaciones de integridad;
   `J03WPY` queda reservado. La partición está fijada por ID, no por puntuación.
2. Comprobar si cada recepción tiene periodo, frame finito y receptor que pueda asociarse sin
   ambigüedad a un equipo en los metadatos DFL, y si ese frame existe en el tracking de esa mitad.
   Contar y explicar exclusiones por causa; no inferir equipo a partir de nuestra predicción.
3. Separar eventos de pase y el resto; detectar duplicados, frames contradictorios y recepciones
   simultáneas. Comprobar cobertura de `BallStatus` y `BallPossession` DFL, sin tratar su acuerdo
   como verdad independiente ni usarlo para filtrar silenciosamente ejemplos difíciles.
4. Documentar las semánticas de `receiver_id`, recepción, pases fallidos, disputas y balón suelto
   desde fuentes del proveedor. Un contacto sin evidencia de control no debe convertirse sin más
   en cambio de posesión; si no se puede distinguir, el instrumento no decide el duelo.
5. Solo si el lector y las semánticas pasan la revisión, escribir y registrar por separado **antes
   de ejecutar predicciones** qué cohortes, métricas, baseline, configuración, criterio y manejo de
   empates se usarían. No usar métricas sobre el slice ni el banco para elegirlos. Se debe registrar
   explícitamente la exposición previa a DFL y no llamar independiente al test por reservar un ID.

La salida de esta fase es un informe de esquema, licencias, cobertura y limitaciones, con pruebas
sintéticas de conversión; no es una puntuación de la cadena, no ordena configuraciones y no modifica
ningún parámetro. Si falla cualquier requisito de interpretación o derechos, se informa y no se usa
el corpus como árbitro. El partido reservado no se abre hasta registrar el protocolo posterior.
