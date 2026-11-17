"""Таксон — маленькие таксы на рабочем столе Windows."""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import random
import sys
import time

from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QIcon, QPixmap, QFont
from PySide6.QtWidgets import (QApplication, QWidget, QMenu, QSystemTrayIcon,
    QDialog, QFormLayout, QSpinBox, QDialogButtonBox, QMessageBox)
from artwork import draw_bed, draw_dog

DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Takson'
SLEEP_SECONDS = 20 * 60


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
    def __init__(self, x, y):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedSize(30, 28)
        self.move(x, y-28)
        self.show()
        QTimer.singleShot(60000, self.close)
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
        self.state, self.direction, self.phase = 'walk', random.choice([-1,1]), 0.
        self.deadline = time.monotonic()+random.uniform(6,14)
        self.digest_at = None
        self.anchor = None
        self.drag = None
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

    def clear_bed(self):
        if self.bed:
            self.bed.close()
            self.bed = None

    def start_sleep(self, now=None, duration=SLEEP_SECONDS):
        now = time.monotonic() if now is None else now
        self.clear_bed()
        self.state, self.deadline = 'sleep', now+duration
        self.pending_feed = False
        self.bed = Bed()
        self.bed.move(round(self.xf+8),round(self.yf+64))
        self.bed.show()
        self.raise_()

    def wake(self, now=None, dragging=False):
        now = time.monotonic() if now is None else now
        if self.state not in ('sleep','wake'):
            return
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
            if self.state in ('sleep','wake'):
                self.pending_feed = True
                if self.state == 'sleep':
                    self.wake()
                return
            self.state = 'eat'
            self.deadline = time.monotonic()+5

    def ground(self):
        s = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        r = s.availableGeometry()
        return r.left(), r.bottom()+1, r.right()+1

    def tick(self, now):
        dt = min(now-self.last, .1)
        self.last = now
        self.phase += dt
        self.hunger = min(100, self.hunger + dt*100/(self.manager.minutes*60)*(.12 if self.state == 'sleep' else 1))
        self.setToolTip(f'Таксон · Голод {self.hunger:.0f}% · Энергия {self.energy:.0f}%\nПеретащите мышью · ПКМ — меню')
        if self.drag is not None:
            self.update()
            return
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
        # Keep a bed on a moving support while its dog is stepping out.
        if self.bed and self.state == 'wake':
            self.bed.move(self.bed.pos()+QPoint(round(self.xf-previous_x),round(self.yf-previous_y)))
        if self.bed and self.state == 'sleep':
            self.bed.move(round(self.xf+8),round(self.yf+64))
        if self.state == 'sleep':
            self.energy = min(100, self.energy+dt*2)
            if now >= self.deadline:
                self.wake(now)
        elif self.state == 'wake':
            elapsed = now-self.wake_started
            if elapsed > .9:
                self.xf += self.direction*38*dt
            if self.bed:
                self.bed.opacity = max(0, min(1, (4.8-elapsed)/.8))
                self.bed.update()
            if now >= self.deadline:
                self.clear_bed()
                self.state,self.deadline = 'walk',now+10
                if self.pending_feed:
                    self.pending_feed = False
                    self.feed()
        elif self.state == 'eat':
            self.hunger = max(0, self.hunger-dt*24)
            if now >= self.deadline:
                self.digest_at = now+random.uniform(45,90)
                self.start_sitting(now)
        elif self.state == 'poop':
            if now >= self.deadline:
                self.manager.droppings.append(Dropping(round(self.xf+35), round(self.yf+98)))
                self.state, self.digest_at = 'walk', None
                self.deadline = now+8
        elif self.hunger >= 70:
            self.feed()
        elif self.digest_at and now >= self.digest_at:
            self.state, self.deadline = 'poop', now+3
        else:
            self.energy = max(0,self.energy-dt*.13)
            if self.energy < 15 and now >= self.awake_until:
                self.start_sleep(now)
            elif now >= self.deadline:
                self.state = random.choices(['walk','sit','lie','sleep'], [55,20,20,5 if now >= self.awake_until else 0])[0]
                self.deadline = now+random.uniform(8,22)
                if self.state == 'sleep':
                    self.start_sleep(now)
                elif self.state == 'sit':
                    self.start_sitting(now)
            if self.state == 'walk':
                self.xf += self.direction*38*dt
        if self.state == 'sit' and self.sit_transition is None and now >= self.next_sit_pose:
            self.sit_transition = now
        lower,upper = left-4,max(left-4,right-156)
        self.xf = max(lower,min(upper,self.xf))
        if self.state in ('walk','wake') and ((self.xf <= lower and self.direction < 0) or
                                            (self.xf >= upper and self.direction > 0)):
            self.direction *= -1
        self.move(round(self.xf), round(self.yf))
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.press_position = e.globalPosition().toPoint()
            self.press_offset = self.press_position-self.pos()
        elif e.button() == Qt.RightButton:
            self.manager.menu(self).exec(e.globalPosition().toPoint())
    def mouseMoveEvent(self, e):
        if self.press_position is not None and self.drag is None:
            distance = (e.globalPosition().toPoint()-self.press_position).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self.wake(dragging=True)
                self.drag = self.press_offset
                self.anchor = None
        if self.drag is not None:
            pos = e.globalPosition().toPoint()-self.drag
            self.xf, self.yf = float(pos.x()), float(pos.y())
            self.move(pos)
    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        self.press_position = None
        self.press_offset = None
        if self.drag is None:
            if self.state == 'sleep':
                self.wake()
            return
        self.drag = None
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
        elapsed = 0
        if state == 'wake':
            elapsed = max(0,time.monotonic()-self.wake_started)
            state = 'wake' if elapsed < .9 else 'walk'
        draw_dog(p, state, self.phase, self.animated_sit_pose(time.monotonic()),elapsed)
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
        saved = {}
        try:
            saved = json.loads((DATA/'state.json').read_text(encoding='utf-8'))
            self.minutes = max(1,min(120,int(saved.get('minutes',10))))
            if not isinstance(saved,dict):
                saved = {}
        except (OSError, ValueError, TypeError, AttributeError):
            saved = {}
            pass
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
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        form.addRow(buttons)
        if d.exec():
            self.minutes = interval.value()
            self.save()
    def save(self):
        try:
            DATA.mkdir(parents=True,exist_ok=True)
            (DATA/'state.tmp').write_text(json.dumps({'minutes':self.minutes,'pups':[{'hunger':p.hunger,'energy':p.energy,'sleep_remaining':max(0,p.deadline-time.monotonic()) if p.state == 'sleep' else 0} for p in self.pups]}),encoding='utf-8')
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
        pup = manager.pups[0]
        pup.feed()
        QTimer.singleShot(300,pup.start_sleep)
        QTimer.singleShot(600,pup.wake)
        QTimer.singleShot(6000,app.quit)
    result = app.exec()
    if mutex:
        ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(mutex))
    return result


if __name__ == '__main__':
    sys.exit(main())
