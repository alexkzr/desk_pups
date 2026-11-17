"""Bezier character rig: continuous anatomy, independent ears, stable coat patterns."""
import math
import random
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QPen

from appearance import Appearance

WALK_SPEED, RUN_SPEED = 38., 210.
WALK_FREQUENCY, RUN_FREQUENCY = 8., 24.


def foot_cycle(angle, running=False):
    frequency = RUN_FREQUENCY if running else WALK_FREQUENCY
    speed = RUN_SPEED if running else WALK_SPEED
    amplitude = speed*math.pi/(2*frequency)
    phase = angle % (2*math.pi)
    if phase < math.pi:
        return -amplitude*math.cos(phase), (6 if running else 2.5)*math.sin(phase)
    # A planted paw moves backwards at precisely the body's forward speed.
    return amplitude*(1-2*(phase-math.pi)/math.pi), 0.


def model_scale(appearance):
    return ((1,1),(.94,1.10),(1,1),(1,.98))[appearance.style]


def rear_drop_offset(appearance, direction):
    # The pile's centre belongs just behind the rump, not at a sprite origin.
    sx,_ = model_scale(appearance)
    x = 80+(20-80)*sx
    return 160-x if direction < 0 else x


def ellipse(p, x, y, w, h, color):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(x, y, w, h))


def rounded(p, x, y, w, h, r, color):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(x, y, w, h), r, r)


def stroke(p, points, color, width):
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(QPointF(*points[0]), QPointF(*points[1]))
    p.setPen(Qt.NoPen)


def path(points):
    q = QPainterPath()
    q.moveTo(*points[0])
    for segment in points[1:]:
        if len(segment) == 6:
            q.cubicTo(*segment)
        elif len(segment) == 4:
            q.quadTo(*segment)
        else:
            q.lineTo(*segment)
    q.closeSubpath()
    return q


def draw_bed(p, opacity=1):
    p.save()
    p.setOpacity(opacity)
    rounded(p, 2, 6, 140, 28, 13, '#587d80')
    ellipse(p, 11, 4, 122, 25, '#9cb5ad')
    ellipse(p, 20, 9, 104, 18, '#e1d3b5')
    rounded(p, 4, 23, 136, 11, 5, '#6c9694')
    stroke(p, ((21,29),(123,29)), '#86aba4', 2)
    p.restore()


@lru_cache(maxsize=512)
def spots(seed, part):
    rng = random.Random(seed+part*100003)
    # Normalised, irregular patches travel with each anatomical part.
    return tuple((rng.random(),rng.random(),rng.uniform(.05,.17),
                  rng.uniform(.10,.24),rng.uniform(-60,60)) for _ in range(16))


