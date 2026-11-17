"""Deterministic checks of timing and attachment without waiting real minutes."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import time
import unittest
import hashlib
import random
from unittest.mock import patch
from types import SimpleNamespace
from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtWidgets import QApplication, QSpinBox, QLineEdit, QCheckBox
from PySide6.QtGui import QImage, QPainter
from main import Pup, Manager, Dropping, SLEEP_SECONDS
from artwork import draw_dog
from shiboken6 import isValid
from appearance import Appearance


class FakeManager:
    minutes = 10
    surfaces = []
    droppings = []


class BehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.manager = FakeManager()
        self.manager.surfaces = []
        self.manager.droppings = []
        self.pup = Pup(self.manager, {'hunger': 10, 'energy': 90})
        self.now = time.monotonic()

    def tearDown(self):
        self.pup.close()
        for w in self.manager.droppings:
            w.close()

    def step(self, delta=.1):
        self.now += delta
        self.pup.tick(self.now)

    def test_hunger_and_automatic_feeding(self):
        self.step()
        self.assertGreater(self.pup.hunger,10)
        self.pup.hunger = 71
        self.step()
        self.assertEqual(self.pup.state,'eat')
        for _ in range(60):
            self.step()
        self.assertLess(self.pup.hunger,5)
        self.assertIsNotNone(self.pup.digest_at)

    def test_digestion_produces_dropping(self):
        self.pup.digest_at = self.now-1
        self.step()
        self.assertEqual(self.pup.state,'poop')
        for _ in range(35):
            self.step()
        self.assertEqual(len(self.manager.droppings),1)
        self.assertIsNone(self.pup.digest_at)

    def test_sleep_restores_energy(self):
        self.pup.energy = 10
        self.step()
        self.assertEqual(self.pup.state,'sleep')
        self.step()
        self.assertGreater(self.pup.energy,10)

    def test_window_move_and_disappear(self):
        self.pup.xf = 100
        self.pup.anchor = (1,0,300,600)
        self.manager.surfaces = [(1,20,350,620)]
        self.pup.state = 'sit'
        self.step()
        self.assertEqual(self.pup.xf,120)
        self.assertEqual(self.pup.yf,252)
        self.manager.surfaces = []
        self.step()
        self.assertIsNone(self.pup.anchor)
        self.assertGreater(self.pup.yf,252)

    def test_sleep_last_twenty_minutes_despite_hunger_and_full_energy(self):
        self.pup.hunger = 99
        self.pup.energy = 100
        self.pup.digest_at = self.now-1
        self.pup.start_sleep(self.now)
        self.assertEqual(self.pup.deadline,self.now+1200)
        self.step(1199)
        self.assertEqual(self.pup.state,'sleep')
        self.assertIsNotNone(self.pup.bed)
        self.assertEqual(len(self.manager.droppings),0)
        self.step(1)
        self.assertEqual(self.pup.state,'wake')
        self.assertIsNotNone(self.pup.bed)

    def test_sleep_hunger_slower_and_saved_duration_restored(self):
        self.pup.start_sleep(self.now)
        before = self.pup.hunger
        self.step()
        self.assertAlmostEqual(self.pup.hunger-before,.1*100/600*.12)
        other = Pup(self.manager,{'sleep_remaining':1100})
        try:
            self.assertEqual(other.state,'sleep')
            self.assertAlmostEqual(other.deadline-other.last,1100)
        finally:
            other.close()

    def event(self, dx=0):
        pos = self.pup.pos()+self.pup.rect().center()
        return SimpleNamespace(button=lambda:Qt.LeftButton,
                               globalPosition=lambda:QPointF(pos.x()+dx,pos.y()))

    def test_click_wakes_without_detaching_and_bed_disappears_after_exit(self):
        self.pup.xf = 200
        self.pup.anchor = (1,0,300,900)
        self.manager.surfaces = [self.pup.anchor]
        self.pup.start_sleep(self.now)
        self.pup.mousePressEvent(self.event())
        self.assertEqual(self.pup.state,'sleep')
        self.assertIsNone(self.pup.drag)
        self.pup.mouseReleaseEvent(self.event())
        self.assertEqual(self.pup.state,'wake')
        self.assertIsNotNone(self.pup.anchor)
        self.assertIsNotNone(self.pup.bed)
        self.now = self.pup.wake_started
        original_x = self.pup.xf
        for _ in range(50):
            self.step()
        self.assertIsNone(self.pup.bed)
        self.assertGreater(abs(self.pup.xf-original_x),120)
        self.assertEqual(self.pup.state,'walk')

    def test_drag_sleeping_dog_wakes_and_removes_bed(self):
        self.pup.start_sleep(self.now)
        self.pup.mousePressEvent(self.event())
        self.pup.mouseMoveEvent(self.event(QApplication.startDragDistance()+5))
        self.assertIsNotNone(self.pup.drag)
        self.assertIsNone(self.pup.bed)
        self.assertEqual(self.pup.state,'walk')
        self.pup.mouseReleaseEvent(self.event())
        self.assertIsNone(self.pup.drag)

    def test_manual_feed_waits_for_waking_exit(self):
        self.pup.start_sleep(self.now)
        self.pup.feed()
        self.assertEqual(self.pup.state,'wake')
        self.assertTrue(self.pup.pending_feed)
        self.now = self.pup.deadline
        self.pup.tick(self.now)
        self.assertEqual(self.pup.state,'eat')
        self.assertIsNone(self.pup.bed)

    def test_four_sitting_poses_cycle_with_smooth_transition(self):
        self.pup.start_sitting(self.now)
        self.pup.sit_pose = 0
        for expected in (1,2,3,0):
            self.now = self.pup.next_sit_pose
            self.pup.tick(self.now)
            halfway = self.pup.animated_sit_pose(self.now+.4)
            self.assertAlmostEqual(halfway,self.pup.sit_pose+.5)
            self.pup.animated_sit_pose(self.now+.81)
            self.assertEqual(self.pup.sit_pose,expected)

    def test_bowl_is_on_support_and_mirrors_with_dog(self):
        def render(left):
            image = QImage(160,112,QImage.Format_ARGB32)
            image.fill(Qt.transparent)
            painter = QPainter(image)
            if left:
                painter.translate(160,0)
                painter.scale(-1,1)
            draw_dog(painter,'eat',0)
            painter.end()
            return image
        right,left = render(False),render(True)
        self.assertGreater(right.pixelColor(130,97).alpha(),0)
        self.assertGreater(left.pixelColor(29,97).alpha(),0)
        for image in (right,left):
            self.assertTrue(all(image.pixelColor(x,y).alpha()==0
                                for y in range(99,112) for x in range(160)))
        # Compare the prop, not floating-point gradient rounding on the dog.
        for x in range(5,40):
            for y in range(85,99):
                self.assertEqual(right.pixelColor(159-x,y),left.pixelColor(x,y))

    def test_saved_appearance_and_marbling_survive_restart(self):
        self.pup.appearance = Appearance(3,2,1,139871)
        other = Pup(self.manager,self.pup.serialize(self.now))
        try:
            self.assertEqual(other.appearance,self.pup.appearance)
        finally:
            other.close()

    def test_old_and_corrupt_appearance_settings_are_supported(self):
        for value in (None,[],{}, {'style':99,'coat':-8,'fur':'oops','seed':None}):
            look=Appearance.restore(value)
            self.assertIn(look.style,range(4))
            self.assertIn(look.coat,range(3))
            self.assertIn(look.fur,range(2))

    def test_new_dogs_randomize_all_four_appearance_fields(self):
        with patch('appearance.random.randrange',side_effect=[3,2,1,12345]):
            self.assertEqual(Appearance.random(),Appearance(3,2,1,12345))

    def test_all_24_looks_are_distinct_and_render_all_poses(self):
        digests=set()
        rng_state=random.getstate()
        for style in range(4):
            for coat in range(3):
                for fur in range(2):
                    look=Appearance(style,coat,fur,7128)
                    for state in ('walk','sit','eat','sleep','wake','lie','zoomies'):
                        image=QImage(160,112,QImage.Format_ARGB32)
                        image.fill(Qt.transparent)
                        p=QPainter(image)
                        draw_dog(p,state,.7,1,.4,look,8)
                        p.end()
                        self.assertTrue(any(image.pixelColor(x,80).alpha() for x in range(160)))
                        if state=='walk':
                            digests.add(hashlib.sha256(image.constBits()).hexdigest())
        self.assertEqual(len(digests),24)
        self.assertEqual(random.getstate(),rng_state)

    def test_zoomies_respect_space_needs_and_stop(self):
        self.pup.ground=lambda:(0,800,1200)
        self.pup.xf=250
        self.pup.hunger=10
        self.pup.energy=90
        self.assertTrue(self.pup.start_zoomies(self.now))
        self.pup.direction=1
        self.step()
        self.assertAlmostEqual(self.pup.xf,271)
        self.assertLess(self.pup.energy,90)
        self.assertGreaterEqual(self.pup.deadline,self.now+4)
        self.now=self.pup.deadline
        self.pup.tick(self.now)
        self.assertEqual(self.pup.state,'walk')
        self.pup.anchor=(1,0,300,360)
        self.assertFalse(self.pup.start_zoomies(self.now))
        self.pup.anchor=None
        self.pup.hunger=80
        self.assertFalse(self.pup.start_zoomies(self.now))
        self.pup.hunger=10
        self.pup.energy=20
        self.assertFalse(self.pup.start_zoomies(self.now))
        self.pup.energy=90
        self.pup.start_sleep(self.now)
        self.assertFalse(self.pup.start_zoomies(self.now))

    def test_ear_motion_has_inertia_and_stays_stable(self):
        self.pup.state='zoomies'
        self.pup.animate_ears(.1)
        first=self.pup.ear_angle
        self.assertGreater(first,0)
        self.assertLess(first,48)
        for _ in range(100):
            self.pup.animate_ears(.1)
        self.assertAlmostEqual(self.pup.ear_angle,48,places=2)
        self.pup.state='sleep'
        self.pup.animate_ears(.033)
        self.assertGreater(self.pup.ear_angle,0)
        for _ in range(100):
            self.pup.animate_ears(.1)
        self.assertAlmostEqual(self.pup.ear_angle,0,places=2)

    def test_dropping_default_is_three_hours_and_changes_preserve_age(self):
        dropping = Dropping(100,800)
        try:
            self.assertEqual(dropping.lifetime_minutes,180)
            self.assertGreater(dropping.removal_timer.interval(),10799000)
            self.assertLessEqual(dropping.removal_timer.interval(),10800000)
            dropping.set_lifetime(60,now=dropping.created_at+120)
            self.assertEqual(dropping.removal_timer.interval(),3480000)
            dropping.set_lifetime(1,now=dropping.created_at+70)
            self.assertEqual(dropping.removal_timer.interval(),0)
            self.app.processEvents()
            self.assertTrue(not isValid(dropping) or not dropping.isVisible())
        finally:
            if isValid(dropping):
                dropping.close()

    def test_dropping_is_behind_rump_in_both_directions_for_every_model(self):
        self.pup.ground=lambda:(0,800,1200)
        self.manager.dropping_minutes=90
        for style in range(4):
            centers=[]
            for direction in (1,-1):
                self.pup.appearance=Appearance(style,1,1,1)
                self.pup.direction=direction
                self.pup.xf=300
                self.pup.yf=702
                self.pup.state='poop'
                self.pup.deadline=self.now-1
                self.step()
                pile=self.manager.droppings[-1]
                centers.append(pile.x()+15-self.pup.xf)
                self.assertEqual(pile.y()+pile.height(),self.pup.yf+98)
                self.assertEqual(pile.lifetime_minutes,90)
            self.assertLess(centers[0],30)
            self.assertGreater(centers[1],130)
            self.assertEqual(sum(centers),160)

    def test_names_are_saved_escaped_and_optional_in_tooltip(self):
        self.pup.name='Бублик <3 & Плюша'
        other=Pup(self.manager,self.pup.serialize(self.now))
        try:
            self.assertEqual(other.name,self.pup.name)
            other.refresh_tooltip()
            self.assertIn('Бублик &lt;3 &amp; Плюша',other.toolTip())
            self.manager.show_names=False
            other.refresh_tooltip()
            self.assertNotIn('Бублик',other.toolTip())
            self.assertIn('Голод',other.toolTip())
        finally:
            other.close()

    def test_settings_apply_names_and_cleanup_and_cancel_is_reversible(self):
        manager=Manager.__new__(Manager)
        manager.minutes=10
        manager.dropping_minutes=180
        manager.show_names=True
        manager.pups=[self.pup]
        manager.droppings=[]
        manager.save=lambda:None
        def edit(accept):
            d=self.app.activeModalWidget()
            d.findChildren(QSpinBox)[1].setValue(240)
            d.findChild(QLineEdit).setText('Плюша')
            d.findChild(QCheckBox).setChecked(False)
            d.accept() if accept else d.reject()
        original=self.pup.name
        QTimer.singleShot(0,lambda:edit(False))
        manager.settings()
        self.assertEqual(self.pup.name,original)
        self.assertEqual(manager.dropping_minutes,180)
        self.assertTrue(manager.show_names)
        QTimer.singleShot(0,lambda:edit(True))
        manager.settings()
        self.assertEqual(self.pup.name,'Плюша')
        self.assertEqual(manager.dropping_minutes,240)
        self.assertFalse(manager.show_names)


if __name__ == '__main__':
    unittest.main()
