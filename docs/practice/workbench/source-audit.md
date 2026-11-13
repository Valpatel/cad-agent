# Current source and reuse audit

**Audit base:** cad-agent `33c3f51b574bdfa9171da62c4573beaf840daa95`.
The transfer candidate is SCADA release 9.3, source revision
`1360585c76987e79f1b36a35b04a19f387d32286`, with UI 1.4.1 and model 0.4.0.
These are provenance identifiers; the implementation will bring all needed source
and documentation into cad-agent rather than depend on a remote checkout.

Independent source reviews cover viewer lifecycle/HUD, asset distribution and
reports, domain formats, and agent tooling. Source inspection and historical
release checks are distinct from new target-runtime validation.

[Design map](README.md)
