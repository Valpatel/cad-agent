**Fixed**
- `cadagent.simulation.cfd.read_results`: a fin block's air temperature now has to settle within 1 °C, like every other
  temperature, not 2 °C. `steady` takes its limits from `convergence_limits`, the same numbers the chart's captions
  show (#175).
- `cadagent.simulation.cfd.read_results`: a continuation that stopped before its first temperature sample (within 9
  iterations) now replaces what the solve before it logged after its start. The histories, the headline values and the
  chart stop where it began, and it gets no convergence window, so nothing is judged steady on the solve before (#176).

**Projects must change**
- Cases with an exchanger fin block whose air still moves by 1–2 °C over the window no longer count as `steady` or
  `converged`, and `run_until_balanced` keeps going there. Re-read such results; none of 13 recorded runs flips (#175).
- When the newest solve stopped within 9 iterations, `convergence` is now empty, `convergence_window` is absent and
  `steady` is False. Continue the case to judge it (#176).
