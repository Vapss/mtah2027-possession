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

Use the frozen reproduction revision below, independently of which branch is the default after
the release merge. The frozen reproduction revision is
`838801e996d61e28715947931640721b1ec6e5c2`, retained under tag `repro/pr71-2026-11-16`;
use the explicit checkout commands below. The inference
implementation is unchanged from `3fabbf4e0e53db4017ef8aa2323ffafa7777524c`; the reproduction
revision also contains the delivery manifest and PDF checks. Later documentation-only commits may
identify that same reproducible revision without changing the candidate.

Tracked inputs are the source, configuration, lockfile and supplied SVG figures. The licensed bundle
is a separate input; `.venv/` and `runs/` are generated locally. Neither the internal reference
`submissions/engine.csv` nor the official delivery files `Chilangorithms.csv` and `Chilangorithms.pdf`
are supplied by a clean clone. The primary workflow needs none of these pre-existing artifacts.

Unix-like shell (replace the bundle path with its authorized local location):

```bash
git clone --branch repro/pr71-2026-11-16 https://github.com/Vapss/mtah2027-possession.git
cd mtah2027-possession
git checkout --detach 838801e996d61e28715947931640721b1ec6e5c2
uv sync --locked --no-dev --inexact
export MTAH_DATA_DIR=/path/to/bundle
.venv/bin/python tools/engine.py --build runs/evaluator --submission runs/evaluator/submission.csv
.venv/bin/python evaluation/validate_submission.py runs/evaluator/submission.csv
.venv/bin/python -c "import hashlib,pathlib; h=hashlib.sha256(pathlib.Path('runs/evaluator/submission.csv').read_bytes()).hexdigest(); print(h); assert h == '7a7f70b68d39cdd749b8f98fcc91d433cf23ff4faf05a27eb71a6e31ef1c2425', 'Submission SHA-256 mismatch'"
```

Windows PowerShell:

```powershell
git clone --branch repro/pr71-2026-11-16 https://github.com/Vapss/mtah2027-possession.git
Set-Location mtah2027-possession
git checkout --detach 838801e996d61e28715947931640721b1ec6e5c2
uv sync --locked --no-dev --inexact
$env:MTAH_DATA_DIR = "C:\path\to\bundle"
.\.venv\Scripts\python.exe tools/engine.py --build runs/evaluator --submission runs/evaluator/submission.csv
.\.venv\Scripts\python.exe evaluation/validate_submission.py runs/evaluator/submission.csv
.\.venv\Scripts\python.exe -c "import hashlib,pathlib; h=hashlib.sha256(pathlib.Path('runs/evaluator/submission.csv').read_bytes()).hexdigest(); print(h); assert h == '7a7f70b68d39cdd749b8f98fcc91d433cf23ff4faf05a27eb71a6e31ef1c2425', 'Submission SHA-256 mismatch'"
```

