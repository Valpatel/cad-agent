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

Other families register here with :func:`register`. Self-clinching (PEM-type) nuts, studs and standoffs and blind
rivets come from #283's catalogue: it adds its own table with ``register('clinch_nut', ...)`` and so on, and a footprint
or body generator reads it with :func:`table`, so the two efforts share one place without one owning the other.
"""
from __future__ import annotations

from typing import Dict

# thread: dk head diameter, k head height, s hex socket size (ISO 4762; bd_warehouse socket_head_cap_parameters.csv)
SOCKET_HEAD = {
    'source': 'ISO 4762, as tabulated in bd_warehouse data/socket_head_cap_parameters.csv', 'verified': True,
    'rows': {'M4': {'dk': 7.22, 'k': 4.0, 's': 3.0}, 'M5': {'dk': 8.72, 'k': 5.0, 's': 4.0},
             'M6': {'dk': 10.22, 'k': 6.0, 's': 5.0}},
}
# thread: dk head diameter, k head height, s hex socket size (ISO 7380-1; bd_warehouse button_head_parameters.csv)
BUTTON_HEAD = {
    'source': 'ISO 7380-1, as tabulated in bd_warehouse data/button_head_parameters.csv', 'verified': True,
    'rows': {'M4': {'dk': 7.6, 'k': 2.2, 's': 2.58}, 'M5': {'dk': 9.5, 'k': 2.75, 's': 3.08},
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

_TABLES: Dict[str, dict] = {'socket_head': SOCKET_HEAD, 'button_head': BUTTON_HEAD, 'nyloc_nut': NYLOC_NUT,
                            'ring_lug': RING_LUG}


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
