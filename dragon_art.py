"""Miniature reptilian dragons, bat anatomy, hoards, fire and fleeing villagers."""
import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainterPath, QPen, QLinearGradient

PALETTES=(
    ('#68747d','#aab4b8','#303f49','#596878','#ded4b2'),
    ('#252930','#59616b','#10131b','#a22f31','#a64b40'),
    ('#426344','#8aab69','#203d32','#7b9850','#d6bb70'),
    ('#dce8ed','#ffffff','#849eae','#a1c7dc','#e9edff'))
FIRE_COLORS=('#ff8a24','#ed3b28','#ffe138','#438cff')


def treasure(p,opacity=1):
    from artwork import ellipse,path
    p.save();p.setOpacity(opacity);p.setPen(Qt.NoPen)
    p.setBrush(QColor('#856018'))
    p.drawPath(path([(3,33),(22,30,27,15,55,13),(72,-1,92,13,110,18),(126,23,132,28,141,33)]))
    for row in range(4):
        for i in range(11-row*2):
            x=8+row*13+i*12+(i%2)*2;y=29-row*7+math.sin(i*3)*2
            ellipse(p,x,y,14,5,'#9d6f19');ellipse(p,x,y-1.3,13,4,'#e7b643')
            ellipse(p,x+2,y-1,6,1.5,'#ffe295')
    for x,y,c in ((25,24,'#ae344b'),(86,10,'#397dba'),(107,23,'#458c6b'),(54,19,'#a07dc5')):
        p.setBrush(QColor(c));p.drawPath(path([(x,y),(x+5,y-7),(x+11,y-4),(x+10,y+2),(x+3,y+4)]))
        p.setPen(QPen(QColor('#e7f4ff'),.7));p.drawLine(QPointF(x+5,y-6),QPointF(x+4,y+2));p.setPen(Qt.NoPen)
    p.restore()


