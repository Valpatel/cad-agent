"""A shared XY drawing for engraved enclosure markings and a matching SVG proof.

Units are millimetres. Connector pin numbering/view direction remain the caller's
responsibility. The drawing is original geometry, not a manufacturer CAD model.
"""
import math
from html import escape
from cadagent._deps import require

class PanelMarkings:
    def __init__(self):
        self.items = []

    def text(self, text, x, y, size, *, bold=False):
        if size <= 0:
            raise ValueError('Text height must be positive')
        self.items.append(('text', str(text), x, y, size, bold))

    def line(self, points, width=0.6):
        if len(points) < 2 or width <= 0:
            raise ValueError('A stroke requires two points and positive width')
        self.items.append(('line', list(points), width))

    def circle(self, x, y, radius, width=0.5):
        if not radius > width / 2 > 0:
            raise ValueError('Require radius > half stroke width > 0')
        self.items.append(('circle', x, y, radius, width))

    def solids(self, z, height):
        """Extrude drawing strokes into a compound at the supplied face datum."""
        cq = require('cadquery', 'panel markings')
        parts = []
        for kind, *args in self.items:
            if kind == 'text':
                text, x, y, size, bold = args
                parts.extend(cq.Workplane('XY').text(
                    text, size, height, font='DejaVu Sans',
                    kind='bold' if bold else 'regular', combine=False
                ).val().translate((x, y, z)).Solids())
            elif kind == 'circle':
                x, y, r, w = args
                parts.append(cq.Workplane('XY').circle(r+w/2).circle(r-w/2)
                             .extrude(height).val().translate((x,y,z)))
            else:
                points, width = args
                for (x1,y1),(x2,y2) in zip(points, points[1:]):
                    length = math.hypot(x2-x1,y2-y1)
                    if length == 0:
                        continue
                    parts.append(cq.Workplane('XY').box(length,width,height,
                                 centered=(False,True,False)).val()
                                 .rotate((0,0,0),(0,0,1),math.degrees(math.atan2(y2-y1,x2-x1)))
                                 .translate((x1,y1,z)))
                for x,y in points:
                    parts.append(cq.Solid.makeCylinder(width/2,height,cq.Vector(x,y,z)))
        return cq.Compound.makeCompound(parts)

    def engrave(self, shape, face_z, depth):
        """Cut each drawing item separately, avoiding overlapping-tool compounds.

        OCCT can spend many minutes resolving a compound of overlapping stroke
        caps/circles. Fuse only the small per-item tool, then perform one cut.
        Font kerning can also create tiny glyph overlaps: a cut with that raw
        compound can look valid in BREP yet tessellate into non-manifold edges.
        """
        if depth <= 0:
            raise ValueError('Engraving depth must be positive')
        for item in self.items:
            one = PanelMarkings()
            one.items = [item]
            tool = one.solids(face_z-depth, depth+.2)
            solids = tool.Solids()
            if item[0] in {'line', 'text'} and len(solids) > 1:
                tool = solids[0].fuse(*solids[1:])
            shape = shape.cut(tool)
        return shape

    def svg(self, bounds, *, background='#24414c', ink='#e9eddc'):
        """Export the identical drawing plan, viewed toward the XY face from +Z."""
        x0,y0,width,height=bounds
        out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {-y0-height} {width} {height}">',
             f'<rect x="{x0}" y="{-y0-height}" width="{width}" height="{height}" rx="1.2" fill="{background}"/>']
        for kind,*args in self.items:
            if kind=='text':
                text,x,y,size,bold=args
                out.append(f'<text x="{x}" y="{-y}" font-family="DejaVu Sans,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" dominant-baseline="central" text-anchor="middle" fill="{ink}">{escape(text)}</text>')
            elif kind=='circle':
                x,y,r,w=args
                out.append(f'<circle cx="{x}" cy="{-y}" r="{r}" fill="none" stroke="{ink}" stroke-width="{w}"/>')
            else:
                points,w=args
                pts=' '.join(f'{x},{-y}' for x,y in points)
                out.append(f'<polyline points="{pts}" fill="none" stroke="{ink}" stroke-width="{w}" stroke-linejoin="round" stroke-linecap="round"/>')
        return '\n'.join(out+['</svg>'])
