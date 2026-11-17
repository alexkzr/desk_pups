"""Three selectable wide breath sprites and persistent small surface flames."""
import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor,QLinearGradient,QPainterPath,QPen
FIRE_STYLES=('Живой факел','Рваная струя','Пиксельное пламя')
COLORS=(('#fff8d5','#ffe68b','#ff9b35','#e84c19','#9a2d19'),
        ('#fff3d6','#ffbf72','#ff5d35','#ca1832','#690f2c'),
        ('#fffef0','#fff7ad','#ffde3c','#e58c16','#8c5419'),
        ('#f1fcff','#a6edff','#55b5ff','#3960e4','#343380'))

def tint(value,alpha=1):
    c=QColor(value);c.setAlphaF(max(0,min(1,alpha)));return c

def polygon(p,points,brush):
    q=QPainterPath(QPointF(*points[0]))
    for v in points[1:]:
        if len(v)==6:q.cubicTo(*v)
        elif len(v)==4:q.quadTo(*v)
        else:q.lineTo(*v)
    q.closeSubpath();p.setBrush(QColor(brush) if isinstance(brush,str) else brush);p.drawPath(q)

def palette_gradient(colors,width):
    g=QLinearGradient(0,0,width,0)
    for pos,col in zip((0,.12,.42,.78,1),colors):g.setColorAt(pos,tint(col,.3 if pos==1 else 1))
    return g

def tongue(p,x,y,r,brush,angle=0,stretch=1):
    p.save();p.translate(x,y);p.rotate(angle);p.scale(stretch,1)
    polygon(p,[(-r,0),(-r*.9,-r*.9,r*.55,-r*.9,r*1.35,-r*.18),
               (r*2,-r*.7),(r*1.3,r*.35,r*.15,r*1.1,-r,0)],brush)
    p.restore()

def flame(p,phase,coat,width=190,style=0):
    colors=COLORS[coat];p.save();p.setPen(Qt.NoPen)
    strength=min(1,max(0,phase*5),max(0,(2.4-phase)*4))
    p.setOpacity(p.opacity()*strength);p.translate(0,35)
    if style==2:
        step=3;frame=math.floor(phase*12)
        for x in range(0,int(width-5),step):
            u=x/width;mid=round(math.sin(x*.09-frame*.7)*u*2)*step
            breadth=round((1+9*math.sin(u*math.pi*.9))*(.8+.2*math.sin(x*.17-frame*1.3)))*step
            for y in range(-breadth,breadth+1,step):
                v=abs(y)/max(1,breadth)
                col=colors[3] if v>.75 else colors[2] if v>.4 else colors[1]
                if u<.3 and v<.4:col=colors[0]
                if u>.82 and (math.sin(x*2+y*3+frame)*43758)%1>.52:continue
                p.setBrush(tint(col));p.drawRect(QRectF(x,y+mid,step,step))
    elif style==1:
        for layer in range(3):
            points=[];length=width-layer*23
            for side in (-1,1):
                for j in range(71):
                    u=j/70 if side==-1 else 1-j/70
                    noise=math.sin(u*37-phase*9)*.5+math.sin(u*79-phase*15)*.3+math.sin(u*131-phase*23)*.2
                    breadth=(3+32*math.sin(math.pi*u*.88))*(1-.24*layer)*max(0,1-u)**.25
                    center=math.sin(u*16-phase*9)*u*5
                    points.append((u*length,center+side*breadth*(.78+.23*noise)))
            c=colors if layer<2 else (colors[0],colors[0],colors[1],colors[2],colors[3])
            polygon(p,points,palette_gradient(c,length))
        for i in range(14):
            u=(phase*.85+i/14)%1;r=2+u*6
            p.save();p.setOpacity(p.opacity()*math.sin(u*math.pi)*.65)
            tongue(p,u*(width-10),math.sin(phase*5+i*7)*u*28,r,colors[1] if u<.4 else colors[2],math.sin(phase*5+i)*40,1.4)
            p.restore()
    else:
        # A broad continuous underlay joins the independently moving tongues.
        polygon(p,[(0,-3),(width*.3,-27,width*.6,-25,width-7,-3),
                   (width*.7,26,width*.3,27,0,3)],palette_gradient(colors,width))
        for layer in range(3):
            for i in range(26):
                u=(phase*(.65+layer*.06)+i/26+layer*.017)%1
                x=u*(width-20);y=math.sin(i*8.14+phase*2.8)*u**.7*(15+layer*7)
                r=2+u*(10-layer)
                p.save();p.setOpacity(p.opacity()*max(0,min(1,u*8,(1-u)*5))*(.62+layer*.08))
                g=QLinearGradient(x-r,y+r,x+r*2,y-r)
                g.setColorAt(0,tint(colors[1] if u<.35 else colors[2]))
                g.setColorAt(.55,tint(colors[0] if u<.2 else colors[2]))
                g.setColorAt(1,tint(colors[3],.25 if u>.65 else 1))
                tongue(p,x,y,r,g,math.sin(phase*7+i)*35,1.5);p.restore()
    if style!=2:
        g=QLinearGradient(0,0,width*.35,0);g.setColorAt(0,tint(colors[0]));g.setColorAt(1,tint(colors[1],.05))
        polygon(p,[(0,-3),(18,-9,35,-7,width*.35,0),(35,8,18,8,0,3)],g)
        for i in range(15):
            u=(phase*.75+i/15)%1;x=20+u*(width-23);y=math.sin(i*12.1+phase*3)*34*u
            p.setPen(QPen(tint(colors[1],math.sin(u*math.pi)*.8),1.1,Qt.SolidLine,Qt.RoundCap))
            p.drawLine(QPointF(x,y),QPointF(x-1-u*3,y));p.setPen(Qt.NoPen)
    p.restore()

def surface_flames(p,width,phase,coat,style=0,intensity=1):
    colors=COLORS[coat];p.save();p.setPen(Qt.NoPen);p.setOpacity(p.opacity()*intensity)
    count=max(2,int(width/13))
    for i in range(count):
        x=6+i*(width-12)/max(1,count-1)
        height=18+9*math.sin(i*2.17)**2+math.sin(phase*9+i*2.3)*5
        lean=math.sin(phase*7+i*2)*5
        if style==2:
            step=3;h=round(height/step)*step
            for row in range(int(h/step)):
                u=row/max(1,h/step);w=max(step,round((1-u)*2)*step)
                xx=x+round(lean*u/step)*step
                p.setBrush(tint(colors[0] if u<.2 else colors[1] if u<.45 else colors[2] if u<.8 else colors[3]))
                p.drawRect(QRectF(xx-w,-row*step-step,w*2,step))
        else:
            g=QLinearGradient(x,0,x,-height);g.setColorAt(0,tint(colors[0]));g.setColorAt(.4,tint(colors[1]));g.setColorAt(.7,tint(colors[2]));g.setColorAt(1,tint(colors[3],.3))
            polygon(p,[(x-5,0),(x-10,-height*.3,x+1,-height*.6,x+lean,-height),
                       (x+2,-height*.4,x+8,-height*.2,x+5,0)],g)
    p.restore()
