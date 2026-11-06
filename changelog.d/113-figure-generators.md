**Changed**
- Eight repository diagram generators now live under `tools/figures/`, reducing the directly counted tools files from 28 to 20 and retiring that folder's clutter exception. Their published image paths and calculated results are preserved (#113).

**Projects must change**
- Maintainers invoking these repository figure generators must use `tools/figures/<name>.py`; the old top-level script paths are removed. Seven retain `--check`; `snapfit_figures.py` remains regeneration-only (#113).
