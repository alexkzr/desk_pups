"""Deterministic checks of timing and attachment without waiting real minutes."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import time
import unittest
from PySide6.QtWidgets import QApplication
from main import Pup


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


if __name__ == '__main__':
    unittest.main()
