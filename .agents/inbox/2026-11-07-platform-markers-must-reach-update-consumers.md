# Platform markers must survive the updater as well as installation

## Observed on 2026-11-07 UTC

Issue 285 reported that the unmarked FEA requirement `pypardiso>=0.4` forced MKL onto unsupported architectures.
Fresh PyPI metadata showed PyPardiso 0.4.7 requires MKL; MKL 2026.2.0 publishes Linux x86-64 and Windows AMD64 wheels.
PyPardiso's upstream README states Linux/Windows support. Gmsh 4.15.2 and pyamg 5.4.1 publish macOS ARM wheels but
no Linux aarch64 wheel; Gmsh has no source distribution for that release. Those are different platform cases.

```text
GET https://pypi.org/pypi/{pypardiso,mkl,gmsh,pyamg}/json
uv 0.11.7 pip compile pyproject.toml --extra fea --python-version 3.12 \
  --python-platform aarch64-apple-darwin --no-build
16 packages resolved; neither pypardiso nor mkl selected
--python-platform x86_64-unknown-linux-gnu: success, pypardiso and mkl selected
--python-platform x86_64-pc-windows-msvc: success, pypardiso and mkl selected
--python-platform aarch64-unknown-linux-gnu: expected refusal, no compatible gmsh wheel
```

These are metadata resolutions without installation or native execution; they do not prove a macOS/Windows solve.
The existing Linux ARM external-mesher guidance remains necessary.

The first controlled platform test patched `platform.system/machine`, but packaging 26.3 caches those process facts;
its six failures were a harness mistake, not solver evidence. Using the library's marker environment correctly then
revealed the real consumer bug: `agentkit.installed_extras` stripped markers and required every package. With the
new correct marker but the old updater, it lost FEA on all six unsupported-PARDISO environments:

```text
PYTHONPATH=software:. python -m pytest -q tests/cli/test_update.py -k fea_markers
6 failed, 2 passed, 14 deselected
failure: 'fea' not in installed_extras despite every active requirement being present
```

## Corrective rule

Use the standard PyPA `packaging.Requirement` and marker evaluator for the updater's existing extra inference.
The standard library has no PEP 508 evaluator; this small existing ecosystem library avoids inventing one or
depending on pip's private vendored imports. Version 26.3 supports the project's Python floor, has no runtime
dependencies, is Apache-2.0 OR BSD-2-Clause, and had no findings in the online supply-chain row. It becomes an
explicit core dependency because updating is a core operation.

Check the actual extra on eight controlled OS/architecture combinations and a genuinely missing active package.
The existing mandatory wheel smoke also reads built `Requires-Dist` for six platform combinations, including the
negative control that PARDISO never enters the core extra. A tiny constrained matrix checks the unchanged SciPy
solve path without PARDISO against its known displacement and free-degree equilibrium.

## Limits

Platform markers express upstream platform support, not CPU performance, all ABI variants or future wheel
availability. The change does not make a PyPI-only Linux ARM Gmsh installation possible. Preserve mesher-build
identity and the existing external-runtime caveats; a metadata resolution is not a full CAD/FEA validation run.
