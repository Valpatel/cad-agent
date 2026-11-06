#!/usr/bin/env python3
"""Draw the repository's evidence → evaluation → method → regression route.

    PYTHONPATH=software python3 tools/anim/repository_map.py [--check]

This is a navigation diagram of existing paths, not a measured engineering result.
The SVG uses the existing embed validator, themes and reduced-motion policy.
"""
from pathlib import Path
import sys
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software"))
from cadagent.publish.anim import svg

OUT = ROOT / "docs/img/hero/repository-map.svg"
# Paths are checked before drawing so the map cannot quietly point at removed capabilities.
STEPS = (
    ("Sources", "docs/research/", "read + cite", "docs/research/references/README.md"),
    ("Evaluate", "tests/", "examples + controls", "tests/review/test_gate_bench.py"),
    ("Methods", "software/ + .agents/", "encode + explain", ".agents/skills/design-process/SKILL.md"),
    ("Regress", "tests/ + docs/lessons/", "keep the failed case", "docs/lessons/process/README.md"),
)


def build():
    body = ['<text x="64" y="75" class="title">Every finding has a next step.</text>',
            '<text x="64" y="123" class="intro">Evidence in. Reusable engineering out.</text>',
            '<path d="M608 330H672M936 470V560M672 700H608M344 560V470" class="route"/>',
            '<path d="m650 318 22 12-22 12m274 196 12 22 12-22m-318 162-22 12 22 12m-298-144 12-22 12 22" class="arrows"/>']
    # Clockwise sequence. Every label survives in the still; the moving dots are decoration only.
    for i, ((title, folder, meaning, target), (x, y)) in enumerate(zip(STEPS, ((64, 190), (672, 190), (672, 560), (64, 560)))):
        if not (ROOT / target).is_file():
            raise ValueError(f"map target is missing: {target}")
        body.append(f'<g transform="translate({x} {y})"><rect width="544" height="280" rx="28" class="card"/>'
                    f'<circle cx="55" cy="59" r="26" class="badge"/><text x="55" y="70" text-anchor="middle" class="number">{i+1}</text>'
                    f'<text x="102" y="74" class="step">{escape(title)}</text>'
                    f'<text x="36" y="151" class="folder">{escape(folder)}</text>'
                    f'<text x="36" y="219" class="meaning">{escape(meaning)}</text></g>')
    body += ['<circle cx="640" cy="330" r="9" class="packet p0"/>',
             '<circle cx="936" cy="515" r="9" class="packet p1"/>',
             '<circle cx="640" cy="700" r="9" class="packet p2"/>',
             '<circle cx="344" cy="515" r="9" class="packet p3"/>',
             '<text x="64" y="906" class="limit">A model checks assumptions. A physical test checks the part.</text>']
    css = '''.title{font-size:43px;font-weight:720;fill:var(--ink)}
.intro,.limit{font-size:26px;fill:var(--muted)}
.card{fill:var(--panel);stroke:var(--line);stroke-width:2}
.badge{fill:var(--ink)}.number{font-size:29px;fill:var(--bg);font-weight:700}
.step{font-size:43px;font-weight:700;fill:var(--ink)}
.folder{font-size:33px;font-weight:600;fill:var(--ink)}
.meaning{font-size:30px;fill:var(--muted)}
.route,.arrows{fill:none;stroke:var(--ink);stroke-width:3;stroke-linecap:round;stroke-linejoin:round}
.packet{fill:var(--accent);opacity:0}.p0{animation:pulse 8s linear infinite}.p1{animation:pulse 8s 2s linear infinite}.p2{animation:pulse 8s 4s linear infinite}.p3{animation:pulse 8s 6s linear infinite}
@keyframes pulse{0%,21%{opacity:1}26%,100%{opacity:0}}
@media(max-width:400px){.intro,.meaning,.limit{display:none}.title{font-size:44px}.step{font-size:46px}.folder{font-size:40px}.card{stroke-width:3}}
''' + svg.REDUCED_MOTION
    return svg.document(640, 480, "Sources, evaluate, methods, regress",
                        "Read and cite research; evaluate examples and controls; encode reusable methods in code and skills; keep failed cases in tests and lessons. Repeat.", css, body)


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
