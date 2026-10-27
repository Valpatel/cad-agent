"""Dimension-driven fastener envelopes and axial stack checks.

No supplier geometry or nominal dimensions are silently supplied. Threads and
knurls are envelopes, not manufacturing models or proof of pull-out strength.
"""
from cadagent._deps import require


def socket_head_envelope(shaft_diameter, length, head_diameter, head_height):
    """Return a screw along +Z; head bearing plane is Z=0, tip is Z=-length."""
    if min(shaft_diameter, length, head_diameter, head_height) <= 0:
        raise ValueError('Fastener dimensions must be positive')
    if head_diameter <= shaft_diameter:
        raise ValueError('Head must be wider than shaft')
    cq = require('cadquery', 'fastener envelope')
    shaft = cq.Solid.makeCylinder(shaft_diameter / 2, length, cq.Vector(0, 0, -length))
    head = cq.Solid.makeCylinder(head_diameter / 2, head_height)
    return shaft.fuse(head)


def insert_envelope(outer_diameter, thread_diameter, length):
    """Annular heat-set envelope, top at Z=0; knurl interference is intentional."""
    if not outer_diameter > thread_diameter > 0 or length <= 0:
        raise ValueError('Require outer > thread > 0 and positive length')
    cq = require('cadquery', 'insert envelope')
    start = cq.Vector(0, 0, -length)
    return cq.Solid.makeCylinder(outer_diameter / 2, length, start).cut(
        cq.Solid.makeCylinder(thread_diameter / 2, length, start))


def blind_insert_stack(*, head_seat, screw_length, insert_top, insert_length, hole_bottom):
    """Measure axial overlap and bottom clearance in a shared Z datum.

    Positive overlap alone is not sufficient thread engagement for a load.
    Caller sets minimum engagement and checks tolerances/material separately.
    """
    if screw_length <= 0 or insert_length <= 0:
        raise ValueError('Lengths must be positive')
    bottom = insert_top - insert_length
    if hole_bottom > bottom or head_seat < insert_top:
        raise ValueError('Invalid blind-insert stack order')
    tip = head_seat - screw_length
    return {'tip_z_mm': round(tip, 6),
            'engagement_mm': round(max(0, min(head_seat, insert_top) - max(tip, bottom)), 6),
            'tip_clearance_mm': round(tip - hole_bottom, 6),
            'insert_bottom_clearance_mm': round(tip - bottom, 6)}
