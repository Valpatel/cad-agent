#!/usr/bin/env python3
"""Draw a conceptual learning workshop, not a measured engineering result.

    PYTHONPATH=software python3 tools/anim/repository_map.py [--check]

The complete story is visible in the still. Quiet repeating light and a travelling
note decorate the route; neither animation is needed to understand it.
"""
from pathlib import Path
import sys
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software"))
from cadagent.publish.anim import svg

OUT = ROOT / "docs/img/hero/repository-map.svg"
# Real destinations make the conceptual route accountable to existing repository homes.
STEPS = (
    ("Study", "docs/research/references/README.md"),
    ("Try", "docs/examples/README.md"),
    ("Test", "tests/README.md"),
    ("Review", ".agents/agents/cad-pr-reviewer.md"),
    ("Learn", ".agents/skills/design-process/SKILL.md"),
)


def build():
    for _, target in STEPS:
        if not (ROOT / target).is_file():
            raise ValueError(f"map target is missing: {target}")
    body = []

    def rect(x, y, w, h, color, extra=""):
        body.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}" {extra}/>')

    def path(d, color, extra=""):
        body.append(f'<path d="{d}" fill="{color}" {extra}/>')

    # One continuous cutaway: midnight hills beyond a warmly lit, inhabited workshop.
    rect(0, 0, 1280, 500, "#141b35")
    rect(0, 82, 1280, 234, "#202b48")
    path("M0 164h76v-32h72v32h84v-54h68v54h92v-32h76v-44h88v44h92v-34h84v34h72v-48h96v48h84v32h96v-32h105v32h100v152H0Z", "#2a4055")
    path("M0 218h100v-36h112v36h120v-26h132v26h100v-46h104v46h148v-30h108v30h110v-44h112v44h134v98H0Z", "#365451")
    # Sky and distant stepped mountains seen through the tall central window.
    path("M474 242V112h24V88h24V64h236v24h24v24h24v130Z", "#10182f")
    path("M490 242V116h24V92h24V80h204v12h24v24h24v126Z", "#30516b")
    rect(714, 100, 32, 32, "#f4cf88")
    rect(704, 100, 16, 24, "#30516b")
    path("M490 220h48v-28h36v-28h36v28h32v28h52v-44h32v-28h28v28h36v66H490Z", "#447b80")
    path("M490 228h60v-20h44v20h52v-12h48v-20h40v20h56v26H490Z", "#6ba99a")
    rect(632, 80, 16, 162, "#182440")
    rect(490, 158, 300, 12, "#182440")
    # Timber frame, continuous floor, and warm pools of light.
    rect(0, 78, 1280, 18, "#10182b")
    for x in (32, 428, 828, 1224):
        rect(x, 96, 20, 230, "#111a2d")
        rect(x + 4, 96, 4, 224, "#4b4b58")
    for x in (270, 944):
        path(f"M{x} 104h8v38h24v8h8v16h-56v-16h8v-8h8Z", "#d7a664")
        path(f"M{x-8} 168h40l48 142H{x-56}Z", "#f0b96d", 'opacity=".07" class="lamplight"')
        rect(x - 8, 158, 40, 8, "#ffe0a1")
    rect(0, 310, 1280, 28, "#10182c")
    rect(0, 314, 1280, 8, "#72645f")
    rect(0, 338, 1280, 162, "#182239")
    for y in (348, 400, 452):
        rect(0, y, 1280, 2, "#26344b")
    for x in range(0, 1280, 128):
        rect(x, 338, 2, 62, "#26344b")
        rect(x + 64, 402, 2, 50, "#26344b")
    # Study: real sources on shelves, with an open book that keeps its author's mark.
    rect(70, 132, 168, 174, "#10182c")
    for y in (184, 244, 300):
        rect(70, y, 168, 10, "#8e7564")
    for row, y in enumerate((138, 202, 256)):
        for i, c in enumerate(("#69b3b4", "#bb7c70", "#e3b574", "#718e6b", "#9a96b2")):
            h = 32 + ((i + row) % 3) * 6
            rect(82 + i * 28, y + 44 - h, 20, h, c)
            rect(86 + i * 28, y + 48 - h, 4, h - 8, "#141b35", 'opacity=".28"')
    path("M114 290v-42h28l18 10 18-10h28v42h-28l-18 10-18-10Z", "#f4d7a3")
    rect(157, 258, 6, 34, "#b18b68")
    # Try: shared workbench, a rough model and hand tools, rather than a product diagram.
    rect(282, 274, 176, 16, "#c08a60")
    rect(290, 290, 14, 22, "#574354")
    rect(434, 290, 14, 22, "#574354")
    path("M320 270v-40h20v-24h56v24h20v40Z", "#64b5bc")
    path("M340 230h56v12h-56Z", "#a2dbd0")
    path("M340 244h12v26h-12m32-26h12v26h-12", "#2c7186")
    path("M300 198h10v30h-10m-8-38h26v10h-26", "#d7b27f")
    rect(422, 242, 8, 30, "#c78a76")
    # Test: a virtual instrument beside a separate physical measuring tool.
    rect(536, 208, 128, 76, "#10182b")
    rect(544, 216, 112, 56, "#265264")
    path("M552 254h16v-16h20v16h20v-26h18v26h22", "none", 'stroke="#91d9cb" stroke-width="6"')
    rect(592, 284, 16, 16, "#82939a")
    rect(570, 300, 60, 6, "#82939a")
    path("M690 270v-40h10v16h30v-16h10v40h-10v-12h-30v12Z", "#d6c6a4")
    rect(710, 222, 10, 18, "#81b5af")
    # Review: two stools at one desk, with an annotated sheet kept visible.
    rect(800, 272, 176, 16, "#be8c62")
    rect(812, 288, 12, 24, "#574354")
    rect(952, 288, 12, 24, "#574354")
    path("M844 226h64v44h-64Z", "#f2d5a2")
    path("M854 236h40v6h-40m0 8h24v6h-24", "#7e715f")
    path("M884 252h6v6h12v-12h6v18h-24Z", "#4b8d7a")
    for x, c in ((808, "#e1b878"), (944, "#7dc0c1")):
        rect(x, 234, 24, 24, c)
        rect(x + 4, 226, 16, 8, c)
        rect(x + 4, 258, 16, 12, "#576c82")
    # Learn: a living archive. A new leaf joins the books; a route returns to study.
    rect(1044, 176, 138, 130, "#10182c")
    for y in (218, 264, 300):
        rect(1044, y, 138, 8, "#927461")
    for i, c in enumerate(("#7eb8b0", "#dda875", "#9e94b0", "#6f936f")):
        rect(1056 + i * 28, 228, 20, 34, c)
    path("M1080 206v-32h24l16 8 16-8h24v32h-24l-16 8-16-8Z", "#f1d5a5")
    rect(1117, 182, 6, 26, "#ae8969")
    rect(1200, 274, 34, 36, "#b88262")
    path("M1214 276v-64h8v64m-8-30h-20v-10h-12v-12h22v10h10m8-10h18v-12h12v-12h-22v12h-8", "#7caa7d")
    # Typography is deliberately outside the busy scene. Meaning survives every still.
    body.append('<text x="52" y="48" class="heading">A workshop that learns.</text>')
    body.append('<text x="1228" y="47" text-anchor="end" class="concept">Conceptual workflow</text>')
    for (label, _), x in zip(STEPS, (154, 370, 640, 888, 1118)):
        body.append(f'<text x="{x}" y="375" text-anchor="middle" class="step">{escape(label)}</text>')
    path("M154 400h964v16H182v16h-28Z", "#536e78")
    path("M1118 392h16v16h-16m-964 16h-16v16h16", "#9fd1bc")
    rect(348, 396, 24, 24, "#efc482", 'class="note"')
    rect(354, 402, 12, 4, "#8b735e", 'class="note"')
    body.append('<text x="640" y="472" text-anchor="middle" class="limit">Virtual checks + real measurements → reviewed, reusable skills.</text>')
    css = '''.heading{font-size:32px;font-weight:650;fill:#f4d6a0;letter-spacing:1px}
.concept{font-size:21px;fill:#a8bec5}.step{font-size:38px;font-weight:650;fill:#e4e7dc}
.limit{font-size:25px;fill:#b5c8c4}.note{animation:carry 18s linear infinite}
.lamplight{animation:warm 18s ease-in-out infinite}
@keyframes carry{0%,12%,100%{transform:translateX(0)}65%,78%{transform:translateX(760px)}}
@keyframes warm{0%,100%{opacity:.07}50%{opacity:.12}}
rect,path{shape-rendering:crispEdges}
svg{max-width:100%;height:auto}
''' + svg.REDUCED_MOTION
    return svg.document(640, 250, "A learning workshop: Study, Try, Test, Review, Learn",
                        "Conceptual pixel-art workshop. Study credited sources, try a method, distinguish virtual checks from real measurements, review the evidence, and preserve reusable skills. The loop is a method, not a claim of physical qualification.", css, body, background=False)


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
