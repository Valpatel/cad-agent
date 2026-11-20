#!/usr/bin/env python3
"""Original conceptual workflow diagrams; no engineering results or universal host claim.
Run python3 tools/anim/documentation_flows.py [--check]. Stdlib only.
"""
import argparse
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'software'))
from cadagent.publish.anim import svg

OUT = ROOT / 'docs/img/architecture'
# Label, explanation, source owner. Arrows mean the documented handoff, not imports.
SCENES = {
 'toolkit-workflow': ('From a project to review', 'Workflows connect tools and reusable presentation.', [
  ('Project inputs', 'Models and assumptions', 'software/cadagent/project.py'),
  ('Domain methods', 'Calculate, build, check', 'software/cadagent/README.md'),
  ('Result artifacts', 'Values, files, evidence', 'software/cadagent/publish/README.md'),
  ('Human review', 'View, inspect, decide', 'software/cadagent/webkit/README.md')]),
 'agent-workflow': ('Skills guide the work', 'Review is a separate step, not an automatic approval.', [
  ('Choose a skill', 'Read sources and limits', '.agents/skills/README.md'),
  ('Use the toolkit', 'Produce a scoped change', 'software/cadagent/README.md'),
  ('Check the result', 'Tests and visible evidence', 'tests/README.md'),
  ('Peer review', 'Approve or return findings', '.agents/agents/cad-pr-reviewer.md')]),
 'site-publication': ('Source becomes a website', 'The generated site is an output, not the library owner.', [
  ('Owned sources', 'Guides, assets, metadata', 'docs/pages.yaml'),
  ('Site compiler', 'Select, link, render', 'tools/site/build-site.mjs'),
  ('Generated dist/', 'Pages and copied toolkit', 'tools/site/compiler/README.md'),
  ('Publish main', 'Cloudflare serves the build', '.github/CONTRIBUTING.md')]),
 'verification': ('What a check establishes', 'A passing test is evidence within its stated scope.', [
  ('Known inputs', 'Fixtures and assumptions', 'tests/fixtures/README.md'),
  ('Execute the subject', 'CLI, model or browser', 'tests/README.md'),
  ('Compare results', 'References and failures', 'tests/repo/README.md'),
  ('Keep the evidence', 'Source, result and limits', 'docs/validation/README.md')]),
 'scada-session': ('One process, several views', 'The host owns the session; diagrams observe its state.', [
  ('System + model', 'IDs, ports and equations', 'software/cadagent/webkit/scada/sim/README.md'),
  ('Shared session', 'Commands and steps', 'software/cadagent/webkit/scada/explorer/README.md'),
  ('Snapshot adapter', 'Readings and capabilities', 'software/cadagent/webkit/scada/sim/src/adapter.mjs'),
  ('Diagram views', 'Symbols and controls', 'software/cadagent/webkit/scada/ui/README.md')]),
}

# The visual grammar belongs to each subject; only paint/text primitives are shared.
CYAN = '#3de0d4'
VIOLET = '#bdacff'
AMBER = '#ffc579'


def text(x, y, value, size=16, anchor='start', color='#e9f5fb', weight=400):
    return (f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
            f'fill="{color}" font-weight="{weight}">{escape(value)}</text>')


def path(d, color=CYAN, cls='', width=2, arrow=False):
    marker = f' marker-end="url(#{"amber-arrow" if color == AMBER else "arrow"})"' if arrow else ''
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" class="{cls}"{marker}/>'


def panel(x, y, w, h, radius=10):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="#132f43" stroke="#4e8499"/>'


def cube(x, y, scale=1):
    return (f'<g transform="translate({x} {y}) scale({scale})">'
            + path('M0 -22L24 -10V18L0 32L-24 18V-10ZM-24 -10L0 4L24 -10M0 4V32') + '</g>')


