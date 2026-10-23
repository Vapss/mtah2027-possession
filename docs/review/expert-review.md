# Crítica técnica adversarial — plan de 26 issues, More than a Hack 2027 (fase 1)

**Rol:** científico de datos deportivos (tracking óptico, detección de posesión, métricas de eventos).
**Alcance:** issues #5–#26 (abiertos), más #1–#4 como contexto. Repo `Vapss/mtah2027-possession`, rama `dev`.
**Método:** lectura del contrato y del scorer (`evaluation/possession_metrics.py`, 723 líneas), más análisis empíricos de solo lectura sobre `data/` con el intérprete del repo. Todo número marcado **[M]** es medición propia reproducible con los scripts del anexo; **[R]** es dato leído del repo; **[O]** es opinión.

---

## 0. Veredicto en una página

El plan está bien *construido* (contrato, escritor único, ledger, tests) y mal *priorizado*. Tres afirmaciones centrales del plan son falsas o indemostrables con los datos disponibles:

1. **"El baseline satura D (recall 0.08): aquí está la ganancia grande de macroF1" (#16).** Cierto para `smooth125` (recall 0.079) **[M]**, falso para `smooth50` — que es el baseline que hay que batir en el partido completo — cuyo recall de D es **0.214** **[M]**. El plan cita el número favorable sin decir a qué variante pertenece, y sobrestima el techo de D por un factor 3×. Y sobre todo: **D vale mucho menos de lo que el stream A supone**. Con `smooth125` en la mano, un D perfecto (oráculo) lleva spellF1 de 0.4242 a **0.5212** (+0.097) **[M]**; con `smooth50`, de 0.3256 a **0.3714** (+0.046) **[M]**.
2. **"Hay que usar broadcast donde el táctico no ve el balón" (#12).** La cobertura conjunta en la primera mitad es 59.3% → **64.5%** (+5.1 puntos) **[M]**. En los 5 minutos etiquetados, el hueco real es de **391 frames de 6.031** frames vivos (6,5%) **[M]**, y ahí el broadcast sólo cubre 157 y con una precisión de equipo de **0.873** frente a **0.990** de la regla trivial "repite la etiqueta anterior" (porque el 99% de esos frames son de un solo equipo) **[M]**. El stream C cuesta 5 issues y no tiene upside medible; tiene downside medible.
3. **"Diferencia menor a ~0.3 es no concluyente" (#22, DECISIONS #3).** Correcto en espíritu, mal derivado. La banda 0.2667–0.5939 es un intervalo *marginal de una submission*, no un test de dos métodos. El test correcto es pareado por posesión: con 17 posesiones hacen falta **≥6 posesiones discordantes en la misma dirección** para p<0.05 (test de signos exacto) **[M]**. Entre `smooth50` y `smooth125` — la decisión que el propio EVALUATION.md usa como ejemplo de trampa — hay **3 posesiones discordantes en total a los tres umbrales** (IoU 0.5: 1 y 1, p=1.0) **[M]**.

Lo que el plan **no** tiene y debería tener: un lector ATD con invariantes (no existe ninguno en `tools/`), una medición de *qué* significa D en el ground truth antes de construir el detector, un modelo de emisión mejor que "el jugador más cercano", y una validación fuera de los 5 minutos que no sea el bootstrap sobre 17 posesiones.

---

## 1. Base factual que uso (medida, no supuesta)

### 1.1 El slice público, desglosado
- 7.500 frames, 21 segmentos, **17 posesiones**, 4 segmentos de D de 5,5 / 20,4 / 18,3 / 14,5 s (58,8 s = 19,6% de los frames) **[M]**.
- Duraciones de posesión (s): 0,76 · 1,32 · 2,84 · 3,24 · 3,48 · 3,60 · 6,64 · 7,44 · 7,56 · 8,08 · 11,84 · 16,04 · 20,0 · 28,6 · 35,72 · 41,64 · 42,44 **[M]**.
- **6 de 17 posesiones duran menos de 4 s** y la más corta son **19 frames** **[M]**. El plan habla de 17 posesiones como si fueran 17 objetos homogéneos; no lo son: el 35% del denominador son spells cortos y el 65% de los frames vivos están en 5 spells largos.
- De las 20 transiciones internas, **12 son H↔A directas sin D en medio** **[M]**. Es decir: el hand-over sin balón muerto es el caso *mayoritario*, no la excepción. Cualquier regla que "espere" un D entre posesiones está modelando mal el dato.

### 1.2 Reproducción exacta de los baselines
Con `starter/baseline.py` sin tocar: raw 0.0378, smooth25 0.2868, smooth50 0.3256, smooth125 0.4242 **[M]** — idénticos a `evaluation/scoreboard.csv`. Cualquier afirmación mía sobre "el baseline" es sobre estos cuatro ficheros.

Ampliando el barrido a ventanas mayores (que el plan no contempla): 250 → 0.1920, 375 → 0.1920, 500 → 0.2087, 750 → 0.0200, 1000 → 0.0400 **[M]**. El óptimo local está en 125 y **colapsa** a partir de 250. Un voto mayoritario simétrico no puede arreglarse ensanchando la ventana: la señal tiene estructura de duración, no de ruido blanco.

### 1.3 Sensibilidad real de `spellF1` a errores de límite
Perturbando *cada* transición de forma independiente sobre el GT real (300 sorteos por nivel) **[M]**:

| ruido por transición | ±1 f | ±3 f | ±5 f | ±8 f | ±13 f (0,5 s) | ±25 f (1 s) |
|---|---|---|---|---|---|---|
| spellF1 medio | 1.0000 | 0.9997 | 0.9951 | 0.9826 | **0.9553** | 0.8978 |

Desplazamiento **global** (todos los límites a la vez, el caso que mide EVALUATION.md): 3 f → 1.0000, 8 f → 0.9529, 25 f → 0.8978 **[M]**.

Dos consecuencias:
- **La precisión de frontera es casi gratis** en `spellF1`: puedes errar medio segundo en *cada* transición y perder 4,5%. El harness B3 (#17) que mide `latency mean/p90` y `transF1@12/25` está instrumentando un término de tercer orden.
- Los números publicados ("8 frames tarde = 0.8933", "1 s tarde = 0.6539") son del **partido completo**, no del slice: en el slice el mismo retraso de 1 s cuesta 0.102 en vez de 0.346 **[M]**. Citarlos como si aplicaran al slice sobrestima 3,4× el coste de la latencia y empuja al equipo a optimizar lo que no importa.

### 1.4 Cuánto cuesta cada tipo de error (sobre el GT del slice)
| error inyectado en el GT perfecto | spellF1 | delta |
|---|---|---|
| ninguno | 1.0000 | — |
| fallar una posesión corta (0,76 s) | 0.9125 | −0.088 |
| fallar una posesión de 3,24 s | 0.9125 | −0.088 |
| fallar una de 3,48 s | 0.9697 | −0.030 |
| **no detectar ningún D** (fusionar los 4) | 0.8121 | **−0.188** |
| meter un D espurio de **6 frames** dentro de un spell de 41,6 s | 0.9371 | −0.063 |
| meter un D espurio de **50 frames** en el mismo sitio | 0.9371 | −0.063 |
| descartar todas las posesiones <4 s (6 de 17) | 0.5600 | −0.440 |

**[M]** Dos hechos no triviales: (a) **un D falso de 6 frames cuesta exactamente lo mismo que uno de 2 segundos** — el coste es el cuanto de partir una posesión (~1/17), no la duración; (b) el D no detectado cuesta 0,19, más que cualquier otra cosa salvo perder posesiones cortas en bloque.

### 1.5 El balón: el 43% "perdido" no es oclusión
- Presencia global 113.488/199.319 = **56,94%** **[M]**, coincide con DATA.md.
- Pero por bloques de 5 minutos en las mitades calificadas: **0,199 … 0,882** **[M]**. La presencia **no es estacionaria** y el slice público (0,882) es **el mejor bloque de toda la primera mitad**.
- **Sólo hay 150 huecos de balón en todo el partido. Mediana 268 frames (10,7 s), p75 526 (21 s), p90 845 (34 s), máximo 5.537 (3,7 min). El 99,9% de los frames sin balón está en huecos de más de 1 segundo; el 56% en huecos de más de 30 s** **[M]**.
- El campo de velocidad del balón (tercera columna) es NaN en el **89,5%** de los frames **[M]**; la velocidad hay que derivarla de las posiciones (mediana 5,54 m/s, p90 17,2 m/s).

Esto tiene tres corolarios que el plan ignora:
1. **C3 (#13, interpolación) está muerto al nacer**: no se interpola un hueco de 10,7 s de mediana. Sólo el 0,1% de los frames ausentes son interpolables con sentido.
2. **A2 (#10, calibrar N) es una búsqueda degenerada**: para cualquier N≤25 el máscara de hueco es prácticamente la misma (el 99,9% de los frames ausentes están en huecos >25). El barrido que el issue pide no puede discriminar.
3. El "41% sin balón" **no es ruido de oclusión frame a frame**: es el tracker perdiendo el balón durante *tramos* enteros, que es exactamente donde el ATD deja de ser informativo y donde el D es probable. Cambia el problema: no es "rellenar frames", es "clasificar tramos".

### 1.6 Sobre las dos cámaras (stream C) — medido
- El offset es **constante dentro de cada mitad**: **−4.014 frames** en la primera, **−26.919** en la segunda (diferencia 22.905 frames = 15,3 min, compatible con el descanso del táctico de 20.156 frames menos el descanso del broadcast) **[M]**.
- Un solo offset global para el partido: funciona en la primera mitad (tasa de acierto a 1,5 m del 53–77% por bloque de 5 min) y **cae a 0,0 en toda la segunda mitad** **[M]**. Es decir: el "desfase" que pide #7 no es un número, son dos, y un pipeline que estime uno solo falla en la mitad del partido sin avisar.
- Aun con el offset correcto, la tasa de coincidencia a 1,5 m es **0,559** (1ª mitad) y **0,490** (2ª) **[M]**. Condicionada a homografía de broadcast válida sube a **0,680**; con `reprojection_error>5` es **0,000** **[M]**. O sea: el 30–40% del residuo es replay/plano cerrado, y la máscara `valid`/`reprojection_error` del broadcast es un detector de replay utilizable gratis.
- Precisión de equipo del broadcast donde ambos ven el balón (5.300 frames vivos): **0,740** frente a **0,775** del táctico; acuerdo entre feeds **0,806** **[M]**. El broadcast no es complementario: es una versión peor del mismo dato.
- Cobertura conjunta 1ª mitad: 59,3% → **64,5%** (+5,1 pp); en el slice: 88,2% → 90,3% (+2,1 pp) **[M]**.
- **Tolerancia de sincronización**, medida como tasa de cambio de la etiqueta de equipo al desplazar el balón k frames (mitad 1) **[M]**:

| lag | 1 f | 2 f | 3 f | 5 f | 8 f | 13 f | 25 f |
|---|---|---|---|---|---|---|---|
| desplazamiento del balón | 0,26 m | 0,52 m | 0,78 m | 1,30 m | 2,07 m | 3,34 m | 6,18 m |
| **cambia la etiqueta de equipo** | 1,6% | 3,7% | 5,5% | 9,1% | **13,3%** | 18,9% | 25,0% |

La distancia mediana balón→jugador más cercano es **1,84 m** **[M]**. La lectura: con ≤3 frames de error el feed fusionado introduce ≤5,5% de flips, y como sólo toca el 6,5% de los frames vivos, el daño es ~0,4% de frames — irrelevante. **Con 8 frames (2,07 m) el error supera la separación típica balón-defensor y el 13% de los frames cambian de dueño.** Por tanto el umbral de 2 frames de #19 es **razonable como umbral de posición** (y alcanzable, porque el offset es estable a ±1 frame), pero **no es el umbral crítico**: el punto de rotura está en ~5–8 frames, y el daño real de C no viene del desfase sino de que la señal del broadcast es peor.

---

## 2. Veredicto por stream

### Stream A — balón muerto (#5, #10, #16, #21)

**Idea:** derivar D de SET PIECES ∪ huecos del balón, calibrar el hueco, decidir la duración de D tras un reinicio, y comprobar que D no se come frames vivos.

**Sólida en intención, mal en el diagnóstico y peor en el criterio.** Medido sobre el slice **[M]**:

| señal de D | precisión | recall | F1 |
|---|---|---|---|
| `SET PIECES` sola (1.189 frames) | 0,561 | 0,454 | 0,500 |
| ausencia de balón | 0,558 | 0,336 | 0,417 |
| inmovilidad del balón (mejor config: ±0,5 s, 2 m/s) | 0,513 | 0,453 | 0,481 |
| **SET PIECES ∪ (hueco>1 s)** — lo que construye #5 | 0,501 | 0,572 | **0,534** |

Y el efecto sobre la submission, que es lo que importa **[M]**:

| | spellF1 | n_pred |
|---|---|---|
| `smooth50` | 0,3256 | 26 |
| `smooth50` + D detectado por SET PIECES | **0,2732** | 24 |
| `smooth50` + D detectado por hueco>1 s | 0,3442 | 26 |
| `smooth50` + D detectado por la unión de #5 | **0,2829** | 24 |
| `smooth50` + **D oráculo** | 0,3714 | 25 |
| `smooth125` + **D oráculo** | 0,5212 | 16 |

Conclusiones duras:
- **El artefacto de #5, tal como está especificado, empeora la submission en −0,043 de spellF1** en el único dato etiquetado que existe. SET PIECES tiene precisión 0,56: el 44% de sus frames son posesión viva, y cada D falso parte una posesión a un coste fijo de 0,063.
- El **criterio de aceptación de #5 no puede detectar eso**: "valida con contract.py y `make submission && make validate` pasan" es un test de formato. Un artefacto que empeora la métrica pasa el criterio sin discusión.
- El techo del stream A es +0,046 sobre `smooth50` / +0,097 sobre `smooth125`, **y eso con D perfecto**, que no es alcanzable: la mejor señal disponible da F1_D 0,53.
- **El "recall 0.08" de #16 es de `smooth125`; el de `smooth50` es 0,214** [M]. El headroom real de D es la mitad de lo que el issue sugiere.
- #16 dice "cuántos frames dura D después de cada set piece" como si el problema fuera la duración. Medido: el coste de un D falso es **independiente de su duración** (6 frames = 50 frames = −0,063) **[M]**. El parámetro que importa es *dónde* empieza y termina el D (que caiga sobre un hueco real entre posesiones), no cuánto dura.
- #21 ("D no canibaliza H/A") mide la matriz de confusión D→H y D→A. Es el criterio correcto para `macroF1` y **el equivocado para `spellF1`**: lo que hay que medir es el número de *poseciones partidas* (`n_pred` y las banderas por posesión), no frames reetiquetados.

**Falta un issue previo (A0).** Nadie ha caracterizado qué es D en el ground truth. Medido: en los 4 segmentos de D del slice, el balón **está presente el 66% de los frames** y su velocidad es <0,3 m/s en sólo el 0,5% **[M]**. O sea: el ATD sigue viendo un balón que se mueve durante el balón muerto (el portero lo tiene, se coloca el córner, etc.). Por eso el baseline acierta D sólo cuando el balón desaparece de verdad. Sin este análisis, A1 se construye a ciegas contra una señal que no mide lo que cree.

### Stream B — motor de posesión (#6, #11, #17, #18)

**Es el stream que importa y está razonablemente planteado en dirección, pero con dos problemas de especificación y uno de medición.**

Lo que dicen los datos **[M]**:

| | segmentos | spells | transiciones | H↔A directas | duración media |
|---|---|---|---|---|---|
| GT | 21 | 17 | 20 | 12 | 14,2 s |
| raw | 137 | 131 | 136 | 125 | 2,0 s |
| smooth25 | 40 | 36 | 39 | 31 | 7,6 s |
| smooth50 | 30 | 26 | 29 | 21 | 10,8 s |
| smooth125 | 17 | 16 | 16 | 14 | 18,5 s |

- El fallo dominante del baseline es **fragmentación por parpadeo de equipo**, no los límites ni el D. Descomposición del gap de `smooth50` (0,3256) **[M]**: con su segmentación intacta pero etiquetas perfectas → **0,6222**; con sus etiquetas pero fronteras perfectas → **0,5037**. Para `smooth125` (0,4242): etiquetas perfectas → **0,5385**; fronteras perfectas → **0,4296**. Es decir: **arreglar las etiquetas vale 3–10× más que arreglar las fronteras**, y en `smooth125` las fronteras ya casi no valen nada (+0,005).
- #6 pide "pase recibido, 2+ pases consecutivos, N segundos de retención". **"2+ pases consecutivos" no es implementable con este dato**: DATA.md es explícito en que no hay identidades, son 46 tracklets anónimos que aparecen, desaparecen e intercambian identidad. Un pase requiere emisor y receptor; con tracklets sólo hay proximidad. El issue especifica una regla que el dato no soporta, y su criterio de aceptación (fragmentation < 1,90) es un número que nadie ha derivado del GT.
- El criterio de #11 ("posesiones predichas acercándose a 17 en los 5 minutos") es la trampa exacta que EVALUATION.md advierte: `smooth125` predice 16 y gana en el slice (0,4242) y pierde en el partido completo (0,2242 vs 0,2433 de `smooth50`, que predice 26). Ajustar el conteo a 17 es ajustar una estadística de 17 muestras.
- #17 (arnés de latencia/transF1) es útil como diagnóstico pero **no puede ser la evidencia de aceptación del stream**: mide el término que vale 0,045 como máximo.
- #18 (ablación) es el issue mejor planteado de los 26. Sólo le falta una cosa: declarar de antemano qué configuración se elige para el partido completo y con qué criterio, porque la ablación se corre en un slice que no puede rankear (ver §4).

**Falta (B0/B5/B6):** un modelo de emisión mejor que `argmin` del jugador más cercano (es la raíz del parpadeo: 0,775 de acierto por frame con una distancia mediana balón→jugador de 1,84 m significa que en ~20% de los frames el jugador más cercano es del equipo equivocado por milímetros), y un post-proceso determinista de longitud mínima de spell.

### Stream C — fusión multi-cámara (#7, #12, #13, #19)

**Técnicamente viable en la parte de alineación, económicamente injustificable en la parte de valor.** Detalle en §1.6 y §3.

- **#7 es factible pero está mal especificado**: pide "el desfase" (singular). Son dos (uno por mitad) y un solo número falla catastróficamente en la segunda mitad [M]. Además la validación que propone (correlación de posición del balón) **no tiene resolución de 2 frames** si se hace con tolerancia de 1,5 m: el balón recorre 0,22 m/frame en mediana, así que ±7 frames caen dentro de la tolerancia. Para certificar ±2 frames hay que ponderar los frames de balón rápido (p90 = 17,2 m/s = 0,69 m/frame) y usar tolerancia submétrica.
- **#7 y #12 confunden el papel de la homografía.** Los dos ATD ya vienen en coordenadas normalizadas de campo; para comparar feeds **no hace falta homografía**. La homografía sólo sirve para (a) detectar replays/planos cerrados vía `valid` y `reprojection_error` — que medido es un detector excelente: con `reprojection_error>5` la coincidencia es 0,000 — y (b) volver al vídeo, que no existe. El issue construye el argumento sobre una dependencia innecesaria.
- **#12 no tiene criterio falsable.** "El artefacto mejora p_home/p_away en los frames que antes eran hueco, con evidencia en el ledger" — en el único ground truth disponible esos frames son 391 (0,25% del partido, 1 posesión), y ahí el broadcast es **peor que repetir la etiqueta anterior** (0,873 vs 0,990) **[M]**. El criterio no puede pasar salvo por azar, y el plan lo interpretaría como éxito.
- **#13 (interpolación) no tiene sujeto**: mediana de hueco 268 frames [M]. Lo único interpolable es el 0,1% de los frames ausentes.
- **#19 (gate) medirá mal**: el error de sincronización es alcanzable por construcción (offset estable a ±1 frame dentro de cada mitad), así que el gate dirá GO siempre. El gate debe ser de **valor**, no de viabilidad.
- **Reencuadre que sí tiene sentido [O]**: usar el broadcast no para rellenar frames sino para **clasificar los 150 huecos largos** (¿fue un paro o el balón salió de plano?). Es un problema de 150 decisiones binarias con evidencia de 30 s de vídeo ajeno, no de 40.000 frames. Coste estimado: 1 issue en vez de 5. Impacto sobre spellF1: acotado por +0,19 (el D no detectado), y probablemente la mitad.

### Stream D — métrica y tuning (#8, #14, #22, #25)

- **#8 (partición en ventanas de 60 s) es metodológicamente inválido.** Un corte a 60 s parte posesiones (la media es 14,2 s y la más larga 42,4 s) y el scorer cuenta *posesiones*, así que un spell cortado por el borde de ventana se convierte en dos spells truncados: el spellF1 por ventana no es comparable con el agregado, y las ventanas no son independientes (comparten equipos, fases y spells). No se fabrican folds cortando una serie temporal continua. **Alternativa correcta:** jackknife dejando fuera una posesión (17 folds), que el scorer ya soporta porque expone las banderas por posesión (`matched_gt_flags`).
- **#14 (ledger) es correcto y barato.** Sin objeción. Sólo falta que registre `n_pred`, `n_gt` y las banderas por posesión, no sólo el escalar.
- **#22 es el issue más peligroso del plan.** Barrido de hiperparámetros optimizando spellF1 sobre 17 posesiones. Mi propio barrido de 20 configuraciones (σ del voto suave × ventana) encontró un "ganador" con 0,4513 frente a 0,4242 del baseline **[M]**: +0,027 que es puro ruido de selección entre 20 candidatos, exactamente el mismo fenómeno que hizo que el slice eligiera `smooth125` sobre `smooth50`. El criterio de #22 ("informe con los barridos, la banda al lado") no incluye corrección por comparaciones múltiples ni una regla pre-registrada de qué configuración se manda al partido completo.
- **#25 (economía del X) está mal encuadrado.** Lo plantea "antes y después de un hand-over". La regla real, que se deduce del scorer: `X` rellena hacia delante con la etiqueta previa, así que **`X` es preferible al argmax si y sólo si P(etiqueta previa) > P(argmax)** — es una comparación de probabilidades, no una cuestión de posición. Y hay una asimetría que el issue no menciona: **D erróneo parte la posesión (coste fijo 0,063); X erróneo la fusiona (coste ~0,06 en el peor caso y 0 si la etiqueta previa era correcta)**. Para `spellF1`, X es un seguro mejor que D cuando hay duda; para `macroF1` es una pérdida segura. Como `macroF1` sólo desempata, la decisión debería tomarse sólo con `spellF1`.

### Stream E — entregables (#9, #15, #23, #26)

Sólido y sin objeción técnica. Dos notas:
- **#15 (byte a byte) tiene un riesgo que no nombra**: `make score` corre `--bootstrap 1000` con semilla fija, así que es determinista; pero el CSV de submission debe formatear 199.319 × 4 números. Cualquier `float` acumulado en un `np.mean` de artefactos es determinista *en la misma máquina y misma versión*, no necesariamente entre BLAS. El test de #15 debe correr en el mismo contenedor que la entrega y con `OMP_NUM_THREADS=1` (reducciones de numpy pueden variar con el número de hilos). Es un fallo de reproducibilidad conocido y barato de cerrar.
- **#26** depende de #3/#4 (X1/X2), que están fuera de mi alcance; no los evalúo.

---

## 3. Los 5 riesgos que más pueden hundir el resultado (probabilidad × impacto)

### R1 — El equipo optimiza `spellF1` local sobre 17 posesiones y elige la configuración equivocada (prob. 0,85 × impacto 0,9) → **el riesgo dominante**
Ya ocurrió una vez con el baseline (el slice prefiere 125; el partido completo prefiere 50) y el plan lo reproduce estructuralmente en #10, #11, #22 y #8. Con 17 posesiones, una decisión necesita **≥6 posesiones discordantes** para ser significativa **[M]**; `smooth50` vs `smooth125` difieren en 3. En la práctica: **casi ninguna decisión de tuning que el plan contempla es demostrable, y varias son demostrablemente erróneas** (el conteo, la ventana, el umbral de D).
*Mitigación:* (a) pre-registrar en `docs/DECISIONS.md` que **ninguna elección se toma por argmax local**; (b) sustituir el bootstrap marginal por un test pareado por posesión (`n_discordant` + test de signos exacto, script de 20 líneas); (c) elegir hiperparámetros por **priors físicos** (tasa de posesiones 3,4/min, duración media 14,2 s, 12 de 20 transiciones sin D) y usar el slice sólo como *test de cordura*; (d) exigir en cada PR el `n_discordant` y la decisión, no el delta.

### R2 — El stream A se mergea porque "valida" y degrada la submission (prob. 0,7 × impacto 0,7)
El artefacto especificado en #5 mide −0,043 de spellF1 sobre la única evidencia etiquetada **[M]**, y su criterio de aceptación es de formato. Un `p_dead` sobrestimado parte posesiones a un coste fijo por split.
*Mitigación:* cambiar el criterio de #5 y #21 a "spellF1 de la submission ensamblada con y sin el artefacto, pareado por posesión, y sólo se mergea con ≥6 discordantes a favor o con un argumento de prior" (que será el caso: D oráculo vale +0,05/+0,10). Añadir un **gate de daño**: `n_pred` no puede crecer más de 15% al añadir A, y ninguna posesión del GT puede quedar partida por un D predicho de menos de 15 frames de separación de sus vecinos.

### R3 — El stream C consume el 25% del esfuerzo y no hay forma de saber si ayuda (prob. 0,9 × impacto 0,6)
5 issues de 21 abiertos, más un gate, para +5,1 pp de cobertura en una señal que es **peor** que la del táctico donde ambas existen (0,740 vs 0,775) y que en el único hueco medible rinde por debajo de la regla trivial. Además #7 está mal especificado (un offset, no dos) y #13 no tiene sujeto (huecos de 10,7 s de mediana).
*Mitigación:* **cerrar C2 y C3 ahora**, antes de la semana 3, y reencuadrar C como "clasificador de los 150 huecos largos" con un único issue cuyo criterio sea: *en los 391 frames del hueco del slice, la etiqueta de equipo derivada del broadcast debe superar 0,95 de acierto (hoy 0,873) o el artefacto no se usa*. Si #7 se queda, exige **dos offsets** y una validación por mitades con tolerancia submétrica sobre frames de balón rápido.

### R4 — El motor de posesión se especifica con reglas que el dato no soporta (prob. 0,6 × impacto 0,6)
"Pase recibido", "2+ pases consecutivos", "primer toque del tracking" (#16) requieren identidades que no existen (46 tracklets anónimos que se intercambian). El equipo gastará días en un parser de pases que no puede funcionar, y el resultado será un montón de reglas ad hoc sin objetivo global.
*Mitigación:* reformular B1 como **un modelo de estado con emisión probabilística y coste de cambio explícito** (ver §5), donde "pase" desaparece y queda "evidencia de que el equipo X controla el balón en el frame t". Es el mismo objetivo con una parametrización que el dato sí soporta.

### R5 — La reproducibilidad byte a byte falla en la máquina del jurado (prob. 0,35 × impacto 0,8)
#15 lo prueba en el mismo host. Reducciones de numpy/BLAS y el número de hilos pueden cambiar el último bit de un `mean`, y el CSV lleva 199.319 × 4 números con formato fijo. También el riesgo de DECISIONS #10: `make ci` en verde en GitHub con 10 de 60 tests saltados, y el jurado leyendo el check como evidencia.
*Mitigación:* `OMP_NUM_THREADS=1` + `PYTHONHASHSEED=0` en `make repro`; comparar hashes en dos directorios y con `--no-cache`; y un fixture sintético mínimo del bundle para que los 10 tests de datos corran en CI (DECISIONS #10 ya lo propone como mitigación y no está implementado).

**Riesgo que el plan no lista y debería:** el lector del ATD. La línea es `frame_id:46 jugadores:balón` y **el balón es el ÚLTIMO campo, no el primero**. Leyendo el primer campo sale una presencia de balón de 39,97%; leyendo el último, exactamente 113.488 (56,94%) **[M]**. Yo mismo caí en eso durante 10 minutos, y el único código del repo que lo hace bien es `starter/baseline.py`, que está congelado y no se importa. No hay ningún lector en `tools/` ni ningún test que fije los invariantes.

---

## 4. Issues que sobran, que faltan y que están mal planteados

### 4.1 Mal planteados (reescribir criterio)
| issue | problema | criterio propuesto |
|---|---|---|
| **#5 [A1]** | criterio sólo de formato; el artefacto medido empeora (−0,043) | "spellF1 de la submission ensamblada con/sin el artefacto, pareado por posesión; se reporta `n_discordant`; se mergea sólo con ≥6 a favor. Además F1_D ≥ 0,55 en el slice (hoy el techo es 0,53 con la unión, así que el issue tendría que replantear la señal, no el umbral)" |
| **#6 [B1]** | "2+ pases consecutivos" no implementable sin identidades; criterion = fragmentation < 1,90 sin derivar | "acierto de equipo por frame ≥ 0,85 (hoy 0,775) y `n_pred/n_gt` ∈ [0,8; 1,25] en los 22 bloques de 5 min; la ablación contra ventana fija la cierra #18" |
| **#8 [D1]** | ventanas de 60 s no son folds válidos | "jackknife dejando fuera una posesión (17 folds); se imprime la bandera por posesión y el agregado; el bootstrap se mantiene como cota, no como test" |
| **#10 [A2]** | barrido degenerado (máscara idéntica para N≤25, el 99,9% de los frames ausentes están en huecos >25) | "caracterizar los 150 huecos por duración y decidir el umbral por la distribución (p.ej. N=2 s), no por barrido; reportar la curva de D-F1 contra duración de hueco" |
| **#11 [B2]** | "acercarse a 17 posesiones" es ajustar el conteo del GT | "ninguna posesión predicha < 15 frames (el GT mínimo es 19) y `n_pred` dentro de [0,8;1,25]× la tasa física 3,4 posesiones/min" |
| **#12 [C2]** | criterio no falsable; la señal es peor que la del táctico | "en los 391 frames del hueco: acierto de equipo ≥ 0,95, o se cierra" |
| **#13 [C3]** | no hay nada que interpolar (mediana de hueco 268 frames) | cerrar; sustituir por "clasificador de huecos" (ver 4.3) |
| **#19 [C4]** | gate de viabilidad, no de valor; se cumplirá siempre | "GO sólo si C2 supera el umbral de valor de #12 y no baja macroF1 del slice en >0,01; si no, NO-GO con el número delante" |
| **#22 [D2]** | argmax local sobre 17 posesiones, sin corrección por múltiples comparaciones | "pre-registro de la rejilla y de la regla de selección antes de correr; se reporta `n_discordant` y p exacto; si ninguna config supera a la baseline con ≥6 discordantes, se entrega la baseline + B" |
| **#25 [D3]** | enmarcado en hand-overs; el criterio real es probabilístico | "regla `X` si P(etiqueta previa) > P(argmax); medido como delta de spellF1 y de macroF1 por separado, con la advertencia de que macroF1 sólo desempata" |

### 4.2 Issues que sobran o deberían posponerse
- **#13 [C3]** — no hay sujeto. Cerrar.
- **#12/#19 [C2/C4]** — posponer a después de que B esté cerrado. Si B llega a `n_pred/n_gt` ≈ 1 con la tasa física, la cobertura del balón deja de ser el cuello de botella.
- **#17 [B3]** — mantener como diagnóstico, no como criterio de aceptación del stream B.
- **#8 [D1]** — sustituir, no posponer.

### 4.3 Issues que faltan (con criterio de aceptación concreto)

**A0 — "Caracterizar el D del ground truth antes de detectarlo"**
*Por qué:* se va a construir un detector de una clase cuya semántica no está medida. Medido: el balón está presente en el 66% de los frames de D y su velocidad es <0,3 m/s sólo en el 0,5% **[M]**.
*Criterio:* memo en `docs/` con los 4 segmentos de D del slice clasificados (saque de banda, de puerta, falta, córner) y el techo de F1_D por señal disponible (SET PIECES 0,50 / hueco 0,42 / inmovilidad 0,48 / unión 0,53), más la decisión de qué señal se usa. Sin esto, A1 no tiene objetivo.

**B0 — "Lector ATD con invariantes"** (bloquea a todo lo demás)
*Criterio:* `tools/atd.py` con tests que fijen: 113.488 frames con balón (56,94%), 199.319 filas, 46 slots, 24/22 reparto de equipos, media de 20,5 objetos por frame en frames calificados, y el balón en el **último** campo de la línea. Un test que falle si alguien lee el primer campo.

**B5 — "Modelo de emisión continuo en vez de vecino más cercano"**
*Por qué:* el `argmin` con distancia mediana 1,84 m produce 0,775 de acierto por frame y es la raíz del parpadeo H↔A que domina el error (arreglar etiquetas vale 0,10–0,30; arreglar fronteras 0,005–0,18) **[M]**.
*Criterio:* log-loss y accuracy por frame en el slice ≥ 0,85; y en la submission, `n_pred` más cerca de la tasa física **sin** usar el conteo del GT como objetivo.

**B6 — "Post-proceso determinista de estructura"**
*Criterio:* filtro de longitud mínima (≥15 frames, justificado por el mínimo del GT de 19), política de fusión de spells adyacentes del mismo equipo, todo en `tools/` con tests; y una tabla de `n_pred` por bloque de 5 min en los 22 bloques del partido.

**D5 — "Test pareado por posesión y regla de decisión pre-registrada"**
*Criterio:* script que, dadas dos submissions, imprima las banderas por posesión a IoU 0,3/0,5/0,7, las posesiones discordantes y el p-valor exacto del test de signos. Regla escrita: *ninguna decisión con <6 discordantes*. Es el issue que convierte #22 de trampa en herramienta.

**D6 — "Validación fuera de los 5 minutos sin ground truth"**
*Por qué:* es el hueco más grave del plan: sólo hay 17 posesiones etiquetadas y el plan entero decide con ellas.
*Criterio:* informe de los **22 bloques de 5 minutos** con, por bloque: nº de posesiones, duración media, reparto H/A, fracción de D, fracción de frames con balón, y acuerdo con la etiqueta `Team` de Smart Tagging (314 Barça / 288 Athletic / 36 N/A) en las fases etiquetadas. Un sistema que se rompe en los bloques 7, 11 y 15 (presencia de balón 0,20–0,37) **[M]** no se detecta mirando el bloque 1 (0,88). Esto es un *holdout distribucional*, no de etiquetas: no viola ninguna regla porque no usa el GT privado.

**E5 — "Determinismo entre máquinas"**
*Criterio:* `make repro` con `OMP_NUM_THREADS=1` y `PYTHONHASHSEED=0`, dos directorios, hash idéntico; y el fixture sintético de DECISIONS #10 para que los 10 tests de datos corran en CI.

---

## 5. Dónde el plan optimiza la métrica equivocada

1. **`macroF1` como objetivo del stream A.** El ranking es `spellF1`; `macroF1` desempata. Cuatro issues (#5, #10, #16, #21) están escritos en términos de `f1_D` y `macroF1`. Medido: mover `f1_D` de 0,32 a 1,0 no arregla `spellF1` si el D cae mal (D oráculo sólo da +0,05/+0,10) **[M]**. Y al revés: el stream A puede subir `f1_D` y bajar `spellF1` (SET PIECES como D: `f1_D` mejora respecto al baseline, `spellF1` cae 0,052) **[M]**. El plan no tiene un solo issue cuyo criterio sea "sube spellF1".
2. **Latencia y `transF1` como criterio del stream B (#17).** El ruido de frontera de ±13 frames cuesta 0,045; una posesión perdida cuesta 0,03–0,09; un split falso 0,063 **[M]**. El harness mide el término más barato.
3. **Conteo de posesiones como objetivo (#11).** El caso documentado del propio repo demuestra que el conteo local no generaliza.
4. **`X` evaluado con la lógica de `macroF1` (#25, DECISIONS #5).** `X` no cuesta nada en `spellF1` dentro de una posesión y cuesta como un error en un hand-over; su valor es una comparación de probabilidades contra la etiqueta previa.

### 5.1 Qué es estadísticamente indemostrable con 17 posesiones
Con 17 posesiones y un test de signos exacto, **el mínimo detectable es 6 posesiones discordantes todas en la misma dirección** (p = 0,031); con 5 es p = 0,062 **[M]**. Traducido a `spellF1`: si una configuración mejora 5 posesiones y no empeora ninguna, el delta puede ser de 0,15–0,25 y **seguir siendo no concluyente**. Por tanto:
- **Indemostrable:** elegir ventana de suavizado, umbral de D, σ del voto, `--abstain-below`, o "eventos vs ventana fija" por comparación local.
- **Demostrable (apenas):** sólo cambios que volteen ≥6 posesiones, es decir, cambios de régimen (p.ej. eliminar el parpadeo H↔A, que mueve 10+).
- **El bug de la banda:** el bootstrap de `bootstrap_spell_f1` remuestrea posesiones del GT **manteniendo `n_pred` fijo** (`false_positive = max(0, n_pred - tp)`) y se calcula por submission. No es un intervalo para la *diferencia* entre dos sistemas, y para un sistema con `n_pred >> n_gt` es optimista en la cola alta. Usarlo como test de comparación es un error de tipo III.

### 5.2 Qué haría en su lugar (evidencia real, sin GT privado)
1. **Test pareado por posesión** (McNemar / signos exactos) con `n_discordant` reportado. Es la única inferencia válida con 17 muestras.
2. **Jackknife leave-one-possession-out** en vez de ventanas de 60 s.
3. **Agregación por mitades/bloques:** el partido tiene 22 bloques de 5 min; reportar por bloque `n_spells`, duración media, reparto H/A, fracción de D y acuerdo con Smart Tagging. No da etiquetas, pero detecta el fallo catastrófico (bloques con 20% de balón) que el slice no puede ver.
4. **Análisis por clase de posesión:** partir las 17 en cortas (<4 s, 6) y largas (11). Un cambio que sólo mueve las cortas se ve distinto de uno que mueve las largas, y el coste por clase es conocido (−0,088 vs −0,03) **[M]**. Reportar el delta por clase reduce la varianza efectiva.
5. **Pre-registro:** escribir en `docs/DECISIONS.md`, antes de correr el barrido, la rejilla y la regla de selección. El plan ya tiene la cultura de decisiones escritas; sólo le falta aplicarla al tuning.
6. **Prior físico como árbitro:** 3,4 posesiones/min, 14,2 s de media, 12 de 20 transiciones sin D, 19 frames de mínimo. Cualquier configuración que produzca 26 posesiones en 5 min (el doble de la tasa física) está mal aunque el slice la premie.

---

## 6. Propuesta alternativa de modelado

**[O] El plan no es correcto en su asignación de esfuerzo, pero sí lo es en su núcleo (B). Mi propuesta conserva B, cierra C y reordena A.**

### 6.1 Diagnóstico que la sustenta
- La información necesaria **está casi siempre presente**: con una ventana de 5 s y etiquetas perfectas, `spellF1` llega a 0,5385 con la segmentación del baseline **[M]**; el problema es de *estimación*, no de *datos que faltan*. Eso descarta por sí solo que el stream C (más datos) sea la palanca.
- El término dominante del error es el **parpadeo de la etiqueta de equipo**, que produce spells espurios de 2 s (raw: 131 spells, media 2,0 s) y splits dentro de posesiones reales.
- La precisión de frontera vale poco (±13 f → −0,045), así que no hace falta un modelo de alta resolución temporal: hace falta uno que **no invente cambios**.

### 6.2 Modelo propuesto: HSMM determinista con emisión continua
1. **Emisión** `e_t(team)`: verosimilitud de que el equipo *team* controle el balón en *t*, calculada como un voto suave sobre los *k* jugadores más cercanos con pesos `exp(-d²/2σ²)`, más features de contexto baratas: distancia del balón al centroide de cada equipo, número de jugadores del equipo en un radio de 10 m, y (si está) `Team` de Smart Tagging como *prior* suave, no como etiqueta. Esto sustituye `argmin`, que es la fuente del parpadeo.
2. **Modelo de duración** sobre las posesiones: geométrica o log-normal con media 14,2 s y mínimo 15 frames. Esto no es un hiperparámetro que barrer: sale de la tasa física de posesiones y del mínimo observado, y es el mismo en cualquier partido de fútbol.
3. **D** como tercer estado con emisión propia: `SET PIECES` (precisión 0,56 → peso moderado), duración del hueco de balón (mediana 10,7 s; los huecos largos son D con alta probabilidad), y homografía (`reprojection_error` alto ⇒ cámara fuera de juego ⇒ D probable). El D no se detecta frame a frame: se detecta como **segmento**, que es lo que la métrica mide.
4. **Decodificación** Viterbi semi-Markov (o programación dinámica sobre fronteras) que maximiza la verosimilitud conjunta con el coste de duración — un único óptimo global y determinista, no reglas que compiten.
5. **Post-proceso:** longitudes mínimas, y `X` sólo cuando `P(etiqueta previa) > P(argmax)` (que en la práctica significa casi nunca, porque el estado ya está regularizado).

**Por qué ganaría `spellF1`:** porque el fallo del baseline es estructural (inventa cambios), y este modelo penaliza cada cambio con un coste explícito ligado a la duración esperada. La evidencia de que el margen está ahí: `smooth50` con etiquetas perfectas y su propia segmentación llega a 0,6222 **[M]**; un modelo que no parpadee se acerca a ese régimen sin necesitar etiquetas perfectas. Y la ablación ya está pedida en #18, así que el coste de probarlo es bajo.

**Qué cuesta:** 2–3 días de implementación (emisión + DP semi-Markov), el DP es O(n·|S|·D) y hay que acotar la duración máxima razonable (~2.000 frames) para que corra en un portátil; y una calibración de σ y del prior de duración que **no** puede hacerse sobre 17 posesiones (§5.1), sino con priors físicos. Riesgo: el voto suave puede ser *peor* que `argmin` si σ está mal (lo vi: σ=0,5 da 0,35 y σ=4 da 0,45 en mi barrido rápido **[M]**), lo que refuerza R1: hay que fijar σ por criterio (distancia mediana balón-jugador 1,84 m), no por argmax local.

### 6.3 Por qué las alternativas obvias no son mejores (o sí, y el plan no las tiene)
- **Modelo aprendido sobre los 5 minutos etiquetados.** Descartado por datos, no por opinión: 17 posesiones y ~7.500 frames de una sola fase del partido. Un clasificador con 10 features ya tiene más parámetros que observaciones independientes. Además las reglas del concurso permiten LLM para código pero no para etiquetar; un modelo entrenado con 17 posesiones es overfitting con forma de metodología. **Pero** un modelo *no supervisado* sobre los 39 minutos de ATD sin etiquetas (p.ej. ajustar σ y la duración por máxima verosimilitud de la señal, no del GT) sí es legítimo y es lo que recomiendo para calibrar.
- **HMM/Viterbi sobre el tracking.** Es exactamente mi propuesta, pero **en su versión ingenua no gana**: lo medí. Un Viterbi de 2 estados con coste de cambio λ y emisión `argmin` da 0,4138 en el mejor λ (50), **por debajo** de `smooth125` (0,4242) **[M]**. La razón es que la emisión es la misma señal ruidosa: el HMM aporta regularización temporal, que un voto de 5 s ya hace. **La ganancia no está en el decodificador, está en la emisión** (voto suave + contexto). Esto es un argumento *contra* el atajo "metemos un HMM y ganamos" y *a favor* de tratar la emisión como el objeto de diseño.
- **Post-proceso global del partido entero** (p.ej. forzar la tasa de posesiones a 3,4/min globalmente). Es una buena idea *como restricción*, no como objetivo: forzar el conteo global es exactamente el error de #11 a otra escala, y con `spellF1` un conteo global correcto puede convivir con miles de spells mal colocados. Úsese como prior de duración (mi punto 2), no como cuota.
- **Fusión multi-cámara como fuente principal.** No: es una señal peor (0,740 vs 0,775), redundante (acuerdo 0,806) y con 34% de frames inutilizables por replay. Su único uso defendible es clasificar los 150 huecos largos.

---

## 7. Resumen de recomendaciones, en orden

1. **Bloquear el tuning local** (R1): pre-registro + test pareado + `n_discordant` obligatorio en cada PR. Es la única mitigación que protege todas las demás decisiones.
2. **Reescribir el criterio de #5/#21** para que midan `spellF1` de la submission, no el formato ni `f1_D`.
3. **Cerrar C2/C3 ya** y quedarse con C1 sólo para clasificar huecos; dos offsets, no uno.
4. **Añadir A0 (semántica de D), B0 (lector ATD con invariantes), B5 (emisión), D5 (test pareado), D6 (22 bloques).**
5. **Implementar el HSMM con emisión suave** y compararlo en #18 contra `smooth50`, `smooth125` y las reglas de #6 — con la advertencia de que el slice no puede decidir, así que la decisión se toma por prior físico y se valida en estructura (22 bloques), no en el escalar.
6. **Reproducibilidad entre máquinas**: hilos fijados, y el fixture sintético de DECISIONS #10.

---

## Anexo — cómo reproducir las mediciones

Todo se hizo con `/root/repos/more-than-a-hack-2027-chilango/.venv/bin/python`, sin escribir en el repo. Scripts en `/root/.hermes/cache/scratch/`:
- `atd_load2.py` — parser del ATD (balón en el **último** campo). Verifica 113.488 / 56,94% y 46 slots; cachea `.npz`.
- Mediciones de sensibilidad (jitter de fronteras, D espurio, spells eliminados, oráculos) — sobre `evaluation.possession_metrics`, 300 sorteos por nivel.
- `starter/baseline.py::build/smooth` importado sin modificar para el barrido de ventanas y las descomposiciones.
- Alineación cross-feed: búsqueda de lag por correlación de posición del balón en coordenadas de campo, por bloques de 5 min y por mitades.

Números que **no** he verificado y por tanto no afirmo: la cobertura de `GOALS` (16.503 frames / 8,3%), el recuento de 638 instancias, la afirmación de que `SET PIECES` cubre 43.987 frames (mi medición en el slice es 1.189 frames de 7.500, coherente con 22,1% pero no equivalente), y todo lo relativo a #1–#4.
