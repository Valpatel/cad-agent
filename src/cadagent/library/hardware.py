"""Standard mechanical hardware, by its dimension tables: the screws, nuts and lugs the library's 3D bodies are built
from, and the place other hardware families plug in.

Each table maps a thread size to its nominal dimensions (mm) and names its source. The socket-head (ISO 4762) and
button-head (ISO 7380-1) rows are the ones the vendored ``bd_warehouse`` (Apache-2.0) ships in its
``socket_head_cap_parameters.csv`` and ``button_head_parameters.csv``, and ``tests/library`` checks them against those
files row by row. ``bd_warehouse`` has no prevailing-torque (nyloc) nut table: those rows are DIN 985's nominal
heights and widths across flats, marked ``verified: False`` until a vendor's specification table confirms them
(``cad-agent mcmaster`` reads one). Ring lugs vary by maker: the row is an envelope (ring only) for a typical
tin-plated copper ring terminal, not a part number.

The bodies built from these are envelopes for pictures, clearance and layout. For a real part number and its
manufacturer model, use the ``mcmaster-parts`` skill (``cad-agent mcmaster``) and keep that model local.

**Washers and the heads' bearing faces** (#292), for the bearing pressure a screw puts on printed plastic: ISO 7089
plain, ISO 7090 chamfered and ISO 7093-1 large washers, whose hole ``d1``, outside ``d2`` and thickness ``h`` are the
columns ``bd_warehouse`` ships in ``plain_washer_parameters.csv`` and ``chamfered_washer_parameters.csv`` (``d1`` its
least, ``d2`` and ``h`` their largest), checked row by row as the heads are; and the largest hole ``d1_max``, least
outside ``d2_min`` and thinnest ``h_min``, from the standards' tolerances, which the bearing checks use as the
cautious side. The heads'
bearing faces are not in ``bd_warehouse``: ``dw`` is the least diameter a head bears on (ISO 4762's and ISO 7380-1's
dw min; ISO 14580 and ISO 1207 give none, so their head's least outside dk min stands in) and ``da`` the largest
diameter of the fillet under the head, each by standard and table. **Adopt or build:** ``bd_warehouse``'s washer
tables are adopted as they are, and its M2.5 row of ISO 7093 is left out (ISO 7093-1 starts at M3); the bearing
faces are built here because no vendored table has them.

Other families register here with :func:`register`. Self-clinching (PEM-type) nuts, studs and standoffs and blind
rivets come from #283's catalogue: it adds its own table with ``register('clinch_nut', ...)`` and so on, and a footprint
or body generator reads it with :func:`table`, so the two efforts share one place without one owning the other.
"""
from __future__ import annotations

from typing import Dict

# thread: dk head diameter, k head height, s hex socket size (ISO 4762; bd_warehouse socket_head_cap_parameters.csv)
SOCKET_HEAD = {
    'source': 'ISO 4762, as tabulated in bd_warehouse data/socket_head_cap_parameters.csv', 'verified': True,
    'rows': {'M2': {'dk': 3.98, 'k': 2.0, 's': 1.5}, 'M2.5': {'dk': 4.68, 'k': 2.5, 's': 2.0},
             'M3': {'dk': 5.68, 'k': 3.0, 's': 2.5},
             'M4': {'dk': 7.22, 'k': 4.0, 's': 3.0}, 'M5': {'dk': 8.72, 'k': 5.0, 's': 4.0},
             'M6': {'dk': 10.22, 'k': 6.0, 's': 5.0}},
}
# thread: dk head diameter, k head height, s hex socket size (ISO 7380-1; bd_warehouse button_head_parameters.csv)
BUTTON_HEAD = {
    'source': 'ISO 7380-1, as tabulated in bd_warehouse data/button_head_parameters.csv', 'verified': True,
    'rows': {'M3': {'dk': 5.7, 'k': 1.65, 's': 2.08},
             'M4': {'dk': 7.6, 'k': 2.2, 's': 2.58}, 'M5': {'dk': 9.5, 'k': 2.75, 's': 3.08},
             'M6': {'dk': 10.5, 'k': 3.3, 's': 4.095}},
}
# thread: m height, s width across flats (DIN 985 nominal; not yet checked against a vendor table)
NYLOC_NUT = {
    'source': 'DIN 985 nominal (unverified: check against a vendor specification table)', 'verified': False,
    'rows': {'M4': {'m': 5.0, 's': 7.0}, 'M5': {'m': 5.0, 's': 8.0}, 'M6': {'m': 6.0, 's': 10.0}},
}
# thread: ring outer diameter, thickness (an envelope of a typical tin-plated copper ring terminal; ring only)
RING_LUG = {
    'source': 'envelope of a typical tin-plated copper ring terminal (no part number; ring only, no tongue)',
    'verified': False,
    'rows': {'M4': {'od': 8.0, 't': 1.0}, 'M5': {'od': 9.5, 't': 1.0}, 'M6': {'od': 12.0, 't': 1.2}},
}

