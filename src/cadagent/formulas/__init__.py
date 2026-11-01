"""Closed-form engineering equations for 3D-printed mechanisms, each with its SI units, validity limits and source.

    from cadagent import formulas as fx
    fx.snap_arm(length=0.020, thickness=0.0016, width=0.006, deflection=0.0012, modulus=1.46e9,
                allowable_strain=0.023)                     # root strain, force, stiffness, pass/fail
    fx.spring_rate(wire_diameter=0.8e-3, mean_diameter=6e-3, active_coils=8, shear_modulus=79.3e9)
    fx.preload_from_torque(torque=0.6, diameter=3e-3)       # N, with the nut factor 0.2
    fx.catalogue()                                          # every formula: units, limits, source

Agents call these instead of re-deriving them; the website's demonstrations call the browser port of the same
functions (``webkit/formulas.js``), and ``tools/formula_vectors.py --check`` keeps the two in step. A closed form is
not proof of fit or strength: each result holds only within the limits it states, and a printed part is weaker
across its layers than any isotropic formula assumes. Test the part. See docs/formulas.md.
"""
from cadagent.formulas._registry import REGISTRY, SOURCES, Formula, catalogue
from cadagent.formulas.beams import (DESIGNS, SUPPORTS, beam_stiffness, cantilever_shape, cantilever_strain_profile,
                                     cantilever_taper_factor, cantilever_thickness_profile, cantilever_tip_deflection,
                                     rect_second_moment, snap_arm, snap_deflection_force, snap_root_strain)
from cadagent.formulas.linkages import (fivebar_inputs, fivebar_jacobians, fivebar_point, fourbar_angles,
                                        fourbar_input_limits, grashof, transmission_angle)
from cadagent.formulas.screws import (NUT_FACTORS, nut_factor, preload_from_torque, tensile_stress_area,
                                      thread_shear_areas, thread_strip_force, torque_for_preload)
from cadagent.formulas.springs import bergstrasser_factor, spring_index, spring_rate, spring_shear_stress
from cadagent.formulas.thermal import (fan_curve_line, fan_operating_point, fan_stall_flow, fans_in_parallel,
                                       fans_in_series, film_resistance, system_coefficient, wall_heat_flow,
                                       wall_resistance)
from cadagent.formulas.torsion import (shear_modulus, torsion_bar_stiffness, torsion_bar_twist,
                                       torsion_constant_rect, torsion_constant_round, torsion_shear_stress_rect,
                                       torsion_shear_stress_round)

__all__ = sorted(REGISTRY) + ["DESIGNS", "NUT_FACTORS", "REGISTRY", "SOURCES", "SUPPORTS", "Formula", "catalogue"]
