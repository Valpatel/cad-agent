**Changed**
- Merge gates: a review verdict counts only from a maintainer (`MAINTAINERS` in `tools/ci_gates.py`) who still has
  write access. Write access alone no longer lets a collaborator pass the review gate on their own PR. Collaborators
  push branches and run CI, and a maintainer reviews before anything merges (#111).