# Washers, by thread: d1 the hole (its least), d2 the outside and h the thickness (their largest), as bd_warehouse
# tabulates them; d1_max the hole's largest (ISO 286 H13 on d1), d2_min the outside's least (ISO 286 h14 on d2), as
# ISO 7089 and ISO 7093-1 give them, and h_min the thinnest (the standard's thickness tolerance). Steel of hardness
# class 200 HV, the standards' first grade.
_WASHER_NOTE = ('; d1_max, d2_min and h_min from the standard\'s tolerances (d1 to H13, d2 to h14; h to its own +/- '
                'band); hardness class 200 HV steel')
PLAIN_WASHER = {
    'source': 'ISO 7089:2000 (plain washers, normal series, product grade A), Table 1, as tabulated in bd_warehouse '
              'data/plain_washer_parameters.csv (iso7089 columns)' + _WASHER_NOTE,
    'verified': True, 'standard': 'ISO 7089', 'hardness_hv': 200,
    'rows': {'M2': {'d1': 2.2, 'd1_max': 2.34, 'd2': 5.0, 'h': 0.35, 'd2_min': 4.7, 'h_min': 0.25},
             'M2.5': {'d1': 2.7, 'd1_max': 2.84, 'd2': 6.0, 'h': 0.55, 'd2_min': 5.7, 'h_min': 0.45},
             'M3': {'d1': 3.2, 'd1_max': 3.38, 'd2': 7.0, 'h': 0.55, 'd2_min': 6.64, 'h_min': 0.45},
             'M4': {'d1': 4.3, 'd1_max': 4.48, 'd2': 9.0, 'h': 0.9, 'd2_min': 8.64, 'h_min': 0.7},
             'M5': {'d1': 5.3, 'd1_max': 5.48, 'd2': 10.0, 'h': 1.1, 'd2_min': 9.64, 'h_min': 0.9},
             'M6': {'d1': 6.4, 'd1_max': 6.62, 'd2': 12.0, 'h': 1.8, 'd2_min': 11.57, 'h_min': 1.4}},
}
CHAMFERED_WASHER = {
    'source': 'ISO 7090:2000 (plain washers, chamfered, normal series, product grade A; from 5 mm), Table 1, as '
              'tabulated in bd_warehouse data/chamfered_washer_parameters.csv (iso7090 columns); the flat face, the '
              'one that bears, as ISO 7089\'s' + _WASHER_NOTE,
    'verified': True, 'standard': 'ISO 7090', 'hardness_hv': 200,
    'rows': {'M5': {'d1': 5.3, 'd1_max': 5.48, 'd2': 10.0, 'h': 1.1, 'd2_min': 9.64, 'h_min': 0.9},
             'M6': {'d1': 6.4, 'd1_max': 6.62, 'd2': 12.0, 'h': 1.8, 'd2_min': 11.57, 'h_min': 1.4}},
}
LARGE_WASHER = {
    'source': 'ISO 7093-1:2000 (plain washers, large series, product grade A), Table 1, as tabulated in bd_warehouse '
              'data/plain_washer_parameters.csv (iso7093 columns; its M2.5 row is left out: ISO 7093-1 starts at '
              'M3)' + _WASHER_NOTE,
    'verified': True, 'standard': 'ISO 7093-1', 'hardness_hv': 200,
    'rows': {'M3': {'d1': 3.2, 'd1_max': 3.38, 'd2': 9.0, 'h': 0.9, 'd2_min': 8.64, 'h_min': 0.7},
             'M4': {'d1': 4.3, 'd1_max': 4.48, 'd2': 12.0, 'h': 1.1, 'd2_min': 11.57, 'h_min': 0.9},
             'M5': {'d1': 5.3, 'd1_max': 5.48, 'd2': 15.0, 'h': 1.4, 'd2_min': 14.57, 'h_min': 1.0},
             'M6': {'d1': 6.4, 'd1_max': 6.62, 'd2': 18.0, 'h': 1.8, 'd2_min': 17.57, 'h_min': 1.4}},
}
# The heads' bearing faces, by thread: dw the least diameter the head bears on, da the fillet under it (its largest).
SOCKET_HEAD_BEARING = {
    'source': 'ISO 4762:2004 (hexagon socket head cap screws), Table 1: dw min and da max; M4-M8 dw also in Bossard, '
              'Surface pressure when mounted (01-2025), p. 55',
    'verified': True, 'standard': 'ISO 4762', 'stands_in': False,
    'rows': {'M2': {'dw': 3.48, 'da': 2.6}, 'M2.5': {'dw': 4.18, 'da': 3.1}, 'M3': {'dw': 5.07, 'da': 3.6},
             'M4': {'dw': 6.53, 'da': 4.7}, 'M5': {'dw': 8.03, 'da': 5.7}, 'M6': {'dw': 9.38, 'da': 6.8},
             'M8': {'dw': 12.33, 'da': 9.2}},
}
BUTTON_HEAD_BEARING = {
    'source': 'ISO 7380-1:2011 (hexagon socket button head screws, M3 to M16), Table 1: dw min and da max',
    'verified': True, 'standard': 'ISO 7380-1', 'stands_in': False,
    'rows': {'M3': {'dw': 5.0, 'da': 3.6}, 'M4': {'dw': 6.84, 'da': 4.7}, 'M5': {'dw': 8.74, 'da': 5.7},
             'M6': {'dw': 9.57, 'da': 6.8}},
}
CHEESE_HEAD_BEARING = {
    'source': 'ISO 14580:2011 (hexalobular socket cheese head screws) and ISO 1207:2011 (slotted cheese head screws), '
              'Table 1: no dw is given, so dk min (the head\'s least outside) stands in for it; da max',
    'verified': True, 'standard': 'ISO 14580 / ISO 1207', 'stands_in': True,
    'rows': {'M2': {'dw': 3.62, 'da': 2.6}, 'M2.5': {'dw': 4.32, 'da': 3.1}, 'M3': {'dw': 5.32, 'da': 3.6},
             'M4': {'dw': 6.78, 'da': 4.7}, 'M5': {'dw': 8.28, 'da': 5.7}, 'M6': {'dw': 9.78, 'da': 6.8}},
}

