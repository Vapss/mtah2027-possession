# P2 · Ronda 1 — Crítico independiente

No he leído `/tmp/expert-review.md` ni `/tmp/debate/p1-r1.md`. Todo número de abajo lo he calculado
yo con `.venv/bin/python` sobre `data/` y `evaluation/gt/BAR-ATH_possession_gt_public.csv`, o lo he
leído con archivo:línea.

## Resumen ejecutivo

1. `spellF1` es un F1 **de conjuntos** (`possession_metrics.py:511-514`): `F1 = 2·TP/(n_pred+n_gt)`.
   Las posesiones son rachas maximales de H o A (`:51`), así que **D no existe como clase en la
   métrica de ranking**: solo pesa por dónde corta las rachas.
2. Con equipos perfectos, **no predecir D nunca puntúa 0.8121**. D sobre la máscara SET PIECES mueve
   ese número entre **0.8000 y 0.8606** según se manden a X o a H los D que la máscara no cubre: todo
   el efecto de la máscara cabe dentro de **una posesión** (1/17 = 0.059). No hay ganancia que
   reclamar en la métrica que decide.
3. El premio entero de saber el balón dentro de los 6 huecos del slice es **0.0235** (0.9765 con
   persistencia en huecos vs 1.0 oráculo): menos que una sola posesión (1/17 = 0.059).
4. **19 de 20 transiciones del ground truth caen en un frame con balón detectado.** El balón no
   falta donde se decide la posesión; falta donde ya da igual.
5. Los criterios de aceptación de **#6 y #11 los cumple el baseline que ya existe**
   (`evaluation/scoreboard.csv`: fragmentation 0.81 < 1.90, latencia media absoluta 9.0 < ~10, y
   exactamente 17 posesiones predichas). El plan puede cerrar 24 issues sin mover el número.

---

## M1 — "El stream A debe construirse sobre SET PIECES y seguir en el plan"

**Posición: NO como inversión de ranking. SÍ, reducido a un prior de 20 líneas con techo escrito.**

El número que la sostiene es 0.8121 contra el rango [0.8000, 0.8606]. Con equipos oráculo en el slice
y D predicho sobre la máscara SET PIECES, `spell_f1_mean` = **0.8000** si los D que la máscara no
cubre van a X y **0.8606** si van a H; no prediciendo D en absoluto (D→último equipo) = **0.8121**. El
efecto total de la máscara (0.06) es exactamente una posesión de 17: la máscara oficial de set pieces
no bate a no tener detector de balón muerto de forma distinguible. La razón es medible: en el slice la máscara
cubre 1.189 frames con precisión **0.561** y recall **0.454** sobre D (667 TP de 1.189); sus
intervalos duran hasta 875 frames (35 s; ids 454 y 464, máscara en `tools/smart_tagging.py:109`), mientras que
el reinicio real llega a los 69 frames (goal kick 18.320 → D→H en 18.389).

El techo del stream A, aun con D perfecto, es **0.1879** (1.0 − 0.8121) y solo con equipos perfectos.
Y dentro de esa ganancia, casi todo es gratis: **rellenar el segmento D de 138 frames (12.851-12.989)
con H cuesta exactamente 0.0000** (1.0000 → 1.0000), porque el error queda dentro de una posesión y
no crea frontera. Lo que sí cuesta es una frontera espuria: partir las 3 posesiones más largas con un
blip de 1 frame baja 1.0 → **0.8216**.

