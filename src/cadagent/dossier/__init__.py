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

# the build-script registry (docs/dossier.md "Declaring geometry in the build script")
from .registry import (  # noqa: E402
    HASH_RECIPE, REGISTRY, Axis, BuildResult, Registry, RegistryError, assembly, brep_sha256, build, build_module,
    cavity, current_registry, fastener, join, joint, load_geometry, part, project_root, shape_sha256, use_registry,
)
from ..evidence import shape_content_hash  # noqa: E402

__all__ += [
    "HASH_RECIPE", "REGISTRY", "Axis", "BuildResult", "Registry", "RegistryError", "assembly", "brep_sha256", "build",
    "build_module", "cavity", "current_registry", "fastener", "join", "joint", "load_geometry", "part",
    "project_root", "shape_content_hash", "shape_sha256", "use_registry",
]
