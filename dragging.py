"""Four-bone hanging rig with bounded spring dynamics and exact cursor pinning."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QTransform


def rotate(point, angle):
    x,y=point
    c,s=math.cos(angle),math.sin(angle)
    return c*x-s*y,s*x+c*y


class Suspension:
    anchor=(160.,120.)
    limits=(1.45,1.05,1.05,.35)
    grab_points=(('Круп',(40,65)),('Спина',(78,65)),('Холка',(108,49)),('Голова',(139,45)))

    def __init__(self, grab, direction=1):
        self.grab=tuple(grab)
        self.direction=direction
        u=grab[0] if direction>0 else 160-grab[0]
        self.scruff=math.exp(-((u-108)/14)**2-((grab[1]-49)/18)**2)
        self.limits=(1.45,1.05,1.05,.35+.95*self.scruff)
        self.rest=[(x if direction>0 else 160-x,y) for x,y in ((36.,75.),(74.,75.),(112.,75.),(130.,53.))]
        self.angles=[0.,0.,0.,0.]
        self.speeds=[0.,0.,0.,0.]
        self.limb_angles=[0.,0.,0.,0.]
        self.limb_speeds=[0.,0.,0.,0.]
        self.previous_cursor=None
        self.cursor_velocity=(0.,0.)
        self.acceleration=(0.,0.)
        self.elapsed=0.
        self._map_key=None

    def bones(self, angles=None):
        theta,rear,front,head=self.angles if angles is None else angles
        mid=self.rest[1]
        a=rotate((-38*self.direction,0),theta+rear)
        b=rotate((38*self.direction,0),theta+front)
        neck=rotate((3*self.direction,-12),theta+front)
        skull=rotate((15*self.direction,-10),theta+front+head)
        return [(mid[0]+a[0],mid[1]+a[1],theta+rear),
                (*mid,theta),(mid[0]+b[0],mid[1]+b[1],theta+front),
                (mid[0]+b[0]+neck[0]+skull[0],mid[1]+b[1]+neck[1]+skull[1],theta+front+head)]

    def raw(self, point, angles=None, bones=None):
        x,y=point
        u=x if self.direction>0 else 160-x
        if u<=36:
            weights=(1,0,0)
        elif u<74:
            t=(u-36)/38
            weights=(1-t,t,0)
        elif u<112:
            t=(u-74)/38
            weights=(0,1-t,t)
        else:
            weights=(0,0,1)
        head_weight=max(0,min(1,(u-108)/22))*max(0,min(1,(80-y)/20))
        weights=tuple(w*(1-head_weight) for w in weights)+(head_weight,)
        out=[0.,0.]
        for weight,rest,bone in zip(weights,self.rest,self.bones(angles) if bones is None else bones):
            dx,dy=rotate((x-rest[0],y-rest[1]),bone[2])
            out[0]+=weight*(bone[0]+dx)
            out[1]+=weight*(bone[1]+dy)
        return tuple(out)

    def map(self, point):
        key=tuple(self.angles)
        if key!=self._map_key:
            self._map_key=key
            self._map_bones=self.bones()
            self._map_grab=self.raw(self.grab,bones=self._map_bones)
        x,y=self.raw(point,bones=self._map_bones)
        gx,gy=self._map_grab
        return x-gx+self.anchor[0],y-gy+self.anchor[1]

    def potential(self, angles, gravity):
        bones=self.bones(angles)
        gx,gy=self.raw(self.grab,bones=bones)
        energy=0.
        for x,y,rear_mass,front_mass in ((42,78,.3,.2),(78,78,.4,.25),(111,70,.2,.3),(130,52,.1,.25)):
            mass=rear_mass+(front_mass-rear_mass)*self.scruff
            point=(x if self.direction>0 else 160-x,y)
            px,py=self.raw(point,bones=bones)
            energy-=mass*((px-gx)*gravity[0]+(py-gy)*gravity[1])
        return energy

    def step(self, dt, cursor):
        dt=max(0.,min(.1,dt))
        if dt<=0:
            return
        cursor=tuple(cursor)
        if self.previous_cursor is not None:
            velocity=tuple(max(-2200,min(2200,(a-b)/dt)) for a,b in zip(cursor,self.previous_cursor))
            acceleration=tuple(max(-1800,min(1800,(a-b)/dt)) for a,b in zip(velocity,self.cursor_velocity))
            self.acceleration=tuple(a*.65+b*.35 for a,b in zip(self.acceleration,acceleration))
            self.cursor_velocity=velocity
        self.previous_cursor=cursor
        gravity=(-self.acceleration[0]*.7,850-self.acceleration[1]*.55)
        count=max(1,math.ceil(dt*180))
        h=dt/count
        for _ in range(count):
            settings=((1900,5,12*self.scruff,self.limits[0]),(650,8,12,self.limits[1]),
                      (650,8,12,self.limits[2]),(420,10,55,self.limits[3]))
            for i,(inertia,damping,stiffness,limit) in enumerate(settings):
                a=self.angles.copy();b=self.angles.copy()
                a[i]+=.001;b[i]-=.001
                torque=-(self.potential(a,gravity)-self.potential(b,gravity))/.002
                rest=(.10*self.scruff*self.direction if i==0 else
                      1.05*self.scruff*self.direction if i==3 else 0.)
                acceleration=torque/inertia-damping*self.speeds[i]-stiffness*(self.angles[i]-rest)
                self.speeds[i]=max(-6,min(6,self.speeds[i]+acceleration*h))
                self.angles[i]+=self.speeds[i]*h
                if abs(self.angles[i])>limit:
                    self.angles[i]=math.copysign(limit,self.angles[i])
                    self.speeds[i]*=-.12
            target=max(-.8,min(.8,math.atan2(self.acceleration[0]*.6,max(250,850-self.acceleration[1]*.5))))
            for i in range(4):
                self.limb_speeds[i]+=((target-self.limb_angles[i])*45-self.limb_speeds[i]*7)*h
                self.limb_angles[i]=max(-.9,min(.9,self.limb_angles[i]+self.limb_speeds[i]*h))
        self.elapsed+=dt


def draw_mesh(p, image, mapping):
    """Skin the existing artwork so all coats and fur follow the same bones."""
    p.save()
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setRenderHint(QPainter.Antialiasing,False)
    xs=list(range(0,161,8))
    ys=list(range(0,113,14))
    vertices={(x,y):mapping((x,y)) for x in xs for y in ys}
    for x in xs[:-1]:
        for y in ys[:-1]:
            for source in (((x,y),(x+8,y),(x+8,y+14)),((x,y),(x+8,y+14),(x,y+14))):
                destination=[vertices[v] for v in source]
                (u0,v0),(u1,v1),(u2,v2)=source
                (x0,y0),(x1,y1),(x2,y2)=destination
                du1,dv1,du2,dv2=u1-u0,v1-v0,u2-u0,v2-v0
                det=du1*dv2-du2*dv1
                a=((x1-x0)*dv2-(x2-x0)*dv1)/det
                c=(-(x1-x0)*du2+(x2-x0)*du1)/det
                b=((y1-y0)*dv2-(y2-y0)*dv1)/det
                d=(-(y1-y0)*du2+(y2-y0)*du1)/det
                clip=QPainterPath(QPointF(x0,y0))
                clip.lineTo(x1,y1);clip.lineTo(x2,y2);clip.closeSubpath()
                p.save()
                p.setClipPath(clip,Qt.IntersectClip)
                p.setTransform(QTransform(a,b,c,d,x0-a*u0-c*v0,y0-b*u0-d*v0),True)
                p.drawImage(QRectF(0,0,160,112),image)
                p.restore()
    p.restore()


def draw_hanging(p, image, rig, appearance, phase, mapping=None, release=0.):
    """Draw limbs as independent pendulums, outside the deforming body texture."""
    from artwork import Artist, model_scale
    mapping = rig.map if mapping is None else mapping
    sx,sy=model_scale(appearance)
    artist=Artist(p,appearance,phase,0)
    def legs(far):
        for index,x in enumerate((43,108) if far else (36,111)):
            source_x=80+(x-80)*sx
            if rig.direction<0:
                source_x=160-source_x
            root=mapping((source_x,98+(82-98)*sy))
            limb=index+(0 if far else 2)
            sway=math.degrees(rig.limb_angles[limb])*(1-release)
            p.save()
            p.setOpacity(p.opacity()*min(1,rig.elapsed/.2))
            p.translate(*root)
            p.rotate(sway)
            p.scale(sx*rig.direction,sy)
            artist.leg(0,0,0,16,far)
            p.restore()
    legs(True)
    draw_mesh(p,image,mapping)
    legs(False)
