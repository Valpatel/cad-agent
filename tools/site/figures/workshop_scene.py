"""Original 16-bit orbital workshop, drawn on one 768 × 384 pixel grid.

Twelve-second story: assemble (0–3.4 s), test (3.4–5.3 s), share the
build guide (5.5–8 s), join the crew (8–10 s), load the next build (10–12 s).
Every sprite and glyph is original. CSS only; no external art or font assets.
The separate image-consumer still is produced by learning-home.finished_still.
"""
from cadagent.publish.anim.svg import REDUCED_MOTION

P={'ink':'#111329','deep':'#191c36','night':'#222643','steel':'#343a58','mid':'#4a5773','edge':'#708aa0','ice':'#aec9cc','cream':'#f2e5bd','gold':'#e9b86a','orange':'#ce784d','rust':'#874651','red':'#c45064','mint':'#91dfbf','teal':'#4aa69e','blue':'#427b98','navy':'#2c4b70','violet':'#665c87'}

def R(x,y,w,h,c,extra=''):
 return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{P.get(c,c)}" {extra}/>'
def Q(points,c,extra=''):
 return f'<path d="M'+ 'L'.join(f'{x} {y}' for x,y in points)+f'Z" fill="{P.get(c,c)}" {extra}/>'
def line(points,c,w=1,extra=''):
 return f'<path d="M'+ 'L'.join(f'{x} {y}' for x,y in points)+f'" fill="none" stroke="{P.get(c,c)}" stroke-width="{w}" {extra}/>'
def stepped_box(x,y,w,h,c,edge=None):
 s=Q([(x+3,y),(x+w-3,y),(x+w-3,y+3),(x+w,y+3),(x+w,y+h-3),(x+w-3,y+h-3),(x+w-3,y+h),(x+3,y+h),(x+3,y+h-3),(x,y+h-3),(x,y+3),(x+3,y+3)],c)
 if edge:s+=R(x+4,y,w-8,2,edge)
 return s

def star(x,y,sz,c):
 return R(x,y,sz,sz,c)+R(x+sz,y-sz,sz,sz*3,c)+R(x+sz*2,y,sz,sz,c)
def screw(x,y,c='edge'):
 return R(x,y,3,3,'ink')+R(x,y,2,1,c)
def panel(x,y,w,h):
 s=R(x,y,w,h,'ink')+R(x+2,y+2,w-4,h-4,'steel')+R(x+3,y+3,w-6,2,'mid')
 for xx in [x+4,x+w-7]:
  for yy in [y+4,y+h-7]:s+=screw(xx,yy)
 return s

def small_robot(cls=''):
 """An original compact robot; origin is the centre of the feet."""
 s=f'<g class="{cls}">'
 # Independent articulated ankles and boots.
 s+='<g class="kid-leg-left">'+R(-17,-20,11,13,'mid')+R(-18,-16,10,12,'ice')+stepped_box(-23,-7,18,8,'ink')+R(-21,-6,15,4,'cream')+R(-21,-2,15,2,'mid')+'</g>'
 s+='<g class="kid-leg-right">'+R(6,-20,11,13,'mid')+R(8,-16,10,12,'ice')+stepped_box(5,-7,18,8,'ink')+R(7,-6,15,4,'cream')+R(7,-2,15,2,'mid')+'</g>'
 s+=stepped_box(-20,-51,40,34,'ink')+stepped_box(-18,-49,36,30,'ice','cream')+R(-16,-43,7,19,'cream')+R(12,-42,6,21,'edge')+R(-7,-44,17,18,'steel')+R(-5,-42,13,14,'deep')
 s+='<g class="kid-core">'+R(-2,-39,7,2,'mint')+R(-4,-37,11,3,'teal')+R(-2,-34,7,2,'mint')+R(0,-32,3,2,'cream')+'</g>'
 s+=R(-13,-23,25,3,'steel')+R(-11,-23,7,1,'orange')
 s+='<g class="kid-arms">'
 s+='<g class="kid-arm-left">'+R(-25,-44,8,9,'mid')+R(-28,-39,8,15,'ice')+R(-28,-39,3,14,'cream')+R(-29,-26,10,7,'steel')+R(-29,-20,3,5,'ice')+R(-22,-20,3,5,'ice')+'</g>'
 s+='<g class="kid-arm-right">'+R(17,-44,8,9,'mid')+R(20,-39,8,15,'ice')+R(25,-39,3,14,'edge')+R(19,-26,10,7,'steel')+R(19,-20,3,5,'ice')+R(26,-20,3,5,'ice')+'</g></g>'
 # Head is held by a visible magnetic lifting tool during assembly.
 s+='<g class="kid-head">'+R(-8,-58,16,8,'mid')+stepped_box(-24,-83,48,29,'ink')+stepped_box(-22,-81,44,25,'cream')+R(-20,-77,40,17,'steel')+R(-18,-75,36,14,'deep')+R(-18,-75,36,2,'navy')+R(18,-75,3,15,'edge')+R(-22,-59,44,3,'ice')
 s+='<g class="kid-eyes">'+R(-12,-70,7,5,'mint')+R(5,-70,7,5,'mint')+R(-11,-69,3,2,'cream')+R(6,-69,3,2,'cream')+'</g>'
 s+='<g class="boot-eye">'+R(-12,-69,7,2,'gold')+R(5,-69,7,2,'gold')+'</g>'
 s+=R(-27,-72,4,11,'mid')+R(24,-72,4,11,'mid')+R(-4,-86,8,3,'edge')+'</g></g>'
 return s

