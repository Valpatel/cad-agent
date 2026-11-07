# Command text does not establish process ownership

## Observed control, 2026-11-07 UTC

During #252's maintainer intake of contributor PR #401, the actual original `own_processes` at `a3689473` accepted
the synthetic command `prusa-slicer --description=x--datadir /home/u/work/prusaslicer-datadir`: the folder text was
inside another option's value, not a datadir argument. It also accepted a similarly named `my-prusa-wrapper` and an
unrelated flatpak. These were calls with supplied command text only. No GUI was opened or real process signalled.

The refined existing selector test gives candidate PIDs and separately controlled NUL-delimited argv. Running that
same test body with the immutable original selector rejects its result, while the corrected selector passes.
`test_actual_proc_reader_preserves_space_arguments_and_rejects_missing_bytes` exercises the actual reader against
owned fake proc files, including a datadir containing spaces and a single argument with identical printed text.
The stop controls replace every signal boundary: they check identity changes after opening/before signalling/escalation,
handle closure, and refusal to report an unverifiable running child as closed. They do not send real signals.

## Cause and corrective rule

`ps` renders a command as text and loses argument boundaries. A substring plus a program name containing "prusa"
was insufficient evidence for terminating a process. Treat process-list output only as PID discovery. Read Linux
NUL-delimited argv and start time, require the actual Prusa executable or known Prusa flatpak invocation and one
exact datadir, and revalidate identity immediately before each signal. Use a pidfd so a recycled PID cannot refer
to a different process. Close handles in `finally`; stop reporting success when a known child remains alive.

## Limits

This is controlled selector/shutdown evidence, not a replay of the contributor's reported GUI checks. Generic
`bwrap` processes are deliberately unowned without a proven argv contract. Linux pidfd support is required for
shutdown. The existing opt-in GUI test remains separate; no printer, slicer or desktop interaction was performed
for these controls. See [desktop diagnosis](../../docs/lessons/process/agent-process.md#diagnose-desktop-problems-without-disrupting-the-users-session)
for the separate rule to avoid disrupting the user's applications.
