# Documento técnico

El documento técnico que se entrega es el paper en inglés de [`docs/paper/`](paper/): la fuente es
`paper.html`, las figuras salen de `figures.py` y el PDF se construye con:

```bash
python docs/paper/figures.py
python docs/paper/build.py --team "<nombre del equipo>" --repo <URL pública> --out "<equipo>.pdf"
```

`build.py` incrusta las figuras, escribe el SHA-256 de `submissions/engine.csv` y lo imprime a PDF con
Chrome o Edge en modo headless. Va en inglés porque así están las reglas y la documentación del reto.

Lo que cambió respecto a la versión anterior de este archivo (decisión 44):

- Los organizadores aclararon las reglas. Nada de la entrega puede descansar en el ground truth
  público ni en el vídeo, y lo que se ajusta, se ajusta con datos externos. Aplicamos la lectura más
  estricta.
- Reaplicamos las reglas de selección escritas, borrando toda compuerta que leía el ground truth. Las
  paradas de los jugadores pasan de la regla de un umbral (W1) al detector logístico entrenado en DFL
  con primer control tras las paradas sin etiqueta (W3). La regla del duelo se queda por el juez
  externo de Metrica.
- La entrega es ahora SHA-256 `7a7f70b68d39…`, y el código que ajustaba valores con el ground truth o
  entrenaba con el vídeo salió del repositorio.

El detalle de cada decisión está en [`DECISIONS.md`](DECISIONS.md), los carriles en
`docs/proposals/` y las tablas generadas en `docs/analysis/`.
