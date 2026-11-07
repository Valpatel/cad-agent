#!/usr/bin/env python3
"""A small, original vector badge around Valpatel's crystal/V emblem.

    PYTHONPATH=software python3 tools/anim/made_with_badge.py [--check]

No fonts, bitmap tracing library, external resources or browser scripts are
needed. The lettering is drawn here; both variants share the same geometry.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software"))
from cadagent.publish.anim import svg

OUT = ROOT / "docs/img/hero/made-with-cad-agent.svg"
STILL_OUT = OUT.with_name("made-with-cad-agent-still.svg")

# Original chamfered letterforms, in a 10 x 14 cell. Strokes stay vectors at any size.
LETTERS = {
    "A": "M0 14V4L4 0H6L10 4V14M0 8H10",
    "C": "M10 2L8 0H2L0 2V12L2 14H8L10 12",
    "D": "M0 14V0H6L10 4V10L6 14Z",
    "E": "M10 0H0V14H10M0 7H8",
    "G": "M10 2L8 0H2L0 2V12L2 14H8L10 12V8H6",
    "H": "M0 0V14M10 0V14M0 7H10",
    "I": "M1 0H9M5 0V14M1 14H9",
    "M": "M0 14V0L5 6L10 0V14",
    "N": "M0 14V0L10 14V0",
    "T": "M0 0H10M5 0V14",
    "W": "M0 0V14L5 8L10 14V0",
    "-": "M2 7H8",
    " ": "",
}


def build(*, still=False):
    body = []

    def add(markup):
        body.append(markup)

    def lettering(words, x, y, scale, color, width):
        add(f'<g transform="translate({x} {y}) scale({scale})" fill="none" '
            f'stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="square">')
        for i, letter in enumerate(words):
            if LETTERS[letter]:
                add(f'<path d="{LETTERS[letter]}" transform="translate({i*14} 0)"/>')
        add('</g>')

    add('''<defs>
<linearGradient id="shell" x1="0" y1="0" x2=".6" y2="1"><stop stop-color="#26354d"/><stop offset=".48" stop-color="#111b30"/><stop offset="1" stop-color="#080e1c"/></linearGradient>
<linearGradient id="rim" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#93b8d9"/><stop offset=".25" stop-color="#3e506c"/><stop offset=".65" stop-color="#16263f"/><stop offset="1" stop-color="#6675a4"/></linearGradient>
<linearGradient id="crystal" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#d97aff"/><stop offset=".42" stop-color="#9147ed"/><stop offset="1" stop-color="#4022a5"/></linearGradient>
<linearGradient id="wing" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#59d6ff"/><stop offset=".5" stop-color="#3373ff"/><stop offset="1" stop-color="#3d27d5"/></linearGradient>
<linearGradient id="glint"><stop stop-color="#bce9ff" stop-opacity="0"/><stop offset=".5" stop-color="#c5b8ff" stop-opacity=".22"/><stop offset="1" stop-color="#bce9ff" stop-opacity="0"/></linearGradient>
<radialGradient id="aura"><stop stop-color="#a845ff" stop-opacity=".24"/><stop offset="1" stop-color="#a845ff" stop-opacity="0"/></radialGradient>
<clipPath id="inside"><path d="M19 3H477L493 19V93L477 109H19L3 93V19Z"/></clipPath>
</defs>''')
    # A bevel, recessed face, engraved edge and corner catches; no blurred filter.
    add('<path d="M18 1H478L495 18V94L478 111H18L1 94V18Z" fill="url(#shell)" stroke="url(#rim)" stroke-width="2"/>')
    add('<path d="M22 8H474L488 22V90L474 104H22L8 90V22Z" fill="#0a1325" stroke="#31415b" stroke-width=".8"/>')
    add('<g clip-path="url(#inside)">')
    add('<path d="M20 10H475L488 23V42H126L110 26H20Z" fill="#1b2b43" opacity=".5"/>')
    add('<ellipse cx="64" cy="56" rx="65" ry="64" fill="url(#aura)" class="aura"/>')
    # Fine machining lines live behind the type, where motion never interrupts reading.
    for y in (18, 94):
        add(f'<path d="M118 {y}H441L452 {y+(-9 if y==18 else 9)}H472" fill="none" stroke="#263c58" stroke-width="1"/>')
        add(f'<path d="M118 {y}H441L452 {y+(-9 if y==18 else 9)}H472" fill="none" stroke="#75d9f3" stroke-width="1.6" pathLength="100" class="signal signal-{y}"/>')
    for x in range(140, 453, 8):
        add(f'<path d="M{x} 99v3" stroke="#4d627d" stroke-width=".7" opacity=".5"/>')
    add('<path d="M111 20V92M115 37V75" stroke="#415671" stroke-width="1"/>')
    add('<path d="M111 42V70" stroke="#9c8bff" stroke-width="2" class="aura"/>')
    # Segmented instrument ring. CSS rotation surrounds an unmoving, recognizable V.
    add('<circle cx="61" cy="56" r="43" fill="#10152e" stroke="#524074" stroke-width="1"/>')
    add('<g transform="translate(61 56)"><g class="orbit">')
    add('<circle r="40" fill="none" stroke="#5d82b8" stroke-width="1" stroke-dasharray="39 6 5 6 20 8"/>')
    add('<path d="M-12-38A40 40 0 0 1 12-38M-12 38A40 40 0 0 1-33 22" fill="none" stroke="#8edfff" stroke-width="2"/>')
    add('<path d="M0-42v4M42 0h-4M0 42v-4M-42 0h4" stroke="#99a7d2" stroke-width="1"/>')
    add('</g></g>')
    # Preserve the source logo's blue descending wings, violet diamond and nested core.
    add('<path d="M24 38H43L61 77L79 38H98L61 96Z" fill="url(#wing)"/>')
    add('<path d="M24 38H43L48 49H32Z" fill="#82caff" opacity=".6"/>')
    add('<path d="M79 38H98L91 49H74Z" fill="#1961f4"/>')
    add('<path d="M61 13L88 50L61 90L34 50Z" fill="#1b103c" stroke="url(#crystal)" stroke-width="3"/>')
    add('<path d="M61 24L78 47V65L61 82L44 65V47Z" fill="url(#crystal)" fill-opacity=".32" stroke="#e888ff" stroke-width="1.7"/>')
    add('<path d="M61 24V39L52 48V62L61 71V82M61 39L70 48V62L61 71M44 47L52 48M78 47L70 48M44 65L52 62M78 65L70 62" fill="none" stroke="#e888ff" stroke-width="1.4"/>')
    add('<path d="M61 40L69 48V61L61 70L53 61V48Z" fill="#c16aff" fill-opacity=".35" class="core"/>')
    add('<path d="M61 14L87 50L61 89L35 50Z" fill="none" stroke="#e8ceff" stroke-width="1.5" pathLength="100" class="facet"/>')
    add('<path d="M50 30L61 15L72 30" fill="none" stroke="#b9c7ff" stroke-width="1"/>')
    # Lettering is always fully present, including the first frame and every still.
    lettering("MADE WITH", 139, 28, 1, "#bdd1e5", 1.5)
    lettering("CAD-AGENT", 139, 54, 2.45, "#edf7ff", 1.35)
    add('<path d="M139 89H170" stroke="#bfa2ff" stroke-width="1.5"/>')
    add('<path d="M174 89H183M187 89H191" stroke="#4f799a" stroke-width="1.5"/>')
    add('<g fill="#a7bdcf"><path d="M460 29h5v5h-5Z"/><path d="M469 29h5v5h-5Z" opacity=".35"/></g>')
    add('<path d="M-100 0H-60L-15 112H-55Z" fill="url(#glint)" class="sweep"/>')
    add('</g>')
    add('<path d="M9 29V22L22 9H42M454 9H474L487 22V29M9 83V90L22 103H42M454 103H474L487 90V83" fill="none" stroke="#87acc7" stroke-width="1.1"/>')
    css = '''
.orbit{animation:orbit 24s linear infinite}
@keyframes orbit{to{transform:rotate(360deg)}}
.aura{animation:breathe 6s ease-in-out infinite}
@keyframes breathe{0%,100%{opacity:.65}50%{opacity:1}}
.core{animation:core 6s ease-in-out infinite}
@keyframes core{0%,100%{fill-opacity:.22}50%{fill-opacity:.65}}
.signal{stroke-dasharray:7 93;stroke-dashoffset:0}
.signal-18{animation:signal 8s linear infinite}
.signal-94{animation:signal 8s -4s linear infinite reverse}
@keyframes signal{to{stroke-dashoffset:-100}}
.facet{stroke-dasharray:14 86;stroke-dashoffset:0;animation:facet 6s linear infinite}
@keyframes facet{to{stroke-dashoffset:-100}}
.sweep{animation:sweep 12s ease-in-out infinite}
@keyframes sweep{0%,48%{transform:translateX(0)}85%,100%{transform:translateX(640px)}}
'''
    css += svg.REDUCED_MOTION
    if still:
        css += '*{animation:none!important}'
    title = "Made with cad-agent" + (" — still badge" if still else "")
    return svg.document(248, 56, title,
        "Valpatel's violet crystal and blue V, redrawn as vectors inside a small titanium instrument panel. "
        "Circuit signals, a segmented orbital ring and a slow light sweep surround permanently readable lettering. "
        "Reusable project attribution, not a certification. Generated by tools/anim/made_with_badge.py.",
        css, body, background=False)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    errors = []
    for still, output in ((False, OUT), (True, STILL_OUT)):
        text = build(still=still)
        errors.extend(f"{output.name}: {p}" for p in svg.problems(text, budget=20_000))
        if args.check:
            if not output.is_file() or output.read_text(encoding="utf-8") != text:
                errors.append(f"{output.name} differs; run tools/anim/made_with_badge.py")
        elif not errors:
            output.write_text(text, encoding="utf-8")
    for error in errors:
        print(error)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