class DragonArtist:
    def __init__(self,p,appearance,phase,ear_angle=0,hang_angles=None,guilty=0,chubby=0):
        self.p,self.look,self.phase=p,appearance,phase
        self.base,self.light,self.shade,self.membrane,self.horn=PALETTES[appearance.coat]
        self.outline=self.shade
        self.chubby=chubby;self.guilty=max(0,min(1,(guilty-.05)/.95));self.hang_angles=hang_angles or (0,0,0,0)
        self.perch_tilt=0.

    def fill(self,shape,part=0,tone=None,patterned=True,outline=True):
        p=self.p;b=shape.boundingRect();g=QLinearGradient(b.topLeft(),b.bottomRight())
        color=QColor(tone or self.base)
        g.setColorAt(0,color.lighter(140));g.setColorAt(.45,color);g.setColorAt(1,color.darker(140))
        p.setBrush(g);p.setPen(QPen(QColor(self.shade),.65) if outline else Qt.NoPen);p.drawPath(shape);p.setPen(Qt.NoPen)
        if part==1:
            p.save();p.setClipPath(shape,Qt.IntersectClip)
            p.setPen(QPen(QColor(self.light),.45));p.setBrush(Qt.NoBrush)
            for row in range(4):
                for col in range(16):
                    x=29+col*6+(row%2)*3;y=61+row*6
                    q=QPainterPath(QPointF(x,y));q.quadTo(x+2,y+3,x+5,y);p.drawPath(q)
            p.restore()

    def detail(self,shape,color,width=.7):
        self.p.setBrush(Qt.NoBrush);self.p.setPen(QPen(QColor(color),width,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));self.p.drawPath(shape);self.p.setPen(Qt.NoPen)

    def leg(self,x,root,foot_x,floor,far=False):
        from artwork import path,stroke
        q=path([(x-4,root),(x-6,root+6,foot_x-5,floor-8,foot_x-3,floor-3),
                (foot_x-1,floor,foot_x+8,floor,foot_x+9,floor-2),
                (foot_x+7,floor-4,foot_x+3,floor-4,foot_x+2,floor-7),
                (x+4,root+7,x+4,root+2,x+3,root)])
        self.fill(q,10,tone=self.shade if far else self.base)
        for dx in (0,3,6):stroke(self.p,((foot_x+dx,floor-2),(foot_x+dx+3,floor-.4)),self.horn,.9)

    def tucked_leg(self,x,root,far=False):
        from artwork import path,stroke
        q=path([(x-5,root),(x-10,root+5,x-1,root+12,x+5,root+10),
                (x+11,root+9,x+11,root+3,x+6,root+2),
                (x+2,root+3,x+2,root+6,x-1,root+5),(x-3,root+4,x-2,root+1,x-5,root)])
        self.fill(q,10,tone=self.shade if far else self.base)
        for dx in (0,2,4):stroke(self.p,((x+dx+4,root+8),(x+dx+2,root+10)),self.horn,.75)

    def tail(self,x,y,running=False,resting=False):
        from artwork import path
        sway=math.sin(self.phase*5)*(4 if running else 2)
        q=path([(x+5,y),(x-14,y+5,x-23,y-17,5,y-14+sway),
                (19,y-8,x-16,y+18,x+5,y+10)])
        self.fill(q,5)
        # Swept dorsal thorns and a barbed tip, rather than a smooth canine tail.
        for dx,dy,size in ((-7,3,6),(-17,-2,6),(-27,-9,5),(-36,-13,4)):
            self.fill(path([(x+dx-2,y+dy+2),(x+dx-5,y+dy-size),(x+dx+4,y+dy+1)]),6,tone=self.horn)
        self.fill(path([(5,y-14+sway),(1,y-22+sway),(13,y-16+sway),(8,y-9+sway)]),7,tone=self.horn)
        self.fill(path([(x-20,y+9),(x-24,y+15),(x-13,y+11)]),6,tone=self.horn)

    def wing(self,x,y,flight=False,far=False,fold=False):
        from artwork import path,stroke
        p=self.p;p.save();p.translate(x,y)
        if far:p.scale(.8,.85);p.translate(8,1)
        if fold:p.scale(.75,.82);p.rotate(8)
        else:
            p.rotate(math.sin(self.phase*(11 if flight else 2))*(29 if flight else 2)-8)
            if flight:p.scale(1,.7+.3*math.cos(self.phase*11))
        membrane=path([(0,0),(-9,-11,-14,-28,-17,-41),(-30,-45,-40,-51,-50,-53),
                       (-39,-38,-38,-30,-43,-20),(-32,-25,-25,-18,-28,-6),(-17,-13,-8,-7,0,0)])
        self.fill(membrane,40,tone=self.shade if far else self.membrane)
        for tip in ((-50,-53),(-43,-20),(-28,-6)):
            line=QPainterPath(QPointF(0,0));line.quadTo(-16,-25,-17,-41);line.lineTo(*tip)
            self.detail(line,self.light,1.1)
        stroke(p,((-17,-41),(-16,-47)),self.horn,1.1)
        p.restore()

    def head(self,x=105,y=36,tilt=0,front=0,sleeping=False,running=False):
        from artwork import path,ellipse,stroke
        p=self.p;p.save();p.translate(x+10,y+10);p.rotate(tilt);p.translate(-10,-10)
        skull=path([(0,20),(0,9,3,-1,12,-3),(21,-4,24,1,27,4),
                    (33,5,40,6,45,9),(49,10,47,14,42,16),
                    (33,18,27,23,20,24),(11,26,3,25,0,20)])
        self.fill(skull,30)
        ridge=QPainterPath(QPointF(12,2));ridge.lineTo(26,5);ridge.lineTo(40,8);self.detail(ridge,self.light,.8)
        jaw=QPainterPath(QPointF(18,19));jaw.quadTo(32,21,44,15);self.detail(jaw,self.shade,1.1)
        for hx,hy in ((7,0),(14,-2)):
            horn=path([(hx,hy+3),(hx-3,hy-4,hx-10,hy-9,hx-11,hy-14),
                       (hx-2,hy-9,hx+2,hy-6,hx+3,hy+1)])
            self.fill(horn,33,tone=self.horn)
        for dx in (0,6):
            self.fill(path([(18+dx,1),(16+dx,-5),(23+dx,0)]),34,tone=self.membrane)
        eye=path([(20,8),(23,5,26,6,27,8),(24,11,22,11,20,8)])
        if sleeping:
            stroke(p,((20,8),(26,8)),self.shade,1)
        else:
            self.fill(eye,35,tone=('#d8b365' if self.look.coat!=3 else '#438cc5'),outline=False)
            stroke(p,((24,6.8),(23.8,10)),self.shade,.8)
            stroke(p,((19,5),(27,6 if not self.guilty else 3)),self.shade,1.3)
        ellipse(p,40,11,1.6,1.2,self.shade)
        if running:
            self.fill(path([(24,20),(33,20,42,16,44,15),(37,25,30,27,24,20)]),36,tone='#39252b')
            for tx in (30,35,40):self.fill(path([(tx,19),(tx-1,22),(tx+1,19)]),37,tone=self.horn)
        p.restore()

    def standing(self,state):
        from artwork import path,foot_cycle,RUN_FREQUENCY,WALK_FREQUENCY
        flight=state in ('fly_meal','zoomies','travel_fly');moving=state=='walk'
        t=self.phase*(RUN_FREQUENCY if flight else WALK_FREQUENCY)
        bob=math.sin(t)*.7 if moving else 0
        self.wing(96,65,flight,True,not flight)
        self.tail(48,58+bob,flight)
        for index,x in enumerate((58,109)):
            if state=='hang_body':continue
            if flight:
                self.tucked_leg(x,74,True);continue
            dx,lift=foot_cycle(t+index*math.pi+math.pi,flight) if moving else (0,0)
            self.leg(x,74+bob,x+dx,92 if flight else 98-lift,True)
        body=path([(47,74),(43,63,48,53,63,54),(77,55,87,59,96,50),
                   (101,43,104,39,112,39),(126,40,130,55,125,68),
                   (120,82,111,88,101,90),(85,93,69,88,57,88),(49,88,44,82,47,74)])
        if self.chubby:
            b=QPainterPath();b.addEllipse(QRectF(37,44,90,52));body=body.united(b)
        self.fill(body,1)
        chest=path([(110,55),(125,58,123,75,109,87),(102,89),(111,73,112,66,110,55)])
        self.fill(chest,2,tone=self.light)
        for index,x in enumerate((52,110)):
            if state=='hang_body':continue
            if flight:
                self.tucked_leg(x,74);continue
            dx,lift=foot_cycle(t+index*math.pi,flight) if moving else (0,0)
            self.leg(x,74+bob,x+dx,92 if flight else 98-lift)
        self.wing(94,65,flight,False,not flight)
        for x,y,height in ((49,60,7),(57,54,11),(65,55,12),(74,56,15),
                           (83,55,16),(92,52,14),(101,46,12),(109,40,9)):
            self.fill(path([(x-3,y+3),(x-4,y-height),(x+6,y+1)]),4,tone=self.horn)
        if state=='eat':self.head(103,63+math.sin(self.phase*9)*.8,25+math.sin(self.phase*8)*2,running=True)
        elif state=='hunt_fire':self.head(103,63,25,running=True)
        else:self.head(105,36+bob,-4 if flight else self.perch_tilt,running=state=='fire')

    def curled(self,unfold=0,show_head=True):
        if unfold>.7:
            self.standing('walk');return
        from artwork import path
        p=self.p;p.save();p.translate(0,math.sin(self.phase*1.6)*.7)
        body=path([(120,83),(124,62,94,52,72,59),(43,61,35,83,52,92),
                   (69,102,95,94,105,88),(81,97,65,84,72,75),
                   (83,65,105,88,120,83)])
        self.fill(body,1)
        self.fill(path([(45,77),(40,95,85,100,110,85),(92,93,58,91,45,77)]),5,tone=self.shade)
        self.wing(91,76,False,False,True)
        if show_head:
            self.head(86,65,27,sleeping=unfold<.2)
        p.restore()


