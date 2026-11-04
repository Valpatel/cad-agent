**Changed**
- The README hero holds its finished frame (wordmark and every check) for about 4 s before it fades and the loop
  restarts, up from 1.4 s; its cycle is 13.2 s (#339).
- `cadagent.publish.anim.svg.problems` refuses an animation that plays once and stops: every animated figure must
  loop, so a reader who scrolls to it late still sees it play (`svg.timed` lists the ones that do not) (#339).
