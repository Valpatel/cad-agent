**Changed**
- Correct physical-path labels in the repository maps and extend the existing CI lesson with measured provisioning, exact-attempt log attribution and current-source receipt limits.
- Co-locate website entry scripts, compiler helpers, figure producers, assets and npm/Wrangler configuration under tools/site; retain explicit SDK module scope when the root npm package moves.

**Projects must change**
- Developer npm commands use npm --prefix tools/site; repository-relative site script and asset paths follow their new owners. Public page, asset and installer addresses retain their existing contract.
