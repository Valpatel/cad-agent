"""Plate-fin heatsinks: thermal resistance, pressure drop, fan operating point, and the porous-zone coefficients that
stand in for the fins in an enclosure CFD model (cadagent.cfd).

    from cadagent.heatsink import PlateFin, FanCurve, operating_point
    hs = PlateFin(length=87, width=100, fin_height=14, fin_thickness=0.3, pitch=1.8, base_thickness=3.5,
                  k_fin=200, k_base=1500, flow_length=43.5, source=(40, 40))
    fan = FanCurve(dp0_pa=15.2, q_free_m3h=38.9)
    op = operating_point(hs, fan)            # flow, pressure, velocity in the channels
    r = hs.resistance(op['q_m3s'])           # K/W from the base (under the heat source) to the inlet air

Models (all from the open literature, cited in the result):
- Channel flow between fins, developing laminar flow, as a composite of the developing and fully developed limits:
  heat transfer after Teertstra, Yovanovich & Culham (1999), apparent friction after Muzychka & Yovanovich (2004),
  with entrance and exit losses (Kays & London contraction / expansion coefficients).
- Fin efficiency of a straight rectangular fin with an adiabatic tip (corrected length).
- Spreading resistance of a centred rectangular source on a finite base (Song, Lee & Au 1994, closed form for an
  equivalent circular source).
- A fan blowing down into the middle of the fins (``flow_length`` = half the fin length when the air leaves at both
  ends) is treated as two channels of that length in parallel; the turn from the fan into the channels is one extra
  velocity head. That is an engineering approximation, good for comparing designs, to calibrate against a test.
- The thermal resistance is referenced to the inlet air (Teertstra's h already includes the air heating along the
  channels), so it never falls below 1 / (m cp), the air's own limit, reported as ``air_limit``.

Units: mm for geometry in, SI inside, K/W, Pa, m3/s out.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Optional, Sequence, Tuple

AIR = {'rho': 1.16, 'mu': 1.86e-5, 'k': 0.0263, 'cp': 1007.0, 'pr': 0.71}   # at about 30 °C

SOURCES = [
    'Teertstra, Yovanovich, Culham, "Analytical forced convection modeling of plate fin heat sinks", SEMI-THERM 1999',
    'Muzychka, Yovanovich, "Pressure drop in laminar developing flow in noncircular ducts", J. Fluids Eng. 2009 / ASME 2004',
    'Song, Lee, Au, "Closed-form equation for thermal constriction/spreading resistances with variable resistance boundary condition", IEPS 1994',
    'Kays & London, Compact Heat Exchangers (entrance/exit loss coefficients)',
]


@dataclass
class FanCurve:
    """A straight-line fan curve between the free-air flow and the zero-flow pressure (datasheet end points)."""
    dp0_pa: float
    q_free_m3h: float

    def dp(self, q_m3s: float) -> float:
        return max(0.0, self.dp0_pa * (1 - q_m3s * 3600 / self.q_free_m3h))


@dataclass
class PlateFin:
    length: float            # along the channels (mm)
    width: float             # across the fins (mm)
    fin_height: float        # mm
    fin_thickness: float     # mm
    pitch: float             # fin centre to centre (mm)
    base_thickness: float    # mm
    k_fin: float = 200.0     # W/mK
    k_base: float = 390.0    # W/mK (effective, with heat pipes)
    flow_length: Optional[float] = None   # mm the air travels between fins (default: length)
    branches: int = 1        # parallel flow paths (2 when a fan blows into the middle and the air leaves at both ends)
    source: Tuple[float, float] = (40.0, 40.0)   # heat source footprint on the base (mm)
    turn_loss: float = 1.0   # velocity heads lost turning from an impinging fan into the channels
    air: dict = field(default_factory=lambda: dict(AIR))

    # --- geometry
    @property
    def n_fins(self) -> int:
        return max(2, int(math.floor((self.width - self.fin_thickness) / self.pitch)) + 1)

    @property
    def gap(self) -> float:      # mm between fins
        return self.pitch - self.fin_thickness

    @property
    def porosity(self) -> float:
        return self.gap / self.pitch

    def _flow_area(self) -> float:   # m2, all channels of one branch
        return (self.n_fins - 1) * self.gap * self.fin_height * 1e-6

    def channel_velocity(self, q_m3s: float) -> float:
        return q_m3s / self.branches / self._flow_area()

    # --- flow
    def pressure_drop(self, q_m3s: float, core_only: bool = False) -> float:
        """Static pressure drop (Pa) at total flow q through the fins (all branches). ``core_only``: channel friction
        alone, without the entrance, exit and turn losses (what a CFD porous block should carry when the CFD resolves
        the block's faces and the fan jet itself)."""
        a = self.air
        L = (self.flow_length or self.length) / 1000
        b = self.gap / 1000
        Dh = 2 * b                                   # parallel plates
        U = self.channel_velocity(q_m3s)
        if U <= 0:
            return 0.0
        Re = a['rho'] * U * Dh / a['mu']
        Ls = L / (Dh * Re)
        fRe = math.sqrt((3.44 / math.sqrt(Ls)) ** 2 + 24.0 ** 2)   # Fanning, apparent, parallel plates
        f = fRe / Re
        sigma = self.porosity
        Kc = 0.42 * (1 - sigma ** 2)                  # sudden contraction
        Ke = (1 - sigma) ** 2                         # sudden expansion
        q = 0.5 * a['rho'] * U ** 2
        if core_only:
            return 4 * f * L / Dh * q
        return (4 * f * L / Dh + Kc + Ke + self.turn_loss) * q

    # --- heat
    def h(self, q_m3s: float) -> float:
        """Mean heat transfer coefficient on the fins (W/m2K), developing laminar channel flow (Teertstra 1999)."""
        a = self.air
        L = (self.flow_length or self.length) / 1000
        b = self.gap / 1000
        U = self.channel_velocity(q_m3s)
        Re_b = a['rho'] * U * b / a['mu'] * (b / L)   # channel Reynolds number based on spacing, times b/L
        if Re_b <= 0:
            return 0.0
        pr = a['pr']
        nu = ((Re_b * pr / 2) ** -3 + (0.664 * math.sqrt(Re_b) * pr ** (1 / 3) * math.sqrt(1 + 3.65 / math.sqrt(Re_b))) ** -3) ** (-1 / 3)
        return nu * a['k'] / b

    def fin_efficiency(self, h: float) -> float:
        t = self.fin_thickness / 1000
        Lc = self.fin_height / 1000 + t / 2
        m = math.sqrt(2 * h / (self.k_fin * t))
        return math.tanh(m * Lc) / (m * Lc) if m * Lc > 1e-9 else 1.0

    def area_fins(self) -> float:        # m2 (fin faces plus the exposed base between fins)
        L = self.length / 1000
        return self.n_fins * 2 * (self.fin_height / 1000) * L + (self.n_fins - 1) * (self.gap / 1000) * L

    def spreading_resistance(self) -> float:
        """Song-Lee-Au closed form, centred source on a finite plate, cooled on the far side with the fins' effective h."""
        return self._spread(self._h_eff)

    def _spread(self, h_eff):
        k, t = self.k_base, self.base_thickness / 1000
        As = self.source[0] * self.source[1] * 1e-6
        Ap = self.length * self.width * 1e-6
        a, bb = math.sqrt(As / math.pi), math.sqrt(Ap / math.pi)
        eps, tau = a / bb, t / bb
        Bi = h_eff * bb / k
        lam = math.pi + 1 / (math.sqrt(math.pi) * eps)
        phi = (math.tanh(lam * tau) + lam / Bi) / (1 + lam / Bi * math.tanh(lam * tau))
        psi_max = (eps * tau) / math.sqrt(math.pi) + (1 - eps) * phi / math.sqrt(math.pi)
        return psi_max / (k * a * math.sqrt(math.pi))

    def resistance(self, q_m3s: float, detail: bool = False):
        """Base (under the source) to inlet air, K/W: spreading + 1D base + fins. The fin term already includes the air
        heating up along the channels: Teertstra's h is referenced to the inlet air, and its low-flow limit is exactly
        1 / (m cp). ``air_limit`` (1 / (m cp)) is reported for comparison, not added."""
        h = self.h(q_m3s)
        eta = self.fin_efficiency(h)
        A = self.area_fins()
        r_fins = 1 / (h * eta * A) if h > 0 else float('inf')
        if q_m3s > 0:   # the air cannot carry more than m cp (T_base - T_in): the base strips between fins add area
            r_fins = max(r_fins, 1 / (self.air['rho'] * self.air['cp'] * q_m3s))   # beyond the correlation's channel basis
        Ap = self.length * self.width * 1e-6
        self._h_eff = 1 / (r_fins * Ap)
        r_spread = self._spread(self._h_eff)
        r_base = (self.base_thickness / 1000) / (self.k_base * Ap)
        r_air = 1 / (self.air['rho'] * self.air['cp'] * q_m3s) if q_m3s > 0 else float('inf')
        total = r_spread + r_base + r_fins
        if not detail:
            return total
        return {'total_k_per_w': total, 'spreading': r_spread, 'base': r_base, 'fins': r_fins, 'air_limit': r_air,
                'h_w_m2k': h, 'fin_efficiency': eta, 'fin_area_m2': A, 'n_fins': self.n_fins,
                'channel_velocity_m_s': self.channel_velocity(q_m3s)}

    # --- porous stand-in for CFD
    def porous_coefficients(self, q_range=(0.002, 0.03), core_only: bool = True) -> dict:
        """Darcy-Forchheimer coefficients (d 1/m2, f 1/m) along the channels that reproduce the channel pressure drop
        at the superficial velocity of a porous block of the fin volume: dp/L = mu d V + rho f V^2 / 2. By default only
        the channel friction (the CFD resolves the block's faces and the fan jet). Also returned: ``d_vector`` and
        ``f_vector`` for local axes (along the channels, across the fins, along the fin height): open along the
        channels and the fin height, nearly closed (1000 x d) across the fins, so the air keeps to the channels."""
        import numpy as np
        a = self.air
        L = (self.flow_length or self.length) / 1000
        face = self.width * self.fin_height * 1e-6 * self.branches
        qs = np.linspace(*q_range, 12)
        V = qs / face
        y = np.array([self.pressure_drop(q, core_only=core_only) for q in qs]) / L
        A = np.stack([a['mu'] * V, 0.5 * a['rho'] * V ** 2], 1)
        (d, f), *_ = np.linalg.lstsq(A, y, rcond=None)
        d, f = float(max(d, 1.0)), float(max(f, 0.0))
        return {'d': d, 'f': f, 'd_vector': (d, 1000 * d, d), 'f_vector': (f, 0.0, f), 'flow_length_m': L,
                'porosity': self.porosity, 'core_only': core_only}

    def describe(self) -> dict:
        d = asdict(self)
        d.pop('air')
        d.update(n_fins=self.n_fins, gap_mm=round(self.gap, 3), porosity=round(self.porosity, 3), sources=SOURCES)
        return d


def operating_point(hs: PlateFin, fan: FanCurve, extra_k: float = 0.0) -> dict:
    """Where the fan curve meets the heatsink's pressure drop (plus ``extra_k`` * q^2 for grilles and vents)."""
    lo, hi = 0.0, fan.q_free_m3h / 3600
    for _ in range(80):
        q = (lo + hi) / 2
        if fan.dp(q) > hs.pressure_drop(q) + extra_k * q * q:
            lo = q
        else:
            hi = q
    q = (lo + hi) / 2
    return {'q_m3s': q, 'q_m3h': q * 3600, 'q_cfm': q * 3600 / 1.699, 'dp_pa': fan.dp(q),
            'channel_velocity_m_s': hs.channel_velocity(q), 'fraction_of_free_air': q * 3600 / fan.q_free_m3h}