def toolkit():
    """Documents enter tools; artifacts become a multi-pane human workspace."""
    parts = [text(24, 65, 'Build artifacts. Bring them into view.', color='#b7d1de'),
             path('M110 165H177', cls='flow', arrow=True),
             path('M294 165H350', cls='flow', arrow=True),
             path('M399 223V263H240V279', cls='flow', arrow=True)]
    parts += [path('M28 124V104H66L78 116H108V209H28Z', AMBER),
              path('M41 143H94M41 158H88M41 173H78', AMBER),
              text(68, 237, 'Inputs', anchor='middle')]
    teeth = ''.join(f'<path d="M-7 -59H7V-47H-7Z" transform="rotate({a})"/>' for a in range(0,360,45))
    parts += ['<g transform="translate(236 165)"><g class="gear" fill="#1e5366" stroke="#3de0d4">'
              + teeth + '<circle r="46"/><circle r="28" fill="#091a29"/></g></g>',
              path('M218 165L230 177L253 151', width=3), text(236, 237, 'Domain tools', anchor='middle')]
    parts += [panel(362,103,76,100,4),panel(353,113,76,100,4),cube(391,154,.66),
              path('M366 194H415', VIOLET),text(391,237,'Artifacts',anchor='middle')]
    parts += [panel(30,283,420,100), path('M174 299V345M309 299V345','#4e8499'),
              cube(87,323,.65),text(126,329,'3D',size=15),
              path('M192 345V307M192 345H290','#4e8499'),
              path('M195 337L213 327L233 335L251 313L286 306',VIOLET),
              path('M328 310L333 315L343 303M328 333L333 338L343 326'),
              path('M352 310H429M352 333H415','#b7d1de'),
              text(240,370,'Human review workspace',anchor='middle',weight=600)]
    return ''.join(parts)


def agent():
    """An independent review gate can return findings to the author."""
    parts = [text(24,65,'Produce, check, review — and revise.',color='#b7d1de')]
    parts += [path('M24 104Q48 94 72 108Q96 94 120 104V162Q96 152 72 166Q48 152 24 162ZM72 108V166',AMBER),
              text(72,192,'Skill',anchor='middle'),path('M125 135H172',cls='flow',arrow=True),
              panel(180,101,118,65),path('M194 117L206 128L194 139M216 141H240',CYAN),
              text(239,192,'Author',anchor='middle'),path('M305 135H347',cls='flow',arrow=True),
              panel(357,97,91,77,4),path('M370 113L376 119L386 106M370 137L376 143L386 130',CYAN,cls='check'),
              path('M398 114H436M398 138H436','#b7d1de'),text(402,192,'Checks',anchor='middle')]
    parts += [path('M402 204V278H314',cls='flow',arrow=True),
              '<path d="M240 222L310 278L240 334L170 278Z" fill="#282743" stroke="#bdacff" stroke-width="2"/>',
              text(240,273,'Peer',anchor='middle',weight=600),text(240,294,'review',anchor='middle',weight=600),
              path('M170 278H72V224H239V207',AMBER,'return',arrow=True),
              text(79,263,'Findings',size=15,color=AMBER),
              path('M240 335V357H352',cls='flow',arrow=True),
              text(393,363,'Pass',anchor='middle',weight=600),
              '<circle cx="363" cy="357" r="8" fill="#3de0d4"/>',
              text(24,400,'A separate reviewer decides; checks alone do not.',size=15,color='#b7d1de')]
    return ''.join(parts)


