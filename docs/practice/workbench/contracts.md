# Workbench contract design

**Proposed contracts, not installed APIs.** Names below are design notation.
Implementation must add versioned schemas and paired positive/negative fixtures
before advertising these interfaces. Existing domain schemas stay authoritative.

## Separate records with separate jobs

| Record | Owns | Does not substitute for |
| --- | --- | --- |
| Capability descriptor | Stable capability ID, availability, supported formats/versions, optional actions, runtime profile and examples | Runtime files, private project contents or an implementation that does not exist |
| Runtime profile/receipt | Entrypoints, transitive assets, styles, workers/WASM/decoders, notices and exact content hashes | Domain document validation or engineering correctness |
| Project artifact index | Typed artifacts, immutable revisions and explicit relationships | A universal CAD/SCADA/PCB document or physics graph |
| Domain document/model/result | Native system topology, geometry, equations, units, assumptions and outputs | View camera, human comments or shared navigation state |
| Session | One owner for a live model/external solver, command sequence and clock | Renderer frames, recorded playback or a saved project |
| View state | Viewer/version, artifact revision, camera, layers, selection, guide step | Simulation snapshot or durable engineering result |
| Review sidecar/receipt | Revision-bound comments, mappings, decisions and evidence identity | Simulation commands or procurement/build progress |
| Migration inventory | One-time source→target paths, hashes, notices, disposition and verification | A second maintained runtime inventory or remote source dependency |

JSON is the canonical interchange for the shared envelopes. Existing YAML project
configuration may reference them; never duplicate a SCADA topology in YAML and
JSON as competing sources. Preserve SCADA system/model/snapshot JSON schemas,
native KiCad/STEP/3MF and existing assembly/result formats behind format adapters.
There is no single standard language that captures all these semantics without
loss. Add XML/OPC UA/P&ID or other industrial imports only through named, tested
adapters with documented retained and dropped information.

## Artifact and object identity

The minimum proposed `ArtifactRef` contains `projectId`, `artifactId`,
`revisionDigest`, `mediaType`, and `schemaVersion` when the format is schema-based.
A revision digest binds the immutable artifact bytes or a versioned canonical
bundle manifest. It is distinct from the source Git commit. Define the exact
UTF-8/canonical JSON encoding, path sorting, hash algorithm and exclusions in that
manifest's schema and test vectors; do not let different consumers invent their
own digest rules. Reuse existing release hashes for byte identity.

An `ObjectRef` adds `namespace`, `kind` and `nativeId`, with optional instance path
or subobject identity where the domain requires it. `viewId`, `layerId` and a point
in a declared frame are context, not substitutes for a stable object ID. Display
names, PCB reference designators, mesh array offsets and screen indices alone are
insufficient across revisions. A source lacking stable IDs can support a
revision-local coordinate anchor, explicitly labelled as such.

For example, an assembly instance path and a PCB UUID may refer to the same
physical board only through an explicit exported mapping. Each mapping names
both artifact revisions and its source/provenance. Changing either revision
invalidates that mapping until it is revalidated. Do not turn geometry equality
or a reused display name into proof of identity.

Resolution returns one of `resolved`, `missing`, `ambiguous`, `wrong-revision` or
`unsupported`. A renderer may offer candidates but cannot silently pick one for
a comment or approval. Units and frames travel with geometric anchors: unit,
origin, handedness, axes, dimensionality and any explicit transform chain.
Validate finite/invertible transforms. PCB bottom-side mirroring and connector
front/rear views are presentation transforms, not changes to stored identity.

## Viewer lifetime and host services

A small mount contract, with capabilities rather than dozens of mandatory methods:

```text
mount(container, {artifact, services, signal}) -> Promise<ViewerHandle>

ViewerHandle:
  capabilities                         # validated action/data capabilities
  dispose()                            # idempotent; releases owned resources
  fit()                                # mandatory for a contained camera view
  getViewState() / restoreViewState()   # versioned, domain-owned payload
  subscribe(listener) -> unsubscribe   # scoped events, not a global bus
  optional: resolveSelection(), select(), capture(), domain command adapter

services:
  assets, selection, navigation, diagnostics
  optional: reviewStore, sessionLease, audio
```