def flame(p,phase,coat,width=190):
    """Turbulent overlapping tongues with a hot core and dark burning tips."""
    p.save();p.setPen(Qt.NoPen)
    strength=min(1,max(0,phase*5),max(0,(2.4-phase)*4))
    p.setOpacity(strength)
    color=QColor(FIRE_COLORS[coat])
    hot=QColor('#eafaff' if coat==3 else '#fff4bc')
    for i in range(4):
        length=(105+i*23)*(.91+.09*math.sin(phase*17+i*4))
        tip=35+math.sin(phase*11+i*2.3)*(4+i*3)
        w=3+i
        q=QPainterPath(QPointF(0,35))
        q.cubicTo(length*.20,33-w*.3,length*.42,tip-w,length*.65,tip-w*.55)
        q.cubicTo(length*.78,tip-w*.9,length*.92,tip+w*.35,length,tip)
        q.cubicTo(length*.86,tip+w*.85,length*.74,tip+w*1.4,length*.56,35+w*.6)
        q.cubicTo(length*.27,35+w*.5,length*.10,37,0,35)
        g=QLinearGradient(0,35,length,35)
        g.setColorAt(0,hot);g.setColorAt(.13,color.lighter(170))
        g.setColorAt(.45,color);g.setColorAt(.79,color.darker(140))
        end=color.darker(220);end.setAlpha(160);g.setColorAt(.97,end)
        end=QColor(end);end.setAlpha(0);g.setColorAt(1,end)
        p.setBrush(g);p.drawPath(q)
    # Advected curls break the outline into separate, rising, pointed flames.
    # They are born at the mouth and fade at the tip instead of stretching a cone.
    for layer in range(3):
        for i in range(9):
            u=(phase*.9+i/9+layer*.037)%1
            x=14+u*(width-22)
            y=35+math.sin(phase*7+i*2.8+layer)*(3+u*7)
            r=(3+u*9)*(.85+.15*math.sin(phase*13+i))
            height=r*(1.7+.5*math.sin(phase*9+i*3))
            tip_x=x+math.sin(phase*12+i)*r*.7+r*.4
            q=QPainterPath(QPointF(x-r,y+r*.5))
            q.cubicTo(x-r*1.4,y-r*.5,x+r*.5,y-height*.4,tip_x,y-height)
            q.cubicTo(x+r*.1,y-height*.2,x+r*1.4,y,x+r*.5,y+r*.7)
            q.cubicTo(x,y+r,x-r,y+r*.8,x-r,y+r*.5)
            c=color.lighter(int(150-55*u)) if u<.65 else color.darker(int(110+100*(u-.65)))
            alpha=int(195*min(1,u/.1,(1-u)/.14))
            c.setAlpha(max(0,alpha))
            g=QLinearGradient(x,y+r*.5,tip_x,y-height)
            g.setColorAt(0,c.lighter(150));g.setColorAt(.5,c)
            edge=c.darker(160);edge.setAlpha(0);g.setColorAt(1,edge)
            p.setBrush(g);p.drawPath(q)
    # Narrow white-hot jets flicker independently inside the broad outer tongues.
    for i in range(3):
        length=55+12*i+9*math.sin(phase*21+i*3)
        tip=35+math.sin(phase*16+i*2)*5
        q=QPainterPath(QPointF(0,35))
        q.cubicTo(20,30,35,tip-5,length,tip)
        q.cubicTo(length*.7,tip+5,22,39,0,35)
        g=QLinearGradient(0,35,length,tip)
        g.setColorAt(0,QColor('#ffffff'));g.setColorAt(.35,hot)
        translucent=QColor(color.lighter(140));translucent.setAlpha(30);g.setColorAt(1,translucent)
        p.setBrush(g);p.drawPath(q)
    for i in range(16):
        t=(phase*1.6+i*.137)%1
        x=width*(.2+t*.8)
        y=max(3,min(67,35+math.sin(i*8+phase*5)*(7+t*18)+(i%3-1)*t*7))
        spark=QColor(color.lighter(180));spark.setAlpha(int(230*(1-t)))
        p.setPen(QPen(spark,1.1,Qt.SolidLine,Qt.RoundCap))
        p.drawLine(QPointF(x,y),QPointF(x-3-t*3,y+math.sin(i+phase)))
    p.restore()


