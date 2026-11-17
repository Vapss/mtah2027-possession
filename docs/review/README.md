# Revisión y debate del plan

Tres documentos y un veredicto. El orden de lectura recomendado es: este archivo, luego
`expert-review.md`, y después las dos posiciones de la ronda 1.

| archivo | qué es |
|---|---|
| `expert-review.md` | crítica adversarial de un científico de datos deportivos senior al plan de 26 issues (43 KB) |
| `round1-defensor.md` | posición de un ingeniero que defiende el plan, con instrucción de rebatir |
| `round1-critico.md` | posición de un crítico independiente que **no** leyó la crítica previa |

Las dos posiciones se escribieron en paralelo y sin verse entre sí; la coincidencia entre ellas, y
con la crítica, es lo que sostiene el veredicto.

---

## Veredicto (arbitraje)

Ninguna cifra de esta sección se repite de los documentos: todas se midieron de nuevo en este repo,
y cuando un agente se equivocó se dice.

### 1. El slice público es la parte más fácil del partido — medido

Frames con balón detectado en la ventana calificada del ground truth público: **88.2%**. En el
partido completo: **56.9%** (113,488 / 199,319). Cualquier medición local sobrestima el rendimiento
y, peor, **no puede evaluar** lo que depende de los huecos: la fusión multi-cámara solo actuaría
donde falta el balón, que es el 43% del partido que no tiene verdad pública.

### 2. `D` no es un problema cinemático — medido

- `P(sin balón | D) = 0.336`: **el 66% de los frames de balón muerto tienen el balón visible.**
- `P(D | sin balón) = 0.558`: la ausencia de balón tampoco implica `D`.

Consecuencia: los streams A y C deben construirse sobre contexto (reanudaciones, set pieces,
celebraciones), no sobre "no veo el balón". Esto mató la premisa del issue A1 original.

### 3. `macroF1` y `spellF1` se mueven en direcciones opuestas — medido

| política | macroF1 | spellF1 |
|---|---|---|
| `smooth50` tal cual | 0.6207 | 0.3256 |
| + `SET PIECES` como `D` | **0.6675** | **0.2732** |
| + etiqueta previa en los huecos de balón | 0.5105 | **0.3805** |
| `smooth125` tal cual | 0.5812 | 0.4242 |
| + etiqueta previa en los huecos | 0.5447 | **0.4774** |

La política que más sube la métrica del ranking cuesta 0.11 de `macroF1`. Por eso **todo criterio de
aceptación del backlog es ahora Δ`spellF1` pareado** y ningún issue puede mergearse por mejorar la
métrica de desempate.

### 4. Dónde se equivocaron los agentes

- **El defensor** afirmó que rellenar huecos da **+0.129**. Medido: **+0.053** (`smooth50` y
  `smooth125`, consistente). Su filtro de longitud mínima de 10 frames da **+0.016** en `smooth50` y
  **0** en `smooth125`, no el 0.4571 que reportó.
- **El crítico** afirmó que **19 de 20** transiciones del ground truth caen en un frame con balón.
  Medido: **15 de 20**. Acertó en todo lo demás que comprobé (88.2%, 0.558/0.336).
- **El primer experto** afirmó que la homografía no hace falta para comparar feeds. El defensor lo
  refutó con razón: el balón del broadcast viene en espacio imagen (x hasta 1.068), y sin homografía
  la coincidencia a 1.5 m es 0.0%.

### 5. Ruido, no señal

El delta más grande que encontró el debate (**+0.053**) está **dentro** de la banda bootstrap
(0.2667–0.5939, ancho ~0.33). Es dirección, no prueba. Con 17 posesiones hacen falta **≥6 pares
discordantes** para p<0.05; `smooth50` vs `smooth125` difieren en 3. Por eso el issue D5 existe y es
requisito de cualquier afirmación de mejora.

---

## Cambios aplicados al backlog

- **A1** reescrito: de "detectar `D` con `SET PIECES`" a "el hueco de balón no es `D`", con
  `SET PIECES` degradado a filtro de precisión (p=0.993, r=0.199).
- **A2** reescrito: el barrido de umbral era degenerado (máscara idéntica para N ≤ 25); ahora es un
  análisis por tramos de la estructura real (150 huecos, mediana 268 frames, 99.9% del déficit en
  huecos > 1 s).
- **A3** corregido: el recall de `D` de `smooth50` es 0.214 (no 0.079, que es `smooth125`), y la
  duración del `D` falso es irrelevante para la métrica.
- **A4** convertido en guardián de la métrica.
- **C2** degradado a opcional, apagado por defecto, con la razón escrita.
- **C3 cerrado** como `not_planned`: con mediana de hueco de 10.7 s no hay nada que interpolar,
  interpolar es inventar.
- **C4** reescrito: el gate mide **valor**, no viabilidad; la tolerancia real de sincronización es
  5–8 frames, no 2.
- **A0, B0 y D5 añadidos**: caracterizar `D` en el ground truth, lector ATD con invariantes (el balón
  es el último campo de la línea; parsear el primero da 40.0% de presencia y un hueco fantasma de
  52,239 frames), y la prueba pareada por posesión.
