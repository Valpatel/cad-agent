"""Check the two printed parts in the same assembly positions used for the STEP files."""
from cadagent.review.dossier import current_registry, not_drawn

from build import box_height, make_box, make_lid

registry = current_registry()
registry.add_part("box", make_box, grounded=True)
registry.add_part("lid", make_lid)
registry.joint("lid-seat", "fixed", parts=("lid", "box"), axis=((0, 0, box_height), (0, 0, 1)))

not_drawn("lid-screws", reason="The four lid screws are sized in cad/build.py and have no solids.",
          near=("lid", "box"))
not_drawn("threaded-inserts", reason="The four heat-set inserts are specified in cad/build.py and have no solids.",
          near="box")
