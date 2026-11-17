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

DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Takson'


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
        self.velocity = 0.
        self.last = time.monotonic()
        r = QApplication.primaryScreen().availableGeometry()
        self.xf = float(random.randint(r.left(), max(r.left(),r.right()-160)))
        self.yf = float(r.bottom()+1-98)
        self.move(round(self.xf), round(self.yf))
        self.show()

    def feed(self):
        if self.drag is None:
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
        self.hunger = min(100, self.hunger + dt*100/(self.manager.minutes*60))
        self.setToolTip(f'Таксон · Голод {self.hunger:.0f}% · Энергия {self.energy:.0f}%\nПеретащите мышью · ПКМ — меню')
        if self.drag is not None:
            self.update()
            return
        left, floor, right = self.ground()
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
        if self.state == 'eat':
            self.hunger = max(0, self.hunger-dt*24)
            if now >= self.deadline:
                self.digest_at = now+random.uniform(45,90)
                self.state = 'sit'
                self.deadline = now+5
        elif self.state == 'poop':
            if now >= self.deadline:
                self.manager.droppings.append(Dropping(round(self.xf+35), round(self.yf+98)))
                self.state, self.digest_at = 'walk', None
                self.deadline = now+8
        elif self.hunger >= 70:
            self.feed()
        elif self.digest_at and now >= self.digest_at:
            self.state, self.deadline = 'poop', now+3
        elif self.state == 'sleep':
            self.energy = min(100, self.energy+dt*2)
            if now >= self.deadline or self.energy >= 100:
                self.state, self.deadline = 'walk', now+10
        else:
            self.energy = max(0,self.energy-dt*.13)
            if self.energy < 15:
                self.state, self.deadline = 'sleep', now+45
            elif now >= self.deadline:
                self.state = random.choices(['walk','sit','lie','sleep'], [55,20,20,5])[0]
                self.deadline = now+random.uniform(8,22)
            if self.state == 'walk':
                self.xf += self.direction*38*dt
        self.xf = max(left-12,min(right-148,self.xf))
        if self.xf <= left-12 or self.xf >= right-148:
            self.direction *= -1
        self.move(round(self.xf), round(self.yf))
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag = e.globalPosition().toPoint()-self.pos()
            self.anchor = None
        elif e.button() == Qt.RightButton:
            self.manager.menu(self).exec(e.globalPosition().toPoint())
    def mouseMoveEvent(self, e):
        if self.drag is not None:
            pos = e.globalPosition().toPoint()-self.drag
            self.xf, self.yf = float(pos.x()), float(pos.y())
            self.move(pos)
    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
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
        low = self.state in ('lie','sleep')
        sitting = self.state == 'sit'
        bob = math.sin(self.phase*12)*1.7 if self.state == 'walk' else 0
        p.translate(0,bob)
        p.setPen(QPen(QColor('#5b2e1b'),6,Qt.SolidLine,Qt.RoundCap))
        wag = math.sin(self.phase*9)*7
        if sitting:
            p.drawLine(62,91,37,94)
        else:
            p.drawLine(28,74,14,round(58+wag))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#7f421f'))
        for i,x in enumerate(() if sitting else (40,55,99,113)):
            stride = math.sin(self.phase*11+i*math.pi)*5 if self.state == 'walk' else 0
            p.drawRoundedRect(round(x+stride),82 if not low else 90,10,16 if not low else 8,4,4)
        p.setBrush(QColor('#a75b2c'))
        if sitting:
            body = QPainterPath()
            body.moveTo(56,90)
            body.cubicTo(56,79,72,76,79,67)
            body.lineTo(94,44)
            body.cubicTo(103,40,113,47,110,59)
            body.lineTo(102,90)
            body.cubicTo(87,98,66,99,56,90)
            p.drawPath(body)
            p.drawEllipse(53,77,35,21)
            p.setBrush(QColor('#7f421f'))
            p.drawRoundedRect(91,68,9,30,4,4)
            p.setBrush(QColor('#c17b40'))
            p.drawRoundedRect(104,65,9,33,4,4)
            p.drawRoundedRect(98,93,18,5,2,2)
            p.drawRoundedRect(65,92,21,6,3,3)
        elif self.state == 'poop':
            p.drawEllipse(34,71,37,27)
            p.drawRoundedRect(52,60,70,30,13,13)
        else:
            p.drawRoundedRect(25,64 if not low else 77,98,26 if not low else 20,13,13)
        p.save()
        if sitting:
            p.translate(-18,-24)
        p.setBrush(QColor('#c17b40'))
        p.drawEllipse(99,49 if not low else 66,33,34)
        p.drawRoundedRect(119,65 if not low else 80,27,14,6,6)
        p.setBrush(QColor('#68371f'))
        p.drawRoundedRect(102,55 if not low else 72,16,35 if not low else 24,8,8)
        p.setBrush(QColor('#251f21'))
        p.drawEllipse(139,65 if not low else 80,8,7)
        eye_y = 60 if not low else 77
        if self.state == 'sleep':
            p.setPen(QPen(QColor('#251f21'),2))
            p.drawLine(123,eye_y+2,128,eye_y+2)
            p.setPen(Qt.NoPen)
        else:
            p.drawEllipse(124,eye_y,4,5)
        p.setBrush(QColor('#42a89c'))
        p.drawRoundedRect(115,78 if not low else 89,7,11 if not low else 6,2,2)
        p.restore()
        p.restore()
        if self.state == 'eat':
            p.setBrush(QColor('#e9b867'))
            p.drawEllipse(116,94,35,6)
            p.setBrush(QColor('#437d91'))
            p.drawRoundedRect(116,97,35,12,5,5)
            p.setPen(QColor('#81562f'))
            p.drawText(78,37,'ням!')
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
            p.state,p.deadline = 'sleep',time.monotonic()+45
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
            (DATA/'state.tmp').write_text(json.dumps({'minutes':self.minutes,'pups':[{'hunger':p.hunger,'energy':p.energy} for p in self.pups]}),encoding='utf-8')
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
        manager.pups[0].feed()
        QTimer.singleShot(1500,app.quit)
    result = app.exec()
    if mutex:
        ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(mutex))
    return result


if __name__ == '__main__':
    sys.exit(main())
