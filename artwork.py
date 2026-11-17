"""Bezier character rig: continuous anatomy, independent ears, stable coat patterns."""
import math
import random
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QPainterPathStroker, QPen

from appearance import Appearance

WALK_SPEED, RUN_SPEED = 38., 210.
WALK_FREQUENCY, RUN_FREQUENCY = 8., 24.


def foot_cycle(angle, running=False):
    frequency = RUN_FREQUENCY if running else WALK_FREQUENCY
    speed = RUN_SPEED if running else WALK_SPEED
    amplitude = speed*math.pi/(2*frequency)
    phase = angle % (2*math.pi)
    if phase < math.pi:
        return -amplitude*math.cos(phase), (6 if running else 2.5)*math.sin(phase)
    # A planted paw moves backwards at precisely the body's forward speed.
    return amplitude*(1-2*(phase-math.pi)/math.pi), 0.


def model_scale(appearance):
    return (1,1)


def rear_drop_offset(appearance, direction):
    # The pile's centre belongs just behind the rump, not at a sprite origin.
    sx,_ = model_scale(appearance)
    x = 80+(20-80)*sx
    return 160-x if direction < 0 else x


def ellipse(p, x, y, w, h, color):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(x, y, w, h))


def rounded(p, x, y, w, h, r, color):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(x, y, w, h), r, r)


def stroke(p, points, color, width):
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(QPointF(*points[0]), QPointF(*points[1]))
    p.setPen(Qt.NoPen)


def path(points):
    q = QPainterPath()
    q.moveTo(*points[0])
    for segment in points[1:]:
        if len(segment) == 6:
            q.cubicTo(*segment)
        elif len(segment) == 4:
            q.quadTo(*segment)
        else:
            q.lineTo(*segment)
    q.closeSubpath()
    return q


@lru_cache(maxsize=512)
def spots(seed, part):
    rng = random.Random(seed+part*100003)
    # Normalised, irregular patches travel with each anatomical part.
    return tuple((rng.random(),rng.random(),rng.uniform(.05,.17),
                  rng.uniform(.10,.24),rng.uniform(-60,60)) for _ in range(16))



from dragon_art import DragonArtist as Artist, treasure as draw_bed

def draw_dog(p,state,phase,sit_pose=0,wake_progress=0,appearance=None,ear_angle=0,hang_angles=None,guilty=0.,chubby=0., sleep_elapsed=0.):
    appearance=appearance or Appearance()
    artist=Artist(p,appearance,phase,ear_angle,hang_angles,guilty,chubby)
    p.save();p.setPen(Qt.NoPen)
    if state=='sleep':
        from sleep_motion import draw_sleeping
        draw_sleeping(p,artist,sleep_elapsed)
    elif state=='wake':artist.curled(min(1,wake_progress/.9))
    elif state=='sit':
        poses=(0,-8,6,-13)
        index=math.floor(sit_pose)%4;t=sit_pose-math.floor(sit_pose)
        artist.perch_tilt=poses[index]+(poses[(index+1)%4]-poses[index])*t
        artist.standing('sit')
    else:artist.standing(state)
    p.restore()
