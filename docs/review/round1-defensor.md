# Ronda 1 — Defensa del plan de 26 issues
**Rol:** defensor del plan, ingeniero escéptico de las modas. Sesgo declarado: prefiero un plan simple, verificable y que entregue antes que una arquitectura elegante que nadie termine.
**Regla de evidencia:** `[M]` = medición propia, reproducible con `/root/.hermes/cache/scratch/p1_*.py`; `[R]` = leído del repo con archivo/línea; `[O]` = opinión.

**Harness.** Reproduzco los cuatro baselines al cuarto decimal antes de afirmar nada: raw 0.0378 / smooth25 0.2868 / smooth50 0.3256 / smooth125 0.4242 `[M]`, idénticos a `evaluation/scoreboard.csv`. Uso `starter/baseline.py::smooth` copiado literal (ventana global, empates a H). Todas las cifras de abajo salen de ese harness, no del informe.

---

## Resumen ejecutivo

1. El plan está bien priorizado en su núcleo: los tres levantamientos que el informe propone como rescate (prior de duración, emisión mejor, quitar D de los huecos) ya tienen issue propio (#11, #6, #5/#21) y se miden con #18. No falta arquitectura: falta editar criterios de aceptación.
2. El informe acierta en el diagnóstico de A1 y se pasa en la conclusión: SET PIECES como señal de D es indefendible (−0.052 medido), pero el hueco de balón —la otra mitad del mismo issue— es la palanca más grande que encontré en todo el slice (+0.129).
3. M2 está mal redactada por el propio informe: manda cerrar C2 *y quedarse con C3*, que es justo el issue que su §1.5 declara sin sujeto (hueco mediano 230 frames `[M]`).
4. M3 propone gastar 2–3 días en un HSMM que, con la emisión que el propio informe admite (argmin), rinde 0.4414 `[M]` — por debajo de un filtro de longitud mínima de 10 líneas (0.4571) `[M]`.
5. Concedo tres cosas y ninguna cambia el plan: #16 cita el recall de D de la variante equivocada, #6 pide "2+ pases" que el dato no soporta, y #19 gatea viabilidad en vez de valor.

---

## M1 — "El stream A debe construirse sobre SET PIECES y seguir en el plan"
**Posición: MODIFICAR.** El stream se queda; SET PIECES deja de ser la señal primaria; el criterio de #5 y #21 se reescribe.

Reproduzco la calidad de las señales de D en la ventana pública (D contra el resto, a nivel de frame) `[M]`:

| señal | precisión | recall | F1 |
|---|---|---|---|
| SET PIECES (1.189 frames) | 0.561 | 0.454 | 0.502 |
| ausencia de balón | 0.558 | 0.336 | 0.420 |
| SET PIECES ∩ ausencia (filtro de precisión) | **0.993** | 0.199 | 0.332 |
| SET PIECES ∪ ausencia (lo que pide #5) | 0.488 | 0.591 | 0.534 |

Y el efecto sobre la submission, que es lo único que puntúa `[M]`:

| submission | spellF1 | Δ vs smooth50 |
|---|---|---|
| smooth50 | 0.3256 | — |
| + D:SET PIECES | 0.2732 | **−0.052** |
| + D:SET PIECES ∪ hueco (#5 tal cual) | 0.2829 | **−0.043** |
| + D:hueco de balón solo | 0.3442 | **+0.019** |
| + D:SET PIECES ∩ hueco | 0.3349 | +0.009 |
| + D oráculo (GT) | 0.3714 | +0.046 |
| smooth125 + D oráculo | 0.5212 | +0.097 |

Confirmo también que el daño de A1 no se arregla con un B mejor: sobre `smooth50 + min_len 60` (0.4571), SET PIECES cuesta −0.057 (0.4000) y el oráculo de D solo añade +0.057 (0.5143) `[M]`. La precisión 0.561 es el problema, no la dosis.

**Lo que el informe no midió, y es lo que salva al stream.** A pregunta "¿cuándo está muerto el balón?". La respuesta con más dinero del slice es *"el hueco de balón no es D"*: rellenar cada tramo sin balón con la etiqueta anterior y re-suavizar da **0.4541** desde 0.3256 (**+0.129**) sin usar broadcast, sin GT y sin modelo `[M]`. Con el hueco etiquetado por oráculo: 0.4649 (+0.139) `[M]`. Es decir: la lección más rentable del slice es una decisión del stream A, y el plan es el único sitio donde vive. Ese es el argumento para no cerrarlo.

**Concesión explícita:** tal como está escrito, #5 empeora la submission y su criterio ("valida con contract.py") es de formato. Eso es indefendible y hay que cambiarlo. Pero es una edición de tres líneas en un issue, no un rediseño: (a) señal primaria = hueco, con SET PIECES sólo como filtro de precisión (p=0.993); (b) criterio = ΔspellF1 de la submission ensamblada, pareado por posesión, con `n_discordant`; (c) #21 gatea posesiones partidas, no frames reetiquetados. Con eso el stream sigue costando 4 de 21 issues abiertos (19%) y conserva el único techo grande medido.

---

## M2 — "Cerrar la fusión (C2/C19) y dejar sólo la interpolación"
**Posición: EN CONTRA de la moción tal como está redactada.** Concedo C2 degradado y C3 cerrado, pero no por el argumento del informe y no con esa composición.

Primero, un error de hecho del informe que cambia el diseño de #7: **los dos feeds no vienen en el mismo sistema de coordenadas.** El balón del broadcast está en espacio imagen: x∈[−0.007, 1.068], y∈[−0.125, 1.257] `[M]`, mientras el táctico está normalizado 0–1 sobre el campo de 105.3×68.0 m (`games.py:62`). Sin homografía, la distancia mediana balón-broadcast a balón-táctico es 38.5–48.5 m para las cuatro orientaciones de ejes y para desplazamientos de −6 a +4 frames, con 0.0% de frames bajo 1.5 m `[M]`. La afirmación del informe (§1.6, §2) de que "no hace falta homografía para comparar feeds" es falsa; #7 pide exactamente lo correcto.

Segundo, el comparador estrella del informe es un oráculo. En los 389 frames vivos del hueco del slice (386 A / 3 H; los otros 494 frames sin balón son D real) `[M]`:

| predictor en el hueco | acierto |
|---|---|
| smooth50 (lo que hace el pipeline hoy) | 0.343 |
| "repite la etiqueta anterior" **implementable** (desde etiquetas predichas) | 0.762 |
| "repite la etiqueta anterior" **con la etiqueta verdadera** | 0.987 |
| broadcast (cifra del informe) | 0.873 |

El 0.990 que sostiene la tesis (b) exige conocer la etiqueta previa correcta. El pipeline no la conoce: su versión implementable da 0.762, **por debajo** del broadcast. Es decir, el mecanismo que el informe usa para declarar C2 de valor negativo está al revés. (Su cifra de 0.873 sí es plausible: coincide con la precisión de equipo del broadcast que él mismo mide, 0.740–0.806.)

Tercero, y aquí sí le doy la razón en el fondo: **el techo de C2 es pequeño y el slice no puede medirlo.** El oráculo de "etiquetar perfectamente todos los huecos" da 0.3814 (+0.056) y 0.4649 (+0.139) tras re-suavizar `[M]`; el relleno gratuito con la etiqueta previa ya da 0.4541 `[M]`. **Margen de C2 sobre el relleno gratis: +0.011.** Y el slice sólo contiene 5 de los 186 huecos del partido (mediana 230 frames, p90 840, máx 8.689) `[M]`; 5 huecos no pueden decidir nada, ni a favor ni en contra.

Cuarto, la moción manda quedarse "sólo con la interpolación", que es el único issue que ambos análisis matan: con huecos de 230 frames de mediana no hay nada que interpolar. Cerrar C2 para conservar C3 es quedarse con el issue equivocado.

**Mi posición operativa:** C3 se cierra (de acuerdo). C2/C19 no se cierran *por decreto* sino que se convierten en un único issue con gate de **valor**, no de viabilidad: se permite C2 sólo si, contra el baseline gratuito de relleno por etiqueta previa, gana ΔspellF1 pareado con ≥6 posesiones discordantes. Eso es literalmente lo que #19 ya intenta; sólo hay que cambiar su umbral de "sync ≤ 2 frames" (que se cumplirá siempre, como dice el informe) a un umbral de valor. Coste: 2 líneas en #19, y el gasto máximo queda acotado a 2 issues en vez de 5. C1 sobrevive medio día porque su hallazgo —dos offsets, −4 y −26.9 frames— es contenido real para el documento técnico de #23.

---

## M3 — "Sustituir B1/B2 por HSMM + emisión continua"
**Posición: EN CONTRA de la sustitución. A FAVOR de plegar emisión y duración dentro de #6/#11 como criterios de aceptación.**

El informe admite el dato que hunde su propia propuesta y luego no lo aplica: su Viterbi de 2 estados con emisión argmin da 0.4138, por debajo de smooth125. Yo lo repito en 3 estados (H/A/D) sobre la misma emisión `[M]`:

| modelo determinista | spellF1 | n_pred |
|---|---|---|
| smooth50 | 0.3256 | 26 |
| smooth125 | 0.4242 | 16 |
| Viterbi 3 estados, λ=20 | 0.3415 | 24 |
| Viterbi 3 estados, λ=50 | 0.4414 | 12 |
| Viterbi 3 estados, λ=100 | 0.2667 | 7 |
| Viterbi 3 estados, λ=300 | 0.0200 | 3 |
| **smooth50 + longitud mínima 60 frames (10 líneas)** | **0.4571** | 18 |
| smooth50 + longitud mínima 100 | 0.5103 | 12 |
| smooth125 + longitud mínima 40 | 0.4516 | 14 |

Tres lecturas:
- El decodificador semi-Markov, con la emisión que hay, vale **+0.017** sobre smooth125 y es una navaja: λ=50 da 0.4414 y λ=100 da 0.2667 `[M]`. Eso no es un modelo, es un hiperparámetro esperando a que alguien lo elija con 17 posesiones — exactamente el pecado que el informe atribuye a #22.
- El prior de duración, en cambio, es real y **gratis**: un filtro determinista de longitud mínima sobre smooth50 supera al HSMM del informe (0.4571 vs 0.4414) `[M]`. La conclusión honesta es que el valor está en la restricción de estructura, no en la maquinaria.
- La curva de longitud mínima sube monótonamente hasta 100 y ahí sigue subiendo (0.5103 con n_pred 12 frente a 17 reales, y 6 de 17 posesiones del GT duran <4 s). **No leo ese 0.5103 como ganancia**: es el mismo argmax local que eligió smooth125. Lo leo como dirección, y la dirección es "el output necesita una duración mínima", que es #11 escrito en castellano.

Por eso la sustitución no procede: (a) el HSMM no elimina el problema de calibración, lo multiplica (σ, prior de duración, pesos de D, longitud mínima); (b) el propio informe mide un spread de 0.10 en σ (0.35 a 0.45) y admite que no se puede fijar con 17 posesiones; (c) su ganancia sobre el plan actual no está demostrada ni contra un filtro de 10 líneas.

**Concesión explícita:** "2+ pases consecutivos" de #6 no es implementable con 46 tracklets anónimos, y el criterio "fragmentation < 1.90" no se deriva de nada. Eso es un error de especificación real. Se arregla sustituyendo esa cláusula por "acierto de equipo por frame ≥ 0.85" (hoy 0.775) y añadiendo la longitud mínima como post-proceso dentro de #11. El HSMM puede entrar como **una variante más de la ablación de #18**, con λ fijado a priori por el prior físico (14.2 s de media, mínimo 19 frames) y no por barrido — pero no como reemplazo del stream en la semana 1.

---

## Los tres errores / exageraciones que le achaco al informe

**1. "Los dos ATD ya vienen en coordenadas de campo; no hace falta homografía" (§1.6, §2).** Falso y medible: el balón del broadcast vive en espacio imagen (x hasta 1.068, y hasta 1.257), y sin homografía la distancia mediana al balón táctico es 38.5–48.5 m con 0.0% de coincidencia a 1.5 m, en las cuatro orientaciones y seis desplazamientos `[M]`. El informe construye un argumento de "dependencia innecesaria" contra #7 sobre una premisa que los datos niegan. Es el error que más caro sale, porque desactiva el único mecanismo (la homografía) que convierte el broadcast en dato.

**2. El "0.990 de la regla trivial" es un oráculo presentado como alternativa implementable (§2, §3-R3, §5.1).** Con la etiqueta previa verdadera da 0.987; con la etiqueta previa del pipeline da 0.762, **peor** que el 0.873 del broadcast `[M]`. La tesis (b) —"C tiene valor esperado negativo"— no se sostiene con ese número. Mi conclusión operativa (degradar C2) coincide con la suya, pero por un margen de +0.011 sobre un relleno gratuito, no por un valor negativo. Acertar la decisión con la aritmética equivocada es peligroso: la próxima vez el número dirá lo contrario y no habrá criterio.

**3. Su descomposición "arreglar etiquetas vale 3–10× más que arreglar fronteras" omite la palanca que él mismo degrada a limpieza.** El tercer eje —estructura del output, no etiquetas ni fronteras— mueve 0.3256→0.4571 con diez líneas `[M]`, más que su HSMM completo (0.4414). Al mismo tiempo su §5.1 afirma que "el plan no tiene un solo issue cuyo criterio sea subir spellF1", y eso es una exageración: #18 exige una tabla de 4+ configuraciones con spellF1, #22 barre optimizando spellF1 y #24 exige números before/after por stream. Lo que falta no es el criterio, es que #5 y #21 lo usen.

*(Errores menores, para constancia: #16 sí cita el recall de D de `smooth125` (0.079) cuando el baseline de referencia `smooth50` tiene 0.214 —verificado en `evaluation/scoreboard.csv`, columna `recall_D`—; es un fallo de atribución en el cuerpo de un issue, no de arquitectura. Y mi recuento de huecos de balón en el partido es 186, no 150: diferencia de definición, sin efecto sobre ninguna conclusión.)*

---

## Qué evidencia me haría cambiar de opinión

**M1 (A / SET PIECES).** Cambiaría a "cerrar A" si, al correr el diagnóstico estructural de los 22 bloques de 5 minutos (el D6 del informe, que sí apoyo), el efecto "el hueco no es D" desaparece por debajo de +0.01 en 3 o más bloques, o si el techo de F1_D con cualquier señal disponible baja de 0.50. Cambiaría a "A tal cual" si alguien muestra un subconjunto de SET PIECES con precisión ≥0.85 y recall ≥0.40 —con esa precisión el D empieza a pagar; hoy el mejor corte que encontré (∩ hueco) tiene precisión 0.993 y recall 0.199, y no llega.

**M2 (fusión).** Cambiaría a favor de C2 si en el partido completo —no en el slice— al menos 8 de los 186 huecos cruzan un cambio de posesión y el relleno por etiqueta previa falla en >30% de sus frames vivos; entonces el margen de C2 pasaría de +0.011 a algo con signo claro y 2 issues estarían justificados. Cambiaría a "cerrar C2 y C3 de golpe" si el gate de valor de #19, ya reescrito, no encuentra ni un hueco donde el broadcast bata al relleno. Lo que no me haría cambiar: la precisión de sincronización, porque es alcanzable por construcción.

**M3 (HSMM).** Cambiaría a favor de la sustitución si un prototipo con λ y σ **fijados a priori** (no barridos) supera 0.4571 —el filtro de 10 líneas sobre smooth50— en el slice, y además mejora el acierto de equipo por frame de 0.775 a ≥0.85, que es la única métrica que ataca la raíz del parpadeo. Mientras eso no pase, el HSMM es una variante de #18, no un plan.

---

## Lo que defiendo del plan, en una línea cada uno

- Contrato único de artifact (`tools/contract.py`, `docs/DECISIONS.md` §1–2): con 26 issues y varios agentes, un solo escritor es la diferencia entre entregar y no entregar.
- #20 (integración temprana) y #18 (ablación) son los dos issues mejor diseñados de la lista; el informe sólo objeta a #18 que fije la regla de selección de antemano, y eso es una línea.
- #14 (ledger) y #23 (documento) convierten el trabajo en evidencia; el informe no tiene objeción técnica a E.
- El reparto 4/4/5/4/4 con gates (#19, #21) es un plan que puede terminar. El del informe (HSMM + emisión + jackknife + test pareado + 6 issues nuevos) no cabe en el calendario y no trae un número que lo respalde.
