**Fixed**
- Replay viewer: Pause holds in WebKit (Safari). The Play/Pause button's text was rewritten on every frame while playing, and WebKit drops a click whose pressed text node was replaced before the release; the button now changes only when the state does (#809).
- Gyropup replay: the landing scenario shows its recorded largest lean, 0.04°, instead of "0.0°"; every lean is shown to the two decimals Gyropup's summary records, and a run whose summary has none shows none. The receipt states how each shown figure is taken from the summary (#809).

**Changed**
- Replay viewer: Fit frames the points the robot's bodies reach rather than the corners of one box around the whole run, so the subject fills more of an oblique view; the two-link arm's thumbnail and the Gyropup cards are recaptured (#809).
- Gyropup replay: the camera follows the robot in every run that travels more than 0.1 m from its start, so the push run now follows its base like the kerb runs and the robot fills a phone's view in all four scenarios; the landing stays framed whole (#809).
- The home and toolkit "Robot simulation replay" cards carry one recorded figure, generated from the replay index for the run they play: the snapshot's verdict and its highest motor torque as a share of that motor's peak-torque limit (#809).
