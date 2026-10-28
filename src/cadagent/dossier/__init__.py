"""The design dossier: requirements, sections, part spec cards, interfaces, decisions and assembly steps, declared
beside the CAD so the gates and the review site can check them (``docs/dossier.md``)."""

from .load import DossierError, dump_yaml, load_dossier, load_project_dossier
from .model import (
    Alternative, AssemblyStep, Containment, Decision, Dossier, FastenerUse, FreePart, GateConfig, Interface, Issue,
    Material, PairExemption, PartCard, Requirement, Section, Source, Where,
)

__all__ = [
    "Alternative", "AssemblyStep", "Containment", "Decision", "Dossier", "DossierError", "FastenerUse", "FreePart",
    "GateConfig", "Interface", "Issue", "Material", "PairExemption", "PartCard", "Requirement", "Section", "Source",
    "Where", "dump_yaml", "load_dossier", "load_project_dossier",
]
