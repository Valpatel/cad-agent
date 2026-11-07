# A cancelled full check needs the active test and its stack

- **Rule:** Preserve the actual job annotation and last test progress before classifying a cancelled check.
  Report test identities while the full suite runs, and use pytest's existing thread-dump option to observe a slow
  test without changing its assertions, selection, dependencies or the job's hard time limit. A thread dump is
  diagnostic output, not a new test deadline or evidence that a native library caused the stall.
- **Observed, 2026-11-07:** PR #465 source `6a5145f1`, CI run 42403450255/job 128496027486, installed its full extras
  successfully. `python -m pytest -q -rs` started 18:54:11 UTC, last printed 97% at 19:04:13 UTC and remained silent
  until 19:23:07 UTC. The check annotation says: `The job has exceeded the maximum execution time of 30m0s`.
  The job/run concluded cancelled. There was no assertion traceback, exact active test or superseding CI run;
  the test and cause remain unknown. Later wheel/floor steps did not run.
- **Comparison:** The separate main `81b9fdc2` full run 42402863701/job 128494211534 passed 3577 tests with 24 skips in 671.27s.
  That successful run does not identify why source `6a5145f1` exceeded its cap.
- **Correction:** The full job reports unbuffered verbose test node IDs and enables the built-in
  `faulthandler_timeout=120` diagnostic. The same complete suite and 30-minute job cap remain; this does not
  skip a slow test, add a dependency, increase a resource bound or establish that the earlier problem is fixed.
- **Evidence:** [Failed full job](https://github.com/Valpatel/cad-agent/actions/runs/42403450255/job/128496027486),
  [independent cancellation classification](https://github.com/Valpatel/cad-agent/pull/465#issuecomment-6711955442),
  [successful comparison](https://github.com/Valpatel/cad-agent/actions/runs/42402863701/job/128494211534),
  [pytest fault-handler contract](https://docs.pytest.org/en/stable/how-to/failures.html#fault-handler).
- **Limits:** A future quiet or successful run cannot supply the missing historical test identity or cause.
  The new full head must actually complete all required checks before integration; this note is not a CI waiver.

The first local layout/release check of the added note retained 67 passes and two layout failures: the incident
inbox had reached 21 direct files against its 20-file growth bound. The note moved into the existing publication
incident folder, with its map and symptom link updated; the growth check and exception list remain unchanged.
