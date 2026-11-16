# Documento técnico

El documento técnico que se entrega es el paper en inglés de [`docs/paper/`](paper/): la fuente es
`paper.html`, las figuras salen de `figures.py` y el PDF se construye con:

```bash
make paper TEAM="<nombre del equipo>" REPO=<URL pública>     # -> runs/paper/<equipo>.pdf
```

`build.py` incrusta las figuras, escribe el SHA-256 de `submissions/engine.csv` y lo imprime a PDF con
Chrome o Edge en modo headless. Va en inglés porque así están las reglas y la documentación del reto.
Ese atajo presupone la referencia local `submissions/engine.csv`; para un clon limpio, usa el
flujo siguiente, que genera su propio candidato y lo pasa explícitamente al constructor del PDF.

## Chilangorithms: reproducing the submitted file

Repository: <https://github.com/Vapss/mtah2027-possession>. The root README describes the inherited
organizer tooling; this section describes the team's final pipeline. Prerequisites are Git, `uv`
and Python 3.12.3; dependencies are pinned in `uv.lock`. Obtain the licensed match bundle separately
through the authorized organizer process. Do not commit, redistribute or upload that bundle to the
public repository.

Clone the team's `dev` branch: the inherited default `main` branch does not contain the final engine
or lockfile in the inspected Git history. The audited pipeline revision is
`3fabbf4e0e53db4017ef8aa2323ffafa7777524c`; this identifies the implementation, not a claim that
later documentation edits have already been published.

Tracked inputs are the source, configuration, lockfile and supplied SVG figures. The licensed bundle
is a separate input; `.venv/` and `runs/` are generated locally. Neither the internal reference
`submissions/engine.csv` nor the official delivery files `Chilangorithms.csv` and `Chilangorithms.pdf`
are supplied by a clean clone. The primary workflow needs none of these pre-existing artifacts.

Unix-like shell (replace the bundle path with its authorized local location):

```bash
git clone --branch dev https://github.com/Vapss/mtah2027-possession.git
cd mtah2027-possession
uv sync --locked --no-dev --inexact
export MTAH_DATA_DIR=/path/to/bundle
.venv/bin/python tools/engine.py --build runs/evaluator --submission runs/evaluator/submission.csv
.venv/bin/python evaluation/validate_submission.py runs/evaluator/submission.csv
.venv/bin/python -c "import hashlib,pathlib; h=hashlib.sha256(pathlib.Path('runs/evaluator/submission.csv').read_bytes()).hexdigest(); print(h); assert h == '7a7f70b68d39cdd749b8f98fcc91d433cf23ff4faf05a27eb71a6e31ef1c2425', 'Submission SHA-256 mismatch'"
```

Windows PowerShell:

```powershell
git clone --branch dev https://github.com/Vapss/mtah2027-possession.git
Set-Location mtah2027-possession
uv sync --locked --no-dev --inexact
$env:MTAH_DATA_DIR = "C:\path\to\bundle"
.\.venv\Scripts\python.exe tools/engine.py --build runs/evaluator --submission runs/evaluator/submission.csv
.\.venv\Scripts\python.exe evaluation/validate_submission.py runs/evaluator/submission.csv
.\.venv\Scripts\python.exe -c "import hashlib,pathlib; h=hashlib.sha256(pathlib.Path('runs/evaluator/submission.csv').read_bytes()).hexdigest(); print(h); assert h == '7a7f70b68d39cdd749b8f98fcc91d433cf23ff4faf05a27eb71a6e31ef1c2425', 'Submission SHA-256 mismatch'"
```

After cloning, all remaining commands run from the repository root. The hash command prints the
generated candidate's SHA-256 and fails unless it matches the recorded submission hash. The validator
checks format, not accuracy. Neither step reads ground-truth labels. The build recreates
`runs/evaluator/`; do not put a preserved reference there. No cached intermediates or external DFL
training files are required: the fitted stoppage weights are embedded in the tracked code.

Optional: if the evaluator separately obtains the delivered `Chilangorithms.csv`, preserve it
outside `runs/evaluator/` and `runs/repro/`. `repro.py --against` performs two additional builds and
compares their SHA-256 hashes with each other and with that reference; it does not obtain the
reference from the public repository. Use its actual preserved path:

```bash
.venv/bin/python tools/repro.py --against /path/to/delivery/Chilangorithms.csv
.venv/bin/python -c "import pathlib; assert pathlib.Path('runs/evaluator/submission.csv').read_bytes() == pathlib.Path('/path/to/delivery/Chilangorithms.csv').read_bytes(), 'Delivery bytes differ'; print('Byte-for-byte match')"
```

```powershell
.\.venv\Scripts\python.exe tools/repro.py --against "C:\path\to\delivery\Chilangorithms.csv"
.\.venv\Scripts\python.exe -c "import pathlib; assert pathlib.Path('runs/evaluator/submission.csv').read_bytes() == pathlib.Path(r'C:\path\to\delivery\Chilangorithms.csv').read_bytes(), 'Delivery bytes differ'; print('Byte-for-byte match')"
```

`repro.py` recreates `runs/repro/a/` and `runs/repro/b/`. The separate byte comparison checks the
primary candidate directly against the preserved delivery, rather than merely comparing digests.

Build the PDF from the tracked SVG figures and the regenerated candidate:

```bash
.venv/bin/python docs/paper/build.py --team "Chilangorithms" --repo "Vapss/mtah2027-possession" --date "November 2026" --submission runs/evaluator/submission.csv --out runs/paper/Chilangorithms.pdf
```

```powershell
.\.venv\Scripts\python.exe docs/paper/build.py --team "Chilangorithms" --repo "Vapss/mtah2027-possession" --date "November 2026" --submission runs/evaluator/submission.csv --out runs/paper/Chilangorithms.pdf
```

Chrome or Edge is required. Close any viewer holding the output PDF before rebuilding, then check
its title and displayed hash. This command preserves the configured paper date; change it only by
an explicit team decision. Regenerating figures with `make paper` additionally requires the
`starter` dependency group (`uv sync --locked --inexact --group starter`).

Static inspection confirms that this primary workflow generates its ignored CSV input before using
it. It does not require prior local outputs. A fresh-clone execution has not been performed as part
of this documentation correction; obtaining the authorized bundle and installing the pinned
environment remain prerequisites.

For delivery, use a byte-identical copy of the verified candidate named `Chilangorithms.csv`, the generated
`Chilangorithms.pdf`, and the public repository URL. Validate and hash the delivery copy itself;
keep the reference unchanged. Local delivery files can be kept under the gitignored `runs/delivery/`.
See [`SUBMISSION.md`](../SUBMISSION.md) for the organizer's delivery instructions. Historical research
protocols are not reproduction steps; the paper and D44–D45 retain the selection-history disclosures
and unresolved methodological and compliance limitations.

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