_TABLES: Dict[str, dict] = {'socket_head': SOCKET_HEAD, 'button_head': BUTTON_HEAD, 'nyloc_nut': NYLOC_NUT,
                            'ring_lug': RING_LUG, 'plain_washer': PLAIN_WASHER,
                            'chamfered_washer': CHAMFERED_WASHER, 'large_washer': LARGE_WASHER,
                            'socket_head_bearing': SOCKET_HEAD_BEARING, 'button_head_bearing': BUTTON_HEAD_BEARING,
                            'cheese_head_bearing': CHEESE_HEAD_BEARING}
# the washers and heads by the name a joint gives them (cadagent.mechanical.inserts)
WASHERS = {'iso7089': 'plain_washer', 'iso7090': 'chamfered_washer', 'iso7093': 'large_washer'}
HEADS = {'socket': 'socket_head_bearing', 'button': 'button_head_bearing', 'cheese': 'cheese_head_bearing'}


def register(kind: str, rows: Dict[str, dict], source: str, verified: bool = False) -> None:
    """Add a hardware family (``kind``: its table's name) with its rows by size and its source. A kind is
    registered once: a second table under the same name is a ``ValueError``, so two efforts cannot overwrite each
    other's numbers without one of them noticing."""
    if not kind or not isinstance(rows, dict) or not rows or not source:
        raise ValueError('register needs a kind, rows by size and a source')
    if kind in _TABLES:
        raise ValueError(f'hardware kind {kind!r} is already registered (from {_TABLES[kind]["source"]})')
    _TABLES[kind] = {'source': source, 'verified': bool(verified), 'rows': dict(rows)}


def table(kind: str) -> dict:
    """The table of ``kind``: ``{'source', 'verified', 'rows'}``."""
    if kind not in _TABLES:
        raise KeyError(f'no hardware kind {kind!r}; registered: {", ".join(sorted(_TABLES))}')
    return _TABLES[kind]


def row(kind: str, size: str) -> dict:
    t = table(kind)
    if size not in t['rows']:
        raise KeyError(f'{kind} has no {size}; sizes: {", ".join(sorted(t["rows"]))}')
    return t['rows'][size]


def kinds() -> list:
    return sorted(_TABLES)