def builder_left():
 s='<g id="builder-left" transform="translate(246 283)">'
 s+=R(-29,0,66,5,'ink')
 s+='<g class="left-body">'
 # Boots and legs have different planes, articulated knees and little wear pixels.
 s+='<g class="builder-step-left">'+R(-21,-32,15,27,'steel')+R(-19,-29,12,19,'rust')+R(-18,-28,8,7,'orange')+stepped_box(-26,-11,23,12,'ink')+R(-24,-9,20,7,'gold')+R(-25,-3,21,4,'rust')+'</g>'
 s+='<g class="builder-step-right">'+R(7,-30,15,25,'steel')+R(9,-28,11,18,'rust')+R(10,-27,7,7,'orange')+stepped_box(5,-11,24,12,'ink')+R(7,-9,20,7,'orange')+R(7,-9,13,2,'gold')+R(6,-3,21,4,'rust')+'</g>'
 # Body front and backpack.
 s+=stepped_box(-32,-70,13,36,'ink')+R(-31,-67,10,28,'steel')+R(-29,-63,4,18,'mid')
 s+=stepped_box(-23,-76,50,49,'ink')+stepped_box(-21,-74,46,44,'orange','gold')+R(-19,-70,8,32,'gold')+R(16,-67,7,34,'rust')+R(-9,-66,23,20,'rust')+R(-7,-64,19,16,'deep')+R(-4,-60,4,8,'teal')+R(2,-60,7,3,'mint')+R(2,-55,5,3,'mint')
 s+=R(-8,-40,21,5,'steel')+R(-5,-39,3,2,'edge')+R(1,-39,3,2,'edge')+R(7,-39,3,2,'edge')+R(-16,-33,4,2,'cream')
 s+=R(-8,-82,24,8,'steel')+stepped_box(-26,-109,57,32,'ink')+stepped_box(-24,-107,53,28,'gold','cream')+R(-22,-102,48,18,'rust')+R(-20,-100,45,16,'deep')+R(-20,-100,45,3,'navy')+R(23,-102,4,20,'orange')
 s+='<g class="left-eyes">'+R(-9,-94,10,6,'ice')+R(10,-94,10,6,'ice')+R(-7,-93,4,3,'mint')+R(12,-93,4,3,'mint')+'</g>'
 s+=R(-28,-99,4,15,'steel')+R(31,-99,4,15,'rust')+R(7,-116,3,9,'mid')+R(4,-119,9,4,'gold')+R(6,-120,4,2,'cream')
 # Near shoulder anchors to a two-segment industrial arm. Whole arm reaches around this hinge.
 s+='<g class="left-arm">'+stepped_box(21,-70,17,16,'ink')+R(24,-68,11,11,'gold')+R(27,-65,5,5,'rust')+Q([(31,-60),(40,-58),(49,-44),(44,-36),(38,-38),(30,-54)],'rust')+Q([(35,-59),(41,-56),(48,-45),(44,-41),(39,-46)],'orange')+stepped_box(39,-44,14,14,'ink')+R(42,-42,8,8,'mid')+R(44,-41,4,3,'ice')
 s+='<g class="left-forearm">'+Q([(46,-41),(66,-52),(72,-45),(51,-30)],'ink')+Q([(48,-39),(65,-48),(68,-45),(51,-34)],'gold')+R(64,-53,9,11,'steel')+R(70,-56,4,7,'ice')+R(70,-44,4,7,'ice')+R(73,-56,6,3,'ice')+R(73,-40,6,3,'ice')+'</g></g>'
 # Far arm rests on the tool crate.
 s+=R(-29,-63,8,23,'rust')+R(-31,-43,11,12,'steel')+R(-30,-33,3,6,'edge')+R(-23,-33,3,6,'edge')
 return s+'</g></g>'