def roof_flames(p,x,base,phase,coat,intensity=1):
    """Small persistent fires on thatch; no dependency on the breath emitter."""
    color=QColor(FIRE_COLORS[coat]);hot=QColor('#e6f7ff' if coat==3 else '#fff3bd')
    p.save();p.setPen(Qt.NoPen);p.setOpacity(min(1,intensity))
    for i in (-1,0,1):
        xx=x+i*6
        height=19+(1-abs(i))*9+math.sin(phase*13+i*3)*4
        tip=xx+math.sin(phase*11+i*4)*5
        q=QPainterPath(QPointF(xx-5,base))
        q.cubicTo(xx-9,base-height*.3,xx+2,base-height*.6,tip,base-height)
        q.cubicTo(xx+3,base-height*.5,xx+8,base-height*.3,xx+5,base)
        q.closeSubpath()
        g=QLinearGradient(xx,base,xx,base-height)
        g.setColorAt(0,hot);g.setColorAt(.35,color.lighter(135));g.setColorAt(.7,color)
        edge=color.darker(200);edge.setAlpha(70);g.setColorAt(1,edge)
        p.setBrush(g);p.drawPath(q)
    for i in range(3):
        rise=(phase*16+i*11)%32
        spark=QColor(color.lighter(160));spark.setAlpha(int(150*(1-rise/32)))
        p.setBrush(spark);p.drawEllipse(QRectF(x+math.sin(phase*3+i)*10,base-14-rise,1.6,2.2))
    p.restore()


