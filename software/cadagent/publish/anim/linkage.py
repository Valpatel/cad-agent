"""Planar linkage poses for the animated figures. The solver moved to ``cadagent.mechanical.linkages`` (#187), where
the closed-loop sweeps live too; this module keeps the old import working for the figures that use it."""
from cadagent.mechanical.linkages import Linkage, circles, ellipse_path

__all__ = ["Linkage", "circles", "ellipse_path"]