def builder_right():
 s='<g id="builder-right" transform="translate(522 281)"><g class="right-body">'
 # Treads, shaded individual links, warm underside highlights.
 s+=stepped_box(-32,-16,66,19,'ink')+stepped_box(-30,-14,62,15,'steel','mid')
 for x in range(-26,28,9):s+=R(x,-12,6,10,'deep')+R(x,-11,6,2,'edge')+R(x,-3,6,2,'mid')
 s+=R(-26,-2,54,2,'rust')+stepped_box(-26,-60,55,46,'ink')+stepped_box(-24,-58,51,41,'blue','teal')+R(-22,-54,8,29,'teal')+R(18,-51,7,30,'navy')+R(-13,-49,26,21,'deep')+R(-10,-46,20,15,'night')
 s+='<g class="teacher-core">'+R(-7,-43,5,2,'mint')+R(-7,-41,10,3,'teal')+R(-7,-38,15,2,'mint')+R(-7,-36,10,2,'teal')+'</g>'
 s+=R(-15,-24,28,3,'steel')+R(-12,-23,5,1,'cream')+R(-4,-23,5,1,'orange')+R(4,-23,5,1,'cream')
 s+=R(-10,-67,25,8,'steel')+stepped_box(-27,-95,59,31,'ink')+stepped_box(-25,-93,55,27,'teal','mint')+R(-23,-88,50,17,'navy')+R(-21,-86,46,14,'deep')+R(-21,-86,46,2,'steel')+R(25,-87,3,18,'blue')
 s+='<g class="right-eyes">'+R(-13,-81,9,5,'gold')+R(8,-81,9,5,'gold')+R(-11,-80,3,2,'cream')+R(10,-80,3,2,'cream')+'</g>'
 s+=R(-31,-84,5,13,'steel')+R(32,-84,4,13,'blue')+R(21,-107,3,14,'edge')+R(18,-110,9,5,'orange')+R(20,-110,5,2,'gold')
 s+='<g class="right-arm">'+stepped_box(-38,-56,16,16,'ink')+R(-36,-54,12,11,'teal')+R(-33,-51,6,5,'blue')+Q([(-32,-44),(-40,-42),(-48,-28),(-40,-22),(-33,-32)],'blue')+R(-49,-31,13,13,'steel')+R(-46,-29,7,8,'edge')+Q([(-45,-30),(-64,-49),(-70,-44),(-49,-21)],'ink')+Q([(-45,-27),(-63,-44),(-66,-42),(-49,-23)],'teal')+R(-73,-50,10,10,'steel')+R(-78,-53,7,3,'ice')+R(-78,-41,7,3,'ice')+R(-78,-50,3,10,'ice')+'</g>'
 s+=R(28,-50,8,20,'navy')+R(29,-33,11,11,'steel')+R(28,-24,4,6,'edge')+R(36,-24,4,6,'edge')
 return s+'</g></g>'

def render(mobile=False):
 s='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 768 384" width="1536" height="768" role="img" aria-label="Robots build, test and teach the next robot in an original pixel-art orbital workshop" aria-labelledby="title" aria-describedby="desc" shape-rendering="crispEdges"><title id="title">The next builder</title><desc id="desc">Original 16-bit science-fiction adventure illustration. In an orbital workshop, two robots assemble a new robot, test it, share their build guide and welcome it to the crew. The new builder helps with the next chassis. A twelve-second conceptual story, not an engineering simulation or a claim of automatic model training. People review and share the real project knowledge.</desc><defs><clipPath id="frame"><rect width="768" height="384"/></clipPath><clipPath id="window"><path d="M104 33H666V162H104Z"/></clipPath><pattern id="floor-grain" width="48" height="24" patternUnits="userSpaceOnUse"><path d="M0 23H48M47 0V24" fill="none" stroke="#343a58" stroke-width="1"/><path d="M3 21h13" stroke="#4a5773" stroke-width="1"/></pattern></defs><style>
