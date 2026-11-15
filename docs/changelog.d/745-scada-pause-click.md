**Fixed**
- SCADA Explorer: live ticks no longer rewrite unchanged text on Pause/Run and the sound controls, so a click whose press and release straddle a tick keeps its target; WebKit could drop such a click and leave the session running (#745).
- SCADA Explorer browser suite: pausing is verified rather than assumed, and a fake-clock check places a tick inside the Pause click, then proves paused and running session round trips restore exactly, with ticks resuming only after import (#745).
