#!/usr/bin/env python3
"""Original conceptual workflow diagrams; no engineering results or universal host claim.
Run python3 tools/anim/documentation_flows.py [--check]. Stdlib only.
"""
import argparse
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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

def render(title, subtitle, nodes, still=False):
    desc = '. '.join(f'{i+1}. {label}: {detail}. Source: {source}' for i,(label,detail,source) in enumerate(nodes))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="350" viewBox="0 0 480 350" role="img" aria-labelledby="title desc"><title id="title">{escape(title)}</title><desc id="desc">Conceptual handoffs, not measured simulation. {escape(desc)}</desc>',
      '<style>text{font-family:system-ui,sans-serif;fill:#e9f5fb}.detail{fill:#b7d1de;font-size:14px}.flow{stroke:#3de0d4;stroke-width:3;stroke-dasharray:6 8;fill:none}' + ('' if still else '.flow{animation:flow 2.8s linear infinite}@keyframes flow{to{stroke-dashoffset:-28}}@media(prefers-reduced-motion:reduce){.flow{animation:none}}') + '</style>',
      '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#3de0d4"/></marker></defs>',
      '<rect width="480" height="350" rx="18" fill="#091a29"/>',
      f'<text x="24" y="34" font-size="22" font-weight="700">{escape(title)}</text>',
      '<path class="flow" d="M218 125H258" marker-end="url(#arrow)"/><path class="flow" d="M362 170V202" marker-end="url(#arrow)"/><path class="flow" d="M262 251H222" marker-end="url(#arrow)"/>']
    for i,((label,detail,source),(x,y)) in enumerate(zip(nodes,[(20,80),(262,80),(262,206),(20,206)])):
        parts += [f'<rect x="{x}" y="{y}" width="198" height="90" rx="12" fill="#132f43" stroke="#4e8499"/>',
          f'<circle cx="{x+19}" cy="{y+20}" r="11" fill="#265269"/><text x="{x+19}" y="{y+25}" text-anchor="middle" font-size="14">{i+1}</text>',
          f'<text x="{x+12}" y="{y+49}" font-size="18" font-weight="600">{escape(label)}</text>',
          f'<text class="detail" x="{x+12}" y="{y+72}">{escape(detail)}</text>']
    parts += [f'<text class="detail" x="24" y="326">{escape(subtitle)}</text>','</svg>\n']
    return '\n'.join(parts)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    bad=[]
    for name,(title,subtitle,nodes) in SCENES.items():
        for _,_,source in nodes:
            if not (ROOT/source).is_file():raise SystemExit(f'Missing source owner: {source}')
        for still in (False,True):
            target=OUT/f'{name}{"-still" if still else ""}.svg';expected=render(title,subtitle,nodes,still)
            if args.check:
                if not target.is_file() or target.read_text()!=expected:bad.append(str(target.relative_to(ROOT)))
            else:target.parent.mkdir(parents=True,exist_ok=True);target.write_text(expected)
    if bad:raise SystemExit('Stale documentation figures: '+', '.join(bad))
    print('documentation-flows: 10 SVGs '+('verified' if args.check else 'generated'))
if __name__=='__main__':main()