/* All geometry uses a single pixel grid. Motions are quantized to the same visual cadence. */
.scene{isolation:isolate}.next-head{animation:nexthead 12s steps(18) infinite}.next-head .kid-eyes,.next-head .boot-eye{display:none}.stars-far{animation:drift 12s steps(8) infinite}.belt-links{animation:belt 1s steps(8) infinite}.signal{animation:signal 12s steps(1) infinite}.crane{animation:crane 12s steps(18) infinite}.hoist-cable{animation:hoist 12s steps(18) infinite;transform-origin:384px 91px}.new-builder{animation:join 12s steps(18) infinite}.new-builder .kid-head{animation:head 12s steps(18) infinite}.new-builder .kid-arms{animation:arms 12s steps(1) infinite}.new-builder .kid-eyes{animation:awake 12s steps(1) infinite}.new-builder .boot-eye{animation:boot 12s steps(1) infinite}.new-builder .kid-core{animation:core 12s steps(1) infinite}.new-builder .kid-arm-right{animation:learn 12s steps(5) infinite;transform-origin:21px -40px}.new-builder .kid-leg-left{animation:walkleft 12s steps(1) infinite}.new-builder .kid-leg-right{animation:walkright 12s steps(1) infinite}.previous-builder{animation:previous 12s steps(12) infinite}.next-chassis{animation:next 12s steps(22) infinite}.builder-step-left{animation:builderstep 12s steps(1) infinite}.builder-step-right{animation:builderstep2 12s steps(1) infinite}.left-body{animation:approachleft 12s steps(10) infinite}.right-body{animation:approachright 12s steps(10) infinite}.left-forearm{animation:forearm 12s steps(8) infinite;transform-origin:46px -37px}.left-arm{animation:reachleft 12s steps(8) infinite;transform-origin:29px -63px}.right-arm{animation:reachright 12s steps(8) infinite;transform-origin:-30px -49px}.assembly-sparks{animation:sparks 12s steps(1) infinite}.test-light{animation:test 12s steps(1) infinite}.guide-new{animation:guide 12s steps(1) infinite}.teacher-core{animation:teacher 12s steps(1) infinite}.left-eyes,.right-eyes{animation:blink 6s steps(1) infinite}.left-part{animation:leftpart 12s steps(12) infinite}.right-part{animation:rightpart 12s steps(12) infinite}.crew-wave{animation:crew 12s steps(5) infinite;transform-origin:0px 0px}.front-light{animation:front 12s steps(1) infinite}
@keyframes nexthead{0%,84%{opacity:0;transform:translateY(-64px)}85%{opacity:1;transform:translateY(-64px)}90%,100%{opacity:1;transform:translateY(-38px)}}
@keyframes drift{0%,100%{transform:translateX(0)}50%{transform:translateX(-3px)}}
@keyframes belt{to{transform:translateX(16px)}}
@keyframes crane{0%,8%,90%,100%{transform:translateY(-38px)}24%,28%{transform:translateY(0)}38%,85%{transform:translateY(-64px)}}
@keyframes hoist{0%,8%,90%,100%{transform:scaleY(.66)}24%,28%{transform:scaleY(1)}38%,85%{transform:scaleY(.43)}}
@keyframes head{0%,8%{transform:translateY(-38px)}24%,100%{transform:translateY(0)}}
@keyframes arms{0%,21%{opacity:0}22%,100%{opacity:1}}
@keyframes awake{0%,33%{opacity:0}34%,36%{opacity:1}37%,39%{opacity:0}40%,100%{opacity:1}}
@keyframes boot{0%,26%,40%,100%{opacity:0}27%,39%{opacity:1}}
@keyframes core{0%,33%{opacity:0}34%,100%{opacity:1}}
@keyframes join{0%,66%{transform:translate(0,0)}70%{transform:translate(12px,8px)}76%{transform:translate(42px,20px)}84%,100%{transform:translate(110px,25px)}}
@keyframes previous{0%{transform:translate(110px,25px);opacity:1}8%{transform:translate(172px,27px);opacity:1}16%{transform:translate(246px,27px);opacity:0}17%,100%{transform:translate(246px,27px);opacity:0}}
@keyframes next{0%,76%{opacity:0;transform:translate(-190px,18px)}77%{opacity:1;transform:translate(-190px,18px)}90%,100%{opacity:1;transform:translate(0,0)}}
@keyframes walkleft{0%,66%,85%,100%{transform:translate(0,0)}68%,72%,76%,80%{transform:translate(-3px,-2px)}70%,74%,78%,82%{transform:translate(3px,0)}}
@keyframes walkright{0%,66%,85%,100%{transform:translate(0,0)}68%,72%,76%,80%{transform:translate(3px,0)}70%,74%,78%,82%{transform:translate(-3px,-2px)}}
@keyframes reachleft{0%,100%{transform:rotate(0)}}
@keyframes builderstep{0%,7%,18%,28%,36%,100%{transform:translate(0,0)}8%,12%,16%,29%,33%{transform:translate(3px,-2px)}10%,14%,30%,34%{transform:translate(-3px,0)}}
@keyframes builderstep2{0%,7%,18%,28%,36%,100%{transform:translate(0,0)}8%,12%,16%,29%,33%{transform:translate(-3px,0)}10%,14%,30%,34%{transform:translate(3px,-2px)}}
@keyframes approachleft{0%,7%,36%,100%{transform:translateX(0)}18%,28%{transform:translateX(32px)}}
@keyframes approachright{0%,8%,36%,100%{transform:translateX(0)}18%,28%{transform:translateX(-40px)}}
@keyframes forearm{0%,7%,36%,100%{transform:rotate(0)}18%,28%{transform:rotate(30deg)}}
@keyframes reachright{0%,8%,34%,44%,70%,100%{transform:rotate(0)}18%,28%{transform:rotate(-20deg)}49%,59%{transform:rotate(47deg)}}
@keyframes learn{0%,52%,70%,100%{transform:rotate(0)}58%,64%{transform:rotate(-66deg)}88%,92%,96%{transform:rotate(-30deg)}90%,94%,98%{transform:rotate(-50deg)}}
@keyframes leftpart{0%,7%{transform:translate(-37px,-20px);opacity:1}20%,21%{transform:translate(0,0);opacity:1}22%,100%{transform:translate(0,0);opacity:0}}
@keyframes rightpart{0%,8%{transform:translate(38px,-19px);opacity:1}20%,21%{transform:translate(0,0);opacity:1}22%,100%{transform:translate(0,0);opacity:0}}
@keyframes sparks{0%,19%,26%,100%{opacity:0}20%,22%,24%{opacity:1}21%,23%,25%{opacity:0}}
@keyframes test{0%,28%,44%,100%{opacity:0}29%,43%{opacity:1}}
@keyframes signal{0%,46%,65%,100%{opacity:0}47%,64%{opacity:1}}
@keyframes guide{0%,48%{opacity:0}49%,100%{opacity:1}}
@keyframes teacher{0%,45%,67%,100%{opacity:.6}46%,66%{opacity:1}}
@keyframes blink{0%,93%,97%,100%{opacity:1}94%,96%{opacity:0}}
@keyframes front{0%,32%,44%,100%{fill:#4aa69e}33%,43%{fill:#e9b86a}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}.new-builder{transform:translate(110px,25px)}.new-builder .kid-head,.new-builder .kid-arm-right{transform:none}.new-builder .kid-arms,.new-builder .kid-eyes,.new-builder .kid-core,.next-chassis,.guide-new{opacity:1}.new-builder .boot-eye,.previous-builder,.assembly-sparks,.signal,.test-light,.left-part,.right-part{opacity:0}.next-chassis{transform:none}.crane{transform:translateY(-38px)}.hoist-cable{transform:scaleY(.66)}.front-light{fill:#4aa69e}.next-head{opacity:1;transform:translateY(-38px)}.left-body,.right-body,.left-forearm,.right-arm{transform:none}}
</style><g clip-path="url(#frame)" class="scene">'''
 # Surrounding architecture and orbital window.
 s+=R(0,0,768,384,'ink')+R(0,16,768,198,'deep')+R(90,24,588,151,'ink')+R(96,29,576,141,'mid')+R(101,32,566,134,'steel')
 s+='<g clip-path="url(#window)">'+R(104,33,562,129,'#202748')+R(104,101,562,61,'#2b3154')+R(104,137,562,25,'#354465')
 s+='<g class="stars-far">'
 for x,y in [(121,55),(158,87),(191,43),(239,68),(288,47),(333,91),(380,42),(432,81),(486,47),(547,70),(592,42),(641,96),(660,61),(212,117),(302,127)]:s+=R(x,y,1,1,'edge')
 s+=star(137,104,1,'ice')+star(471,64,1,'ice')+star(611,115,1,'ice')
 # A stepped planet, its bands and clouds are original pixel shapes.
 s+=Q([(503,31),(547,31),(547,34),(563,34),(563,39),(576,39),(576,46),(585,46),(585,57),(591,57),(591,71),(595,71),(595,95),(591,95),(591,109),(585,109),(585,121),(574,121),(574,129),(560,129),(560,134),(543,134),(543,137),(509,137),(509,134),(490,134),(490,128),(478,128),(478,120),(467,120),(467,109),(461,109),(461,95),(457,95),(457,73),(461,73),(461,58),(468,58),(468,47),(480,47),(480,40),(491,40),(491,34),(503,34)],'#547488')
 s+=Q([(493,35),(547,35),(547,38),(561,38),(561,43),(573,43),(573,50),(583,50),(583,58),(588,58),(588,69),(574,69),(574,64),(550,64),(550,60),(523,60),(523,56),(491,56),(491,51),(477,51),(477,44),(493,44)],'#7a9c9d')
 s+=Q([(462,77),(479,77),(479,82),(506,82),(506,88),(541,88),(541,92),(577,92),(577,97),(591,97),(591,110),(584,110),(584,119),(569,119),(569,114),(545,114),(545,111),(515,111),(515,106),(487,106),(487,100),(462,100)],'#3b607c')
 s+=Q([(479,42),(504,42),(504,38),(537,38),(537,42),(552,42),(552,47),(525,47),(525,51),(488,51),(488,48),(479,48)],'#aac0b5')
 s+=Q([(490,69),(510,69),(510,65),(548,65),(548,69),(567,69),(567,74),(546,74),(546,78),(515,78),(515,74),(490,74)],'#83a8ab')
 s+=Q([(473,114),(495,114),(495,119),(525,119),(525,123),(549,123),(549,127),(564,127),(564,131),(543,131),(543,134),(513,134),(513,131),(496,131),(496,126),(484,126),(484,122),(473,122)],'#6f91a0')
 # Ring system crosses behind foreground architecture, giving adventure scale.
 s+=Q([(424,132),(437,124),(470,110),(508,95),(552,80),(598,67),(627,63),(639,66),(639,71),(624,78),(602,86),(580,92),(580,88),(617,74),(626,69),(610,71),(578,80),(540,94),(498,110),(458,126),(436,137),(437,140),(455,139),(475,133),(475,137),(450,145),(429,146),(420,143),(420,138)],'#a9b6a9')
 s+=Q([(425,138),(444,128),(487,110),(540,90),(594,73),(619,68),(627,69),(604,76),(550,93),(499,113),(457,130),(435,142),(427,142)],'#d4d1b1')
 s+='</g>'
 # Distant orbital structures and blue city points, not moving particles.
 s+=Q([(104,148),(115,148),(115,139),(123,139),(123,131),(129,131),(129,139),(142,139),(142,151),(163,151),(163,143),(175,143),(175,125),(179,125),(179,146),(194,146),(194,137),(212,137),(212,152),(238,152),(238,133),(252,133),(252,141),(265,141),(265,149),(306,149),(306,139),(328,139),(328,154),(384,154),(384,145),(403,145),(403,152),(437,152),(437,144),(449,144),(449,153),(505,153),(505,146),(524,146),(524,157),(566,157),(566,145),(582,145),(582,154),(621,154),(621,140),(630,140),(630,128),(634,128),(634,140),(646,140),(646,153),(666,153),(666,164),(104,164)],'#1b2845')
 for x in [120,137,166,197,243,250,312,323,394,513,570,626,639]:s+=R(x,152,3,2,'teal')
 s+='</g>'
 # Window framing, with warm hanging lights.
 s+=R(100,162,568,7,'edge')+R(100,169,568,8,'night')+R(101,166,566,2,'steel')
 for x in [102,286,474,662]:s+=R(x,31,5,133,'night')+R(x+1,33,1,128,'mid')
 s+=R(93,27,580,5,'edge')+R(93,25,580,2,'steel')
 # Thick side columns, cables and inset panels.
 for x in [53,683]:
  s+=R(x,0,31,245,'ink')+R(x+3,0,25,243,'steel')+R(x+5,0,5,243,'mid')+R(x+20,0,6,243,'night')+R(x+8,66,11,108,'deep')+R(x+10,69,3,101,'edge')
  s+=R(x-6,180,43,12,'ink')+R(x-4,182,39,7,'mid')+R(x-4,189,39,2,'night')+R(x-8,237,47,13,'steel')+R(x-6,237,43,3,'edge')
 for x in [19,724]:
  s+=R(x,25,10,191,'steel')+R(x+2,27,3,184,'edge')
  for y in [42,93,145,199]:s+=R(x-3,y,16,6,'night')+R(x-2,y,14,2,'mid')
 s+=R(0,207,768,49,'night')+R(0,208,768,3,'mid')
 # Back worktop: instrumentation and maintenance items.
 s+=panel(93,184,89,47)+R(98,189,79,25,'deep')
 for x in range(104,170,9):s+=R(x,195,4,13,'steel')+R(x,195,4,(x%3+1)*3,'teal')
 s+=R(103,218,5,3,'gold')+R(113,218,5,3,'rust')+R(146,219,25,2,'edge')
 s+=R(102,231,82,9,'ink')+R(105,231,76,3,'mid')
 # Fixed shared build terminal: actual on-screen robot plan, no floating cards.
 s+=R(585,170,5,61,'steel')+R(571,229,35,7,'ink')+stepped_box(553,178,84,53,'ink')+R(557,182,76,42,'mid')+R(559,184,72,37,'deep')+R(561,186,68,2,'blue')
 s+='<g id="guide-screen">'+R(570,194,15,9,'blue')+R(572,192,11,2,'teal')+R(574,197,3,2,'mint')+R(581,197,2,2,'mint')+R(573,205,10,11,'blue')+R(568,207,3,7,'teal')+R(585,207,3,7,'teal')+R(573,218,3,3,'teal')+R(580,218,3,3,'teal')
 for y,w in [(195,24),(200,17),(205,21),(210,13)]:s+=R(596,y,w,1,'mid')
 s+='<g class="guide-new">'+R(594,194,2,2,'mint')+R(598,195,23,1,'teal')+R(594,199,2,2,'mint')+R(598,200,17,1,'teal')+R(594,204,2,2,'mint')+R(598,205,21,1,'teal')+R(595,215,5,2,'mint')+R(598,212,2,5,'mint')+R(600,210,2,3,'mint')+'</g></g>'
 s+=R(562,226,16,2,'gold')+R(582,226,2,2,'teal')+R(587,226,2,2,'teal')
 # Data cable is physically routed along the workbench and into the robot station.
 s+=line([(590,235),(590,248),(445,248),(445,272),(405,272)],'ink',5)+line([(590,234),(590,248),(445,248),(445,272),(405,272)],'blue',2)
 s+='<g class="signal">'+line([(590,234),(590,248),(445,248),(445,272),(405,272)],'mint',2, 'stroke-dasharray="5 12"')+'</g>'
 # Floor has a coherent low viewpoint and a slotted foreground conveyor.
 s+=R(0,253,768,131,'night')+R(0,253,768,3,'edge')+R(0,256,768,128,'url(#floor-grain)')
 for x,y,w in [(20,279,72),(611,278,124),(22,335,93),(625,339,91)]:
  s+=R(x,y,w,3,'ink')+R(x,y+3,w,1,'mid')
 s+=Q([(94,268),(122,268),(91,318),(63,318)],'steel')+Q([(638,268),(664,268),(698,318),(672,318)],'steel')
 s+=R(94,306,579,18,'ink')+R(96,306,575,3,'edge')+R(96,309,575,12,'steel')+R(96,321,575,3,'night')
 for x in range(104,663,16):s+=R(x,311,11,6,'night')+R(x,311,11,1,'mid')
 s+='<g class="belt-links">'
 for x in range(94,650,16):s+=R(x,309,2,2,'ice')
 s+='</g>'+R(78,303,21,25,'steel')+R(78,303,21,3,'edge')+R(661,303,21,25,'steel')+R(661,303,21,3,'edge')
 # Centered assembly platform with lit front, caution stripe and diagnostic hardware.
 s+=Q([(328,273),(426,273),(449,288),(306,288)],'mid')+R(306,288,143,14,'ink')+R(309,289,137,10,'steel')+R(315,292,125,3,'teal','class="front-light"')+R(315,296,125,1,'navy')
 s+=Q([(332,271),(421,271),(435,280),(319,280)],'edge')+Q([(336,273),(417,273),(425,278),(328,278)],'steel')
 for x in range(319,434,13):s+=Q([(x,281),(x+7,281),(x+4,285),(x-3,285)],'gold')
 s+=R(314,257,6,18,'steel')+R(315,257,4,4,'teal')+R(427,257,6,18,'steel')+R(428,257,4,4,'teal')
 s+='<g class="test-light">'+R(317,251,2,22,'mint')+R(428,251,2,22,'mint')+R(320,253,108,1,'teal')+R(320,259,108,1,'blue')+R(331,276,86,1,'mint')+'</g>'
 # Overhead crane is supported by the columns, with trolley, separate cable and magnet.
 s+=R(77,67,610,24,'ink')+R(79,69,606,18,'steel')+R(79,69,606,3,'edge')+R(79,86,606,3,'night')
 for x in range(85,675,30):s+=R(x,75,23,8,'night')+R(x+1,75,21,1,'mid')
 s+=panel(350,65,65,29)+R(357,70,50,5,'orange')+R(363,72,38,2,'gold')+R(359,85,46,3,'edge')+R(361,93,6,6,'mid')+R(398,93,6,6,'mid')
 s+='<g class="hoist-cable">'+R(374,91,3,105,'mid')+R(375,91,1,105,'ice')+R(391,91,3,105,'mid')+R(392,91,1,105,'ice')+'</g>'
 s+='<g class="crane">'+stepped_box(367,189,34,12,'ink')+R(369,191,30,7,'orange')+R(371,191,26,2,'gold')+R(368,199,5,7,'steel')+R(395,199,5,7,'steel')+R(368,204,10,3,'edge')+R(390,204,10,3,'edge')+'</g>'
 # Builders and prototype station. Arms and the carried parts converge on real shoulders.
 s+=builder_left()+builder_right()
 head_art=small_robot().split('<g class="kid-head">',1)[1].rsplit('</g>',2)[0]
 s+='<g transform="translate(384 286)"><g class="next-head">'+head_art+'</g></g>'
 s+='<g transform="translate(384 286)"><g class="previous-builder">'+small_robot(cls='previous')+'</g><g class="next-chassis">'+small_robot(cls='unbuilt')+'</g><g class="new-builder">'+small_robot(cls='current')+'</g>'
 s+='<g class="left-part">'+R(-28,-39,8,15,'ice')+R(-28,-39,3,14,'cream')+R(-29,-26,10,7,'steel')+R(-29,-20,3,5,'ice')+R(-22,-20,3,5,'ice')+'</g><g class="right-part">'+R(20,-39,8,15,'ice')+R(25,-39,3,14,'edge')+R(19,-26,10,7,'steel')+R(19,-20,3,5,'ice')+R(26,-20,3,5,'ice')+'</g></g>'
 s+='<g class="assembly-sparks">'+star(350,240,1,'cream')+star(415,242,1,'gold')+R(345,234,2,2,'gold')+R(354,232,1,2,'orange')+R(421,235,2,2,'cream')+R(418,249,2,2,'orange')+'</g>'
 # A successor's first small job is at a lower bench: tangible participation in the next build.
 s+=R(511,301,87,5,'edge')+R(511,306,87,16,'steel')+R(514,308,81,2,'mid')+R(516,321,7,18,'night')+R(585,321,7,18,'night')
 s+=stepped_box(527,286,44,16,'ink')+R(529,288,40,11,'orange')+R(531,289,36,2,'gold')+R(534,294,28,6,'rust')+R(539,290,5,3,'steel')+R(554,290,5,3,'steel')
 s+=R(579,286,8,14,'mid')+R(581,283,4,6,'cream')
 # Foreground crates, spares and warm floor lights give depth without competing with the cast.
 s+=panel(102,255,62,41)+R(108,261,50,7,'orange')+R(110,263,46,2,'gold')+R(111,274,45,14,'night')
 for x in [118,132,146]:s+=R(x,277,5,8,'mid')+R(x,277,5,2,'edge')
 s+=stepped_box(137,237,19,17,'ink')+R(140,239,13,12,'ice')+R(142,243,9,5,'deep')+R(143,244,2,2,'mint')+R(148,244,2,2,'mint')
 s+=panel(27,333,95,38)+R(33,339,83,3,'orange')+R(33,346,83,18,'night')
 for x in [41,60,79,98]:s+=R(x,349,10,11,'steel')+R(x,350,10,2,'mid')
 s+=panel(631,325,104,47)+R(637,331,92,4,'blue')
 for y in [343,350,357]:s+=R(640,y,84,3,'night')+R(641,y,82,1,'mid')
 s+=R(0,375,768,9,'ink')+R(0,375,768,2,'steel')
 for x in [155,303,453,603]:s+=R(x,365,24,4,'gold')+R(x+3,366,18,1,'cream')+R(x-4,370,32,1,'rust')
 s+='</g></svg>\n'
 # Only the incomplete chassis lacks head and arms. The crane carries the head into frame.
 s=s.replace('<style>','<style>'+REDUCED_MOTION+'.unbuilt .kid-head,.unbuilt .kid-arms,.unbuilt .kid-core,.unbuilt .kid-eyes{display:none}.previous .boot-eye{display:none}',1)
 if mobile:
  s=s.replace('viewBox="0 0 768 384" width="1536" height="768"','viewBox="145 13 478 355" width="956" height="710"')
 return s