class Artist:
    def __init__(self, p, appearance, phase, ear_angle, hang_angles=None, guilty=0.):
        self.p, self.look, self.phase, self.ear_angle = p,appearance,phase,ear_angle
        self.hang_angles=hang_angles or (0.,0.,0.)
        self.guilty=max(0,min(1,(guilty-.05)/.95))
        self.base, self.light, self.shade, self.tan, self.outline = (
            ('#b55b2d','#d47d41','#8a3e24','#e4a465','#67331f'),
            ('#292831','#4b4650','#171820','#ca803f','#14151c'),
            ('#aaa6aa','#c4bfc0','#85818c','#d49a60','#49414a'),
        )[appearance.coat]

    def fill(self, shape, part=0, tone=None, patterned=True, outline=True):
        p = self.p
        bounds = shape.boundingRect()
        base = QColor(tone or self.base)
        if self.look.style == 3:
            p.setBrush(base)
        else:
            gradient = QLinearGradient(bounds.topLeft(),bounds.bottomRight())
            gradient.setColorAt(0,base.lighter(125 if self.look.style == 1 else 114))
            gradient.setColorAt(.5,base)
            gradient.setColorAt(1,base.darker(112))
            p.setBrush(gradient)
        p.setPen(QPen(QColor(self.outline), .85 if self.look.style == 2 else .35,
                      Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin) if outline else Qt.NoPen)
        p.drawPath(shape)
        p.setPen(Qt.NoPen)
        if self.look.coat == 2 and patterned:
            p.save()
            p.setClipPath(shape,Qt.IntersectClip)
            for i,(x,y,w,h,angle) in enumerate(spots(self.look.seed,part)):
                p.save()
                p.translate(bounds.x()+x*bounds.width(),bounds.y()+y*bounds.height())
                p.rotate(angle)
                blob = path([(-w*bounds.width()/2,0),
                             (-w*bounds.width(),-h*bounds.height(),w*bounds.width()/3,-h*bounds.height(),w*bounds.width()/2,0),
                             (w*bounds.width(),h*bounds.height(),-w*bounds.width()/3,h*bounds.height(),-w*bounds.width()/2,0)])
                p.setBrush(QColor('#45424b' if i%3 else '#706773'))
                p.drawPath(blob)
                p.restore()
            p.restore()
        if self.look.style == 2 and self.look.fur:
            p.save()
            p.setClipPath(shape,Qt.IntersectClip)
            for i in range(6):
                x = bounds.x()+bounds.width()*(i+1)/8
                y = bounds.y()+bounds.height()*.65
                stroke(p,((x,y),(x+3,y-2)),self.shade,.55)
            p.restore()

    def detail(self, shape, color, width=.7):
        self.p.setBrush(Qt.NoBrush)
        self.p.setPen(QPen(QColor(color),width,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
        self.p.drawPath(shape)
        self.p.setPen(Qt.NoPen)

    def tail(self, x, y, running=False, resting=False):
        swing = math.sin(self.phase*(15 if running else 5))* (5 if running else 2)
        if resting:
            shape = path([(x,y),(x-13,y+3,x-23,y+4,x-28,y+1),
                          (x-27,y+7,x-12,y+7,x+3,y+4)])
        else:
            width = 3 if self.look.fur else 0
            shape = path([(x+2,y+2),(x-11,y+1,x-18,y-8,x-19,y-20-swing),
                          (x-23-width,y-7,x-15-width,y+8,x+2,y+7)])
        self.fill(shape,5,tone=self.base)

    def leg(self, x, root, foot_x, floor, far=False):
        tone = self.shade if far else self.base
        knee = x+(foot_x-x)*.4
        mid = (root+floor)*.5
        feather = 1.7 if self.look.fur else 0
        shape = path([(x-4,root),
                      (x-4-feather,root+4,knee-4-feather,mid,foot_x-3.5,floor-5),
                      (foot_x-4.5,floor-2,foot_x-4,floor-.5,foot_x-1,floor),
                      (foot_x+2,floor+.3,foot_x+7,floor+.3,foot_x+7,floor-1.7),
                      (foot_x+7,floor-3.5,foot_x+4,floor-4,foot_x+2.5,floor-4.5),
                      (knee+4,mid,x+4,root+4,x+4,root)])
        self.fill(shape,10 if far else 11,tone=tone,outline=False)
        if self.look.coat:
            self.p.save()
            self.p.setClipPath(shape,Qt.IntersectClip)
            ellipse(self.p,foot_x-8,floor-8,23,12,self.tan)
            self.p.restore()
        if not far:
            stroke(self.p,((foot_x+4,floor-2),(foot_x+4,floor-.5)),self.shade,.55)

    def ear(self, x, y, length, width, angle, far=False):
        p = self.p
        p.save()
        p.translate(x,y)
        p.rotate(angle)
        length = length+(4 if self.look.fur else 0)
        ear = path([(0,0),(-width*.75,2,-width*.65,length*.44,-width*.7,length*.72),
                    (-width*.8,length+3,width*.48,length+4,width*.63,length*.70),
                    (width*.76,length*.38,width*.43,-3,0,0)])
        self.fill(ear,20 if far else 21,tone=self.shade if far else self.base)
        if self.look.fur:
            for dx in (-2,2):
                line=QPainterPath(QPointF(dx, length*.40))
                line.cubicTo(dx-2,length*.65,dx+1,length*.8,dx,length*.9)
                self.detail(line,self.shade,.4)
        highlight=QPainterPath(QPointF(-width*.3,5))
        highlight.cubicTo(-width*.55,length*.3,-width*.55,length*.65,-width*.35,length*.8)
        self.detail(highlight,QColor(self.light).name(),.65)
        p.restore()

    def head(self, x, y, tilt=0, front=0, sleeping=False, running=False):
        p = self.p
        p.save()
        p.translate(x+10,y+12)
        p.rotate(tilt)
        p.translate(-10,-12)
        plush = self.look.style == 1
        scale = 1.10 if plush else (1.03 if self.look.style == 0 else 1)
        p.scale(scale,scale)
        if front > .15:
            self.ear(16,10,27,7,self.ear_angle*.65-8,True)
        head = path([(0,23),(-6,11,-1,-3,10,-4),
                     (20,-5,24,1,27,8),
                     (32,11,38,10,43,9),
                     (48,8,49,15,42,20),
                     (35,26,27,27,22,28),
                     (17,33,6,32,0,23)])
        self.fill(head,30)
        # Cheeks and muzzle; tan markings do not recolour the crown or ears.
        p.save()
        p.setClipPath(head,Qt.IntersectClip)
        muzzle = path([(17,13),(24,15,35,12,46,10),(50,20,36,29,20,28),
                       (15,25,13,20,17,13)])
        self.fill(muzzle,31,tone=self.tan if self.look.coat else self.light,patterned=False,outline=False)
        p.restore()
        eye_x = 21-front*3
        eye_y = 7
        if self.look.coat or self.guilty:
            # In profile the muzzle is the inner side of this visible brow.
            brow=path([(eye_x-2,eye_y-2),
                       (eye_x-1,eye_y-4,eye_x+2,eye_y-6-2*self.guilty,eye_x+4,eye_y-5-2*self.guilty),
                       (eye_x+5,eye_y-3,eye_x+1,eye_y-2,eye_x-2,eye_y-1)])
            p.save()
            if not self.look.coat:
                p.setOpacity(p.opacity()*self.guilty)
            self.fill(brow,35,tone=self.tan if self.look.coat else self.shade,patterned=False,outline=False)
            p.restore()
        if sleeping:
            eyelid=QPainterPath(QPointF(eye_x-1,eye_y+3))
            eyelid.quadTo(eye_x+2,eye_y+5,eye_x+5,eye_y+2)
            self.detail(eyelid,'#241c1a',1)
        else:
            eye_size = 5.4 if plush else (4.7 if self.look.style == 0 else 4)
            ellipse(p,eye_x,eye_y,eye_size,eye_size+1,'#241c1a')
            if self.guilty:
                p.save();p.setOpacity(p.opacity()*self.guilty)
                ellipse(p,eye_x+.3,eye_y+1,eye_size-.5,eye_size,'#f6e6d2')
                ellipse(p,eye_x+.8,eye_y-.4*self.guilty,eye_size-1,eye_size-.2,'#241c1a')
                p.restore()
            ellipse(p,eye_x+1.2,eye_y+.8-1.2*self.guilty,1.4,1.8,'#fff5e2')
            if front > .5:
                ellipse(p,12,8,2.8,4.1,'#241c1a')
                if self.look.coat:
                    other_brow=path([(11,6),(11,4,13,2,15,3),
                                     (16,4,14,5,11,6)])
                    self.fill(other_brow,36,tone=self.tan,patterned=False,outline=False)
        nose = path([(42,9),(45,6,50,8,49,11),(48,16,44,17,42,13)])
        self.fill(nose,32,tone='#35231f',patterned=False,outline=False)
        ellipse(p,44,8.7,2.8,1.2,'#8f7366')
        smile=QPainterPath(QPointF(29,22))
        smile.quadTo(35,25-3*self.guilty,40,20+2*self.guilty)
        self.detail(smile,'#64351f',.8)
        if running:
            mouth=path([(30,22),(34,24,38,22,40,20),
                        (39,26,34,28,30,22)])
            self.fill(mouth,33,tone='#623127',patterned=False,outline=False)
            ellipse(p,34,25,6,2.4,'#df8c78')
        self.ear(4,7,29 if self.look.style != 1 else 31,9 if not plush else 10,
                 self.ear_angle,False)
        # Long-haired dachshunds have soft ear feathering, not a pointed beard.
        p.restore()

    def body(self, shape, chest=None):
        self.fill(shape,1)
        if chest:
            self.p.save()
            self.p.setClipPath(shape,Qt.IntersectClip)
            self.fill(chest,2,tone=self.tan if self.look.coat else self.light,patterned=False,outline=False)
            self.p.restore()
        if self.look.fur:
            b = shape.boundingRect()
            x,y,w = b.left()+9,min(94,b.bottom()-4),b.width()-21
            fringe = path([(x,y-3),
                           (x+w*.15,y+1,x+w*.2,y+3,x+w*.34,y+1),
                           (x+w*.46,y+4,x+w*.54,y+3,x+w*.65,y+1),
                           (x+w*.8,y+3,x+w*.94,y+1,x+w,y-3),
                           (x+w*.7,y-5,x+w*.3,y-5,x,y-3)])
            self.fill(fringe,3,outline=False)

    def standing(self, state):
        p=self.p
        run=state=='zoomies'
        eating=state=='eat'
        low=state in ('lie','stretch')
        hanging=state in ('hang','hang_body')
        gait=self.phase*(RUN_FREQUENCY if run else WALK_FREQUENCY)
        bob=(-abs(math.sin(gait))*5 if run else math.sin(gait)*.7) if state in ('walk','zoomies') else 0
        p.save()
        if eating:
            p.scale(.83,1)
        root=82+bob if not low else 90
        p.save()
        if hanging:
            p.translate(28,74)
            p.rotate(-math.degrees(self.hang_angles[0])*.55+math.sin(self.phase*5)*5)
            p.translate(-28,-74)
        self.tail(28,72+bob if not low else 86,run,low)
        p.restore()
        for index,x in enumerate((43,108)):
            if state=='hang_body':
                continue
            angle=gait+(index*.6 if run else index*math.pi)+math.pi
            dx,lift=foot_cycle(angle,run) if state in ('walk','zoomies') else (0,0)
            foot=x+dx
            if hanging:
                p.save();p.translate(x,root)
                p.rotate(-math.degrees(self.hang_angles[0 if index==0 else 2])+math.sin(self.phase*6+index)*5)
                self.leg(0,0,0,17,True);p.restore()
            else:
                self.leg(x,root,foot,98-lift,True)
        top = (65 if self.look.style == 2 else 63)+bob if not low else 71
        neck = 7 if eating else (10 if low else 24)
        if state=='poop':
            top-=4
        body=path([(27,top+10),(25,top-1,37,top-5,53,top-2),
                   (73,top+1,86,top+2,98,top-5),
                   (107,top-min(13,neck),109,top-neck,116,top-neck),
                   (127,top-neck-2,132,top-11,128,top+1),
                   (125,top+12,118,top+25,106,top+27),
                   (88,top+28,61,top+25,46,top+27),
                   (31,top+31,25,top+23,27,top+10)])
        chest=path([(112,top-neck+5),(125,top-neck+4,128,top-6,121,top+10),
                    (118,top+20,112,top+24,106,top+25),
                    (110,top+11,112,top-5,112,top-neck+5)])
        self.body(body,chest)
        for index,x in enumerate((36,111)):
            if state=='hang_body':
                continue
            angle=gait+(index*.6 if run else index*math.pi)
            dx,lift=foot_cycle(angle,run) if state in ('walk','zoomies') else (0,0)
            foot=x+dx
            if hanging:
                p.save();p.translate(x,root)
                p.rotate(-math.degrees(self.hang_angles[0 if index==0 else 2])+math.sin(self.phase*6+index+1)*6)
                self.leg(0,0,0,17);p.restore()
            else:
                self.leg(x,root,foot,98-lift)
        if eating:
            self.head(116,59+math.sin(self.phase*7),27)
        elif low:
            self.head(100,50,-5)
        else:
            self.head(105,36+bob, -8 if run else 0,running=run)
        p.restore()
        if eating:
            rounded(p,121,88,34,10,4,'#437d91')
            ellipse(p,121,85,34,7,'#e9b867')
            for x,y in ((129,87),(135,86),(142,88),(148,87)):
                ellipse(p,x,y,3,2,'#81562f')

    def sitting(self, pose):
        controls=[(39,78,95,54,89,29,0,0,0),
                  (34,80,96,57,90,32,0,0,1),
                  (56,77,88,49,81,23,0,1,0),
                  (52,80,94,53,87,25,-12,.35,0)]
        i=math.floor(pose)%4
        t=pose-math.floor(pose)
        rear,hip,chest,shoulder,hx,hy,tilt,front,relax=[a+(b-a)*t for a,b in zip(controls[i],controls[(i+1)%4])]
        self.tail(rear+6,90,resting=True)
        self.leg(chest,shoulder+20,chest+1,98,True)
        body=path([(rear,87),(rear-4,73,rear+15,72,chest-13,shoulder+7),
                   (chest-6,shoulder-3,chest-2,shoulder-12,chest+8,shoulder-9),
                   (chest+23,shoulder-5,chest+21,shoulder+17,chest+15,shoulder+27),
                   (chest+8,96,rear+24,101,rear+7,96),
                   (rear-1,95,rear-2,92,rear,87)])
        chest_shape=path([(chest+3,shoulder-2),(chest+19,shoulder-5,chest+21,shoulder+13,chest+9,shoulder+27),
                          (chest+3,shoulder+32,chest-4,shoulder+36,chest-6,shoulder+33),
                          (chest+2,shoulder+18,chest+1,shoulder+9,chest+3,shoulder-2)])
        self.body(body,chest_shape)
        hipshape=path([(rear+2,92),(rear-3,72,rear+29,73,rear+31,87),
                       (rear+32,92,rear+18,92,rear+22,95),
                       (rear+24,99,rear+4,99,rear+2,92)])
        self.fill(hipshape,4)
        if relax:
            ellipse(self.p,rear+22,88,17*relax,10,self.tan if self.look.coat else self.light)
            for dx in (0,4,7):
                ellipse(self.p,rear+28+dx,91,2*relax,2,self.shade)
        self.leg(chest+13,shoulder+19,chest+14,98)
        self.head(hx,hy,tilt,front)

    def curled(self, unfold=0):
        p=self.p
        p.save()
        p.translate(0,math.sin(self.phase*1.6)*.6*(1-unfold))
        def blend(a,b):
            return tuple(x+(y-x)*unfold for x,y in zip(a,b))
        body=path([blend((121,84),(123,85)),
                   blend((125,62,102,51,78,54),(123,77,109,77,86,77)),
                   blend((51,55,37,69,42,84),(56,77,25,77,25,87)),
                   blend((47,98,78,98,95,91),(25,97,66,97,100,97)),
                   blend((81,92,66,86,66,79),(118,97,125,94,123,86)),
                   blend((68,69,88,73,96,79),(123,85,123,85,123,85)),
                   blend((104,88,115,94,121,84),(123,85,123,85,123,85))])
        self.body(body)
        tail=path([blend((49,84),(15,84)),blend((54,94,75,96,88,89),(20,87,22,89,28,87)),
                   blend((67,94,55,85,49,84),(25,83,20,81,15,84))])
        self.fill(tail,5,tone=self.shade)
        p.save()
        p.translate(103-3*unfold,78-20*unfold-17*math.sin(math.pi*unfold))
        p.rotate(155*(1-unfold))
        p.scale(.68+.32*unfold,.68+.32*unfold)
        p.translate(-12,-10)
        previous=self.ear_angle
        self.ear_angle*=.1+.9*unfold
        self.head(0,0,sleeping=unfold<.15)
        self.ear_angle=previous
        p.restore()
        p.restore()


def draw_dog(p, state, phase, sit_pose=0, wake_progress=0, appearance=None, ear_angle=0, hang_angles=None, guilty=0.):
    p.save()
    p.setPen(Qt.NoPen)
    appearance = appearance or Appearance()
    sx,sy=model_scale(appearance)
    p.translate(80,98)
    p.scale(sx,sy)
    p.translate(-80,-98)
    artist=Artist(p,appearance,phase,ear_angle,hang_angles,guilty)
    if state=='sit':
        artist.sitting(sit_pose)
    elif state=='sleep':
        artist.curled()
    elif state=='wake':
        t=min(1,max(0,wake_progress/.9))
        artist.curled(t*t*(3-2*t))
    else:
        artist.standing(state)
    p.restore()
