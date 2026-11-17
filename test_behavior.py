"""Deterministic checks of timing and attachment without waiting real minutes."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import time
import unittest
from types import SimpleNamespace
from PySide6.QtCore import Qt, QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter
from main import Pup, SLEEP_SECONDS
from artwork import draw_dog


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
        self.assertEqual(right.mirrored(True,False),left)


if __name__ == '__main__':
    unittest.main()
