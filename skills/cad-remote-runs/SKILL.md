---
name: cad-remote-runs
description: Use before starting any CAD/FEA/CFD/topology run or full pipeline that takes more than a few minutes or several GB of memory. Run it on a compute host instead of the workstation the agents share, detached so it survives the session, recorded in the GitHub issue (host, command, log, done marker, how to collect results) so any machine can pick it up, and its results pulled back and committed.
---

# Long runs on a compute host

Heavy runs (OpenFOAM CFD, FEA sweeps, topology optimisation, `cad-agent all`) on the workstation the agents share
can exhaust its memory and crash every session on it. Run them on a compute host, detached, and write them down
where another computer can find them.

```mermaid
flowchart TD
    B["before: a host by need,<br/>code from git,<br/>its own env"] --> S["start detached, then<br/>record it in the issue:<br/>host, command, log,<br/>done marker"]
    S --> W["while it runs:<br/>checkpoints; any<br/>machine can check it"]
    W --> A["after: check the result,<br/>pull it back, commit,<br/>update the issue"]
    class S,W here
    class B near
    class A out
```

## Before the run

- **Pick the host by need**: cores and memory for the solver, a GPU only if the tool uses one, Docker for OpenFOAM.
  Check its load first (`uptime`, `free -g`); other people's jobs may be running there.
- **Give it the code from git**, not a hand copy, where possible: clone the repo there and `git fetch && git checkout
  <sha>` of your pushed branch. If you must copy a working tree (uncommitted changes, large untracked references),
  use `rsync -a` with excludes for virtualenvs, caches and run folders. Pull back anything the host produced before
  you copy to it again. Use `--delete` only right after such a pull (it removes remote files that are not in your
  copy, including results newer than it); without it, files you deleted locally stay on the host.
- **Give it its own environment** (a virtualenv from the project's pinned requirements, `pip install -e` of the
  cad-agent checkout or version the project uses). Record which cad-agent commit it runs.

  <details>
  <summary>FEA on an aarch64 host: gmsh from conda-forge</summary>

  PyPI has no aarch64 Linux wheel for gmsh (4.15.2 or any other release), so the `fea` extra does not install
  there; nor does pypardiso, whose MKL is x86-64 only. Install `cad-agent[cad]` with `scikit-fem pyamg`, then link
  conda-forge's gmsh into the venv:

      micromamba create -y -p <gmsh-env> -c conda-forge python-gmsh=4.15.2
      ln -s <gmsh-env>/lib/python3.*/site-packages/gmsh.py <venv site-packages>/

  If `import gmsh` then fails because version `OPENSSL_3.4.0` is not found (the venv's Python loaded the system
  OpenSSL first), start the run with `LD_PRELOAD=<gmsh-env>/lib/libcrypto.so.3:<gmsh-env>/lib/libssl.so.3`. Record
  which gmsh build the run used (`micromamba list -p <gmsh-env> gmsh`): two builds of one version can mesh a part
  differently, and the newest 4.15.2 build links a newer OCCT (8.0.1) than cadquery-ocp's (7.9.3). The FEA section
  of `docs/toolkit.md` in cad-agent has the details.
  </details>

## Starting it

Detach it from the ssh session and the agent, and make the log say when it is done:

```bash
ssh <host> 'cd <repo> && mkdir -p build && (setsid nohup nice -n 5 bash -c "<command> > build/<run>.log 2>&1; echo RUN-DONE rc=\$? >> build/<run>.log" < /dev/null > /dev/null 2>&1 &)'
```

Then **record it in the issue** right away (see `cad-work-tracking`):
`<host role>: <command> (commit <sha>), log <path>, done when "RUN-DONE", results in <paths>, collect with <command>`.

```mermaid
flowchart TD
    R["the run, detached<br/>setsid nohup nice"] -->|"stdout and stderr"| L["build/run.log<br/>on the host"]
    L -->|"its last line"| D["RUN-DONE rc=N"]
    I["the issue: host role,<br/>command, commit, log,<br/>how to collect"] -.->|"any machine<br/>checks"| L
    class R,L here
    class D near
    class I out
```

## While it runs

- Watch it from the agent with a poll every few minutes (`ssh <host> 'tail -n 3 <log>'`) or the harness's monitor;
  match the failure markers too (`Traceback`, `Error`, `Killed`, `FAIL`, non-zero `rc=`), not only success.
- When watching processes over ssh, anchor patterns so they do not match the ssh command line itself
  (`ps -eo pid,args | grep "^ *[0-9]* <exact command>"`, or the `[x]` bracket trick). Stop jobs by PID or process
  group, never with a broad `pkill -f`.
- A finding that changes the inputs (a wrong assumption, a geometry fix) means stop the run, fix, push, restart, and
  note the stopped run in the issue so nobody collects its stale results.

## After it

- Check the result before trusting it: converged and steady, balances closed, the inputs it used are the committed
  ones (hashes or revision recorded in the result file).
- Pull the results back (`rsync -a <host>:<repo>/<result paths> <local paths>`), commit them with the command that
  made them in the message, push, and tick the issue.
- Leave the host clean: stop containers you started, delete large scratch case folders you no longer need.
