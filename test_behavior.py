"""Deterministic checks of timing and attachment without waiting real minutes."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import time
import unittest
import hashlib
import random
import math
from unittest.mock import patch
from types import SimpleNamespace
from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtWidgets import QApplication, QSpinBox, QLineEdit, QCheckBox, QComboBox
from PySide6.QtGui import QImage, QPainter
from main import Pup, Manager, Dropping, AppearancePreview, Village, FireBreath, SLEEP_SECONDS
from artwork import Artist, draw_dog, foot_cycle, WALK_SPEED, RUN_SPEED, WALK_FREQUENCY, RUN_FREQUENCY, model_scale
from shiboken6 import isValid
from dragging import Suspension, draw_mesh, draw_hanging
from appearance import Appearance
from dragon_art import FIRE_COLORS, flame, treasure, village


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
        self.assertEqual(self.pup.state,'fly_meal')
        for _ in range(115):
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
        self.assertEqual(self.pup.state,'fly_meal')
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

    def test_hunt_flies_to_village_with_fleeing_people_and_cleans_up(self):
        self.pup.ground=lambda:(0,800,1200)
        self.pup.xf,self.pup.yf=300,702
        self.pup.feed()
        self.assertEqual(self.pup.state,'fly_meal')
        self.assertIsNotNone(self.pup.village)
        self.now=self.pup.flight_started+1.1
        self.pup.tick(self.now)
        self.assertLess(self.pup.flight_offset,-30)
        self.now=self.pup.flight_started+2.2
        self.pup.tick(self.now)
        self.assertEqual(self.pup.state,'hunt_fire')
        self.assertEqual(self.pup.flight_offset,0)
        self.assertIsNotNone(self.pup.flame)
        self.assertFalse(self.pup.breathe_fire(self.now))
        self.now=self.pup.deadline
        self.pup.tick(self.now)
        self.assertEqual(self.pup.state,'eat')
        self.assertIsNone(self.pup.flame)
        self.assertFalse(self.pup.breathe_fire(self.now))
        scene=self.pup.village
        self.assertEqual(scene.eaten_count,0)
        for _ in range(52):self.step()
        self.assertEqual(scene.eaten_count,5)
        self.assertIsNone(self.pup.village)
        self.assertIsNone(self.pup.flame)

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
            self.assertIn(look.style,range(1))
            self.assertIn(look.coat,range(4))
            self.assertIn(look.fur,range(2))

    def test_new_dogs_randomize_all_four_appearance_fields(self):
        with patch('appearance.random.randrange',side_effect=[2,12345]):
            self.assertEqual(Appearance.random(),Appearance(0,2,1,12345))

    def test_all_six_looks_are_distinct_and_render_all_poses(self):
        digests=set()
        rng_state=random.getstate()
        for style in range(1):
            for coat in range(4):
                for fur in range(1):
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
        self.assertEqual(len(digests),4)
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
        for style in range(1):
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
            self.assertIn('Сытость',other.toolTip())
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

    def test_hanging_cursor_pin_lengths_and_joint_limits_under_sharp_moves(self):
        for direction in (1,-1):
            for point in ((54,62),(83,56),(108,49),(139,45)):
                grab=point if direction>0 else (160-point[0],point[1])
                rig=Suspension(grab,direction)
                for i in range(45):
                    rig.step(.08,((1 if i%2 else -1)*900,math.sin(i)*500))
                    self.assertEqual(rig.map(grab),rig.anchor)
                    self.assertTrue(all(math.isfinite(a) for a in rig.angles+rig.speeds))
                    self.assertTrue(all(abs(a)<=limit+1e-8 for a,limit in zip(rig.angles,rig.limits)))
                    bones=rig.bones()
                    for j in (0,2):
                        self.assertAlmostEqual(math.hypot(bones[j][0]-bones[1][0],bones[j][1]-bones[1][1]),math.dist(rig.rest[j][:2],rig.rest[1][:2]))

    def test_head_and_rump_grabs_let_the_opposite_end_hang_down(self):
        for grab,target in (((139,45),(54,78)),((54,62),(130,53))):
            rig=Suspension(grab)
            for _ in range(90):
                rig.step(1/30,(200,200))
            self.assertGreater(rig.map(target)[1],rig.anchor[1]+35)
            self.assertLess(abs(rig.angles[3]),.35)

    def test_hanging_swing_damps_after_mouse_stops(self):
        rig=Suspension((78,65))
        for i in range(15):
            rig.step(1/30,(i*20,200))
        for _ in range(180):
            rig.step(1/30,(300,200))
        self.assertLess(sum(abs(v) for v in rig.speeds),.02)

    def test_dragged_grab_point_follows_cursor_and_release_returns_to_normal_canvas(self):
        self.pup.ground=lambda:(0,800,1200)
        self.pup.xf,self.pup.yf=300.,200.
        self.pup.move(300,200)
        self.pup.press_offset=QPointF(139,45).toPoint()
        self.pup.begin_drag(QPointF(500,300).toPoint())
        self.assertEqual(self.pup.width(),320)
        self.now=self.pup.last+.033
        self.pup.tick(self.now)
        px,py=self.pup.suspension.map((139,45))
        self.assertAlmostEqual(self.pup.x()+px,500)
        self.assertAlmostEqual(self.pup.y()+py,300)
        image=self.pup.grab().toImage()
        self.assertFalse(image.isNull())
        rig=self.pup.suspension
        before=(self.pup.x()+rig.map((74,75))[0],self.pup.y()+rig.map((74,75))[1])
        self.pup.end_drag()
        after=(self.pup.xf+rig.map((74,75))[0]+self.pup.release_origin[0],
               self.pup.yf+rig.map((74,75))[1]+self.pup.release_origin[1])
        for a,b in zip(before,after):
            self.assertAlmostEqual(a,b,places=7)
        self.assertEqual(self.pup.state,'fall')
        self.assertIsNone(self.pup.anchor)
        self.now=self.pup.release_started+.4
        self.pup.tick(self.now)
        self.assertEqual(self.pup.width(),160)
        self.assertIsNone(self.pup.release_rig)
        for _ in range(90):self.step()
        self.assertAlmostEqual(self.pup.yf+98,800)
        self.assertNotEqual(self.pup.state,'fall')

    def test_all_coats_can_be_skinned_with_head_and_body_bones(self):
        rig=Suspension((139,45),-1)
        rig.angles=[-.6,-.2,.2,.1]
        for style in range(1):
            for coat in range(4):
                for fur in range(1):
                    image=QImage(160,112,QImage.Format_ARGB32_Premultiplied)
                    image.fill(Qt.transparent)
                    p=QPainter(image)
                    p.translate(160,0);p.scale(-1,1)
                    look=Appearance(style,coat,fur,13)
                    draw_dog(p,'hang_body',1,appearance=look,hang_angles=(.4,.6,.8,.9))
                    p.end()
                    output=QImage(320,320,QImage.Format_ARGB32_Premultiplied)
                    output.fill(Qt.transparent)
                    rig.elapsed=1
                    p=QPainter(output);draw_hanging(p,image,rig,look,1);p.end()
                    self.assertTrue(any(output.pixelColor(x,150).alpha() for x in range(320)))

    def test_planted_feet_stay_fixed_on_ground_during_walk_and_run(self):
        for running in (False,True):
            speed=RUN_SPEED if running else WALK_SPEED
            frequency=RUN_FREQUENCY if running else WALK_FREQUENCY
            for direction in (1,-1):
                world_positions=[]
                for i in range(21):
                    angle=math.pi+math.pi*i/20
                    t=angle/frequency
                    dx,lift=foot_cycle(angle,running)
                    self.assertAlmostEqual(lift,0)
                    world_positions.append(direction*(speed*t+dx))
                self.assertLess(max(world_positions)-min(world_positions),1e-8)
                a,h1=foot_cycle(math.pi*.2,running)
                b,h2=foot_cycle(math.pi*.8,running)
                self.assertGreater(b,a)
                self.assertGreater(min(h1,h2),0)

    def test_back_grab_sags_both_rump_and_head_in_both_directions(self):
        for direction in (1,-1):
            def mirror(point):
                return point if direction>0 else (160-point[0],point[1])
            rig=Suspension(mirror((83,56)),direction)
            for _ in range(150):rig.step(1/30,(200,200))
            for end in ((54,78),(130,53)):
                self.assertGreater(rig.map(mirror(end))[1],rig.anchor[1]+25)
            self.assertLess(rig.angles[1]*direction,-.4)
            self.assertGreater(rig.angles[2]*direction,.4)

    def test_paws_are_painted_below_attachment_even_when_torso_is_vertical(self):
        for direction in (1,-1):
            rig=Suspension((78,65),direction)
            rig.angles=[1.1,-.8,.8,.2]
            rig.elapsed=1
            look=Appearance(0,1,1,13)
            blank=QImage(160,112,QImage.Format_ARGB32_Premultiplied)
            blank.fill(Qt.transparent)
            out=QImage(320,320,QImage.Format_ARGB32_Premultiplied)
            out.fill(Qt.transparent)
            p=QPainter(out);draw_hanging(p,blank,rig,look,1);p.end()
            for x in (58,108,52,111):
                root=rig.map((x if direction>0 else 160-x,74))
                tx,ty=round(root[0]),round(root[1]+13)
                self.assertTrue(any(out.pixelColor(tx+dx,ty+dy).alpha()
                                    for dx in (-1,0,1) for dy in (-1,0,1)))

    def test_scruff_grab_droops_head_and_rump_with_forward_balance(self):
        for direction in (1,-1):
            def mirror(point):
                return point if direction>0 else (160-point[0],point[1])
            rig=Suspension(mirror((108,49)),direction)
            for _ in range(150):rig.step(1/30,(200,200))
            self.assertAlmostEqual(rig.scruff,1)
            for end in ((40,78),(130,53),(149,49)):
                self.assertGreater(rig.map(mirror(end))[1],rig.anchor[1]+15)
            head_angle=rig.bones()[-1][2]*direction
            self.assertGreater(head_angle,.6)
            self.assertLess(abs(rig.angles[0]),.5)
            self.assertGreater(rig.angles[3]*direction,.8)
            self.assertEqual(rig.map(rig.grab),rig.anchor)

    def test_scruff_expression_is_drawn_and_other_grabs_keep_usual_expression(self):
        rig=Suspension((108,49))
        self.assertGreater(rig.scruff,.99)
        self.assertLess(Suspension((40,65)).scruff,.01)
        self.assertLess(Suspension((139,45)).scruff,.01)
        for coat in range(4):
            images=[]
            for guilty in (0,1,Suspension((139,45)).scruff):
                image=QImage(160,112,QImage.Format_ARGB32_Premultiplied)
                image.fill(Qt.transparent)
                p=QPainter(image)
                draw_dog(p,'hang_body',1,appearance=Appearance(0,coat,0,1),guilty=guilty)
                p.end();images.append(image)
            self.assertNotEqual(images[0],images[1])
            self.assertEqual(images[0],images[2])

    def test_only_coat_and_fur_choices_remain_and_preview_updates(self):
        manager=Manager.__new__(Manager)
        manager.save=lambda:None
        observed=[]
        def edit():
            dialog=self.app.activeModalWidget()
            boxes=dialog.findChildren(QComboBox)
            observed.append(len(boxes))
            boxes[0].setCurrentIndex(2)
            preview=dialog.findChild(AppearancePreview)
            observed.append(preview.appearance)
            dialog.accept()
        QTimer.singleShot(0,edit)
        manager.appearance_dialog(self.pup)
        self.assertEqual(observed[0],1)
        self.assertEqual(self.pup.appearance,observed[1])
        self.assertEqual(self.pup.appearance.style,0)
        self.assertEqual(self.pup.appearance.coat,2)
        self.assertEqual(self.pup.appearance.fur,0)
        original=self.pup.appearance
        def cancel():
            dialog=self.app.activeModalWidget()
            dialog.findChildren(QComboBox)[0].setCurrentIndex(0)
            dialog.reject()
        QTimer.singleShot(0,cancel)
        manager.appearance_dialog(self.pup)
        self.assertEqual(self.pup.appearance,original)

    def test_retired_models_migrate_without_losing_coat_fur_seed_or_name(self):
        for legacy in (0,1,2,3):
            saved={'name':'Бублик','appearance':{'style':legacy,'coat':2,'fur':1,'seed':718}}
            other=Pup(self.manager,saved)
            try:
                self.assertEqual(other.appearance,Appearance(0,2,1,718))
                self.assertEqual(other.name,'Бублик')
                self.assertEqual(other.serialize()['appearance']['style'],0)
            finally:
                other.close()

    def test_single_meal_normal_but_repeat_meals_make_dog_overfull(self):
        self.pup.feed()
        self.assertEqual(self.pup.overfeed,0)
        self.pup.feed()
        deadline=self.pup.deadline
        self.assertGreater(self.pup.fullness,100)
        self.pup.feed()
        self.assertEqual(self.pup.overfeed,70)
        self.assertEqual(self.pup.deadline,deadline)
        for _ in range(100):self.pup.feed()
        self.assertEqual(self.pup.overfeed,100)
        self.assertLessEqual(self.pup.fullness,200)
        self.assertFalse(self.pup.can_zoom())

    def test_overfull_dog_walks_slowly_to_bed_then_recovers_after_full_sleep(self):
        self.pup.ground=lambda:(0,800,1200)
        self.pup.xf,self.pup.yf=300,702
        self.pup.feed();self.pup.feed()
        self.now=self.pup.flight_started+2.2
        self.pup.tick(self.now)
        self.now=self.pup.deadline
        self.pup.tick(self.now)
        self.now=self.pup.deadline
        self.pup.tick(self.now)
        self.assertEqual(self.pup.state,'to_bed')
        self.assertIsNotNone(self.pup.bed)
        destination=self.pup.bed_target_x
        before=self.pup.xf
        for _ in range(10):self.step()
        self.assertAlmostEqual(abs(self.pup.xf-before),14,places=5)
        self.assertGreater(self.pup.fatness,.4)
        self.assertLess(self.pup.speed_factor,1)
        for _ in range(55):self.step()
        self.assertEqual(self.pup.state,'sleep')
        self.assertAlmostEqual(self.pup.xf,destination,delta=.5)
        self.assertGreater(self.pup.overfeed,0)
        self.now=self.pup.deadline
        self.pup.tick(self.now)
        self.assertEqual(self.pup.state,'wake')
        self.assertEqual(self.pup.overfeed,0)
        self.assertEqual(self.pup.fatness,0)
        self.assertEqual(self.pup.speed_factor,1)

    def test_overfeeding_persists_and_early_waking_does_not_remove_it(self):
        self.pup.overfeed=70
        self.pup.has_eaten=True
        other=Pup(self.manager,self.pup.serialize(self.now))
        try:
            self.assertEqual(other.overfeed,70)
            self.assertEqual(other.state,'to_bed')
            other.start_sleep(self.now)
            other.wake(self.now+2)
            self.assertEqual(other.overfeed,70)
            other.tick(other.deadline)
            self.assertEqual(other.state,'to_bed')
            self.assertFalse(other.can_zoom())
        finally:
            other.close()

    def test_feeding_again_while_still_sated_is_counted_and_sleep_requests_accumulate(self):
        self.pup.has_eaten=True
        self.pup.hunger=5
        self.pup.feed()
        self.assertEqual(self.pup.overfeed,35)
        self.pup.overfeed=0
        self.pup.has_eaten=False
        self.pup.start_sleep(self.now)
        self.pup.feed();self.pup.feed();self.pup.feed()
        self.assertEqual(self.pup.overfeed,70)
        self.assertTrue(self.pup.pending_feed)

    def test_chubby_silhouette_differs_for_every_coat_and_fur(self):
        for coat in range(4):
            for fur in range(1):
                images=[]
                for chubby in (0,1):
                    image=QImage(160,112,QImage.Format_ARGB32_Premultiplied)
                    image.fill(Qt.transparent);p=QPainter(image)
                    draw_dog(p,'walk',.2,appearance=Appearance(0,coat,fur,1),chubby=chubby)
                    p.end();images.append(image)
                def area(image):
                    # Measure the belly, rather than the much larger wings and spines.
                    return sum(image.pixelColor(x,y).alpha()>100 for x in range(35,126) for y in range(65,98))
                self.assertGreater(area(images[1]),area(images[0])*1.15)

    def test_tail_root_joins_upper_back_instead_of_middle_of_thigh(self):
        for style in range(1):
            for state in ('walk','zoomies','poop','hang_body'):
                image=QImage(160,112,QImage.Format_ARGB32_Premultiplied)
                image.fill(Qt.transparent)
                p=QPainter(image)
                with patch.object(Artist,'tail',autospec=True) as tail, patch.object(Artist,'fill',autospec=True) as fill:
                    draw_dog(p,state,.4,appearance=Appearance(style,0,0,1))
                    x,y=tail.call_args.args[1:3]
                    body=next(call.args[1] for call in fill.call_args_list if len(call.args)>2 and call.args[2]==1)
                    joint=QPointF(x+2,y+5)
                    self.assertTrue(body.contains(joint))
                    top=next(v*.25 for v in range(440) if body.contains(QPointF(joint.x(),v*.25)))
                    self.assertLessEqual(joint.y()-top,6)
                p.end()

    def test_larger_models_and_ears_do_not_cross_support_when_eating(self):
        for style in range(1):
            for fur in range(1):
                for phase in (0,.2,.6,.9):
                    image=QImage(160,112,QImage.Format_ARGB32)
                    image.fill(Qt.transparent)
                    p=QPainter(image)
                    draw_dog(p,'eat',phase,appearance=Appearance(style,0,fur,1))
                    p.end()
                    self.assertTrue(all(image.pixelColor(x,y).alpha()<30
                                        for y in range(99,112) for x in range(160)))

    def test_all_four_dragon_colors_and_flames_are_distinct(self):
        self.assertEqual(FIRE_COLORS,('#ff8a24','#ed3b28','#ffe138','#438cff'))
        hashes=set()
        for coat in range(4):
            for state in ('walk','sit','sleep','wake','fly_meal','fire','eat'):
                image=QImage(200,112,QImage.Format_ARGB32_Premultiplied)
                image.fill(Qt.transparent);p=QPainter(image)
                draw_dog(p,state,.5,0,.4,Appearance(0,coat,0,1));p.end()
                self.assertTrue(any(image.pixelColor(x,70).alpha() for x in range(160)))
                if state=='walk':hashes.add(hashlib.sha256(image.constBits()).hexdigest())
            image=QImage(190,70,QImage.Format_ARGB32_Premultiplied)
            image.fill(Qt.transparent);p=QPainter(image);flame(p,.8,coat);p.end()
            c=image.pixelColor(75,35)
            if coat==3:self.assertGreater(c.blue(),c.red())
            elif coat==1:self.assertGreater(c.red(),c.green())
            elif coat==2:self.assertGreater(c.green(),c.blue())
        self.assertEqual(len(hashes),4)

    def test_fire_can_be_triggered_but_not_during_sleep_and_effect_cleans_up(self):
        self.assertTrue(self.pup.breathe_fire(self.now))
        self.assertEqual(self.pup.state,'fire')
        self.assertIsNotNone(self.pup.flame)
        self.assertFalse(self.pup.breathe_fire(self.now))
        self.pup.flame.phase=2.4;self.pup.flame.advance()
        self.assertFalse(self.pup.flame.isVisible())
        self.now=self.pup.deadline;self.pup.tick(self.now)
        self.assertEqual(self.pup.state,'walk')
        self.pup.start_sleep(self.now)
        self.assertFalse(self.pup.breathe_fire(self.now))

    def test_grab_or_sleep_interrupts_flight_without_leaving_village_or_fire(self):
        self.pup.feed();scene=self.pup.village
        self.pup.start_sleep(self.now)
        self.assertIsNone(self.pup.village)
        self.assertFalse(scene.isVisible())
        self.pup.wake(self.now,dragging=True)
        self.pup.feed()
        self.pup.press_offset=QPointF(108,49).toPoint()
        self.pup.begin_drag(QPointF(400,300).toPoint())
        self.assertIsNone(self.pup.village)
        self.assertIsNone(self.pup.flame)
        self.pup.end_drag()

    def test_hunt_and_village_fit_work_area_in_both_directions(self):
        self.pup.ground=lambda:(0,800,1200)
        for x in (20,1020):
            self.pup.clear_village();self.pup.state='walk';self.pup.xf=x
            self.pup.feed()
            self.assertGreaterEqual(self.pup.village.x(),0)
            self.assertLessEqual(self.pup.village.x()+190,1200)
            self.assertEqual(self.pup.village.y()+85,800)

    def test_treasure_and_village_draw_on_their_support_without_bowl(self):
        for width,height,draw in ((144,34,lambda p:treasure(p)),(190,85,lambda p:village(p,1,.3))):
            image=QImage(width,height,QImage.Format_ARGB32_Premultiplied)
            image.fill(Qt.transparent);p=QPainter(image);draw(p);p.end()
            self.assertTrue(any(image.pixelColor(x,height-2).alpha() for x in range(width)))

    def test_fire_ends_before_eating_and_manual_fire_stays_blocked_during_meal(self):
        self.pup.feed()
        self.now=self.pup.flight_started+2.2
        self.pup.tick(self.now)
        self.assertEqual(self.pup.state,'hunt_fire')
        effect=self.pup.flame
        hunger=self.pup.hunger
        for _ in range(10):self.step()
        self.assertGreaterEqual(self.pup.hunger,hunger)
        self.assertEqual(self.pup.village.eaten_count,0)
        self.assertFalse(self.pup.breathe_fire(self.now))
        self.now=self.pup.deadline
        self.pup.tick(self.now)
        self.assertEqual(self.pup.state,'eat')
        self.assertFalse(effect.isVisible())
        self.assertIsNone(self.pup.flame)
        for _ in range(20):
            self.assertFalse(self.pup.breathe_fire(self.now))
            self.step()
            self.assertIsNone(self.pup.flame)
        manager=Manager.__new__(Manager)
        manager.pups=[self.pup]
        manager.app=self.app
        menu=manager.menu(self.pup)
        action=next(a for a in menu.actions() if a.text()=='Выдохнуть огонь')
        self.assertFalse(action.isEnabled())
        for _ in range(35):self.step()
        menu.aboutToShow.emit()
        self.assertTrue(action.isEnabled())
        self.assertTrue(self.pup.breathe_fire(self.now))
        self.pup.feed()
        self.assertEqual(self.pup.state,'fly_meal')
        self.assertIsNone(self.pup.flame)

    def test_interrupting_pre_meal_fire_removes_both_scene_and_effect(self):
        self.pup.feed()
        self.now=self.pup.flight_started+2.2
        self.pup.tick(self.now)
        scene,effect=self.pup.village,self.pup.flame
        self.pup.start_sleep(self.now)
        self.assertFalse(scene.isVisible())
        self.assertFalse(effect.isVisible())
        self.assertIsNone(self.pup.village)
        self.assertIsNone(self.pup.flame)

    def test_dragon_has_compact_torso_dorsal_ridge_and_barbed_tail(self):
        image=QImage(160,112,QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent);p=QPainter(image)
        with patch.object(Artist,'fill',autospec=True) as fill:
            draw_dog(p,'walk',0,appearance=Appearance())
            body=next(c.args[1] for c in fill.call_args_list if len(c.args)>2 and c.args[2]==1)
            self.assertLess(body.boundingRect().width(),90)
            self.assertGreater(body.boundingRect().height(),40)
            parts=[c.args[2] for c in fill.call_args_list if len(c.args)>2]
            self.assertGreaterEqual(parts.count(4),8)
            self.assertGreaterEqual(parts.count(6),4)
            self.assertEqual(parts.count(7),1)
        p.end()


    def test_roofs_keep_burning_after_breath_stops(self):
        self.pup.feed()
        self.assertFalse(self.pup.village.burning)
        self.now=self.pup.flight_started+2.2
        self.pup.tick(self.now)
        scene=self.pup.village
        self.assertTrue(scene.burning)
        age=scene.burn_age
        self.step()
        self.assertGreater(scene.burn_age,age)
        self.now=self.pup.deadline
        self.pup.tick(self.now)
        self.assertEqual(self.pup.state,'eat')
        self.assertIsNone(self.pup.flame)
        self.assertTrue(scene.burning)
        self.assertEqual(scene.coat,self.pup.appearance.coat)
        self.pup.start_sleep(self.now)
        self.assertIsNone(self.pup.village)
        self.assertFalse(scene.isVisible())

    def test_flame_and_roof_animation_change_over_time_for_every_color(self):
        def render(draw):
            im=QImage(220,160,QImage.Format_ARGB32_Premultiplied)
            im.fill(Qt.transparent);p=QPainter(im);draw(p);p.end()
            return bytes(im.constBits())
        for coat in range(4):
            self.assertNotEqual(render(lambda p:flame(p,.4,coat)),render(lambda p:flame(p,.8,coat)))
            unlit=render(lambda p:village(p,1,0,1,coat,0))
            lit=render(lambda p:village(p,1,0,1,coat,1))
            later=render(lambda p:village(p,1.3,0,1,coat,1.3))
            self.assertNotEqual(unlit,lit)
            self.assertNotEqual(lit,later)

    def test_seven_minute_sleep_roll_timing_and_render(self):
        from sleep_motion import sleep_roll
        self.assertEqual(sleep_roll(419.99),0)
        self.assertAlmostEqual(sleep_roll(420.7),.5)
        self.assertEqual(sleep_roll(422),1)
        self.assertEqual(sleep_roll(464),0)
        self.assertEqual(sleep_roll(842),1)
        self.pup.start_sleep(self.now,600)
        self.assertEqual(self.pup.sleep_started,self.now-600)
        hashes=[]
        for elapsed in (0,420.7,422):
            im=QImage(160,112,QImage.Format_ARGB32_Premultiplied)
            im.fill(Qt.transparent);p=QPainter(im)
            draw_dog(p,'sleep',0,appearance=Appearance(),sleep_elapsed=elapsed)
            p.end();hashes.append(bytes(im.constBits()))
        self.assertEqual(len(set(hashes)),3)
        self.assertEqual(self.pup.state,'sleep')
        self.pup.wake(self.now)
        self.assertEqual(self.pup.state,'wake')

    def test_back_sleep_head_is_independent_and_eyes_are_closed(self):
        from sleep_motion import draw_sleeping
        image=QImage(160,112,QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent);p=QPainter(image)
        artist=Artist(p,Appearance(),0,0)
        with patch.object(artist,'head',wraps=artist.head) as head:
            draw_sleeping(p,artist,422)
            self.assertEqual(head.call_count,1)
            self.assertTrue(head.call_args.kwargs['sleeping'])
            self.assertEqual(head.call_args.kwargs['tilt'],25)
        p.end()

    def test_belly_up_has_a_solid_abdomen_for_every_coat(self):
        for coat in range(3 if 'desk_pups' in __file__ else 4):
            im=QImage(160,112,QImage.Format_ARGB32_Premultiplied)
            im.fill(Qt.transparent);p=QPainter(im)
            draw_dog(p,'sleep',0,appearance=Appearance(coat=coat),sleep_elapsed=422)
            p.end()
            for x in range(65,81):
                for y in range(67,85):
                    self.assertEqual(im.pixelColor(x,y).alpha(),255)

    def test_sleep_roll_supports_lean_and_chubby_pets_and_four_visible_feet(self):
        from sleep_motion import draw_back_sleep
        images=[]
        for fat in (0,1):
            im=QImage(160,112,QImage.Format_ARGB32_Premultiplied)
            im.fill(Qt.transparent);p=QPainter(im)
            draw_dog(p,'sleep',0,appearance=Appearance(),sleep_elapsed=422,chubby=fat)
            p.end();images.append(im)
        def area(im):
            return sum(im.pixelColor(x,y).alpha()>128 for x in range(160) for y in range(112))
        self.assertGreater(area(images[1]),area(images[0])*1.12)
        im=QImage(160,112,QImage.Format_ARGB32_Premultiplied)
        im.fill(Qt.transparent);p=QPainter(im);artist=Artist(p,Appearance(),0,0)
        with patch.object(artist,'fill',wraps=artist.fill) as fill:
            draw_back_sleep(p,artist,422)
            feet=[c for c in fill.call_args_list if len(c.args)>1 and c.args[1] in (42,43,44)]
            self.assertEqual(len(feet),4)
        p.end()

    def test_dragon_droppings_contain_gold_inside_the_pile(self):
        from dragon_art import dragon_dropping
        im=QImage(30,28,QImage.Format_ARGB32_Premultiplied)
        im.fill(Qt.transparent);p=QPainter(im);dragon_dropping(p);p.end()
        gold=[(x,y) for x in range(30) for y in range(28)
              if (c:=im.pixelColor(x,y)).alpha()>200 and c.red()>180 and c.green()>120 and c.blue()<180]
        self.assertGreater(len(gold),20)
        self.assertEqual(im.pixelColor(0,0).alpha(),0)

    def flight_scene(self):
        r=self.app.primaryScreen().availableGeometry()
        self.pup.xf=float(r.left()+20);self.pup.yf=float(r.bottom()+1-98)
        self.pup.anchor=None;self.pup.state='walk';self.pup.hunger=10
        self.pup.energy=90;self.pup.next_fire=self.now+1000
        a=(1001,r.left()+180,r.top()+220,r.left()+600)
        b=(1002,r.left()+40,r.top()+350,r.left()+470)
        self.manager.surfaces=[a,b]
        return a,b

    def finish_flight(self):
        self.now=self.pup.flight_started+self.pup.travel_duration
        self.pup.tick(self.now)

    def test_taskbar_to_window_flight_lands_on_top(self):
        a,b=self.flight_scene()
        self.assertTrue(self.pup.start_flight(a,self.now))
        self.assertEqual(self.pup.state,'travel_fly')
        self.assertIsNone(self.pup.anchor)
        self.now+=self.pup.travel_duration/2;self.pup.tick(self.now)
        self.assertLess(self.pup.flight_offset,0)
        self.assertFalse(self.pup.breathe_fire(self.now))
        self.assertFalse(self.pup.can_zoom())
        self.finish_flight()
        self.assertEqual(self.pup.anchor,a)
        self.assertAlmostEqual(self.pup.yf+98,a[2])
        self.assertGreaterEqual(self.pup.xf,a[1])
        self.assertLessEqual(self.pup.xf+160,a[3])
        self.assertEqual(self.pup.state,'settle')
        self.assertEqual(self.pup.flight_offset,0)

    def test_window_to_other_window_in_both_vertical_directions(self):
        a,b=self.flight_scene()
        for origin,destination in ((a,b),(b,a)):
            self.pup.anchor=origin;self.pup.xf=float(origin[1]+20);self.pup.yf=float(origin[2]-98)
            self.pup.state='sit'
            self.assertNotIn(origin,self.pup.flight_surfaces())
            self.assertTrue(self.pup.start_flight(destination,self.now))
            self.finish_flight()
            self.assertEqual(self.pup.anchor,destination)

    def test_flight_retargets_a_moved_window_without_position_jump(self):
        a,b=self.flight_scene();self.pup.start_flight(a,self.now)
        self.now+=.4;self.pup.tick(self.now)
        x,y=self.pup.xf,self.pup.yf+self.pup.flight_offset
        moved=(a[0],a[1]+50,a[2]+35,a[3]+50);self.manager.surfaces=[moved,b]
        self.step(.01)
        self.assertAlmostEqual(self.pup.xf,x)
        self.assertAlmostEqual(self.pup.yf+self.pup.flight_offset,y)
        self.finish_flight()
        self.assertEqual(self.pup.anchor,moved)

    def test_missing_or_occluded_destination_returns_to_taskbar(self):
        a,b=self.flight_scene();self.pup.start_flight(a,self.now)
        self.step(.4);self.manager.surfaces=[]
        self.step();self.assertIsNone(self.pup.travel_window)
        self.finish_flight()
        self.assertIsNone(self.pup.anchor)
        self.assertEqual(self.pup.yf+98,self.pup.ground()[1])

    def test_too_narrow_destination_also_aborts_safely(self):
        a,b=self.flight_scene();self.pup.start_flight(a,self.now)
        self.manager.surfaces=[(a[0],a[1],a[2],a[1]+100)]
        self.step();self.finish_flight()
        self.assertIsNone(self.pup.anchor)
        self.assertEqual(self.pup.yf+98,self.pup.ground()[1])

    def test_no_flight_during_meals_sleep_overfeeding_or_drag(self):
        a,b=self.flight_scene()
        for state in ('eat','sleep','wake','poop','fire','fly_meal','hunt_fire','travel_fly','to_bed','fall'):
            self.pup.state=state
            self.assertFalse(self.pup.start_flight(a,self.now),state)
        self.pup.state='walk';self.pup.overfeed=35
        self.assertFalse(self.pup.start_flight(a,self.now))
        self.pup.overfeed=0;self.pup.energy=10
        self.assertFalse(self.pup.start_flight(a,self.now))
        self.pup.energy=90;self.pup.hunger=80
        self.assertFalse(self.pup.start_flight(a,self.now))

    def test_feed_or_sleep_requested_in_flight_waits_until_landing(self):
        a,b=self.flight_scene();self.pup.start_flight(a,self.now)
        self.pup.feed()
        self.assertEqual(self.pup.state,'travel_fly')
        self.assertTrue(self.pup.pending_feed)
        self.finish_flight()
        self.assertEqual(self.pup.state,'fly_meal')
        self.pup.clear_village();self.pup.state='sit'
        self.assertTrue(self.pup.start_flight(b,self.now))
        self.pup.start_sleep(self.now)
        self.assertEqual(self.pup.state,'travel_fly')
        self.assertIsNone(self.pup.bed)
        self.finish_flight()
        self.assertEqual(self.pup.state,'sleep')
        self.assertEqual(self.pup.anchor,b)

    def test_dragging_interrupts_travel(self):
        a,b=self.flight_scene();self.pup.start_flight(a,self.now)
        self.step(.4);self.pup.press_offset=QPointF(80,60).toPoint()
        self.pup.begin_drag(QPointF(self.pup.xf+80,self.pup.yf+60).toPoint())
        self.assertIsNone(self.pup.travel_window)
        self.assertNotEqual(self.pup.state,'travel_fly')
        self.assertEqual(self.pup.flight_offset,0)
        self.assertIsNotNone(self.pup.drag)

    def test_automatic_flight_uses_its_timer(self):
        a,b=self.flight_scene();self.pup.next_flight=self.now-.1
        self.pup.next_zoomies=self.now+1000;self.pup.deadline=self.now+1000
        self.step()
        self.assertEqual(self.pup.state,'travel_fly')
        self.assertGreater(self.pup.next_flight,self.now)

    def test_flight_surfaces_exclude_narrow_and_offscreen_spans(self):
        a,b=self.flight_scene();r=self.app.primaryScreen().availableGeometry()
        self.manager.surfaces+=[(3,a[1],a[2],a[1]+159),(4,r.left()-200,a[2],r.left()+30),
                               (5,a[1],r.top()+20,a[3])]
        self.assertEqual(self.pup.flight_surfaces(),[a,b])

    def test_all_flying_states_use_four_tucked_legs_without_walking(self):
        image=QImage(160,112,QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent);p=QPainter(image)
        for state in ('travel_fly','fly_meal','zoomies'):
            with patch.object(Artist,'leg',autospec=True) as leg,patch.object(Artist,'tucked_leg',autospec=True) as tucked:
                draw_dog(p,state,.8,appearance=Appearance())
                self.assertEqual(leg.call_count,0)
                self.assertEqual(tucked.call_count,4)
        p.end()


if __name__ == '__main__':
    unittest.main()
