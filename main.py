"""Дракарий — маленькие драконы на рабочем столе Windows."""
from __future__ import annotations
import argparse
import ctypes
import html
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import random
import sys
import time

from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QIcon, QPixmap, QFont, QImage
from PySide6.QtWidgets import (QApplication, QWidget, QMenu, QSystemTrayIcon,
    QDialog, QFormLayout, QSpinBox, QComboBox, QCheckBox, QLineEdit, QDialogButtonBox, QMessageBox)
from artwork import draw_bed, draw_dog, rear_drop_offset, WALK_SPEED, RUN_SPEED
from appearance import Appearance, STYLES, COATS, FURS
from fire_art import FIRE_STYLES, surface_flames
from dragging import Suspension, draw_hanging
from dragon_art import flame as draw_flame, village as draw_village, dragon_dropping, dragon_mouth, breathing_pose

DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Drakarium'
SLEEP_SECONDS = 20 * 60
DEFAULT_DROPPING_MINUTES = 180


class Village(QWidget):
    def __init__(self,x,floor,direction,coat=0):
        super().__init__(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.WindowDoesNotAcceptFocus|Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(190,85)
        self.phase,self.progress,self.direction=0.,0.,direction
        self.coat=coat
        self.burning=False
        self.burn_age=0.
        self.move(round(x),round(floor-85));self.show()

    @property
    def eaten_count(self):
        return sum(70+i*22-min(self.phase,4.7)*6-self.progress*175<16 for i in range(5))

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        draw_village(p,self.phase,self.progress,self.direction,self.coat,self.burn_age if self.burning else 0)


class FireBreath(QWidget):
    def __init__(self,owner):
        super().__init__(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.WindowDoesNotAcceptFocus|Qt.WindowTransparentForInput)
        self.owner=owner;self.phase=0.;self.ignited=False
        self.style=getattr(owner.manager,'fire_style',0)
        self.setAttribute(Qt.WA_TranslucentBackground);self.setFixedSize(240,140)
        self.timer=QTimer(self);self.timer.timeout.connect(self.advance);self.timer.start(33)
        self.advance();self.show()

    def advance(self):
        self.phase+=.033
        pet=self.owner
        progress=pet.feeding_progress()
        mouth_x,mouth_y=dragon_mouth(pet.state,pet.phase,progress)
        self.angle=math.sin(pet.phase*3.8)*7*progress
        x=pet.xf+(mouth_x if pet.direction>0 else 160-mouth_x-240)
        self.move(round(x),round(pet.yf+pet.flight_offset+mouth_y-70))
        if self.phase>=.28 and not self.ignited:
            self.owner.ignite_surface(mouth_x,self.style)
            self.ignited=True
        self.update()
        if self.phase>=2.4:self.close()

    def closeEvent(self,event):
        self.timer.stop();super().closeEvent(event)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        if self.owner.direction<0:p.translate(240,0);p.scale(-1,1)
        if self.style==2:p.setRenderHint(QPainter.Antialiasing,False)
        p.translate(0,70);p.rotate(self.angle);p.translate(0,-35)
        draw_flame(p,self.phase,self.owner.appearance.coat,210,self.style)


SURFACE_FIRE_SECONDS=14.

class SurfaceFire(QWidget):
    def __init__(self,manager,left,right,floor,coat,style,support=None,now=None):
        super().__init__(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.WindowDoesNotAcceptFocus|Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAttribute(Qt.WA_DeleteOnClose)
        self.manager,self.left,self.right,self.floor=manager,float(left),float(right),float(floor)
        self.coat,self.style,self.support=coat,style,support
        self.created=time.monotonic() if now is None else now
        self.age=0.;self.opacity=0.
        screen=QApplication.screenAt(QPoint(round((left+right)/2),round(floor-2))) or QApplication.primaryScreen()
        self.screen_name=screen.name();self.screen_left=screen.availableGeometry().left()
        self.setFixedSize(max(1,round(right-left)),76)
        self.move(round(left),round(floor-70));self.show()

    def tick(self,now):
        self.age=max(0,now-self.created)
        if self.age>=SURFACE_FIRE_SECONDS:
            self.close();return False
        if self.support:
            matches=[v for v in self.manager.surfaces if v[0]==self.support[0]]
            if not matches:
                self.close();return False
            v=min(matches,key=lambda v:abs(v[1]-self.support[1]))
            shift=v[1]-self.support[1]
            left=max(v[1],self.left+shift);right=min(v[3],self.right+shift)
            if right-left<10:
                self.close();return False
            self.left,self.right,self.floor,self.support=left,right,v[2],v
        else:
            screen=next((s for s in QApplication.screens() if s.name()==self.screen_name),None)
            if not screen:self.close();return False
            r=screen.availableGeometry();shift=r.left()-self.screen_left
            self.left=max(r.left(),self.left+shift);self.right=min(r.right()+1,self.right+shift)
            self.screen_left=r.left();self.floor=r.bottom()+1
            if self.right-self.left<10:self.close();return False
        self.opacity=min(1,self.age/.35,(SURFACE_FIRE_SECONDS-self.age)/3)
        self.setFixedSize(max(1,round(self.right-self.left)),76)
        self.move(round(self.left),round(self.floor-70));self.update()
        return True

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.translate(0,70)
        surface_flames(p,self.width(),self.age,self.coat,self.style,self.opacity)


def setting_int(value, default, minimum, maximum):
    try:
        return max(minimum,min(maximum,int(value)))
    except (ValueError,TypeError,OverflowError):
        return default


class Bed(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(144, 34)
        self.opacity = 1.

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        draw_bed(p, self.opacity)


class AppearancePreview(QWidget):
    def __init__(self, appearance):
        super().__init__()
        self.appearance=appearance
        self.setFixedSize(320,230)
        self.setObjectName('appearancePreview')

    def paintEvent(self, event):
        p=QPainter(self)
        p.fillRect(self.rect(),QColor('#f6f0e6'))
        p.setRenderHint(QPainter.Antialiasing)
        p.save();p.scale(2,2)
        draw_dog(p,'walk',.2,appearance=self.appearance)
        p.restore()
        p.setPen(QColor('#59402e'))
        p.drawText(12,218,STYLES[self.appearance.style])


def bounded(value, fallback):
    try:
        value = float(value)
        return max(0,min(100,value)) if math.isfinite(value) else fallback
    except (TypeError,ValueError):
        return fallback


def window_tops(excluded):
    """Visible, unoccluded window tops in Qt logical coordinates, front to back."""
    if sys.platform != 'win32':
        return []
    user = ctypes.windll.user32
    user.GetWindowLongW.restype = ctypes.c_long
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    user.IsZoomed.argtypes = [wintypes.HWND]
    user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user.MonitorFromWindow.restype = wintypes.HANDLE
    class MonitorInfo(ctypes.Structure):
        _fields_ = [('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),('flags',wintypes.DWORD),('device',wintypes.WCHAR*32)]
    user.GetMonitorInfoW.argtypes = [wintypes.HANDLE,ctypes.POINTER(MonitorInfo)]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    surfaces, covers = [], []
    def visit(hwnd, _):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid() or not user.IsWindowVisible(hwnd) or user.IsIconic(hwnd):
            return True
        rect = wintypes.RECT()
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(rect), ctypes.sizeof(rect)):
            user.GetWindowRect(hwnd, ctypes.byref(rect))
        cloaked = wintypes.DWORD()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value or rect.right - rect.left < 160 or rect.bottom - rect.top < 70:
            return True
        # Convert physical Windows coordinates with the matching monitor origin.
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        user.GetMonitorInfoW(user.MonitorFromWindow(hwnd,2),ctypes.byref(info))
        screen = next((s for s in QApplication.screens() if s.name() == info.device), QApplication.primaryScreen())
        d = screen.devicePixelRatio()
        origin = screen.geometry().topLeft()
        left = origin.x()+round((rect.left-info.monitor.left)/d)
        right = origin.x()+round((rect.right-info.monitor.left)/d)
        top = origin.y()+round((rect.top-info.monitor.top)/d)
        bottom = origin.y()+round((rect.bottom-info.monitor.top)/d)
        spans = [(left, right)]
        for a, b, c, e in covers:
            if b <= top < e:
                spans = [(x, y) for l, r in spans for x, y in ((l, min(r, a)), (max(l, c), r)) if y-x >= 140]
        fullscreen=(rect.left<=info.monitor.left and rect.top<=info.monitor.top
                    and rect.right>=info.monitor.right and rect.bottom>=info.monitor.bottom)
        if not user.IsZoomed(hwnd) and not fullscreen:
            surfaces.extend((int(hwnd), l, top, r) for l, r in spans if top >= screen.geometry().top()+80)
        covers.append((left, top, right, bottom))
        return True
    callback = callback_type(visit)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.EnumWindows(callback, 0)
    return surfaces


class Dropping(QWidget):
    def __init__(self, x, y, minutes=DEFAULT_DROPPING_MINUTES):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedSize(30, 28)
        self.move(x, y-28)
        self.created_at = time.monotonic()
        self.removal_timer = QTimer(self)
        self.removal_timer.setTimerType(Qt.PreciseTimer)
        self.removal_timer.setSingleShot(True)
        self.removal_timer.timeout.connect(self.close)
        self.set_lifetime(minutes)
        self.show()
    def set_lifetime(self, minutes, now=None):
        now = time.monotonic() if now is None else now
        self.lifetime_minutes = setting_int(minutes,DEFAULT_DROPPING_MINUTES,1,1440)
        self.expires_at = self.created_at+self.lifetime_minutes*60
        self.removal_timer.start(max(0,math.ceil((self.expires_at-now)*1000)))
    def mousePressEvent(self, event):
        self.close()
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dragon_dropping(p)


class Pup(QWidget):
    def __init__(self, manager, saved=None):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.manager = manager
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(160, 112)
        self.hunger = bounded((saved or {}).get('hunger'), random.uniform(5,25))
        self.energy = bounded((saved or {}).get('energy'), 90)
        self.overfeed=bounded((saved or {}).get('overfeed'),0)
        self.fatness=min(1,self.overfeed/65)
        self.has_eaten=(saved or {}).get('has_eaten',False) is True
        self.bed_target_x=None
        value = (saved or {}).get('name')
        self.name = value.strip()[:40] if isinstance(value,str) and value.strip() else f'Дракон {len(getattr(manager,"pups",[]))+1}'
        self.appearance = Appearance.restore((saved or {}).get('appearance'))
        self.ear_angle = 0.
        self.ear_velocity = 0.
        self.next_zoomies = time.monotonic()+random.uniform(90,180)
        self.state, self.direction, self.phase = 'walk', random.choice([-1,1]), 0.
        self.deadline = time.monotonic()+random.uniform(6,14)
        self.digest_at = None
        self.anchor = None
        self.drag = None
        self.suspension = None
        self.drag_cursor = None
        self.drag_snapshot = None
        self.release_rig = None
        self.release_started = 0.
        self.release_origin = (0.,0.)
        self.canvas_padding = (0,0)
        self.landing_started = -10.
        self.press_position = None
        self.press_offset = None
        self.bed = None
        self.village=None
        self.flame=None
        self.flight_offset=0.
        self.flight_started=0.
        self.flight_origin=(0.,0.)
        self.flight_target=(0.,0.)
        self.flight_anchor=None
        self.travel_window=None
        self.travel_fraction=.5
        self.travel_duration=2.
        self.pending_sleep=False
        self.next_flight=time.monotonic()+random.uniform(35,75)
        self.meal_started=0.
        self.next_fire=time.monotonic()+random.uniform(75,150)
        self.wake_started = 0.
        self.awake_until = 0.
        self.pending_feed = False
        self.sit_pose = random.randrange(4)
        self.next_sit_pose = time.monotonic()+random.uniform(4,7)
        self.sit_transition = None
        self.velocity = 0.
        self.last = time.monotonic()
        r = QApplication.primaryScreen().availableGeometry()
        self.xf = float(random.randint(r.left(), max(r.left(),r.right()-160)))
        self.yf = float(r.bottom()+1-98)
        self.move(round(self.xf), round(self.yf))
        self.show()
        # Unlike hunger, sleep duration is in seconds and may exceed 100.
        try:
            remaining = max(0,min(SLEEP_SECONDS,float((saved or {}).get('sleep_remaining',0))))
        except (ValueError,TypeError):
            remaining = 0
        if remaining:
            self.start_sleep(self.last, remaining)
        elif self.overfeed:
            self.head_to_bed(self.last)

    @property
    def fullness(self):
        return max(0,100-self.hunger+self.overfeed)

    @property
    def speed_factor(self):
        return 1-.65*self.fatness

    def head_to_bed(self, now=None):
        now=time.monotonic() if now is None else now
        self.clear_bed()
        left,_,right=self.ground()
        if self.anchor:
            _,left,_,right=self.anchor
        lower,upper=left-4,max(left-4,right-156)
        self.direction=1 if upper-self.xf>=self.xf-lower else -1
        self.bed_target_x=max(lower,min(upper,self.xf+self.direction*75))
        self.bed=Bed()
        self.bed.move(round(self.bed_target_x+8),round(self.yf+64))
        self.bed.show();self.raise_()
        self.state='to_bed'
        self.deadline=now+30

    def add_extra_food(self):
        self.overfeed=min(100,self.overfeed+35)
        self.hunger=0

    def clear_bed(self):
        if self.bed:
            self.bed.close()
            self.bed = None
        self.bed_target_x=None

    def clear_village(self):
        if self.village:self.village.close();self.village=None
        if self.flame:self.flame.close();self.flame=None
        self.flight_offset=0.

    def feeding_progress(self,now=None):
        now=time.monotonic() if now is None else now
        if self.state=='hunt_fire':return max(0,min(1,(now-(self.deadline-2.5))/.4))
        if self.state=='fire':return max(0,min(1,(now-(self.deadline-2.4))/.25,(self.deadline-now)/.25))
        return 1.

    def ignite_surface(self,mouth_x,style=None):
        if self.state not in ('fire','hunt_fire'):return None
        if self.anchor:
            support=self.anchor;_,left,floor,right=support
        else:
            support=None;left,floor,right=self.ground()
        start=self.xf+(mouth_x if self.direction>0 else 160-mouth_x)
        ends=sorted((start+self.direction*20,start+self.direction*205))
        a,b=max(left,ends[0]),min(right,ends[1])
        if b-a<12:return None
        manager=self.manager
        if not hasattr(manager,'ground_fires'):manager.ground_fires=[]
        if len(manager.ground_fires)>=24:
            old=manager.ground_fires.pop(0)
            from shiboken6 import isValid
            if isValid(old):old.close()
        fire=SurfaceFire(manager,a,b,floor,self.appearance.coat,getattr(manager,'fire_style',0) if style is None else style,support)
        manager.ground_fires.append(fire)
        return fire

    def can_breathe_fire(self):
        return self.drag is None and self.state in ('walk','sit','lie') and not self.overfeed and not (self.flame and self.flame.isVisible())

    def breathe_fire(self,now=None):
        now=time.monotonic() if now is None else now
        if not self.can_breathe_fire():return False
        self.next_fire=now+random.uniform(75,150)
        self.flame=FireBreath(self)
        self.state,self.deadline='fire',now+2.4
        return True

    def launch_hunt(self,now=None):
        now=time.monotonic() if now is None else now
        self.clear_village()
        left,floor,right=self.ground()
        anchor=self.anchor
        if anchor and anchor[3]-anchor[1]>=480:
            _,left,floor,right=anchor
        else:anchor=None
        self.direction=1 if right-(self.xf+160)>=self.xf-left else -1
        if self.direction>0:
            target=max(left,min(right-316,self.xf+80))
            village_x=target+126
        else:
            target=min(right-160,max(left+156,self.xf-80))
            village_x=target-156
        self.flight_origin=(self.xf,self.yf)
        self.flight_target=(target,floor-98)
        self.flight_anchor=anchor
        self.flight_started=now
        self.state='fly_meal'
        self.village=Village(village_x,floor,self.direction,self.appearance.coat)
        self.raise_()

    def drag_image(self, state='hang_body', factor=1.):
        image=QImage(480,336,QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        p=QPainter(image)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(3,3)
        if self.direction<0:
            p.translate(160,0);p.scale(-1,1)
        rig=self.suspension or self.release_rig
        angles=tuple(b[2]*self.direction*factor for b in rig.bones()) if rig else None
        draw_dog(p,state,self.phase,self.animated_sit_pose(time.monotonic()),0,
                 self.appearance,self.ear_angle,angles,(rig.scruff*factor if rig else 0.),self.fatness)
        p.end()
        return image

    def begin_drag(self, cursor):
        self.clear_village()
        self.finish_release()
        self.travel_window=None
        self.pending_sleep=False
        self.pending_feed=False
        self.drag_snapshot=self.drag_image(self.state)
        self.wake(dragging=True)
        self.clear_bed()
        self.suspension=Suspension((self.press_offset.x(),self.press_offset.y()),self.direction)
        self.suspension.previous_cursor=(cursor.x(),cursor.y())
        self.drag=self.press_offset
        self.anchor=None
        self.state,self.deadline='walk',time.monotonic()+8
        self.setFixedSize(320,320)
        self.place_drag(cursor)

    def place_drag(self, cursor):
        self.drag_cursor=(float(cursor.x()),float(cursor.y()))
        x,y=cursor.x()-160,cursor.y()-120
        self.move(round(x),round(y))
        center=self.suspension.map(self.suspension.rest[1])
        rest=self.suspension.rest[1]
        self.xf,self.yf=x+center[0]-rest[0],y+center[1]-rest[1]

    def finish_release(self):
        if self.release_rig:
            self.release_rig=None
            self.canvas_padding=(0,0)
            self.setFixedSize(160,112)
            self.move(round(self.xf),round(self.yf))

    def place_normal(self):
        self.move(round(self.xf-self.canvas_padding[0]),round(self.yf+self.flight_offset-self.canvas_padding[1]))

    def serialize(self, now=None):
        now = time.monotonic() if now is None else now
        return {'hunger':self.hunger,'energy':self.energy,'name':self.name,
                'overfeed':self.overfeed,'has_eaten':self.has_eaten,
                'appearance':self.appearance.serialize(),
                'sleep_remaining':max(0,self.deadline-now) if self.state == 'sleep' else 0}

    def refresh_tooltip(self):
        lines = [self.name] if getattr(self.manager,'show_names',True) else []
        lines += [self.appearance.description,
                  f'Сытость {self.fullness:.0f}% · Энергия {self.energy:.0f}%',
                  'Перетащите мышью · ПКМ — меню']
        self.setToolTip('<qt>'+html.escape('\n'.join(lines)).replace('\n','<br>')+'</qt>')

    def can_zoom(self):
        left,_,right = self.ground()
        if self.anchor:
            _,left,_,right = self.anchor
        return not self.overfeed and right-left >= 420 and self.energy >= 55 and self.hunger < 45 and self.state not in ('sleep','wake','eat','poop','to_bed','fly_meal','travel_fly','hunt_fire','fire') and self.drag is None

    def start_zoomies(self, now=None):
        now = time.monotonic() if now is None else now
        self.next_zoomies = now+random.uniform(90,180)
        if not self.can_zoom():
            return False
        self.state,self.deadline = 'zoomies',now+random.uniform(5,9)
        return True

    def animate_ears(self, dt):
        target = (-math.degrees(self.suspension.bones()[-1][2])*self.direction+math.sin(self.phase*5)*3 if self.suspension else
                  48+math.sin(self.phase*18)*13 if self.state == 'zoomies' else
                  math.sin(self.phase*8)*9 if self.state == 'walk' else
                  math.sin(self.phase*1.6)*.5 if self.state == 'sleep' else
                  math.sin(self.phase*3)*2)
        # Small stable spring steps retain inertia even when a frame is late.
        steps = max(1,math.ceil(dt*120))
        step = dt/steps
        for _ in range(steps):
            self.ear_velocity += ((target-self.ear_angle)*100-self.ear_velocity*16)*step
            self.ear_angle += self.ear_velocity*step

    def start_sleep(self, now=None, duration=SLEEP_SECONDS):
        now = time.monotonic() if now is None else now
        if self.state=='travel_fly':
            self.pending_sleep=True
            return
        self.clear_village()
        self.clear_bed()
        self.state, self.deadline = 'sleep', now+duration
        self.sleep_started = now-(SLEEP_SECONDS-duration)
        self.pending_feed = False
        self.bed = Bed()
        self.bed.move(round(self.xf+8),round(self.yf+64))
        self.bed.show()
        self.raise_()

    def wake(self, now=None, dragging=False):
        now = time.monotonic() if now is None else now
        if self.state not in ('sleep','wake'):
            return
        if self.state=='sleep' and now>=self.deadline:
            self.overfeed=0
            self.fatness=0
        self.awake_until = now+60
        if dragging:
            self.clear_bed()
            self.state, self.deadline = 'walk', now+8
        else:
            self.state, self.wake_started = 'wake', now
            self.deadline = now+4.8
            left, _, right = self.ground()
            if self.anchor:
                _,left,_,right = self.anchor
            # Choose the side with enough room to step out of the bed.
            self.direction = 1 if right-(self.xf+148) >= self.xf-left else -1

    def start_sitting(self, now):
        self.state, self.deadline = 'sit', now+random.uniform(32,42)
        self.next_sit_pose = now+random.uniform(4,7)
        self.sit_transition = None

    def animated_sit_pose(self, now):
        if self.sit_transition is not None:
            t = min(1,max(0,(now-self.sit_transition)/.8))
            value = self.sit_pose+t*t*(3-2*t)
            if t >= 1:
                self.sit_pose = (self.sit_pose+1)%4
                self.sit_transition = None
                self.next_sit_pose = now+random.uniform(4,7)
            return value
        return float(self.sit_pose)

    def feed(self):
        if self.drag is None:
            if self.state=='travel_fly':
                if self.pending_feed:self.add_extra_food()
                self.pending_feed=True
                return
            if self.state in ('fly_meal','hunt_fire'):
                self.add_extra_food()
                return
            if self.state=='eat':
                self.add_extra_food()
                self.deadline=min(self.deadline,time.monotonic()+.8)
                return
            if self.overfeed and self.state in ('to_bed','sleep','wake'):
                self.add_extra_food()
                return
            if self.state in ('sleep','wake'):
                if self.pending_feed:
                    self.add_extra_food()
                self.pending_feed = True
                if self.state == 'sleep':
                    self.wake()
                return
            if self.has_eaten and self.hunger<20:
                self.add_extra_food()
            self.launch_hunt()

    def flight_surfaces(self):
        screen=QApplication.screenAt(QPoint(round(self.xf+80),round(self.yf+70))) or QApplication.primaryScreen()
        r=screen.availableGeometry()
        current=self.anchor[0] if self.anchor else None
        return [v for v in self.manager.surfaces
                if v[0]!=current and v[3]-v[1]>=160
                and r.left()<=v[1] and v[3]<=r.right()+1
                and r.top()+98<=v[2]<r.bottom()+1]

    def can_travel(self):
        return (self.state in ('walk','sit','lie') and self.drag is None
                and not self.release_rig and not self.overfeed and self.energy>=20
                and self.hunger<70 and self.flame is None)

    def start_flight(self, surface=None, now=None):
        now=time.monotonic() if now is None else now
        self.next_flight=now+random.uniform(35,75)
        choices=self.flight_surfaces()
        if not self.can_travel() or not choices:return False
        if surface is None:surface=random.choice(choices)
        if surface not in choices:return False
        self.clear_bed()
        self.travel_window=surface[0]
        self.travel_fraction=random.uniform(.2,.8)
        self.flight_origin=(self.xf,self.yf)
        self.flight_target=(surface[1]+self.travel_fraction*(surface[3]-surface[1]-160),surface[2]-98)
        self.travel_duration=max(1.4,min(5.,math.dist(self.flight_origin,self.flight_target)/185))
        self.flight_started=now
        self.flight_offset=0.
        self.anchor=None
        self.velocity=0
        self.state='travel_fly'
        self.direction=1 if self.flight_target[0]>=self.xf else -1
        return True

    def tick_flight(self, now, dt):
        # Replan from the visible position if the destination moves or vanishes.
        if self.travel_window is not None:
            matches=[v for v in self.flight_surfaces() if v[0]==self.travel_window]
            if matches:
                span=min(matches,key=lambda v:abs((v[1]+v[3])/2-(self.flight_target[0]+80)))
                target=(span[1]+self.travel_fraction*(span[3]-span[1]-160),span[2]-98)
            else:
                self.travel_window=None
                left,floor,right=self.ground()
                target=(max(left,min(right-160,self.xf)),floor-98)
            if math.dist(target,self.flight_target)>2:
                self.flight_origin=(self.xf,self.yf+self.flight_offset)
                self.flight_target=target
                self.flight_offset=0.
                self.flight_started=now
                self.travel_duration=max(1.,min(5.,math.dist(self.flight_origin,target)/185))
        progress=min(1,max(0,(now-self.flight_started)/self.travel_duration))
        ease=progress*progress*(3-2*progress)
        self.xf=self.flight_origin[0]+(self.flight_target[0]-self.flight_origin[0])*ease
        self.yf=self.flight_origin[1]+(self.flight_target[1]-self.flight_origin[1])*ease
        self.flight_offset=-math.sin(progress*math.pi)*min(65,20+self.travel_duration*10)
        self.energy=max(0,self.energy-dt*.6)
        if progress>=1-1e-8:
            self.flight_offset=0.
            matches=[v for v in self.manager.surfaces if v[0]==self.travel_window
                     and v[1]<=self.xf and self.xf+160<=v[3] and abs(v[2]-98-self.yf)<.5]
            self.anchor=matches[0] if matches else None
            self.travel_window=None
            self.landing_started=now
            self.next_flight=now+random.uniform(35,75)
            self.state,self.deadline='settle',now+.35
            if self.pending_feed or self.hunger>=70:
                self.pending_feed=False;self.pending_sleep=False;self.feed()
            elif self.pending_sleep:
                self.pending_sleep=False;self.start_sleep(now)
        self.place_normal();self.update()

    def ground(self):
        s = QApplication.screenAt(QPoint(round(self.xf+80),round(self.yf+70))) or QApplication.primaryScreen()
        r = s.availableGeometry()
        return r.left(), r.bottom()+1, r.right()+1

    def tick(self, now):
        dt = min(now-self.last, .1)
        self.last = now
        moving=self.state in ('walk','wake','to_bed')
        self.phase += dt*(14/WALK_SPEED if self.state=='to_bed' else self.speed_factor if moving else 1)
        target_fat=min(1,self.overfeed/65)
        self.fatness+=(target_fat-self.fatness)*min(1,dt*5)
        self.animate_ears(dt)
        self.hunger = min(100, self.hunger + dt*100/(self.manager.minutes*60)*(.12 if self.state == 'sleep' else 1))
        self.refresh_tooltip()
        if self.village:
            self.village.phase+=dt
            self.village.coat=self.appearance.coat
            if self.village.burning:self.village.burn_age+=dt
            if self.state=='eat':self.village.progress=min(1,(now-self.meal_started)/5)
            self.village.update()
        if self.drag is not None:
            self.suspension.step(dt,self.drag_cursor)
            self.place_drag(QPoint(round(self.drag_cursor[0]),round(self.drag_cursor[1])))
            self.update()
            return
        if self.release_rig and now-self.release_started >= .35:
            self.finish_release()
        if self.state=='travel_fly':
            self.tick_flight(now,dt)
            return
        if self.state=='fly_meal':
            progress=min(1,max(0,(now-self.flight_started)/2.2))
            t=progress*progress*(3-2*progress)
            self.xf=self.flight_origin[0]+(self.flight_target[0]-self.flight_origin[0])*t
            self.yf=self.flight_origin[1]+(self.flight_target[1]-self.flight_origin[1])*t
            self.flight_offset=-math.sin(progress*math.pi)*42
            if progress>=1-1e-8:
                self.flight_offset=0
                self.anchor=self.flight_anchor
                self.state='hunt_fire'
                self.deadline=now+2.5
                self.flame=FireBreath(self)
                if self.village:
                    self.village.burning=True
                    self.village.burn_age=.001
            self.place_normal();self.update();return
        left, floor, right = self.ground()
        previous_x, previous_y = self.xf,self.yf
        if self.anchor:
            matching = [s for s in self.manager.surfaces if s[0] == self.anchor[0]]
            predicted_x = self.xf + (matching[0][1]-self.anchor[1] if matching else 0)
            surface = next((s for s in matching if s[1] <= predicted_x+80 <= s[3]), None)
            if surface:
                self.xf = predicted_x
                self.anchor = surface
                _, left, floor, right = surface
                self.yf = floor-98
            else:
                self.anchor = None
        if not self.anchor and self.yf+98 < floor:
            self.velocity += 700*dt
            old = self.yf+98
            self.yf += self.velocity*dt
            candidates = [s for s in self.manager.surfaces if s[1] <= self.xf+80 <= s[3] and old <= s[2] <= self.yf+98]
            if candidates:
                surface = min(candidates, key=lambda s:s[2])
                self.anchor = surface
                self.yf = surface[2]-98
                self.velocity = 0
            elif self.yf+98 >= floor:
                self.yf = floor-98
                self.velocity = 0
        elif not self.anchor:
            self.yf = floor-98
        if self.state == 'fall' and (self.anchor or self.yf+98>=floor):
            self.landing_started=now
            self.state,self.deadline='settle',now+.35
        if self.state=='to_bed' and self.bed:
            self.bed_target_x+=self.xf-previous_x
            self.bed_target_x=max(left-4,min(max(left-4,right-156),self.bed_target_x))
            self.bed.move(round(self.bed_target_x+8),round(self.yf+64))
        # Keep a bed on a moving support while its dog is stepping out.
        if self.bed and self.state == 'wake':
            self.bed.move(self.bed.pos()+QPoint(round(self.xf-previous_x),round(self.yf-previous_y)))
        if self.bed and self.state == 'sleep':
            self.bed.move(round(self.xf+8),round(self.yf+64))
        if self.state == 'fall':
            pass
        elif self.state == 'settle':
            if now >= self.deadline:
                if self.overfeed:
                    self.head_to_bed(now)
                else:
                    self.state,self.deadline='walk',now+8
        elif self.state=='to_bed':
            distance=self.bed_target_x-self.xf
            step=min(abs(distance),14*dt)
            self.direction=1 if distance>=0 else -1
            self.xf+=self.direction*step
            if abs(self.bed_target_x-self.xf)<.5:
                self.start_sleep(now)
        elif self.state == 'sleep':
            self.energy = min(100, self.energy+dt*2)
            if now >= self.deadline:
                self.wake(now)
        elif self.state == 'wake':
            elapsed = now-self.wake_started
            if elapsed > .9:
                self.xf += self.direction*WALK_SPEED*self.speed_factor*dt
            if self.bed:
                self.bed.opacity = max(0, min(1, (4.8-elapsed)/.8))
                self.bed.update()
            if now >= self.deadline:
                self.clear_bed()
                self.state,self.deadline = 'walk',now+10
                if self.pending_feed:
                    self.pending_feed = False
                    self.feed()
                elif self.overfeed:
                    self.head_to_bed(now)
        elif self.state=='hunt_fire':
            if now>=self.deadline:
                if self.flame:self.flame.close();self.flame=None
                self.state='eat';self.meal_started=now
                self.deadline=now+(.8 if self.overfeed else 5)
        elif self.state == 'eat':
            self.hunger = max(0, self.hunger-dt*24)
            if now >= self.deadline:
                self.clear_village()
                self.digest_at = now+random.uniform(45,90)
                self.has_eaten=True
                if self.overfeed:
                    self.head_to_bed(now)
                else:
                    self.start_sitting(now)
        elif self.state=='fire':
            if now>=self.deadline:
                if self.flame:self.flame.close();self.flame=None
                self.state,self.deadline='walk',now+8
        elif self.state == 'poop':
            if now >= self.deadline:
                center = self.xf+rear_drop_offset(self.appearance,self.direction)
                self.manager.droppings.append(Dropping(round(center-15),round(self.yf+98),
                    getattr(self.manager,'dropping_minutes',DEFAULT_DROPPING_MINUTES)))
                self.state, self.digest_at = 'walk', None
                self.deadline = now+8
        elif self.state == 'zoomies':
            self.energy = max(0,self.energy-dt*1.1)
            self.xf += self.direction*RUN_SPEED*dt
            if now >= self.deadline:
                self.state,self.deadline = 'walk',now+8
        elif self.hunger >= 70:
            self.feed()
        elif self.digest_at and now >= self.digest_at:
            self.state, self.deadline = 'poop', now+3
        else:
            self.energy = max(0,self.energy-dt*.13)
            if now>=self.next_flight and self.can_travel() and self.hunger<45:
                if self.start_flight(now=now):
                    self.place_normal();self.update();return
            if now >= self.next_zoomies and self.can_zoom():
                self.start_zoomies(now)
            elif self.energy < 15 and now >= self.awake_until:
                self.start_sleep(now)
            elif now >= self.deadline:
                self.state = random.choices(['walk','sit','lie','sleep'], [55,20,20,5 if now >= self.awake_until else 0])[0]
                self.deadline = now+random.uniform(8,22)
                if self.state == 'sleep':
                    self.start_sleep(now)
                elif self.state == 'sit':
                    self.start_sitting(now)
            if self.state == 'walk':
                self.xf += self.direction*WALK_SPEED*self.speed_factor*dt
        if self.state == 'sit' and self.sit_transition is None and now >= self.next_sit_pose:
            self.sit_transition = now
        lower,upper = left-4,max(left-4,right-156)
        self.xf = max(lower,min(upper,self.xf))
        if self.state in ('walk','wake','zoomies') and ((self.xf <= lower and self.direction < 0) or
                                            (self.xf >= upper and self.direction > 0)):
            self.direction *= -1
        self.place_normal()
        if self.village and self.state=='eat':
            self.village.move(self.village.pos()+QPoint(round(self.xf-previous_x),round(self.yf-previous_y)))
        if now>=self.next_fire and self.state in ('walk','sit') and not self.overfeed:
            self.breathe_fire(now)
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.finish_release()
            self.press_position = e.globalPosition().toPoint()
            self.press_offset = self.press_position-self.pos()
        elif e.button() == Qt.RightButton:
            self.manager.menu(self).exec(e.globalPosition().toPoint())
    def mouseMoveEvent(self, e):
        if self.press_position is not None and self.drag is None:
            distance = (e.globalPosition().toPoint()-self.press_position).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self.begin_drag(e.globalPosition().toPoint())
        if self.drag is not None:
            self.place_drag(e.globalPosition().toPoint())
    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        self.press_position = None
        self.press_offset = None
        if self.drag is None:
            if self.state == 'sleep':
                self.wake()
            return
        self.end_drag()

    def end_drag(self):
        if self.drag is None:
            return
        self.press_position=None
        self.press_offset=None
        self.drag = None
        self.release_rig=self.suspension
        self.suspension=None
        self.release_started=time.monotonic()
        self.release_origin=(self.x()-self.xf,self.y()-self.yf)
        self.canvas_padding=(80,100)
        self.state,self.deadline='fall',self.release_started+1
        self.place_normal()
        self.velocity = 0
        surfaces = [s for s in self.manager.surfaces if s[1] <= self.xf+80 <= s[3] and abs(s[2]-(self.yf+98)) < 55]
        if surfaces:
            self.anchor = min(surfaces,key=lambda s:abs(s[2]-self.yf-98))
            self.yf = self.anchor[2]-98
        else:
            left, floor, right = self.ground()
            self.yf = min(self.yf, floor-98)

    def closeEvent(self, event):
        self.clear_village()
        self.clear_bed()
        super().closeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        if self.suspension:
            image=self.drag_image()
            t=min(1,self.suspension.elapsed/.2)
            if self.drag_snapshot is not None and t<1:
                blend=QPainter(image)
                blend.setCompositionMode(QPainter.CompositionMode_Source)
                blend.fillRect(image.rect(),Qt.transparent)
                blend.setOpacity(1-t);blend.drawImage(0,0,self.drag_snapshot)
                blend.setCompositionMode(QPainter.CompositionMode_SourceOver)
                blend.setOpacity(t);blend.drawImage(0,0,self.drag_image())
                blend.end()
            draw_hanging(p,image,self.suspension,self.appearance,self.phase)
            return
        p.translate(*self.canvas_padding)
        landing=(time.monotonic()-self.landing_started)/.35
        if 0<landing<1:
            squash=math.sin(math.pi*landing)
            p.translate(80,98);p.scale(1+.09*squash,1-.12*squash);p.translate(-80,-98)
        if self.release_rig:
            t=min(1,max(0,(time.monotonic()-self.release_started)/.35))
            ease=t*t*(3-2*t)
            def mapping(point):
                x,y=self.release_rig.map(point)
                x+=self.release_origin[0];y+=self.release_origin[1]
                return x*(1-ease)+point[0]*ease,y*(1-ease)+point[1]*ease
            draw_hanging(p,self.drag_image(factor=1-ease),self.release_rig,
                         self.appearance,self.phase,mapping,ease)
            return
        if self.state == 'sleep':
            p.setPen(QColor('#57758a'))
            p.drawText(95,25,'z Z z')
        elif self.hunger >= 45 and self.state != 'eat':
            p.setBrush(QColor('#fff4d7'))
            p.drawRoundedRect(41,3,82,24,10,10)
            p.setPen(QColor('#6d452b'))
            p.drawText(47,20,'Голод')
        p.setPen(Qt.NoPen)
        p.save()
        if self.direction < 0:
            p.translate(160,0)
            p.scale(-1,1)
        state = self.state
        if state in ('to_bed','fall','settle'):
            state='walk' if state=='to_bed' else 'sit'
        elapsed = 0
        if state == 'wake':
            elapsed = max(0,time.monotonic()-self.wake_started)
            state = 'wake' if elapsed < .9 else 'walk'
        draw_dog(p, state, self.phase, self.animated_sit_pose(time.monotonic()),elapsed,
                 self.appearance,self.ear_angle,chubby=self.fatness,
                 sleep_elapsed=max(0,time.monotonic()-getattr(self,'sleep_started',time.monotonic())),
                 feeding_progress=self.feeding_progress())
        p.restore()
        if self.state == 'eat':
            p.setPen(QColor('#81562f'))
            p.drawText(65,32,'')
        if self.drag is not None:
            p.setPen(QColor('#4b7979'))
            p.drawText(54,35,'')


class Manager:
    def __init__(self, app):
        self.app = app
        self.pups, self.surfaces, self.droppings = [], [], []
        self.ground_fires=[]
        self.fire_style=0
        self.minutes = 10
        self.dropping_minutes = DEFAULT_DROPPING_MINUTES
        self.show_names = True
        saved = {}
        try:
            saved = json.loads((DATA/'state.json').read_text(encoding='utf-8'))
            self.minutes = max(1,min(120,int(saved.get('minutes',10))))
            if not isinstance(saved,dict):
                saved = {}
        except (OSError, ValueError, TypeError, AttributeError):
            saved = {}
            pass
        self.dropping_minutes = setting_int(saved.get('dropping_minutes'),DEFAULT_DROPPING_MINUTES,1,1440)
        self.show_names = saved.get('show_names',True) is not False
        self.fire_style=setting_int(saved.get('fire_style'),0,0,len(FIRE_STYLES)-1)
        pix = QPixmap(64,64)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.scale(.4,.4)
        draw_dog(painter,'sit',0,appearance=Appearance(0,1,0,1))
        painter.end()
        app.setWindowIcon(QIcon(pix))
        self.tray = QSystemTrayIcon(QIcon(pix),app)
        self.tray.setToolTip('Дракарий — драконы на рабочем столе')
        self.tray.setContextMenu(self.menu())
        self.tray.show()
        states = saved.get('pups',[{}])
        if not isinstance(states,list):
            states = [{}]
        for state in states[:10]:
            self.add(state if isinstance(state,dict) else {})
        if not self.pups:
            self.add()
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)
        self.scan = QTimer()
        self.scan.timeout.connect(self.scan_windows)
        self.scan.start(250)
        self.autosave = QTimer()
        self.autosave.timeout.connect(self.save)
        self.autosave.start(30000)
        app.aboutToQuit.connect(self.save)
        app.aboutToQuit.connect(self.extinguish)
        self.scan_windows()
    def add(self, saved=None):
        if len(self.pups)<10:
            self.pups.append(Pup(self,saved))
    def scan_windows(self):
        self.surfaces = window_tops([])
    def tick(self):
        now = time.monotonic()
        for pup in self.pups:
            pup.tick(now)
        from shiboken6 import isValid
        self.droppings = [w for w in self.droppings if isValid(w)]
        self.ground_fires=[w for w in self.ground_fires if isValid(w) and w.tick(now)]
    def menu(self, pup=None):
        m = QMenu()
        m.addAction('Дракарий • настольные драконы').setEnabled(False)
        m.addSeparator()
        m.addAction('Добавить дракона',lambda:self.add())
        m.addAction('Покормить',lambda:[p.feed() for p in ([pup] if pup else self.pups)])
        fire_action=m.addAction('Выдохнуть огонь',lambda:[p.breathe_fire() for p in ([pup] if pup else self.pups)])
        fire_action.setEnabled(any(p.can_breathe_fire() for p in ([pup] if pup else self.pups)))
        m.aboutToShow.connect(lambda:fire_action.setEnabled(any(p.can_breathe_fire() for p in ([pup] if pup else self.pups))))
        m.addAction('Уложить спать',lambda:self.sleep(pup))
        if pup:
            flights=m.addMenu('Перелететь на окно')
            def refresh_flights():
                flights.clear()
                options=pup.flight_surfaces()
                if not options:
                    flights.addAction('Нет подходящих окон').setEnabled(False)
                else:
                    any_window=flights.addAction('Случайное окно',lambda:pup.start_flight())
                    any_window.setEnabled(pup.can_travel())
                    flights.addSeparator()
                    seen=set()
                    for surface in options:
                        if surface[0] in seen:continue
                        seen.add(surface[0])
                        title=f'Окно {surface[0]}'
                        if sys.platform=='win32':
                            text=ctypes.create_unicode_buffer(256)
                            ctypes.windll.user32.GetWindowTextW(wintypes.HWND(surface[0]),text,256)
                            title=text.value or title
                        action=flights.addAction(title[:70],lambda _checked=False,s=surface:pup.start_flight(s))
                        action.setEnabled(pup.can_travel())
            flights.aboutToShow.connect(refresh_flights)
            refresh_flights()
            m.addAction('Внешность…',lambda:self.appearance_dialog(pup))
            zoom = m.addAction('Устроить zoomies!',lambda:pup.start_zoomies())
            zoom.setEnabled(pup.can_zoom())
        m.addAction('Убрать за драконами',self.clean)
        m.addAction('Потушить огонь на поверхностях',self.extinguish)
        m.addAction('Настройки…',self.settings)
        if pup and len(self.pups)>1:
            m.addAction('Убрать этого дракона',lambda:self.remove(pup))
        m.addSeparator()
        m.addAction('Выход',self.app.quit)
        return m
    def sleep(self,pup):
        for p in ([pup] if pup else self.pups):
            p.start_sleep()
    def remove(self,pup):
        self.pups.remove(pup)
        pup.close()
    def extinguish(self):
        from shiboken6 import isValid
        for effect in getattr(self,'ground_fires',[]):
            if isValid(effect):effect.close()
        self.ground_fires=[]

    def clean(self):
        for w in self.droppings:
            try:
                w.close()
            except RuntimeError:
                pass
        self.droppings.clear()
    def settings(self):
        d = QDialog()
        d.setWindowTitle('Дракарий · Настройки')
        form = QFormLayout(d)
        interval = QSpinBox()
        interval.setRange(1,120)
        interval.setValue(self.minutes)
        interval.setSuffix(' мин')
        form.addRow('От сытости до полного голода:',interval)
        cleanup = QSpinBox()
        cleanup.setRange(1,1440)
        cleanup.setValue(self.dropping_minutes)
        cleanup.setSuffix(' мин')
        cleanup.setToolTip('180 минут = 3 часа. Отсчёт идёт от появления каждой какахи.')
        form.addRow('Удалять какахи через:',cleanup)
        fire_style=QComboBox()
        fire_style.setObjectName('fireStyle')
        fire_style.addItems(FIRE_STYLES)
        fire_style.setCurrentIndex(getattr(self,'fire_style',0))
        form.addRow('Вид драконьего огня:',fire_style)
        names_visible = QCheckBox('Показывать имя при наведении')
        names_visible.setChecked(self.show_names)
        form.addRow(names_visible)
        name_fields = []
        for i,pup in enumerate(self.pups):
            field = QLineEdit(pup.name)
            field.setMaxLength(40)
            form.addRow(f'Имя дракона {i+1} ({COATS[pup.appearance.coat]}):',field)
            name_fields.append((pup,field))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        form.addRow(buttons)
        if d.exec():
            self.minutes = interval.value()
            self.dropping_minutes = cleanup.value()
            self.show_names = names_visible.isChecked()
            self.fire_style=fire_style.currentIndex()
            for i,(pup,field) in enumerate(name_fields):
                pup.name = field.text().strip() or f'Дракон {i+1}'
                pup.refresh_tooltip()
            from shiboken6 import isValid
            for dropping in self.droppings:
                if isValid(dropping):
                    dropping.set_lifetime(self.dropping_minutes)
            self.save()
    def appearance_dialog(self,pup):
        d = QDialog()
        d.setWindowTitle('Дракарий · Внешность')
        form = QFormLayout(d)
        boxes = []
        for title,options,value in (('Окрас:',COATS,pup.appearance.coat),):
            box = QComboBox()
            box.addItems(options)
            box.setCurrentIndex(value)
            form.addRow(title,box)
            boxes.append(box)
        preview=AppearancePreview(pup.appearance)
        form.addRow(preview)
        def refresh_preview():
            preview.appearance=Appearance(coat=boxes[0].currentIndex(),
                fur=0,seed=pup.appearance.seed)
            preview.update()
        for box in boxes:
            box.currentIndexChanged.connect(refresh_preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        form.addRow(buttons)
        if d.exec():
            pup.appearance = preview.appearance
            pup.refresh_tooltip()
            pup.update()
            self.save()
    def save(self):
        try:
            DATA.mkdir(parents=True,exist_ok=True)
            (DATA/'state.tmp').write_text(json.dumps({'minutes':self.minutes,'dropping_minutes':self.dropping_minutes,
                'show_names':self.show_names,'fire_style':getattr(self,'fire_style',0),'pups':[p.serialize() for p in self.pups]}),encoding='utf-8')
            (DATA/'state.tmp').replace(DATA/'state.json')
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test',action='store_true')
    args = parser.parse_args()
    mutex = None
    if sys.platform == 'win32' and not args.smoke_test:
        kernel = ctypes.windll.kernel32
        kernel.CreateMutexW.restype = wintypes.HANDLE
        mutex = kernel.CreateMutexW(None,False,'Local\\DrakariumDesktopPets')
        if kernel.GetLastError() == 183:
            return 0
    app = QApplication(sys.argv[:1])
    app.setFont(QFont('Segoe UI',9))
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName('Дракарий')
    manager = Manager(app)
    if args.smoke_test:
        while len(manager.pups)<4:
            manager.add()
        for i,pup in enumerate(manager.pups):
            pup.appearance=Appearance(0,i%4,0,1729+i)
            pup.feed()
        pet=manager.pups[0]
        QTimer.singleShot(3300,pet.feed)
        QTimer.singleShot(8000,manager.pups[1].start_sleep)
        QTimer.singleShot(8500,manager.pups[1].wake)
        QTimer.singleShot(8500,manager.pups[2].breathe_fire)
        QTimer.singleShot(8500,manager.pups[3].breathe_fire)
        grabbed=manager.pups[1]
        def smoke_grab():
            offset=QPoint(108 if grabbed.direction>0 else 52,49)
            grabbed.press_offset=offset
            grabbed.begin_drag(QPoint(round(grabbed.xf),round(grabbed.yf))+offset)
        def smoke_move():
            grabbed.place_drag(QPoint(round(grabbed.drag_cursor[0]+60),round(grabbed.drag_cursor[1]-25)))
        QTimer.singleShot(9000,smoke_grab)
        QTimer.singleShot(9400,smoke_move)
        QTimer.singleShot(10000,grabbed.end_drag)
        def recover():
            pet.start_sleep()
            pet.deadline=time.monotonic()
        QTimer.singleShot(11000,recover)
        def smoke_fire_style(style,index):
            manager.fire_style=style
            dragon=manager.pups[index]
            dragon.clear_village();dragon.clear_bed();dragon.anchor=None
            r=app.primaryScreen().availableGeometry()
            dragon.xf=float(r.left()+20);dragon.yf=float(r.bottom()+1-98)
            dragon.direction=1;dragon.state='walk';dragon.overfeed=0
            assert dragon.breathe_fire()
            assert dragon.flame.style==style
        QTimer.singleShot(5500,lambda:smoke_fire_style(1,3))
        QTimer.singleShot(8000,lambda:smoke_fire_style(2,2))
        def smoke_flight():
            manager.scan.stop()
            r=app.primaryScreen().availableGeometry()
            surface=(90001,r.left()+180,r.top()+220,r.left()+620)
            manager.surfaces=[surface]
            flyer=manager.pups[2]
            flyer.clear_village();flyer.clear_bed();flyer.anchor=None
            flyer.xf=float(r.left()+20);flyer.yf=float(r.bottom()+1-98)
            flyer.state='walk';flyer.hunger=10;flyer.energy=90;flyer.overfeed=0
            assert flyer.start_flight(surface)
        def smoke_flight_landed():
            flyer=manager.pups[2]
            if not flyer.anchor or flyer.anchor[0]!=90001:
                app.exit(2)
            if not any(f.style==2 for f in manager.ground_fires):
                app.exit(3)
        QTimer.singleShot(13000,smoke_flight)
        QTimer.singleShot(18500,smoke_flight_landed)
        QTimer.singleShot(19500,app.quit)
    result = app.exec()
    if mutex:
        ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(mutex))
    return result


if __name__ == '__main__':
    sys.exit(main())
