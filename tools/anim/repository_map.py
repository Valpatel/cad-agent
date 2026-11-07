#!/usr/bin/env python3
"""An original 16-bit robot-factory cinematic, not an engineering result.

    PYTHONPATH=software python3 tools/anim/repository_map.py [--check]

One continuous 24-second shot: a builder assembles its successor; the successor
crosses the conveyor and builds again. The orbital network and distant laser
battle are fiction. All three generations remain visible with motion disabled.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software"))
from cadagent.publish.anim import svg

OUT = ROOT / "docs/img/hero/repository-map.svg"
# The story's real destinations live below the image in the compact README.
STEPS = (
    ("Study", "docs/research/references/README.md"),
    ("Try", "docs/examples/README.md"),
    ("Test", "tests/README.md"),
    ("Review", ".agents/agents/cad-pr-reviewer.md"),
    ("Learn", ".agents/skills/design-process/SKILL.md"),
)

# Original little 5x7 letterforms: paths, so image-mode needs no font download.
LETTERS = {
    "A": "01110/11011/11011/11111/11011/11011/11011",
    "B": "11110/11011/11011/11110/11011/11011/11110",
    "D": "11110/11011/11011/11011/11011/11011/11110",
    "E": "11111/11000/11000/11110/11000/11000/11111",
    "H": "11011/11011/11011/11111/11011/11011/11011",
    "I": "11111/00100/00100/00100/00100/00100/11111",
    "L": "11000/11000/11000/11000/11000/11000/11111",
    "R": "11110/11011/11011/11110/11100/11010/11011",
    "S": "01111/11000/11000/01110/00011/00011/11110",
    "T": "11111/00100/00100/00100/00100/00100/00100",
    "U": "11011/11011/11011/11011/11011/11011/01110",
    " ": "00000/00000/00000/00000/00000/00000/00000",
}


def build():
    for _, target in STEPS:
        if not (ROOT / target).is_file():
            raise ValueError(f"map target is missing: {target}")
    body = []

    def rect(x, y, w, h, color, extra=""):
        body.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}" {extra}/>')

    def path(d, color, extra=""):
        body.append(f'<path d="{d}" fill="{color}" {extra}/>')

    def group(transform="", cls=""):
        body.append(f'<g transform="{transform}" class="{cls}">')

    def end():
        body.append('</g>')

    def lettering(words, x, y, unit, color):
        cells = []
        for i, char in enumerate(words):
            for row, bits in enumerate(LETTERS[char].split("/")):
                for col, bit in enumerate(bits):
                    if bit == "1":
                        cells.append(f"M{x+(i*6+col)*unit} {y+row*unit}h{unit}v{unit}h-{unit}z")
        path("".join(cells), color)

    def satellite(x, y, scale=1):
        group(f"translate({x} {y}) scale({scale})")
        group(cls="satellite")
        path("M-88-20h52v8h72v-8h52v40H36v-8h-72v8h-52Z", "#19283e")
        for px in (-84, 40):
            rect(px, -16, 44, 32, "#338baf")
            rect(px, -16, 44, 4, "#8bd4db")
            for col in range(3):
                for row in range(2):
                    rect(px+4+col*14, -8+row*12, 8, 8, "#254b77")
        path("M-20-16h40v32h-40Z", "#bacacb")
        rect(-20, 8, 40, 8, "#647893")
        rect(-8, -8, 16, 12, "#ffe6a0")
        path("M-4-16v-16h8v16m-12-16v-4H8v4", "#e2e6cc")
        path("M-8 16v12H8V16M-4 28v8h8v-8", "#78e6dd")
        end()
        end()

    def robot(x, y, scale, tint, shade, cls=""):
        """A shared builder silhouette; the nested arm is its manufacturing tool."""
        group(f"translate({x} {y})")
        group(cls=cls)
        group(f"scale({scale})")
        path("M-30-8h24v12h-30v-8m42-4h24V4H6Z", "#090f24")
        rect(-24, -26, 16, 22, shade)
        rect(8, -26, 16, 22, shade)
        rect(-28, -10, 22, 10, tint)
        rect(8, -10, 22, 10, tint)
        path("M-28-76h56v46H16v10h-32v-10h-12Z", shade)
        rect(-28, -76, 48, 32, tint)
        rect(-22, -70, 38, 4, "#d1f2df")
        rect(-16, -60, 20, 14, "#14253d")
        rect(-12, -56, 12, 6, "#ffcc75")
        rect(-4, -38, 12, 6, "#17354b")
        for px in (-24, 16):
            rect(px, -72, 4, 4, "#fff1c3")
            rect(px, -40, 4, 4, "#32495a")
        rect(20, -66, 8, 22, shade)
        rect(-20, -24, 4, 12, "#a7c5bf")
        rect(12, -24, 4, 12, "#a7c5bf")
        group(cls="successor-head" if cls == "successor" else "")
        rect(-10, -86, 20, 10, "#15243d")
        path("M-26-116h44v6h10v26h-54Z", shade)
        rect(-26, -116, 44, 24, tint)
        rect(-20, -108, 42, 12, "#0a1c32")
        rect(-14, -104, 12, 4, "#b4ffec")
        rect(6, -104, 12, 4, "#b4ffec")
        rect(-26, -124, 8, 8, "#ffb760")
        end()
        path("M-28-72h-12v34h12v-8h-4v-16h4Z", tint)
        group("translate(24 -64)")
        group(cls="apprentice-arm" if cls == "successor" else "")
        path("M0-8h24v16H8v16H-4V4Z", shade)
        rect(0, -8, 24, 8, tint)
        path("M24-4h28v8H24m28-8h12v-8h8v12h-8v8h8v12h-8V8H52Z", "#e5cfa2")
        rect(44, -6, 12, 12, "#ffb45d")
        end()
        end()
        end()
        end()
        end()

    # Dusk, a rising planet and a star field: flat, stepped colour instead of blur.
    rect(0, 0, 1280, 480, "#0b1026")
    for y, color in ((88, "#141830"), (160, "#23203e"), (220, "#352543"), (268, "#50334c")):
        rect(0, y, 1280, 300-y, color)
    group(cls="stars")
    for i in range(76):
        x, y = (i*181+37) % 1336 - 28, (i*i*13+17) % 190 + 12
        rect(x, y, 4 if i % 7 else 6, 4 if i % 7 else 6,
             ("#8b8bab", "#d4bbac", "#517391")[i % 3])
    end()
    # Ringed world, drawn as horizontal pixel runs with a cool night-side crescent.
    group("translate(1096 110)")
    for y, half in ((-84, 24), (-76, 40), (-68, 52), (-60, 60), (-52, 68), (-40, 76), (-24, 80),
                    (-8, 84), (8, 84), (24, 80), (40, 72), (52, 64), (64, 52), (76, 32)):
        rect(-half, y, half*2, 16, "#aa687e")
        rect(-half, y, half+12, 16, "#cc8b8d")
        rect(half-20, y, 20, 16, "#784d76")
    path("M-56-48h56v8h32v12h-68v8h-40v-12h20Zm24 68h64v12h32v16H20v16h-40V44h-24Z", "#e8a99a")
    for px, py in ((-64, -24), (-48, -16), (-56, 8), (-32, 12), (0, -60), (16, -52), (40, -36), (44, 20), (32, 60)):
        rect(px, py, 8, 4, "#e6a299")
        rect(px+8, py+4, 4, 4, "#bc7a88")
    path("M-144 40h32v-8h32v-8h32v-8h32V8h32V0h32v-8h32v-8h32v-8h32v-8h32v-8h16v12h-24v8h-32v8H80v8H48v8H16v8h-32v8h-32v8h-32v8h-32v8h-32Z", "#e7b5a1")
    end()
    # Distant orbit traces, carrier and scouts, behind the factory's silhouette.
    path("M664 84h72v-8h88v-8h96v-8h88", "none", 'stroke="#3e6478" stroke-width="2" stroke-dasharray="12 20"')
    satellite(850, 80)
    satellite(1238, 166, .45)
    # One scout crosses the upper sky each cycle, its exhaust tapering into pixels.
    group("translate(650 174)")
    group(cls="scout")
    path("M-36 0h20v-4h20v-8h12v8h28v4h16v8H12v8H0v-8h-16V4h-20Z", "#9aa4b6")
    path("M0 0h28v4H0Z", "#a5f1dd")
    path("M-28 0h-24v4h24m-28 0h-16v4h16m-20 0h-8v4h8", "#dc9989")
    end()
    end()
    group(cls="carrier")
    path("M560 122h28v-8h60v8h32v8h28v8H540v-8h20Z", "#38465f")
    rect(578, 120, 68, 4, "#9b899e")
    for x in (556, 580, 604):
        rect(x, 136, 12, 4, "#7ee5e2")
    end()
    # Two depth planes drift only a few pixels. Original silhouettes, no game assets.
    group(cls="horizon")
    path("M-40 284h64v-32h40v-20h36v-40h20v-24h8v24h20v80h40v-32h48v24h44v-56h48v-24h8v24h44v64h64v-40h32v-20h44v60h60v-32h40v-24h24v-32h8v32h24v56h64v-36h60v28h40v-56h24v-32h8v32h24v68h56v-32h64v-36h48v68h48v-60h24v-12h8v12h24v40h44v-52h16v-24h8v24h16v76h100v56H-40Z", "#25354a")
    for i in range(42):
        rect((i*101+22) % 1280, 240+(i % 4)*12, 6, 4, "#a48a79", 'opacity=".55"')
    end()
    path("M1102 270l-32-86h12l28 86m80 0 44-64h8l-44 64", "#677184", 'opacity=".16"')
    path("M0 332v-36h60v-12h76v32h68v-8h84v28h44v-24h64v20h52v-12h76v16h88v-28h64v16h72v-12h92v28h56v-24h72v16h68v-24h68v20h84v-36h64v12h44v-16h64v56Z", "#17283c")
    # Exterior battle: a guarded city gate, two mechs and small bounded laser bolts.
    rect(968, 326, 312, 66, "#132b3d")
    for x in range(980, 1280, 36):
        rect(x, 330, 20, 4, "#38606b")
    group("translate(1164 324)")
    group(cls="sentinel")
    path("M-24-12h16v28h-24v-8h8m24-20h16v28h12v8H0Z", "#895773")
    path("M-30-66h60v16h12v40H16v-10h-32v10h-26v-40h12Z", "#bc687c")
    rect(-24, -60, 42, 20, "#ec9a8b")
    rect(-22, -54, 32, 8, "#1d1931")
    rect(-18, -52, 24, 4, "#ffc07d")
    path("M-38-44h-24v12h-28v12h52Z", "#9a6b84")
    rect(-90, -32, 26, 8, "#eb9889")
    end()
    end()
    robot(1018, 354, .42, "#78c5c4", "#35718b")
    path("M996 264h24v12h12v56h-12v12h-24", "none", 'class="shield" stroke="#7ee4df" stroke-width="4"')
    group(cls="red-shot")
    rect(1058, 292, 32, 4, "#ffab90")
    rect(1050, 292, 8, 4, "#ffefd1")
    end()
    group(cls="blue-shot")
    rect(1044, 316, 32, 4, "#66ced6")
    rect(1076, 316, 8, 4, "#c6ffed")
    end()
    group("translate(1014 294)")
    group(cls="impact")
    path("M-4-16h8v10h8v-6h6v8H8v8h10v6H8v8H0V8h-12V2h8v-8h-8v-6h8Z", "#b5f4de")
    end()
    end()
    # A cutaway factory: lit amber inside, indigo load-bearing frame outside.
    path("M76 382V218h72v-40h72v-24h492v24h80v28h152v176Z", "#0b192b")
    path("M224 182h476v24h80v28h140v136H100V238h72v-40h52Z", "#302e3a")
    rect(244, 194, 446, 162, "#4b3a42")
    rect(258, 202, 422, 142, "#654747")
    for x in range(264, 680, 52):
        rect(x, 206, 4, 130, "#8b5a4c")
        rect(x+4, 206, 2, 130, "#be7c56")
    path("M268 212h404v8H268Z", "#f3ba70")
    path("M272 222h392l-36 116H308Z", "#f6ae60", 'opacity=".10"')
    rect(106, 246, 118, 120, "#162a37")
    for y in (256, 294, 332):
        rect(118, y, 92, 26, "#304753")
        for x in (126, 142, 158):
            rect(x, y+8, 8, 4, "#7dd8c3")
        rect(186, y+6, 12, 14, "#141e32")
    for px, py in ((110, 242), (214, 242), (110, 358), (214, 358)):
        rect(px, py, 4, 4, "#a4a98c")
    # Raised walkway, roof ribs, hanging wires, overhead tool and a little diagnostics screen.
    for x in (230, 698, 920):
        rect(x, 176 if x < 800 else 224, 16, 200 if x < 800 else 152, "#122438")
        rect(x, 176 if x < 800 else 224, 4, 200 if x < 800 else 152, "#5c6371")
    rect(212, 170, 504, 12, "#65727b")
    rect(212, 182, 504, 8, "#15283a")
    for x in range(244, 700, 36):
        path(f"M{x} 170h8l12-16h-8Z", "#b98b65")
    path("M590 188v22h-24v16h-24v24", "none", 'stroke="#1a2335" stroke-width="8"')
    rect(516, 248, 56, 12, "#baa07e")
    rect(522, 260, 44, 8, "#e9c88b")
    rect(772, 248, 86, 60, "#0f1d2f")
    rect(780, 256, 70, 42, "#225064")
    path("M788 282h12v-12h12v16h12v-22h12v10h8", "none", 'stroke="#8be8d0" stroke-width="4"')
    rect(808, 308, 12, 12, "#536474")
    # Factory plumbing and small tools add texture without competing with the builders.
    path("M880 238v88h-28v18m-600-20v-62h18", "none", 'stroke="#a17b60" stroke-width="6"')
    for y in (252, 284, 316):
        rect(874, y, 12, 4, "#d8ac71")
    rect(622, 302, 60, 42, "#252f40")
    rect(626, 306, 52, 6, "#8d795f")
    for x in range(630, 676, 12):
        rect(x, 316, 6, 20, "#445766")
    path("M588 342v-28h8v28m12 0v-20h8v20", "#c4a77c")
    # Floor and conveyor: belt moves by exactly one tooth per repeat.
    rect(64, 374, 886, 24, "#637681")
    rect(64, 380, 886, 10, "#1a2e40")
    rect(64, 398, 886, 12, "#0b192b")
    rect(444, 354, 472, 20, "#19283b")
    group(cls="belt")
    for x in range(444, 900, 24):
        rect(x, 354, 12, 6, "#b8b9a5")
        rect(x+4, 362, 12, 4, "#435b69")
    end()
    rect(438, 350, 16, 24, "#dcaa6c")
    rect(904, 350, 16, 24, "#dcaa6c")
    for x in (476, 668, 864):
        rect(x, 374, 12, 24, "#354659")
    # The parent builder: silhouette, shoulders, plated torso, piston feet and warm rim light.
    group("translate(358 368)")
    path("M-62-22h44v24h-58v-12h14m80-12h44v12h18V2H18Z", "#111e31")
    rect(-54, -66, 30, 44, "#416b7b")
    rect(22, -66, 30, 44, "#385569")
    for x in (-48, 28):
        rect(x, -60, 10, 36, "#9dbcb9")
    rect(-68, -18, 50, 16, "#6b9fa5")
    rect(18, -18, 50, 16, "#517e8b")
    path("M-60-158h108v12h20v62H44v28h-88v-20h-24v-64h8Z", "#315468")
    path("M-56-158H44v12h16v50H36v22h-76v-20h-16Z", "#6eaeb2")
    rect(-48, -150, 88, 8, "#b2e1cb")
    rect(-44, -128, 68, 38, "#1c3b51")
    rect(-32, -120, 44, 18, "#dcad68")
    rect(-24, -116, 28, 8, "#fff1bb")
    rect(32, -134, 12, 24, "#e6bd80")
    rect(-28, -78, 52, 6, "#112c42")
    # Bevels, fasteners, vents and a three-quarter shadow keep the hero sprite dimensional.
    rect(48, -136, 12, 36, "#386c80")
    rect(-56, -136, 6, 36, "#98d4c5")
    for x, y in ((-46, -138), (30, -138), (-38, -88), (24, -88)):
        rect(x, y, 4, 4, "#e2e4b9")
    for x in (-26, -14, -2, 10):
        rect(x, -96, 6, 4, "#84b6b5")
    for x in (-58, 28):
        rect(x, -12, 28, 4, "#bdd3bd")
        rect(x+4, -4, 24, 2, "#294154")
    path("M-20-64v10h36v-10", "none", 'stroke="#1a354b" stroke-width="4"')
    for x in (-20, -4, 12):
        rect(x, -60, 8, 6, "#94d6cc")
    # Left hand holds a source/blueprint tablet; right hand is the animated welder.
    path("M-62-146h-26v30h-18v48h22v-38h16v-20h6Z", "#41697b")
    rect(-92, -146, 22, 20, "#8fbcbb")
    path("M-128-88h62v44h-62Z", "#192c43")
    rect(-122, -82, 50, 30, "#36758b")
    path("M-112-58v-16h28v16m-22-8h16m-8-8v16", "none", 'stroke="#94e3d0" stroke-width="3"')
    rect(-18, -174, 38, 18, "#152b40")
    group(cls="builder-head")
    path("M-46-222h72v10h20v40h-92Z", "#33556e")
    rect(-46, -222, 72, 40, "#87c6c3")
    rect(-46, -222, 72, 8, "#c6e9cd")
    rect(28, -208, 12, 24, "#437888")
    rect(-46, -212, 6, 24, "#b0decc")
    rect(-36, -206, 76, 16, "#0d253d")
    rect(-28, -202, 24, 6, "#bbfff0")
    rect(12, -202, 24, 6, "#bbfff0")
    rect(-42, -238, 8, 16, "#e0b87b")
    rect(-46, -242, 16, 6, "#ffe6a2")
    rect(-30, -180, 40, 4, "#34536b")
    end()
    group("translate(56 -144)")
    group(cls="builder-arm")
    path("M-8-14h38v24h-8v34H6V12H-8Z", "#32546b")
    rect(-8, -14, 38, 16, "#94c5bb")
    path("M14 22h26v14h44v-8h20v28H28V44H14Z", "#6b9fa5")
    rect(28, 28, 58, 8, "#bee2c9")
    rect(92, 28, 16, 28, "#263f54")
    path("M108 34h20v12h-12v26h-8Z", "#f2c987")
    rect(108, 66, 8, 12, "#fff0ba")
    end()
    end()
    end()
    # Three generations share the screen even in the static, reduced-motion frame.
    robot(722, 348, .72, "#e3b77a", "#9c7364", "successor")
    group("translate(816 350)")
    group(cls="hatchling")
    robot(0, 0, .48, "#8ddbd0", "#418ca1")
    end()
    end()
    # Welding particles follow actual tool locations; small luminous marks, no full-frame flashes.
    group(cls="first-sparks")
    for x, y in ((518, 308), (530, 318), (512, 330), (542, 302), (548, 324)):
        rect(x, y, 4, 8, "#ffe6a3")
    end()
    group(cls="next-sparks")
    for x, y in ((798, 306), (810, 316), (818, 298), (824, 318)):
        rect(x, y, 4, 6, "#ffe5a9")
    end()
    # A data return line: lessons travel back to the builder's tablet.
    path("M850 396v22H190v-62", "none", 'stroke="#316976" stroke-width="4"')
    group(cls="return-signal")
    rect(844, 412, 12, 12, "#8ce8ce")
    end()
    # Foreground pipes, grating and amber practical lights anchor the wide composition.
    path("M0 398h42v-16h14v44h108v-16h28v16h152v-12h28v12h600v-24h52v24h114v-36h18v36h124v-28h18v52H0Z", "#080f23")
    for x in range(28, 1280, 64):
        rect(x, 434, 32, 4, "#2c4154")
    for x in (94, 408, 944, 1190):
        rect(x, 404, 32, 4, "#a77354")
        rect(x+4, 404, 24, 4, "#f8c57c")
    # Film-frame typography stays out of the action; the README supplies navigation.
    rect(28, 12, 554, 48, "#0b1026")
    lettering("BUILD THE BUILDERS", 36, 24, 5, "#060d20")
    lettering("BUILD THE BUILDERS", 36, 20, 5, "#f5dbac")
    rect(36, 70, 44, 3, "#75daca")
    body.append('<text x="92" y="76" class="subtitle">EVERY GENERATION LEARNS.</text>')
    body.append('<text x="36" y="466" class="caption">STUDY / BUILD / TEST / EVOLVE</text>')
    body.append('<text x="1244" y="466" text-anchor="end" class="credit">cad-agent</text>')
    css = '''
svg{max-width:100%;height:auto;background:#0b1026}
rect,path{shape-rendering:crispEdges}
.subtitle,.caption,.credit{font-family:ui-monospace,monospace;font-weight:700;letter-spacing:2px}
.subtitle{font-size:18px;fill:#83c5bf}.caption{font-size:24px;fill:#a2c7c8}.credit{font-size:24px;fill:#e4b784}
.stars{animation:stars 24s linear infinite}
.horizon{animation:horizon 24s ease-in-out infinite}
.satellite{animation:orbit 24s ease-in-out infinite}
.carrier{animation:carrier 24s linear infinite}
.scout{animation:scout 24s linear infinite}
.belt{animation:belt 2s linear infinite}
.builder-head{animation:watch 24s ease-in-out infinite}
.builder-arm{animation:weld 24s ease-in-out infinite}
.successor{animation:successor 24s linear infinite}
.successor-head{animation:assemble 24s ease-in-out infinite}
.apprentice-arm{animation:teach 24s ease-in-out infinite}
.hatchling{animation:hatchling 24s linear infinite}
.first-sparks{opacity:.7;animation:first-sparks 24s linear infinite}
.next-sparks{opacity:.8;animation:next-sparks 24s linear infinite}
.return-signal{animation:feedback 24s linear infinite}
.sentinel{animation:sentinel 8s ease-in-out infinite}
.shield{opacity:.4;animation:shield 6s ease-in-out infinite}
.red-shot{animation:red-shot 6s linear infinite}
.blue-shot{animation:blue-shot 6s linear infinite}
.impact{opacity:.5;animation:impact 6s ease-out infinite}
@keyframes stars{0%,100%{transform:translateX(0)}50%{transform:translateX(-12px)}}
@keyframes horizon{0%,100%{transform:translateX(0)}50%{transform:translateX(-8px)}}
@keyframes orbit{0%,100%{transform:translate(0,0)}50%{transform:translate(-28px,12px)}}
@keyframes carrier{0%,100%{transform:translate(0,0)}50%{transform:translate(56px,-8px)}}
@keyframes scout{0%,28%,100%{opacity:0;transform:translate(-740px,40px)}30%{opacity:1;transform:translate(-740px,40px)}62%{opacity:1;transform:translate(740px,-100px)}64%,99%{opacity:0;transform:translate(740px,-100px)}}
@keyframes belt{to{transform:translateX(24px)}}
@keyframes watch{0%,26%,100%{transform:translateY(0)}40%,88%{transform:translate(4px,4px)}}
@keyframes weld{0%,28%,100%{transform:rotate(0deg)}6%,18%{transform:rotate(6deg)}12%,24%{transform:rotate(-4deg)}38%,88%{transform:rotate(-24deg)}}
@keyframes successor{0%,28%{transform:translateX(-184px);opacity:1}50%,92%{transform:translateX(0);opacity:1}97%{transform:translateX(0);opacity:0}98%,100%{transform:translateX(-184px);opacity:0}}
@keyframes assemble{0%,5%,100%{transform:translateY(-36px)}18%,97%{transform:translateY(0)}}
@keyframes teach{0%,46%,100%{transform:rotate(-48deg)}56%,76%{transform:rotate(0deg)}82%,97%{transform:rotate(-24deg)}}
@keyframes hatchling{0%,50%,100%{opacity:0;transform:translateY(-12px)}66%,76%{opacity:1;transform:translate(0,0)}90%{opacity:1;transform:translate(72px,0)}96%,99%{opacity:0;transform:translate(96px,0)}}
@keyframes first-sparks{0%,28%,100%{opacity:0;transform:translateY(0)}8%,20%{opacity:.9;transform:translateY(6px)}14%,26%{opacity:.3;transform:translateY(12px)}30%,99%{opacity:0}}
@keyframes next-sparks{0%,50%,80%,100%{opacity:0;transform:translateY(0)}59%,71%{opacity:.9;transform:translateY(4px)}65%,77%{opacity:.3;transform:translateY(10px)}}
@keyframes feedback{0%,76%,100%{opacity:0;transform:translate(0,0)}78%{opacity:1;transform:translate(0,0)}90%{opacity:1;transform:translate(-660px,0)}96%{opacity:1;transform:translate(-660px,-62px)}99%{opacity:0;transform:translate(-660px,-62px)}}
@keyframes sentinel{0%,100%{transform:translateY(0)}50%{transform:translateY(4px)}}
@keyframes shield{0%,30%,80%,100%{opacity:.15}50%,65%{opacity:.65}}
@keyframes red-shot{0%,18%,60%,100%{opacity:0;transform:translateX(0)}20%{opacity:1;transform:translateX(0)}50%{opacity:1;transform:translateX(-52px)}}
@keyframes blue-shot{0%,55%,96%,100%{opacity:0;transform:translateX(0)}58%{opacity:1;transform:translateX(0)}88%{opacity:1;transform:translateX(58px)}}
@keyframes impact{0%,48%,74%,100%{opacity:0;transform:scale(.4)}54%{opacity:.9;transform:scale(.7)}70%{opacity:0;transform:scale(1.2)}}
''' + svg.REDUCED_MOTION
    return svg.document(640, 240, "Build the builders — a robot-factory cinematic",
                        "Original conceptual pixel art. A large robot studies a blueprint and assembles a smaller builder; its successor makes another robot, and a signal carries lessons back. Satellites orbit a ringed world above a distant, fictional robot battle. A 24-second repeating scene; reduced motion shows all three generations at once. This is a story about self-improvement, not a hardware design or a claim of autonomous physical qualification.", css, body, background=False)


def main():
    text = build()
    issues = svg.problems(text)
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text() != text:
            issues.append("repository map differs: run tools/anim/repository_map.py")
    elif not issues:
        OUT.write_text(text)
    for issue in issues:
        print(issue)
    return bool(issues)


if __name__ == "__main__":
    raise SystemExit(main())
