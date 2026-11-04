# Dead-ball onset: leave-one-match-out on DFL

Generado por `python tools/loo_dead_ball.py --write docs/analysis/loo-dead-ball.md`. No lee ground truth ni vídeo: solo el corpus
DFL/IDSSE (CC-BY 4.0). Regla de selección, métricas y criterio de decisión:
`docs/proposals/lane-loo-dead-v3.md`, commiteado antes de la primera corrida.

| partido fuera | constante elegida en los otros 6 | precisión | recall | F1 | \|inicio\| (s) | F1 de W1 | \|inicio\| de W1 (s) | ΔF1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| J03WMX | onset<3.25/40s | 0.916 | 0.812 | 0.861 | 2.04 | 0.823 | 4.86 | +0.0378 |
| J03WN1 | onset<3.25/40s | 0.913 | 0.828 | 0.868 | 1.40 | 0.828 | 4.52 | +0.0406 |
| J03WOH | onset<3.25/40s | 0.934 | 0.771 | 0.845 | 2.36 | 0.793 | 5.88 | +0.0522 |
| J03WOY | onset<3.25/40s | 0.926 | 0.734 | 0.819 | 2.04 | 0.775 | 4.08 | +0.0443 |
| J03WPY | onset<3.25/40s | 0.930 | 0.819 | 0.871 | 1.44 | 0.813 | 4.72 | +0.0577 |
| J03WQQ | onset<3.25/40s | 0.906 | 0.746 | 0.818 | 1.52 | 0.732 | 6.64 | +0.0861 |
| J03WR9 | onset<3.25/40s | 0.906 | 0.812 | 0.857 | 1.80 | 0.792 | 7.36 | +0.0644 |

- Constante elegida con los 7 partidos (lo que ya estaba publicado): **onset<3.25/40s**.
- Estabilidad de la elección entre pliegues: {'onset<3.25/40s': 7}.
- Gana a W1 en F1 fuera de muestra: **7/7** (test de signos bilateral p = 0.016).
- ΔF1 mediano fuera de muestra: **+0.0522**; ganancia mediana de \|inicio\|: **3.28 s**.

## Cómo se lee

Criterio escrito antes de correr: la evidencia de DFL para `onset` es **fuera de
muestra** si gana a W1 en al menos 6 de 7 pliegues y la constante elegida es la misma en
al menos 5. Si no, el 7/7 publicado es un ajuste sobre los mismos siete partidos y así
hay que declararlo.