def publication():
    """Many owned sources are compiled to output, then published."""
    parts = [text(24,65,'Source owners stay outside generated dist/.',color='#b7d1de')]
    for x,label,color in [(80,'Guides',AMBER),(240,'Assets',VIOLET),(400,'Metadata',CYAN)]:
        parts += [f'<path d="M{x-24} 87H{x+11}L{x+24} 100V137H{x-24}Z" fill="#132f43" stroke="{color}"/>',
                  path(f'M{x+11} 87V100H{x+24}M{x-13} 110H{x+13}M{x-13} 122H{x+7}',color),
                  text(x,161,label,anchor='middle'),path(f'M{x} 172V193',cls='flow',arrow=True)]
    parts += ['<path d="M40 199H440L300 270H180Z" fill="#162d40" stroke="#4e8499" stroke-width="2"/>',
              path('M117 238H363',VIOLET,'scan'),text(240,225,'Site compiler',anchor='middle',weight=600),
              text(240,253,'Select · link · render',anchor='middle',size=15),
              path('M240 273V294H119V311',cls='flow',arrow=True),
              panel(53,315,128,60,4),panel(63,324,128,60,4),
              text(127,352,'dist/',anchor='middle',weight=600),text(127,373,'Build output',anchor='middle',size=15),
              path('M198 352H294',cls='flow',arrow=True),
              '<path d="M317 367C282 365 283 325 312 324C309 292 360 287 372 313C411 295 439 325 425 347C451 372 408 385 389 371H317Z" fill="#103c42" stroke="#3de0d4"/>',
              text(363,341,'Website',anchor='middle',weight=600),text(363,361,'Cloudflare',anchor='middle',size=15),
              text(24,411,'Released main is built and served to readers.',size=15,color='#b7d1de')]
    return ''.join(parts)


def verification():
    """Compare a result to a reference; preserve scope with the evidence."""
    parts = [text(24,65,'Compare results with a known reference.',color='#b7d1de'),
             panel(24,89,276,211),text(43,116,'Fixture → subject',weight=600),
             path('M45 252V140M45 252H280','#4e8499')]
    for y in [162,192,222]: parts.append(path(f'M45 {y}H280','#24485b',width=1))
    parts += [path('M48 239C84 239 79 163 116 174S151 235 184 191S239 152 277 153',CYAN,width=3),
              path('M48 241C84 237 81 169 117 179S152 239 185 196S239 156 277 158',VIOLET,width=2),
              path('M174 140V251',AMBER,'sweep'),
              path('M43 277H65',CYAN),text(72,282,'Reference',size=14),
              path('M179 277H201',VIOLET),text(208,282,'Result',size=14),
              path('M306 187H331',cls='flow',arrow=True),
              '<circle cx="388" cy="184" r="48" fill="#162d40" stroke="#bdacff" stroke-width="3"/>',
              text(388,183,'Δ',size=32,anchor='middle',color=VIOLET),
              text(388,208,'Compare',anchor='middle',size=15),
              text(388,255,'Pass / fail',anchor='middle'),
              path('M388 266V324H240V338',cls='flow',arrow=True),
              panel(24,343,432,40,5),text(240,369,'Evidence: result + revision + limits',anchor='middle',weight=600),
              text(24,411,'Illustrative traces; no measured data is shown.',size=15,color='#b7d1de')]
    return ''.join(parts)


