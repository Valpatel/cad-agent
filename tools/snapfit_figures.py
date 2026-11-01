#!/usr/bin/env python3
"""Regenerate docs/img/compliant/*.svg from the snap-fit calculator (the design guide's worked examples)."""
from pathlib import Path

from cadagent.mechanical.compliant import figures, snapfit as sf

OUT = Path(__file__).resolve().parents[1] / "docs" / "img" / "compliant"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pc = sf.MATERIALS["pc"]
    sec = sf.rect_section(9.5, 3.28)
    ex1 = sf.check_cantilever(name="Example I (PC, tapered hook)", length=19, section=sec, undercut=2.4, design=2,
                              strain_allow=pc.allowable(), secant_mpa=1815, friction=0.6, lead_deg=30,
                              root_radius=1.0)
    (OUT / "example-1.svg").write_text(figures.cantilever_svg(ex1, 19, 3.28, design=2))
    short = sf.check_cantilever(name="Same hook, 12 mm arm", length=12, section=sec, undercut=2.4, design=2,
                                strain_allow=pc.allowable(), secant_mpa=1815, friction=0.6, lead_deg=30,
                                root_radius=1.0)
    (OUT / "example-1-short.svg").write_text(figures.cantilever_svg(short, 12, 3.28, design=2))


if __name__ == "__main__":
    main()