def village(p,phase,progress=0,direction=1,coat=0,burn_age=0):
    from artwork import path,ellipse,stroke
    p.save();p.setPen(Qt.NoPen)
    if direction<0:p.translate(190,0);p.scale(-1,1)
    for i,(x,h) in enumerate(((58,27),(103,34),(150,23))):
        p.setBrush(QColor('#a98760'));p.drawRoundedRect(QRectF(x,85-h,27,h),1,1)
        p.setBrush(QColor('#3d3026'));p.drawRect(QRectF(x+10,74,7,11))
        p.setBrush(QColor('#c8a553'));p.drawPath(path([(x-6,85-h),(x+13,85-h-18),(x+33,85-h)]))
        for dx in range(-1,29,4):stroke(p,((x+dx,84-h),(x+13,69-h)),'#8b7137',.5)
        age=burn_age-i*.2
        if age>0:
            p.save();p.setOpacity(min(.65,age*.2));p.setBrush(QColor('#493a30'))
            p.drawPath(path([(x-6,85-h),(x+13,85-h-18),(x+33,85-h)]));p.restore()
            roof_flames(p,x+13,85-h-6,phase+i*.7,coat,min(1,age*2))
    for i in range(5):
        x=70+i*22-min(phase,4.7)*6-progress*175
        if x<16:continue
        stride=math.sin(phase*17+i)*2
        ellipse(p,x,74,2.6,2.6,'#342d27')
        stroke(p,((x+1.3,77),(x+1.3,81)),'#342d27',1)
        stroke(p,((x+1,78),(x-1,79+stride*.4)),'#342d27',.8)
        stroke(p,((x+1,81),(x-1+stride,84)),'#342d27',.8)
        stroke(p,((x+1,81),(x+3-stride,84)),'#342d27',.8)
    p.restore()


def dragon_dropping(p):
    """Small gold coin fragments embedded in the pile, not floating around it."""
    from artwork import path
    p.save();p.setPen(Qt.NoPen)
    pile=QPainterPath()
    for x,y,w,h in ((3,18,24,9),(7,12,17,10),(11,6,10,11)):
        q=QPainterPath();q.addEllipse(QRectF(x,y,w,h));pile=pile.united(q)
    p.setBrush(QColor('#70472f'));p.drawPath(pile)
    p.setClipPath(pile,Qt.IntersectClip)
    for x,y,angle in ((14,10,-22),(20,16,30),(8,22,-12),(16,23,18),(23,23,-40)):
        p.save();p.translate(x,y);p.rotate(angle)
        shard=path([(-2,-1),(-1,-2,2,-2,3,0),(1,2),(-2,1)])
        p.setPen(QPen(QColor('#a27119'),.55));p.setBrush(QColor('#e6b84b'));p.drawPath(shard)
        p.setPen(QPen(QColor('#fff0a3'),.6));p.drawLine(QPointF(-1,-1),QPointF(1.5,-.7))
        p.restore()
    p.restore()