Non-camera report/table views do not implement fake `fit()` methods. Capabilities
must agree with supplied methods; absent or forbidden actions remain unavailable
in the HUD. Static previews remain useful when enhancement or a capability fails.
No document can specify an arbitrary JavaScript import URL. Trusted viewer/provider
implementations are registered by the installed application.

The host owns its container and layout; the view owns only its descendants,
listeners, observers, GPU/parser resources and subscriptions. It must reject a
late mount result after cancellation and clean allocations even if mounting fails
before returning a handle. Container-relative overlays must not inject `#app`,
body styles or page-global readiness/error flags. Resize uses the actual container,
not `window.innerWidth`. Preserve a deliberate camera on resize unless the user
or documented initial-fit policy requests fitting.

Shared asset services use leases/refcounts or equivalent explicit ownership.
Disposing one viewer must not abort a sibling's asset read or destroy a shared
session. The assembly controller currently owns its viewer disposal; introduce
an explicit owned/borrowed lifetime when adapting it, preserving standalone
ownership by default. A host does not call both controller and renderer disposal
without an ownership contract.

Use `createViewer` (ordinary assembly/STL manifest) and `createFileViewer`
(original-file input) to prove this API first. Adapt
the inline `<cad-model>` with disconnect/reconnect cancellation while retaining
its lazy poster mode. FEA follows after its page-global HUD and overlays become
scoped. The SCADA viewer remains independent of Three.js.

## Selection, commands and navigation

Selection is a request envelope containing object reference, origin view,
correlation ID and intent (`inspect`, `highlight`, `open`). The receiving adapter
returns a resolution result. Echoed events retain the correlation ID and must not
form selection loops. Highlighting an item must not dispatch a machine command
or automatically execute a model. Cross-view selection follows explicit mappings.

Domain commands are separately declared and validated. Their envelope names the
target artifact/session revision, command ID, arguments and authority context.
For remote/asynchronous sessions, the adapter also defines expected sequence,
deduplication, acknowledgement and rejection semantics; the local synchronous
adapter need not pretend it has network guarantees. The host disables unavailable
controls, but actual permission/validation remains in the command authority.
Distinguish rejected, accepted and completed operations. Never retry a potentially
accepted mutation blindly after a timeout.

A read-only renderer can still allow comments if the review service permits them.
Model control, annotation editing, build/procurement progress, engineering approval
and geometry editing are different capability namespaces. No single `editable`
Boolean grants all of them. Fault injection is an explicit simulation command;
real control-system writes are outside this integration.

A navigation entry contains artifact revision, capability/view ID, object
selection and versioned opaque view state. Browser history and breadcrumbs return
to the same graph/camera/step when compatible. A stale state gets a visible fallback
and Fit; it is not applied to a different model. Private project content and
credentials never enter public catalogue feeds or URL query strings. Shareable
deep links contain identifiers resolvable by the receiving host's authority.

## SCADA model and session seam

Transfer the existing viewer adapter, `getSnapshot()`, `subscribe(listener)`
returning an unsubscribe function, and optional `dispatch(command)`. Do not wrap
the headless model in a renderer or create one model per layout. The application
creates one session; each view borrows it. Changing layout or removing an observer
does not advance, reset or destroy the model.

The existing v1 read-only adapter omits dispatch; the v2 read-only adapter retains
a dispatch method that rejects writes. The host adapter must express a false
control capability for both and test both behaviours, instead of inferring
permission solely from method presence.

Keep two supported model replacement seams:

1. **Equation providers within the existing kernels.** Trusted synchronous modules
   declare ID/version/state version, supported engine/phases, units and closed
   parameter/state schemas. Data-only bindings choose family/type/component
   overrides; component wins over type, then family, then built-in behaviour.
   Pure `evaluate` may repeat during solving; owned state advances once per
   accepted substep. Swaps and invalid restore must be atomic. Binding swaps
   preserve core stocks/time and reset provider-owned state; compatible snapshot
   restore separately restores validated provider state. Kernel fault gates remain
   authoritative through both operations.
2. **Whole external solver adapter.** A different hydraulic, thermal, process,
   PLC-training or remote model can supply snapshots/subscriptions/commands without
   adopting the normalized kernel. It explicitly maps quantities, units, stable
   equipment IDs, timestamps, quality and authority. Unknown/stale data remains
   unknown/stale; a visual widget does not fill it with plausible numbers.

Preserve v1/v2 snapshot and time-base compatibility. V1 normalized stock accounting
uses rate × minutes / 10, while v2 uses rate × minutes. SI pump/heater examples
must retain their explicit conversion and accepted-flow/power semantics. Do not
rename normalized values to SI during transfer. Local pump equations do not make
the complete network a qualified hydraulic solver.

The session owner controls start/pause/step/reset/snapshot and fault policy.
Renderer animation clocks, assembly playback and solver clocks remain distinct.
Real-time, fixed-step, paused and externally driven modes must be declared.
Navigation does not silently change a session clock. Alarm/effect consumers observe
events once per session and respect host audio/reduced-motion settings.

Reproducibility receipts must include system/model/configuration inputs, seed and
time-step policy, engine version, provider implementation bytes and dependency
closure, parameter/binding/state schema identity, snapshot and output hashes.
Current provider ID/version and schema signature are declared compatibility
metadata, **not code hashes**. A mismatched provider implementation cannot inherit
an earlier receipt merely by reusing the same ID.

## Review and evidence

The proposed portable annotation sidecar includes its own format/version, record
ID, artifact/object anchor, body, author attribution, creation/edit history and
resolution state. A local export's author is self-asserted until authenticated by
a real host service; do not label it verified. Review permissions and persistence
are supplied by the application. A remote multi-user backend is not required for
the initial portable roundtrip and is not implemented by a new comment textbox.

Reopening a sidecar on changed artifacts retains unresolved comments visibly.
Explicit remapping records old/new anchors, who remapped them and why. A comment
being resolved does not approve the engineering result. Approval/sign-off binds
the relevant requirements, evidence and immutable revision with its own authority
and currentness rules. Existing assembly progress and procurement checkboxes keep
their different meanings.

For new SCADA checks, use a strict versioned receipt before the existing report
consumer sees a pass Boolean. Require actual producer success, current input/code
hashes, valid schemas, expected outputs and required evidence. A stale success
file left by a failed run is a failure. Preserve compatibility for existing
legacy reports that allow optional hashes; do not globally tighten old formats
as an incidental platform change.

## Distribution and compatibility

The runtime profile resolver belongs with existing publishing. Profiles reference
one owned file inventory and extend the current release receipt. Validate a closed
set of relative paths, hashes, notices and dependencies, including dynamic imports,
CSS URLs, parser workers and WASM. Reject traversal, escaping symlinks, missing
assets, undeclared code and unsupported schema versions before publication.

Separate minimal `model`, `assembly-reader`, `documents` and `scada-viewer` closures
from optional `scada-models`, scenario/example and gallery payloads. Exact profile
names are selected by the implementation schema. Gallery source remains inside
its library while minimal wheels/reports omit it unless requested. The public site
publishes selected galleries explicitly, not by copying everything under webkit.

Keep legacy entry URLs/imports through a documented deprecation cycle. Owned-copy
updates remove an obsolete file only if a prior receipt proves ownership and its
current hash still matches; modified/project-owned files produce a conflict report.
Fresh exports use new profiles; immutable historical releases are not rewritten.
No generated artifact or skill may require the old SCADA repository to build,
open, regenerate assets or explain an API.

[Design map](README.md) · [Implementation gates](migration-and-validation.md)