After cloning, all remaining commands run from the repository root. The hash command prints the
generated candidate's SHA-256 and fails unless it matches the recorded submission hash, independently
stored in `configs/delivery.json`. The validator
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
.venv/bin/python docs/paper/build.py --team "Chilangorithms" --repo "https://github.com/Vapss/mtah2027-possession" --date "November 2026" --submission runs/evaluator/submission.csv --out runs/paper/Chilangorithms.pdf
```

```powershell
.\.venv\Scripts\python.exe docs/paper/build.py --team "Chilangorithms" --repo "https://github.com/Vapss/mtah2027-possession" --date "November 2026" --submission runs/evaluator/submission.csv --out runs/paper/Chilangorithms.pdf
```

Chrome or Edge is required. Close any viewer holding the output PDF before rebuilding, then check
its title and displayed hash. The builder rejects a CSV whose digest differs from the delivery
manifest before writing HTML or launching the browser. It includes the current Git commit in the
paper's checkout command; build from the clean, committed checkout described above.
This command preserves the configured paper date; change it only by
an explicit team decision. Regenerating figures with `make paper` additionally requires the
`starter` dependency group (`uv sync --locked --inexact --group starter`).

### Verified local reproduction: 16 November 2026

The real-data verification ran at `4146b2453b2bd4618549077182bc640a8ae69cae` (#69), with Python
3.12.3 and the pinned environment. The `dev` merge `acf1eb8a4c0ce8062098fdbf1ee21cf519c9126e`
has the same tree. The engine and its inference dependencies are unchanged from the frozen source
revision used by the primary instructions above.

- Two fresh builds ran in separate Python processes under the GT audit hook. The engine emitted
  contract-checked artifacts, the assembler wrote each candidate and the official validator passed
  for both. A direct byte comparison of the two generated files also passed.
- Both complete digests matched the independently recorded reference:
  `7a7f70b68d39cdd749b8f98fcc91d433cf23ff4faf05a27eb71a6e31ef1c2425`.
- Seven Python processes registered the guard; no forbidden GT access attempt was recorded.
- A clean local source clone used the separately stored licensed bundle and passed **509 tests**,
  with **6 skipped**, **0 failures** and **0 errors**. Lint, formatting and the licensed-data guard
  passed. CI remains a separate data-free check; its demo does not reproduce the final engine.

The audit hook covers Python file-open events in participating processes, not arbitrary native
access or deliberate evasion. It proves the observed build behaviour within that scope; it does
not establish historical selection independence or predictive accuracy. Licensed inputs, generated
CSVs and detailed logs remained local and ignored by Git. The sanitized verification record is
[`analysis/reproduction-verification.json`](analysis/reproduction-verification.json).

The original preserved delivery CSV was not supplied. Matching the recorded digest is verified;
direct comparison with a separately preserved or actually uploaded delivery file remains a distinct
delivery check. The optional `--against` workflow above performs it when that reference is available.

The paper was built locally with Chrome headless from a verified generated candidate. All **8 A4
pages** were rendered to PNG and visually inspected: title, team, full repository URL and candidate
hash were checked; figures, tables, code blocks and references are readable without clipped or
overlapping content. The long alternatives table repeats its header across the page break, and
page numbering runs from 1/8 to 8/8. Text extraction also found no unfilled template markers,
local profile paths or characters outside page bounds. The PDF remains a generated local artifact,
not a committed dataset or a new possession result. Its metadata timestamps are not part of the
byte-identical CSV reproduction contract.

For delivery, use a byte-identical copy of the verified candidate named `Chilangorithms.csv`, the generated
`Chilangorithms.pdf`, and the public repository URL. Validate and hash the delivery copy itself;
keep the reference unchanged. Local delivery files can be kept under the gitignored `runs/delivery/`.
See [`SUBMISSION.md`](../SUBMISSION.md) for the organizer's delivery instructions. Historical research
protocols are not reproduction steps; the paper and D44–D45 retain the selection-history disclosures
and unresolved methodological and compliance limitations.

### Verification status and remaining delivery gates

| Gate | Evidence required before delivery | Status |
|---|---|---|
| Candidate reproduction | Two fresh engine builds, official format validation and complete SHA-256 match | Verified locally at #69; two generated candidates also compared byte for byte |
| Exact delivery file | Compare the preserved or uploaded CSV with the verified candidate | Pending: separate delivery reference not supplied |
| Final document | Generate the PDF from the verified candidate; inspect layout, title, repository URL and recorded hash | Verified locally: 8 A4 pages, all pages visually reviewed |
| Selection provenance | Traceable independent justification for control thresholds and resolution of the historical slice exposure, including the W3 reselection (D44–D45, issue #63) | Unresolved; this PR does not establish compliance |
| Public access | Public repository containing the pinned reproduction revision, accessible without authentication after a data/history audit | Pending: repository was private at review time |

The recorded hash is an existing delivery reference; the verification does not select a new candidate.
These documentation and packaging checks do not change model parameters, possession labels or
the interpretation of the organisers' rules. A technical fix does not resolve the selection history.
The W3 provenance inventory and Python-process GT audit tests are described in
[`analysis/issue63-progress.md`](analysis/issue63-progress.md). The real-data check above supplements
the synthetic controls; B5 calibration remains historical research and has no active inference consumer.

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
  paper. La vigilancia de accesos al GT ya pasó con el bundle real dentro del alcance descrito arriba;
  #63 sigue abierto por la procedencia independiente de los umbrales y la exposición de selección.

El detalle de cada decisión está en [`DECISIONS.md`](DECISIONS.md), los carriles en
`docs/proposals/` y las tablas generadas en `docs/analysis/`.
