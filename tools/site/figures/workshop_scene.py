"""Original cinematic technical workshop: projected illustration, never an engineering result.

One consistent orthographic camera, anchored machinery, a human input station and
an eight-second build/test/revise/share story. No faces, vendor models or random particles.
"""
import math
from xml.sax.saxutils import escape
from cadagent.publish.anim.svg import REDUCED_MOTION


def render(mobile=False):
    width,height=(1000,1000) if mobile else (1440,640)
    scale=36 if mobile else 48
    centre,ground=(500,650) if mobile else (720,520)
    def project(p):
        x,y,z=p
        return centre+scale*(x-y),ground+scale*(.46*(x+y)-1.12*z)
    def path(points,close=False):
        return 'M'+'L'.join(f'{x:.2f} {y:.2f}' for x,y in points)+('Z' if close else '')
    def line3(points,stroke='#5a8894',sw=1,cls='',opacity=1):
        return f'<path d="{path([project(p) for p in points])}" fill="none" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}" class="{cls}"/>'
    def add(a,b):return tuple(x+y for x,y in zip(a,b))
    def mul(a,k):return tuple(x*k for x in a)
    def sub(a,b):return tuple(x-y for x,y in zip(a,b))
    def dot(a,b):return sum(x*y for x,y in zip(a,b))
    def cross(a,b):return(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    def norm(a):return mul(a,1/math.sqrt(dot(a,a)))
    def shade(colour,factor):
        return '#'+''.join(f'{max(0,min(255,round(int(colour[i:i+2],16)*factor))):02x}' for i in (1,3,5))
    faces=[(0,3,2,1),(0,1,5,4),(0,4,7,3),(1,2,6,5),(2,3,7,6),(4,5,6,7)]
    def mesh(vertices,colour='#728c98',edge='#8babb5'):
        visible=[]
        for face in faces:
            ps=[vertices[i] for i in face];n=norm(cross(sub(ps[1],ps[0]),sub(ps[2],ps[0])))
            if dot(n,(1,1,.82))<=0:continue
            light=.57+.5*max(0,dot(n,norm((-.3,-.4,1))))
            visible.append((sum(sum(p) for p in ps),f'<path d="{path([project(p) for p in ps],True)}" fill="{shade(colour,light)}" stroke="{edge}" stroke-width="1.2" stroke-linejoin="round"/>'))
        return ''.join(value for _,value in sorted(visible))
    def box(c,d,colour='#728c98',edge='#8babb5'):
        x,y,z=c;dx,dy,dz=d
        return mesh([(x+sx*dx/2,y+sy*dy/2,z+sz*dz) for sz in (0,1) for sy,sx in [(-1,-1),(-1,1),(1,1),(1,-1)]],colour,edge)
    def beam(a,b,w=.48,d=.55,colour='#94a8af'):
        along=norm(sub(b,a));u=norm(cross(along,(0,1,0))) if abs(along[1])<.99 else(1,0,0);v=norm(cross(along,u))
        vertices=[add(p,add(mul(u,sx*w/2),mul(v,sy*d/2))) for p in (a,b) for sy,sx in [(-1,-1),(-1,1),(1,1),(1,-1)]]
        return mesh(vertices,colour,'#8aabb4')
    def joint(c,r=.32,axis=(0,1,0),accent='#d3b17a'):
        axis=norm(axis);u=norm(cross(axis,(0,0,1))) if abs(axis[2])<.99 else(1,0,0);v=norm(cross(axis,u))
        def ring(radius):return [project(add(c,add(mul(u,math.cos(t)*radius),mul(v,math.sin(t)*radius)))) for t in [j*math.tau/48 for j in range(49)]]
        result=f'<path d="{path(ring(r),True)}" fill="#172b36" stroke="{accent}" stroke-width="3"/><path d="{path(ring(r*.65),True)}" fill="#48636f" stroke="#a0b9bf" stroke-width="1"/>'
        for t in [math.pi/4+j*math.pi/2 for j in range(4)]:
            x,y=project(add(c,add(mul(u,math.cos(t)*r*.8),mul(v,math.sin(t)*r*.8))))
            result+=f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.6" fill="#d1e2e3"/>'
        return result
    def arm(points,colour='#a0afb4',small=False):
        r=.22 if small else .4;result=''
        for a,b in zip(points,points[1:]):result+=beam(a,b,.28 if small else .62,.34 if small else .68,colour)
        for p in points:result+=joint(p,r)
        return result
    def table(c,size):
        x,y=c;dx,dy=size;result=box((x,y,1.45),(dx,dy,.42),'#263f4c','#577e8b')
        for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]:result+=box((x+sx*(dx/2-.28),y+sy*(dy/2-.28),0),(.26,.26,1.45),'#1c303c','#355361')
        for j in range(11):
            u=x-dx/2+j*dx/10;result+=line3([(u,y-dy/2,1.89),(u,y+dy/2,1.89)],'#416675',.65,opacity=.65)
        for j in range(6):
            v=y-dy/2+j*dy/5;result+=line3([(x-dx/2,v,1.89),(x+dx/2,v,1.89)],'#416675',.65,opacity=.65)
        return result
    def module(c,revised=True):
        x,y,z=c;result=box(c,(1.25,1,.25),'#607f8a','#a4c8cd')
        pts=[(x,y,z+.3),(x-.15,y,z+1.6),(x+1.05,y,z+(1.75 if revised else .95))]
        result+=arm(pts,'#8ba2aa' if revised else '#b68b5b',True)
        result+=box((x+.4,y,z+.3),(.8,.6,.16),'#3a777b' if revised else '#806242')
        if revised:result+=beam((x+.5,y,z+.3),(x-.15,y,z+1.1),.18,.18,'#63b9a7')
        return result
    css=REDUCED_MOTION+'''
.flow{stroke-dasharray:5 12;animation:signal 2s linear infinite}.toolhead{animation:tool 8s ease-in-out infinite}.testprobe{animation:test 8s ease-in-out infinite}.first-version{animation:first 8s linear infinite}.revised-version{opacity:1;animation:revision 8s ease-in-out infinite}.receiving{animation:receive 8s ease-in-out infinite}.human-input{transform-origin:0 100%;animation:input 8s ease-in-out infinite}.core-pulse{animation:core 8s linear infinite}.test-fault{opacity:0;animation:fault 8s linear infinite}.still{display:none}
@keyframes signal{to{stroke-dashoffset:-102}}
@keyframes tool{0%,12%{transform:translateY(-20px)}24%,34%{transform:translateY(0)}45%,56%{transform:translateY(-16px)}68%,86%{transform:translateY(0)}100%{transform:translateY(-20px)}}
@keyframes test{0%,25%,77%,100%{transform:translate(18px,8px)}35%,65%{transform:translate(0,0)}}
@keyframes first{0%,48%{opacity:1}55%,100%{opacity:0}}
@keyframes revision{0%,47%{opacity:0;transform:translateY(-22px)}67%,100%{opacity:1;transform:translateY(0)}}
@keyframes receive{0%,65%{opacity:.2}82%,100%{opacity:1}}
@keyframes input{0%,28%,100%{transform:translate(0,0)}40%,48%{transform:translate(4px,-5px)}60%,88%{transform:translate(0,0)}}
@keyframes core{0%,45%{opacity:.45}56%,100%{opacity:1}}
@keyframes fault{0%,31%,60%,100%{opacity:0}38%,48%{opacity:1}}
@media(prefers-reduced-motion:reduce){.first-version,.test-fault{display:none}.revised-version,.receiving,.core-pulse{opacity:1;transform:none}.toolhead,.testprobe,.human-input{transform:none}.moving{display:none}.still{display:inline}}
'''
    s=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="A human and precise maker machines build, test, revise and teach the next machine" aria-labelledby="title" aria-describedby="desc"><title id="title">A shared workshop that learns from each build</title><desc id="desc">Original cinematic sci-fi workshop illustration. Human insight enters a warm input station. A precision maker arm constructs a small successor machine, a test reveals blocked access, feedback changes the joint and reinforcement, and a second anchored station receives the improved design. Shared source knowledge, including a MANUFACTURER GUIDE with source, edition, limits, is represented by the luminous design core. An eight-second conceptual story, not a hardware simulation or automatic model training; Human-reviewed contributions remain the real improvement mechanism.</desc><defs><radialGradient id="room"><stop stop-color="#193541"/><stop offset="1" stop-color="#080f18"/></radialGradient><linearGradient id="hand" x2=".8" y2="1"><stop stop-color="#f4d1ac"/><stop offset=".6" stop-color="#c89773"/><stop offset="1" stop-color="#91684e"/></linearGradient><linearGradient id="sleeve"><stop stop-color="#34424d"/><stop offset="1" stop-color="#111e2a"/></linearGradient><radialGradient id="warm"><stop stop-color="#edb26b" stop-opacity=".24"/><stop offset="1" stop-color="#edb26b" stop-opacity="0"/></radialGradient><radialGradient id="cyan"><stop stop-color="#69d4cf" stop-opacity=".22"/><stop offset="1" stop-color="#69d4cf" stop-opacity="0"/></radialGradient><filter id="bloom"><feGaussianBlur stdDeviation="7"/></filter></defs><style>{css}</style><rect width="{width}" height="{height}" rx="26" fill="url(#room)"/>'''
    # Architectural grid and controlled pools of light, all tied to the same camera.
    s+=f'<ellipse cx="{width*.28}" cy="{height*.73}" rx="{width*.36}" ry="{height*.3}" fill="url(#warm)"/><ellipse cx="{width*.68}" cy="{height*.62}" rx="{width*.38}" ry="{height*.4}" fill="url(#cyan)"/>'
    for j in range(-14,15):s+=line3([(j,-11,0),(j,12,0)],'#29434f',.65,opacity=.6)+line3([(-14,j,0),(14,j,0)],'#29434f',.65,opacity=.6)
    for x in [-9,-3,3,9]:
        s+=box((x,-7,0),(.2,.2,7.4),'#152a37','#294555')
        s+=line3([(x,-7,1),(x,-7,7)],'#6bb5bb',1.5,opacity=.35)
    # Second station sits behind, not in an unanchored floating panel.
    s+=table((5.6,-3.7),(3.8,2.8))
    s+=box((6.3,-4,1.9),(1,.9,.45),'#273f4e')
    s+=arm([(6.3,-4,2.35),(6.4,-4,4.2),(4.8,-3.6,4.1)],'#819ba6')
    s+='<g class="receiving">'+module((4.8,-3.2,1.9),True)+'</g>'
    # Main slotted fixture and maker arm.
    s+=table((-.7,1),(7.3,4.5))
    s+=box((-2.9,-.3,1.9),(1.4,1.3,.55),'#263b49')
    s+=joint((-2.9,-.3,2.5),.65,(0,0,1),'#8ebfc1')
    s+=arm([(-2.9,-.3,2.55),(-2.3,-.3,5.2),(-.2,1.2,5.25)],'#99aab1')
    s+='<g class="toolhead">'+beam((-.2,1.2,5.25),(-.2,1.2,4.12),.32,.36,'#344e60')
    s+=box((-.2,1.2,3.95),(.7,.6,.2),'#7c969f')
    s+=beam((-.48,1.2,4.05),(-.48,1.2,3.7),.12,.16,'#bfccd0')+beam((.08,1.2,4.05),(.08,1.2,3.7),.12,.16,'#bfccd0')+'</g>'
    s+=box((-.45,2,1.9),(2.8,1.9,.22),'#344f5c','#7dabb4')
    s+='<g class="first-version">'+module((-.7,2,2.12),False)+'</g><g class="revised-version">'+module((-.7,2,2.12),True)+'</g>'
    # A real-looking physical probe checks the access path; no numerical verdict is fabricated.
    s+='<g class="testprobe">'+box((1.2,2,2.13),(.4,1.2,1.15),'#294654')+beam((1.2,2,3.23),(.55,2,3.23),.14,.2,'#c3d2d5')+'</g>'
    px,py=project((.55,2,3.23));s+=f'<g class="test-fault"><circle cx="{px:.2f}" cy="{py:.2f}" r="18" fill="#ef9b66" opacity=".18"/><path d="M{px-9} {py-9}l18 18m-18 0l18-18" stroke="#ffb17c" stroke-width="2.5"/></g>'
    # Shared design core is mounted on a tower, with purposeful connections to both stations.
    s+=box((1,-3,0),(1.3,1.3,.35),'#1b303e')+box((1,-3,.35),(.45,.45,3.5),'#294654')
    s+=box((1,-3,3.85),(2.2,1.7,1.9),'#254e5a','#62b7b7')
    cx,cy=project((1,-3,4.95));s+=f'<g class="core-pulse"><path d="M{cx-45} {cy-34}h90v68h-90Z" fill="#0b2631" stroke="#7edbd1" stroke-width="1.4"/>'
    nodes=[(-25,-15),(0,-15),(25,-15),(-25,7),(0,7),(25,7),(-25,25),(0,25),(25,25)]
    for a,b in [(0,1),(1,2),(1,4),(4,3),(4,5),(4,7),(7,6),(7,8)]:
        s+=f'<path d="M{cx+nodes[a][0]} {cy+nodes[a][1]}L{cx+nodes[b][0]} {cy+nodes[b][1]}" stroke="#70cfc9" stroke-width="1.3"/>'
    for x,y in nodes:s+=f'<circle cx="{cx+x}" cy="{cy+y}" r="3" fill="#a6f1d9"/>'
    s+='</g>'
    s+=line3([(1,-3,4.5),(-2.9,-.3,4.9)],'#72c9c9',2,'flow',.8)+line3([(1,-3,4.5),(6.3,-4,3.2)],'#72c9c9',2,'flow',.8)
    # Human workstation: a softly drawn hand, not an uncanny face or polygon portrait.
    s+=table((-6.2,3.4),(3.5,2.2))
    screen=[(-7.6,2.5,1.95),(-4.8,2.5,1.95),(-4.8,4.3,1.95),(-7.6,4.3,1.95)]
    s+=f'<path d="{path([project(p) for p in screen],True)}" fill="#0c2632" stroke="#ddb782" stroke-width="2"/>'
    for j in range(5):s+=line3([(-7.35,2.7+j*.24,1.99),(-6.4,2.7+j*.24,1.99)],'#d0b48a',1.3,opacity=.85)
    s+=line3([(-6.2,3.9,2),(-6.2,2.9,2),(-5.55,2.9,2),(-5.55,3.4,2),(-5.05,3.4,2)],'#89ddd0',2.2,'flow')
    tipx,tipy=project((-5.6,3.35,2.02));hx,hy=tipx-155,tipy-20
    s+=f'<g transform="translate({hx:.2f} {hy:.2f})"><g class="human-input"><path d="M-120 300C-65 250-12 210 25 178L112 240C55 295-5 335-65 365Z" fill="url(#sleeve)" stroke="#53616a" stroke-width="2"/><path d="M18 180C30 155 48 136 68 119L139 24C147 13 159 15 165 24C171 34 163 45 156 54L118 106L133 89C141 81 151 87 150 97L140 120L153 108C162 99 171 108 165 120L150 149C139 174 119 191 100 208L75 232Z" fill="url(#hand)" stroke="#9a765d" stroke-width="1.8"/><path d="M68 119q21 3 34 18M93 160q17-4 29 4M142 32l10 5" fill="none" stroke="#9b7358" stroke-width="1.3"/><path d="M26 181l55 46" stroke="#d1ac81" stroke-width="3"/></g></g>'
    s+=line3([(-5.6,3.35,2.05),(1,-3,4.5)],'#d7ae74',1.8,'flow',.8)
    return s+'</svg>\n'
