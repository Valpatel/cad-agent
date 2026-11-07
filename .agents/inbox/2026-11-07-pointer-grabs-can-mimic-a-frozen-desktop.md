# A persistent application pointer grab can mimic a frozen desktop

## Observed on 2026-11-07 UTC

The display and pointer moved, but clicks did not reach other applications. Resource samples showed about 40 GiB
available memory, 79–91% CPU idle, zero sampled swap I/O and memory pressure `avg10=0.00`; no recent kernel GPU
fault was observed. Device/button mapping was normal and physical button press/release events arrived. Those
observations did not establish a resource shortage or a persistently stuck button.

The coordinator retained this redacted command/output receipt:

```text
DISPLAY=:1 xdotool key XF86LogGrabInfo
Active grab 0x4000000 (xi2) on device 'Virtual core pointer' (2):
client pid 1753582 /snap/bambu-studio/8/opt/bambu-studio/bin/bambu-studio <private project path redacted>
at 284565897 (from active grab) (device thawed, state 1)
owner-events true, kb 1 ptr 1, confine 0, cursor 0x0
```

The user explicitly requested termination of Bambu Studio. The coordinator opened a pidfd for that PID, verified
the executable as Bambu Studio and `comm=bambustu_main`, and sent SIGTERM through `signal.pidfd_send_signal`.
Poll observed exit within the initial three-second bound; no SIGKILL was sent. A fresh Xorg grab diagnostic no
longer showed Bambu's grab. The user confirmed: “Great, fixed.” No other application or desktop session was killed
or restarted, and no printer connection or action occurred.

## Why broad resource checks were insufficient

Healthy CPU/memory and a moving pointer do not show which client owns mouse input. The application's persistent
XI2 grab explains why other applications did not receive the observed clicks. This repeats the Bambu grab class
already recorded in [the desktop diagnosis lesson](../../docs/lessons/process/agent-process.md#diagnose-desktop-problems-without-disrupting-the-users-session).

## Corrective rule and limits

Inspect input events and active grabs before treating blocked clicks as a system-wide freeze. Diagnose without
logging out or restarting the session. Obtain explicit permission before terminating an application; bind any
authorized signal to the verified process identity and confirm the resulting state. A transient ordinary grab is
not itself an application defect. User-requested termination does not prove an unsaved project was preserved.
This is an observed recovery receipt, not a reason to launch a GUI or encode an automatic process-killing test.