La pata de "huecos del balón" (A1/#5) es la más débil y es la que tiene issue propio (#10). En el
slice: `P(D | balón ausente) = 0.559`, `P(balón ausente | D) = 0.337`. **974 de 1.469 frames de D
tienen balón detectado (66%).** De los 886 frames sin balón, 386 son A y 5 H: 44% de los "huecos"
son juego vivo. Un detector D basado en huecos hereda ese 44% de falsos positivos, y cada uno de
ellos parte una posesión.

Y #10 ("calibrar el umbral N") no tiene gradiente donde calibrar: en los 199.319 frames del táctico
hay 184 huecos, mediana **229 frames (9,2 s)**, máximo 5.537; solo **43 huecos son ≤ 25 frames y
suman el 0,2% de los frames sin balón**. Cualquier N entre 26 y ~229 produce la misma salida. OPINIÓN:
#10 se cierra en una hora con N=25 y una tabla que documente la meseta; el barrido con banda bootstrap
que pide el criterio es ceremonia sobre 0,2% de los frames.

Lo que sí vale de SET PIECES no es la ventana: es la etiqueta `Team`. Solo **27 de 59** instancias la
traen (32 son `N/A`), y en el slice hay 2 casos utilizables, ambos aciertan el equipo del reinicio
(goal kick Barça 18.320 → H en 18.389; falta Atleti 17.533 → A en 17.838). 2/2 no es evidencia, es
una hipótesis barata: úsala como prior del equipo post-reinicio, no como máscara de D.

Riesgo político del plan, y esto es lo que más me molesta: **#16 se justifica con macroF1 y no tiene
guardián de spellF1**; #21 solo vigila que D no se coma frames vivos (precisión), nunca que el
ranking no baje. Con los 4 únicos puntos que existen en el repo, `f1_D` y `spellF1` van en **orden
inverso**: raw 0.420→0.0378, s25 0.386→0.2868, s50 0.323→0.3256, s125 0.146→0.4242. N=4 y
confundido con la ventana de suavizado — es un hecho, no una causalidad — pero apunta exactamente en
contra de la apuesta del plan y nadie la ha mirado.

## M2 — "Cerrar la fusión multi-cámara (C2/#12, C4/#19) y dejar solo la interpolación"

**Posición: SÍ al cierre de C2/C4, NO por el motivo que dan, y NO a "dejar solo la interpolación".**

El número: **0.0235**. Oráculo etiquetando todo, salvo que dentro de los 6 huecos de balón del slice
se persiste la etiqueta anterior, da 0.9765. Ese 0.0235 es el premio *completo* de conocer el balón
en los huecos, con oráculo de equipos incluido — por debajo de la resolución del slice (una posesión
= 0.059). Y la estructura lo explica: **19 de 20 transiciones del GT están en un frame con balón**
(distancia 0 a la detección más cercana); la única excepción (A→D en 12.851) está 20 frames dentro de
un hueco de 148. Los cambios de posesión ocurren cuando el balón se ve.

Pero "dejar solo la interpolación" es exactamente al revés. La interpolación es la fabricación: los
huecos del táctico tienen mediana 229 frames (9,2 s) y en el slice 4 de 6 pasan de 130 frames. En 9
segundos el balón cruza el campo; lo que se interpola ahí no es una medición. Lo que sí es defendible
es la persistencia (última posición conocida), que es gratis y es lo que la métrica ya premia. Si
C2/C4 se cierran, C3 debe convertirse en "carry de última posición + regla de equipo", no en
"interpolación con homografía y velocidad".

Dos defectos técnicos del par C1/#7 + C4/#19, que el plan no ha visto:

- El táctico tiene 199.319 frames y el broadcast 164.488 (`DATA.md:12`): **34.831 frames de
  diferencia (23,2 min)**, con 20.156 de descanso (`DATA.md:257`) dentro del táctico. Un desfase
  global no puede alinear las dos mitades; #7 pide "el desfase" y #19 pone el gate en ≤ 2 frames
  sobre un objeto que no es un offset único. La correlación de posición de balón se va a enganchar
  en el descanso.
- El gate mide la cosa equivocada: sincronizar bien no es ganar nada (#12 dice "mejora p_home/p_away
  con evidencia en el ledger", pero en el slice el balón está presente el **88,2%** de los frames —
  6.614/7.500 — frente al 56,9% del partido completo; el slice es el *mejor* caso posible de
  cobertura, y no hay sitio donde medir la mejora que C2 promete). 4 issues (C1, C2, C3, C4) + F1
  para un techo de 0.0235 en el único sitio donde se puede medir.

## M3 — "Sustituir B1/B2 por un HSMM determinista, emisión continua y prior de duración"

**Posición: sí a decodificar sin causalidad; no al prior de duración aprendido; no a borrar B2.**

Lo que sostiene la mitad que sí: la latencia es el mayor impuesto medible del slice. Desplazar el
oráculo k frames: k=1, 2 y 3 → **1.0000 exacto** (la posesión más corta, 19 frames, tolera 3 frames de
error: IoU 0.727 ≥ 0.7); k=6 → 0.9647; k=12 → **0.9059**; k=25 → 0.7765; k=50 →
0.5882. Un sistema offline (Viterbi) no paga ese impuesto por construcción; una regla tipo B1 ("2+
pases consecutivos", "N segundos de retención") sí, porque espera evidencia. El premio de la
decodificación no causal es, por tanto, **≤ 0.094**, y eso es todo lo que M3 puede reclamar.

Lo que no sostiene:
- El **prior de duración** se estimaría con 17 posesiones (duraciones 19…1.061 frames) y **4
  segmentos de D** (138, 511, 458, 362). Un prior ajustado ahí es el slice disfrazado de
  hiperparámetro. La alternativa sin parámetros nuevos: fijar el número esperado de posesiones por
  tiempo vivo (`mean_possession_duration_s = 14.191`, meta del GT) en vez de una distribución.
- **B2 no sobra, es la parte alineada con la métrica.** `fill_abstentions` (`:274-293`) ya convierte
  X en persistencia, y el criterio de #11 ("posesiones predichas acercándose a 17") es el único del
  plan escrito en la moneda de la métrica. Borrar B2 borra ese criterio.
- Un HSMM maximiza verosimilitud de segmentación, no `spellF1`. La métrica penaliza **doblemente**
  la frontera de más (FP más pérdida de IoU del padre): medido, una frontera espuria por posesión lleva
  el oráculo 1.0 → **0.3137**, y un blip cada 100 frames → **0.2286**. El decodificador debe llevar coste de
  transición asimétrico (cortar caro, fusionar barato), y eso no sale de un prior de duración
  simétrico.

## Los tres defectos que no veo en el plan

**D1 — El plan optimiza el desempate en la dirección en que la evidencia dice que pierde.**
Stream A = 4 issues cuyo objetivo declarado es `f1_D`/macroF1 (#16: "aquí está la ganancia grande de
macroF1"), y en los 4 únicos puntos medidos del repo `f1_D` y `spellF1` van en orden inverso: el
baseline con peor `f1_D` (smooth125, 0.146) tiene el mejor spellF1 (0.4242), y el de mejor `f1_D`
(raw, 0.420) tiene el peor (0.0378). Además macroF1 es solo el primer desempate. Ningún issue tiene
como criterio "spellF1 no baja".

**D2 — Los criterios de aceptación los cumple el baseline, así que ningún issue puede fallar.**
`evaluation/scoreboard.csv`: smooth125 ya tiene fragmentation 0.810 (el listón de #6 es < 1.90),
latencia media absoluta 9.0 frames (el listón de #11 es ~10), 17 posesiones (el objetivo de #11) y
spellF1 0.4242. Un issue puede "cerrar con números before/after" reenviando el baseline. El plan no
tiene ni un criterio por encima del estado del arte actual, ni un criterio de *no-regresión*.

**D3 — Todo se calibra en los 5 minutos menos representativos del partido, y nadie lo ha medido.**
El slice público tiene balón en el **88,2%** de los frames; el partido completo, **56,9%**. Tiene
**4 segmentos de D** y **2 set pieces con etiqueta de equipo**. Ahí se calibran N (#10), los umbrales
de A y B (#22) y el "17" (#11). El baseline oficial hace 0.2433 en el partido completo y 0.4242 en
el slice: el slice es **1,74× más generoso**. Cualquier constante ajustada ahí llega al privado con
ese sesgo, y el plan lo trata como si fuera una muestra.

*Deuda sin dueño:* entre los 26 issues **no hay ninguno que lea `atd.txt`**. `kloppy` no está
instalado en el venv y `tools/` no tiene lector. El balón es el **último** campo, tras el segundo
`:` (`starter/load_atd.py:45`). Parsear tras el primer `:` da 79.674 frames con balón (40,0%) en vez
de 113.488 (56,9%) y un hueco fantasma de 52.239 frames en vez de 5.537 — un artefacto
silenciosamente mal y con aspecto plausible. Un test que afirme `113488` (el número está en
`DATA.md:109`) cuesta 5 líneas y protege a los tres streams.

## Qué evidencia me haría cambiar de opinión

- **M1:** un experimento que, **manteniendo n_pred fijo en 17**, mueva solo D y muestre que subir
  `f1_D` sube `spellF1` ≥ 0.06 en ≥ 3 configuraciones. O una variante de la máscara que supere
  **0.8721** (0.8121 + una posesión) sin inventar fronteras. Mi 0.8000/0.8606 y mi 0.8121 salen de 17
  posesiones: si con las dos mitades etiquetadas el signo se invierte, me retracto.
- **M2:** que la fracción de transiciones del GT dentro de huecos de balón pase de 1/20 a > 20%, o que
  el techo de persistencia en huecos pase de 0.0235 a > 0.10. En el partido completo, con 43,1% de
  ausencia, el techo *podría* ser mayor — pero entonces hay que poder medirlo, y hoy no se puede.
- **M3:** que un prior de duración ajustado en la primera mitad prediga la segunda (holdout), o que
  Viterbi con las mismas emisiones gane ≥ 0.05 a una regla causal + refinado de fronteras offline.
  Si el refinado de fronteras captura la mayor parte de los 0.094, el HSMM es sobreingeniería.
