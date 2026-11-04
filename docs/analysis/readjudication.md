# Revisión estricta: los episodios cortos fuera del campo, sin ground truth

Generado por `python tools/readjudicate.py --write docs/analysis/readjudication.md`.
No se edita a mano. Nada lee las etiquetas de BAR-ATH (decisión 45, adenda A).

## Prueba B: episodios cortos fuera del campo

Paradas etiquetadas que abre un episodio fuera del campo, por la reanudación que las
cierra (saque de banda, córner o saque de puerta: solo siguen a un balón fuera).

| episodio | saque de banda, córner o de puerta | otra reanudación |
|---|---:|---:|
| < 1 s | 11 | 5 |
| ≥ 1 s | 11 | 1 |

11 de 16 cortos terminan en un balón fuera (69%). Regla: la corrección 2 sigue revertida si son más de la mitad. **Veredicto: la corrección 2 sigue revertida.**
