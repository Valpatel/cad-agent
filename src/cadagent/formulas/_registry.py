"""The formula registry: every public function in ``cadagent.formulas`` declares its units, limits and source here, so
agents can list what exists (:func:`catalogue`) and every number can be traced to a book, a guide or a standard."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Mapping, Sequence, Tuple

# Sources are cited by author, title, edition and section in each function; their text and figures are never copied.
SOURCES: Dict[str, str] = {
    "roark": "W. C. Young, R. G. Budynas and A. M. Sadegh, Roark's Formulas for Stress and Strain, 8th ed., "
             "McGraw-Hill, 2012",
    "shigley": "R. G. Budynas and J. K. Nisbett, Shigley's Mechanical Engineering Design, 10th ed., McGraw-Hill, 2015",
    "covestro": "Covestro LLC, Snap-Fit Joints for Plastics - A Design Guide (the Bayer method)",
    "norton": "R. L. Norton, Design of Machinery, 5th ed., McGraw-Hill, 2012",
    "freudenstein": "F. Freudenstein, Approximate synthesis of four-bar linkages, Transactions of the ASME 77 (1955) "
                    "853-861",
    "gosselin": "C. Gosselin and J. Angeles, Singularity analysis of closed-loop kinematic chains, IEEE Transactions "
                "on Robotics and Automation 6 (1990) 281-290",
    "goncalves": "R. S. Goncalves, J. C. M. Carvalho and R. R. Santos, A multi-objective optimization design for "
                 "parallel structures, Proceedings of COBEM 2009, the 20th International Congress of Mechanical "
                 "Engineering (ABCM, 2009)",
    "incropera": "T. L. Bergman, A. S. Lavine, F. P. Incropera and D. P. DeWitt, Fundamentals of Heat and Mass "
                 "Transfer, 7th ed., Wiley, 2011",
    "white": "F. M. White, Fluid Mechanics, 7th ed., McGraw-Hill, 2011",
    "iso68": "ISO 68-1:1998, ISO general purpose screw threads - Basic profile - Part 1: Metric screw threads",
    "iso898": "ISO 898-1:2013, Mechanical properties of fasteners made of carbon steel and alloy steel - Part 1",
    # Makers' design documents carry a dated edition, not a numbered one.
    "covestro-screws": "Covestro Deutschland AG, Self-tapping screws for thermoplastics, COV00073610, edition "
                       "2016-04",
    "covestro-joining": "Covestro LLC, Engineering Polymers: Joining Techniques - A Design Guide (PDF of 2015-10-30)",
    "bulten": "Bulten AB, DELTA PT: a superior thread-former for plastics, brochure version 250422 (2025-04-22), made "
              "under licence from EJOT",
}


@dataclass(frozen=True)
class Formula:
    """What a function computes, in which units, where it stops being valid, and who published it."""
    name: str
    module: str
    summary: str
    units: Mapping[str, str]
    returns: str
    limits: Tuple[str, ...]
    source: str

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["units"] = dict(self.units)
        d["limits"] = list(self.limits)
        return d


REGISTRY: Dict[str, Formula] = {}


def formula(*, units: Mapping[str, str], returns: str, limits: Sequence[str], source: str) -> Callable:
    """Register a function: ``units`` names every argument's SI unit, ``returns`` the result and its unit, ``limits``
    where the closed form stops being valid, ``source`` the citation (``SOURCES`` key + edition section)."""
    def wrap(fn: Callable) -> Callable:
        if fn.__name__ in REGISTRY:
            raise ValueError(f"formula {fn.__name__} is registered twice")
        if not limits or not source:
            raise ValueError(f"formula {fn.__name__} needs its limits and its source")
        summary = (fn.__doc__ or "").strip().split("\n\n")[0].replace("\n", " ")
        REGISTRY[fn.__name__] = Formula(fn.__name__, fn.__module__, summary, dict(units), returns, tuple(limits), source)
        fn.formula = REGISTRY[fn.__name__]
        return fn
    return wrap


def cite(key: str, where: str) -> str:
    """A citation: the source's full reference and the section, table or equation in it."""
    return f"{SOURCES[key]}, {where}"


def catalogue() -> List[Dict[str, Any]]:
    """Every registered formula as plain data (name, module, summary, units, returns, limits, source)."""
    return [REGISTRY[name].as_dict() for name in sorted(REGISTRY)]
