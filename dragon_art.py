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

    def tail(self,x,y,running=False,resting=False):
        from artwork import path
        sway=math.sin(self.phase*5)*(4 if running else 2)
        q=path([(x+5,y),(x-13,y+5,x-17,y-15,2,y-17+sway),
                (9,y-9,x-12,y+14,x+5,y+9)])
        self.fill(q,5)

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
        flight=state in ('fly_meal','zoomies');moving=state=='walk' or flight
        t=self.phase*(RUN_FREQUENCY if flight else WALK_FREQUENCY)
        bob=math.sin(t)*.7 if moving else 0
        self.wing(86,65,flight,True,not flight)
        self.tail(30,63+bob,flight)
        for index,x in enumerate((43,109)):
            if state=='hang_body':continue
            dx,lift=foot_cycle(t+index*math.pi+math.pi,flight) if moving else (0,0)
            self.leg(x,79+bob,x+dx,92 if flight else 98-lift,True)
        body=path([(28,73),(26,62,38,58,54,61),(72,66,85,61,98,54),
                   (105,48,106,45,114,45),(126,45,128,58,122,69),
                   (116,84,109,90,95,90),(72,89,49,89,37,91),(28,91,25,83,28,73)])
        if self.chubby:
            b=QPainterPath();b.addEllipse(QRectF(23,50,101,46));body=body.united(b)
        self.fill(body,1)
        chest=path([(110,55),(125,58,123,75,109,87),(102,89),(111,73,112,66,110,55)])
        self.fill(chest,2,tone=self.light)
        for index,x in enumerate((37,110)):
            if state=='hang_body':continue
            dx,lift=foot_cycle(t+index*math.pi,flight) if moving else (0,0)
            self.leg(x,79+bob,x+dx,92 if flight else 98-lift)
        for x,y in ((37,61),(46,61),(56,63),(67,64),(78,61),(88,58),(98,53)):
            self.fill(path([(x,y+2),(x-2,y-5),(x+5,y+1)]),4,tone=self.horn)
        self.wing(83,65,flight,False,not flight)
        if state=='eat':self.head(103,63+math.sin(self.phase*9)*.8,25+math.sin(self.phase*8)*2,running=True)
        else:self.head(105,36+bob,-4 if flight else self.perch_tilt,running=state=='fire')

    def curled(self,unfold=0):
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
        self.head(86,65,27,sleeping=unfold<.2)
        p.restore()


def flame(p,phase,coat,width=190):
    color=QColor(FIRE_COLORS[coat]);p.save();p.setPen(Qt.NoPen)
    strength=min(1,phase*4,max(0,(2.4-phase)*3))
    p.setOpacity(strength)
    length=width*(.80+.13*math.sin(phase*19))
    g=QLinearGradient(0,35,length,35);g.setColorAt(0,QColor('#fff9de'));g.setColorAt(.16,color.lighter(170));g.setColorAt(.6,color);end=QColor(color);end.setAlpha(0);g.setColorAt(1,end)
    p.setBrush(g)
    q=QPainterPath(QPointF(0,35))
    q.cubicTo(35,29,40,3,length,9+math.sin(phase*23)*8)
    q.cubicTo(length*.7,25,length,23,length,37)
    q.cubicTo(length*.7,47,length*.85,68,length*.45,54)
    q.cubicTo(35,46,20,39,0,35)
    p.drawPath(q)
    for i in range(11):
        t=(phase*1.6+i*.11)%1
        spark=QColor(color.lighter(145));spark.setAlpha(int(210*(1-t)))
        p.setBrush(spark);p.drawEllipse(QRectF(t*width,33+math.sin(i*8+phase*9)*(5+t*21),2+2*t,1.4+2*t))
    p.restore()


def village(p,phase,progress=0,direction=1):
    from artwork import path,ellipse,stroke
    p.save();p.setPen(Qt.NoPen)
    if direction<0:p.translate(190,0);p.scale(-1,1)
    for i,(x,h) in enumerate(((58,27),(103,34),(150,23))):
        p.setBrush(QColor('#a98760'));p.drawRoundedRect(QRectF(x,85-h,27,h),1,1)
        p.setBrush(QColor('#3d3026'));p.drawRect(QRectF(x+10,74,7,11))
        p.setBrush(QColor('#c8a553'));p.drawPath(path([(x-6,85-h),(x+13,85-h-18),(x+33,85-h)]))
        for dx in range(-1,29,4):stroke(p,((x+dx,84-h),(x+13,69-h)),'#8b7137',.5)
    for i in range(5):
        x=70+i*22-min(phase,2.2)*6-progress*175
        if x<16:continue
        stride=math.sin(phase*17+i)*2
        ellipse(p,x,74,2.6,2.6,'#342d27')
        stroke(p,((x+1.3,77),(x+1.3,81)),'#342d27',1)
        stroke(p,((x+1,78),(x-1,79+stride*.4)),'#342d27',.8)
        stroke(p,((x+1,81),(x-1+stride,84)),'#342d27',.8)
        stroke(p,((x+1,81),(x+3-stride,84)),'#342d27',.8)
    p.restore()
