# Documento técnico

El documento técnico que se entrega es el paper en inglés de [`docs/paper/`](paper/): la fuente es
`paper.html`, las figuras salen de `figures.py` y el PDF se construye con:

```bash
make paper TEAM="<nombre del equipo>" REPO=<URL pública>     # -> runs/paper/<equipo>.pdf
```

`build.py` incrusta las figuras, escribe el SHA-256 de `submissions/engine.csv` y lo imprime a PDF con
Chrome o Edge en modo headless. Va en inglés porque así están las reglas y la documentación del reto.

Lo que cambió respecto a la versión anterior de este archivo (decisiones 44 y 45):

- Los organizadores aclararon las reglas el 3 de noviembre. El slice y el banco comprueban, no eligen
  (decisión 44, del equipo). Aplicamos la lectura más estricta (decisión 45).
- Reaplicamos las reglas de selección escritas, borrando toda compuerta que leía el ground truth. Las
  paradas de los jugadores pasan de la regla de un umbral (W1) al detector logístico entrenado en DFL,
  con primer control tras las paradas sin etiqueta (W3).
- La regla del duelo y el primer control se justifican por la definición del reto. Metrica no se usa
  como evidencia mientras no haya permiso escrito.
- La entrega es ahora SHA-256 `7a7f70b68d39…`. El código que ajustaba valores con el ground truth o
  entrenaba con el vídeo salió del repositorio.
- La sección 9 de cumplimiento que añadieron #62 y #64 pasó, con sus salvedades, a la sección 9 del
  paper. Lo que sigue abierto está en #63: la justificación externa de 1,5 m / 5 m/s / `dwell` 1 y la
  garantía mecánica de que el build no lee el ground truth.

El detalle de cada decisión está en [`DECISIONS.md`](DECISIONS.md), los carriles en
`docs/proposals/` y las tablas generadas en `docs/analysis/`.