def scada():
    """One shared state fans out; a view's commands return to the session."""
    parts = [text(24,65,'One running model. Several diagram views.',color='#b7d1de')]
    for x,y,h in [(38,96,70),(133,86,80)]:
        parts += [f'<path d="M{x} {y}V{y+h}Q{x+30} {y+h+16} {x+60} {y+h}V{y}Z" fill="#132f43" stroke="#4e8499"/>',
                  f'<path d="M{x+3} {y+36}Q{x+30} {y+29} {x+57} {y+36}V{y+h-2}Q{x+30} {y+h+10} {x+3} {y+h-2}Z" fill="#186c77"/>',
                  f'<ellipse cx="{x+30}" cy="{y}" rx="30" ry="10" fill="#203f50" stroke="#4e8499"/>',
                  path(f'M{x+4} {y+36}Q{x+30} {y+29} {x+56} {y+36}',CYAN,'level')]
    parts += [path('M98 147H133M193 147H238M268 147H303',cls='flow',width=3),
              '<path d="M238 134L268 160V134L238 160Z" fill="#103c42" stroke="#3de0d4"/>',
              panel(332,104,116,70,4),text(390,131,'PLC',anchor='middle',weight=600),
              '<circle class="check" cx="355" cy="152" r="5" fill="#3de0d4"/>',
              path('M369 152H432',CYAN),
              path('M390 177V201H294V165H274',AMBER,'return',arrow=True),
              text(24,199,'Equipment + control model',size=15,color='#b7d1de'),
              path('M240 166V217',cls='flow',arrow=True),panel(142,222,196,55),
              text(240,245,'Shared session',anchor='middle',weight=600),
              text(240,266,'State + commands',anchor='middle',size=15),
              path('M240 282V309H86V327',cls='flow',arrow=True),
              path('M240 309V327',cls='flow',arrow=True),
              path('M240 309H394V327',cls='flow',arrow=True)]
    for x,label in [(20,'Plant'),(174,'Sludge'),(328,'Digesters')]:
        parts += [panel(x,333,132,54,4),path(f'M{x+12} 348H{x+40}V361H{x+61}M{x+40} 348H{x+118}',CYAN),
                  text(x+66,378,label,anchor='middle',size=15)]
    parts += [path('M19 359H9V249H135',AMBER,'return',arrow=True),
              text(240,408,'Snapshots ↓   •   Controls return to the session',anchor='middle',size=15,color='#b7d1de')]
    return ''.join(parts)


DRAW = {'toolkit-workflow': toolkit, 'agent-workflow': agent,
        'site-publication': publication, 'verification': verification, 'scada-session': scada}


def render(name, title, subtitle, nodes, still=False):
    desc = '. '.join(f'{label}: {detail}. Source: {source}' for label,detail,source in nodes)
    motion = '' if still else (
        '.flow{animation:flow 2.8s linear infinite}.return{animation:flow 4s linear infinite}'
        '.gear{animation:turn 20s linear infinite}.scan{animation:scan 3s ease-in-out infinite alternate}'
        '.check,.level{animation:readout 2s ease-in-out infinite alternate}'
        '.sweep{animation:sweep 4s ease-in-out infinite alternate}@keyframes sweep{from{transform:translateX(-90px)}to{transform:translateX(90px)}}'
        '@keyframes flow{to{stroke-dashoffset:-28}}@keyframes turn{to{transform:rotate(360deg)}}'
        '@keyframes scan{to{opacity:.25}}@keyframes readout{to{opacity:.5}}' + svg.REDUCED_MOTION)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="480" height="430" viewBox="0 0 480 430" '
            'role="img" aria-labelledby="title desc">'
            f'<title id="title">{escape(title)}</title><desc id="desc">Conceptual illustration, '
            f'not measured simulation. {escape(subtitle)} {escape(desc)}</desc>\n'
            '<style>text{font-family:system-ui,sans-serif}.flow,.return{stroke-dasharray:6 8}'
            + motion + '</style>\n'
            '<defs><marker id="amber-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#ffc579"/></marker><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" '
            'markerHeight="4" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="#3de0d4"/></marker></defs>\n'
            '<rect width="480" height="430" rx="18" fill="#091a29"/>\n'
            + text(24,34,title,size=22,weight=700) + '\n' + DRAW[name]() + '\n</svg>\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    bad=[]
    for name,(title,subtitle,nodes) in SCENES.items():
        for _,_,source in nodes:
            if not (ROOT/source).is_file():raise SystemExit(f'Missing source owner: {source}')
        for still in (False,True):
            target=OUT/f'{name}{"-still" if still else ""}.svg';expected=render(name,title,subtitle,nodes,still)
            if args.check:
                if not target.is_file() or target.read_text()!=expected:bad.append(str(target.relative_to(ROOT)))
            else:target.parent.mkdir(parents=True,exist_ok=True);target.write_text(expected)
    if bad:raise SystemExit('Stale documentation figures: '+', '.join(bad))
    print('documentation-flows: 10 SVGs '+('verified' if args.check else 'generated'))
if __name__=='__main__':main()
