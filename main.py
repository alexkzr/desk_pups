"""Таксон — маленькие таксы на рабочем столе Windows."""
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
from dragging import Suspension, draw_hanging

DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Takson'
SLEEP_SECONDS = 20 * 60
DEFAULT_DROPPING_MINUTES = 180


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
        if not user.IsZoomed(hwnd):
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
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#70472f'))
        for x, y, w, h in [(3,18,24,9),(7,12,17,10),(11,6,10,11)]:
            p.drawEllipse(x,y,w,h)


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
        self.name = value.strip()[:40] if isinstance(value,str) and value.strip() else f'Такса {len(getattr(manager,"pups",[]))+1}'
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
        self.finish_release()
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
        self.move(round(self.xf-self.canvas_padding[0]),round(self.yf-self.canvas_padding[1]))

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
        return not self.overfeed and right-left >= 420 and self.energy >= 55 and self.hunger < 45 and self.state not in ('sleep','wake','eat','poop','to_bed') and self.drag is None

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
            self.state = 'eat'
            self.deadline = time.monotonic()+(.8 if self.overfeed else 5)

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
        if self.drag is not None:
            self.suspension.step(dt,self.drag_cursor)
            self.place_drag(QPoint(round(self.drag_cursor[0]),round(self.drag_cursor[1])))
            self.update()
            return
        if self.release_rig and now-self.release_started >= .35:
            self.finish_release()
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
        elif self.state == 'eat':
            self.hunger = max(0, self.hunger-dt*24)
            if now >= self.deadline:
                self.digest_at = now+random.uniform(45,90)
                self.has_eaten=True
                if self.overfeed:
                    self.head_to_bed(now)
                else:
                    self.start_sitting(now)
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
            p.drawText(47,20,'Хочу есть…')
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
                 sleep_elapsed=max(0,time.monotonic()-getattr(self,'sleep_started',time.monotonic())))
        p.restore()
        if self.state == 'eat':
            p.setPen(QColor('#81562f'))
            p.drawText(65,32,'ням!')
        if self.drag is not None:
            p.setPen(QColor('#4b7979'))
            p.drawText(54,35,'уиии!')


class Manager:
    def __init__(self, app):
        self.app = app
        self.pups, self.surfaces, self.droppings = [], [], []
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
        pix = QPixmap(64,64)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setBrush(QColor('#a75b2c'))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(5,25,45,20,8,8)
        painter.drawEllipse(40,14,20,24)
        painter.end()
        self.tray = QSystemTrayIcon(QIcon(pix),app)
        self.tray.setToolTip('Таксон — таксы на рабочем столе')
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
    def menu(self, pup=None):
        m = QMenu()
        m.addAction('Таксон • настольные таксы').setEnabled(False)
        m.addSeparator()
        m.addAction('Добавить таксу',lambda:self.add())
        m.addAction('Покормить',lambda:[p.feed() for p in ([pup] if pup else self.pups)])
        m.addAction('Уложить спать',lambda:self.sleep(pup))
        if pup:
            m.addAction('Внешность…',lambda:self.appearance_dialog(pup))
            zoom = m.addAction('Устроить zoomies!',lambda:pup.start_zoomies())
            zoom.setEnabled(pup.can_zoom())
        m.addAction('Убрать за собаками',self.clean)
        m.addAction('Настройки…',self.settings)
        if pup and len(self.pups)>1:
            m.addAction('Убрать эту таксу',lambda:self.remove(pup))
        m.addSeparator()
        m.addAction('Выход',self.app.quit)
        return m
    def sleep(self,pup):
        for p in ([pup] if pup else self.pups):
            p.start_sleep()
    def remove(self,pup):
        self.pups.remove(pup)
        pup.close()
    def clean(self):
        for w in self.droppings:
            try:
                w.close()
            except RuntimeError:
                pass
        self.droppings.clear()
    def settings(self):
        d = QDialog()
        d.setWindowTitle('Таксон · Настройки')
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
        names_visible = QCheckBox('Показывать имя при наведении')
        names_visible.setChecked(self.show_names)
        form.addRow(names_visible)
        name_fields = []
        for i,pup in enumerate(self.pups):
            field = QLineEdit(pup.name)
            field.setMaxLength(40)
            form.addRow(f'Имя таксы {i+1} ({COATS[pup.appearance.coat]}):',field)
            name_fields.append((pup,field))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        form.addRow(buttons)
        if d.exec():
            self.minutes = interval.value()
            self.dropping_minutes = cleanup.value()
            self.show_names = names_visible.isChecked()
            for i,(pup,field) in enumerate(name_fields):
                pup.name = field.text().strip() or f'Такса {i+1}'
                pup.refresh_tooltip()
            from shiboken6 import isValid
            for dropping in self.droppings:
                if isValid(dropping):
                    dropping.set_lifetime(self.dropping_minutes)
            self.save()
    def appearance_dialog(self,pup):
        d = QDialog()
        d.setWindowTitle('Таксон · Внешность')
        form = QFormLayout(d)
        boxes = []
        for title,options,value in (('Окрас:',COATS,pup.appearance.coat),
                                    ('Шерсть:',FURS,pup.appearance.fur)):
            box = QComboBox()
            box.addItems(options)
            box.setCurrentIndex(value)
            form.addRow(title,box)
            boxes.append(box)
        preview=AppearancePreview(pup.appearance)
        form.addRow(preview)
        def refresh_preview():
            preview.appearance=Appearance(coat=boxes[0].currentIndex(),
                fur=boxes[1].currentIndex(),seed=pup.appearance.seed)
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
                'show_names':self.show_names,'pups':[p.serialize() for p in self.pups]}),encoding='utf-8')
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
        mutex = kernel.CreateMutexW(None,False,'Local\\TaksonDesktopPets')
        if kernel.GetLastError() == 183:
            return 0
    app = QApplication(sys.argv[:1])
    app.setFont(QFont('Segoe UI',9))
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName('Таксон')
    manager = Manager(app)
    if args.smoke_test:
        while len(manager.pups)<4:
            manager.add()
        for i,pup in enumerate(manager.pups):
            pup.appearance = Appearance(i%4,i%3,i%2,1729+i)
            pup.feed()
        QTimer.singleShot(300,lambda:[p.start_sleep() for p in manager.pups])
        QTimer.singleShot(600,lambda:[p.wake() for p in manager.pups])
        pet=manager.pups[0]
        def smoke_grab():
            offset=QPoint(108 if pet.direction>0 else 52,49)
            pet.press_offset=offset
            pet.begin_drag(QPoint(round(pet.xf),round(pet.yf))+offset)
        def smoke_move(dx,dy):
            if pet.drag_cursor:
                pet.place_drag(QPoint(round(pet.drag_cursor[0]+dx),round(pet.drag_cursor[1]+dy)))
        QTimer.singleShot(850,smoke_grab)
        QTimer.singleShot(1300,lambda:smoke_move(90,-20))
        QTimer.singleShot(1900,lambda:smoke_move(-50,25))
        QTimer.singleShot(2300,pet.end_drag)
        QTimer.singleShot(2600,pet.feed)
        QTimer.singleShot(2800,pet.feed)
        QTimer.singleShot(6000,lambda:[p.start_zoomies() for p in manager.pups])
        def smoke_recover():
            if pet.overfeed:
                pet.start_sleep()
                pet.deadline=time.monotonic()
        QTimer.singleShot(10000,smoke_recover)
        QTimer.singleShot(11800,app.quit)
    result = app.exec()
    if mutex:
        ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(mutex))
    return result


if __name__ == '__main__':
    sys.exit(main())
