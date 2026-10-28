# Review of section S1: Store

You are the reviewer of this section. You did not build it, and you must not change its geometry or its
YAML: your only output is a reviewer record. Rebuilding unchanged geometry is harmless; changing it voids
your review.

Purpose: Hold the balls
Requirements: R1, R2
Computed status: gated
Built by: base=builder, hopper=builder, lid=builder, ball=builder

## What is in this bundle

- `section/`: the section's YAML (and the project file for the requirements and project decisions).
- `gates.json`: every gate's verdict for this section's parts (status, stale reason, the checks that name
  its parts) and the dossier lint findings for it. Read this first.
- `status.json`: the computed status of the section and each part, and who built each part.
- `packet/`: the review packet: `manifest.json` (measurements, findings with witness points, views, the
  checklist) and the images it names.
- `checklist.json`: the questions to answer, the decisions to judge, the requirements to trace.
- `diff.patch`: what changed in the section's sources since the last sign-off (no earlier sign-off of this section: review all of it).
- `record-template.json`: your record, with the hashes and questions filled in. Copy it and fill it in.

## How to review

1. Read `gates.json` and the packet's `measurements` and `findings` before any image. A stale verdict is
   not a pass.
2. Answer every checklist question `yes`, `no` or `unclear` from the views it names. Give `evidence` (what
   you saw or read), the `views` you used, and set `image_only`: `true` when the answer rests on the images
   alone, `false` when a measurement backs it (list it in `measurements`: `gate:<name>`, a check id or a
   finding id). Never answer a count, a gap, a wall thickness or an engagement from an image: the gates
   measured those (`checklist.measured_only`). `unclear` is never a pass; ask for another view instead.
3. Judge each decision `justified`, `weak` or `missing_alternative`, with evidence.
4. Trace each requirement: `traced` is `yes` when a check or part of this section verifiably serves it,
   with evidence; `no` or `unclear` otherwise.
5. Write `findings`: `id` (F1, F2, ...), `severity` (`critical`, `major`, `minor`, `note`), `text`, and
   where useful `parts`, `view` (a packet view id, so the site shows it beside that image) and `checklist`.
6. Set `verdict`: `sign_off` only with no critical or major finding, no `unclear` answer, no answer that
   is the question's `bad_answer`, no decision missing an alternative and every requirement traced;
   otherwise `changes_requested` with at least one finding. Leave `actor`, `date` and `timestamp` empty.

Submit it (this checks the hashes against the current build and stamps your actor, the time and the
commit):

```bash
CAD_AGENT_ACTOR=<you> cad-agent review-section S1 --submit <your record.json>
```

A sign-off is refused when the geometry changed since this bundle (stale hashes), when you built or wrote
any part of the section (separate review is required), when a
decision is open, when the packet is not current, or when the section's gates do not pass.

## Limits

Renders and gates show the model, not the part: a review does not prove fit, strength or that a
mechanism works. Say what you could not see.
