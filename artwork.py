"""Small vector poses. All props and paws share the y=98 support line."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen


def ellipse(p, x, y, w, h, color):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(x, y, w, h))


def rounded(p, x, y, w, h, r, color):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(x, y, w, h), r, r)


def stroke(p, points, color, width):
    p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(QPointF(*points[0]), QPointF(*points[1]))
    p.setPen(Qt.NoPen)


def draw_bed(p, opacity=1):
    p.save()
    p.setOpacity(opacity)
    rounded(p, 2, 6, 140, 28, 13, '#587d80')
    ellipse(p, 11, 4, 122, 25, '#9cb5ad')
    ellipse(p, 20, 9, 104, 18, '#e1d3b5')
    # A low front bolster keeps the bed visibly planted on its support.
    rounded(p, 4, 23, 136, 11, 5, '#6c9694')
    stroke(p, ((21, 29), (123, 29)), '#86aba4', 2)
    p.restore()


def draw_head(p, x=99, y=49, tilt=0, front=0, closed=False):
    p.save()
    p.translate(x+16, y+20)
    p.rotate(tilt)
    p.translate(-16, -20)
    if front:
        rounded(p, -7, 8, 13, 32, 6, '#68371f')
    ellipse(p, 0, 0, 33, 34, '#c17b40')
    rounded(p, 20-front*7, 16, 27-front*5, 14, 6, '#c17b40')
    rounded(p, 3, 6, 16, 35, 8, '#68371f')
    ellipse(p, 40-front*12, 16, 8, 7, '#251f21')
    if closed:
        stroke(p, ((24, 14), (29, 14)), '#251f21', 2)
    else:
        ellipse(p, 25-front*2, 11, 4, 5, '#251f21')
        ellipse(p, 26-front*2, 11.5, 1, 1.5, '#fff6e8')
        if front:
            ellipse(p, 16, 10, 3*front, 5, '#251f21')
    rounded(p, 16, 30, 7, 10, 2, '#42a89c')
    p.restore()


def draw_sitting(p, pose):
    # Interpolate anatomical controls, rather than swapping four still frames.
    controls = [
        (43, 78, 94, 54, 88, 36, 0, 0, 0),
        (38, 80, 96, 57, 89, 39, 0, 0, 1),
        (57, 76, 88, 48, 79, 28, 0, 1, 0),
        (55, 79, 94, 52, 85, 31, -12, .35, 0),
    ]
    i = math.floor(pose) % 4
    t = pose-math.floor(pose)
    a, b = controls[i], controls[(i+1) % 4]
    rear_x, rear_y, chest_x, chest_y, head_x, head_y, tilt, front, relax = [x+(y-x)*t for x,y in zip(a,b)]
    stroke(p, ((rear_x+8, 93), (rear_x-20, 95)), '#68371f', 6)
    body = QPainterPath()
    body.moveTo(rear_x, 88)
    body.cubicTo(rear_x-3, rear_y-4, chest_x-16, chest_y+18, chest_x-7, chest_y)
    body.cubicTo(chest_x+1, chest_y-12, chest_x+22, chest_y-4, chest_x+19, chest_y+12)
    body.lineTo(chest_x+12, 91)
    body.cubicTo(chest_x-6, 100, rear_x+5, 98, rear_x, 88)
    p.setBrush(QColor('#a75b2c'))
    p.drawPath(body)
    ellipse(p, rear_x-1, rear_y, 35, 98-rear_y, '#a75b2c')
    rounded(p, chest_x, chest_y+22, 8, 98-(chest_y+22), 4, '#7f421f')
    rounded(p, chest_x+12, chest_y+19, 8, 98-(chest_y+19), 4, '#c17b40')
    rounded(p, chest_x+10, 93, 15, 5, 2, '#c17b40')
    rounded(p, rear_x+11, 92, 20, 6, 3, '#c17b40')
    if relax > 0:
        ellipse(p, rear_x+22, 87, 19*relax, 11, '#c17b40')
        for dx, dy in ((0,0),(5,1),(8,4)):
            ellipse(p, rear_x+29+dx, 90+dy, 3*relax, 3, '#68371f')
    draw_head(p, head_x, head_y, tilt, front)


def draw_curled(p, phase, unfold=0):
    breath = math.sin(phase*1.6)*.8*(1-unfold)
    def point(a,b):
        return tuple(x+(y-x)*unfold for x,y in zip(a,b))
    p.save()
    p.translate(0, breath)
    # A continuous crescent back, tucked paws, nose toward the belly.
    body = QPainterPath()
    body.moveTo(*point((120,85),(123,85)))
    body.cubicTo(*point((124,65,107,53,82,55),(123,77,109,77,86,77)))
    body.cubicTo(*point((56,54,38,67,41,82),(56,77,25,77,25,87)))
    body.cubicTo(*point((42,97,69,97,91,94),(25,97,66,97,100,97)))
    body.cubicTo(*point((79,91,67,87,66,80),(118,97,125,94,123,86)))
    body.cubicTo(*point((64,72,76,69,87,74),(123,85,123,85,123,85)))
    body.cubicTo(*point((100,82,109,92,120,85),(123,85,123,85,123,85)))
    p.setBrush(QColor('#a75b2c'))
    p.drawPath(body)
    stroke(p, (point((51,86),(14,84)), point((80,91),(28,80))), '#7f421f', 8-2*unfold)
    ellipse(p, *point((75,85,23,7),(99,90,23,8)), '#c17b40')
    ellipse(p, *point((91,71,29,24),(99,55,33,34)), '#c17b40')
    rounded(p, *point((77,82,25,11),(119,71,27,14)), 5, '#c17b40')
    ellipse(p, *point((76,83,7,6),(139,71,8,7)), '#251f21')
    rounded(p, *point((103,76,13,21),(102,61,16,35)), 6, '#68371f')
    eye = point((92,80),(124,66))
    if unfold > .1:
        ellipse(p, eye[0],eye[1],4,5*min(1,unfold*3),'#251f21')
    else:
        stroke(p, (eye,(eye[0]+5,eye[1]+1)), '#251f21', 2)
    p.restore()


def draw_dog(p, state, phase, sit_pose=0, wake_progress=0):
    if state == 'sit':
        draw_sitting(p, sit_pose)
        return
    if state == 'sleep':
        draw_curled(p, phase)
        return
    if state == 'wake':
        t = min(1,max(0,wake_progress/.9))
        draw_curled(p,phase,t*t*(3-2*t))
        return
    low = state in ('lie', 'stretch')
    eating = state == 'eat'
    bob = math.sin(phase*12)*1.2 if state == 'walk' else 0
    p.save()
    # Body is shortened slightly while eating to leave room for the bowl.
    if eating:
        p.translate(0, 0)
        p.scale(.84, 1)
    p.translate(0, bob)
    stroke(p, ((28, 80 if low else 74), (14, 84 if low else 58+math.sin(phase*9)*7)), '#5b2e1b', 6)
    for i, x in enumerate((40,55,99,113)):
        stride = math.sin(phase*11+i*math.pi)*5 if state == 'walk' else 0
        rounded(p, x+stride, 90 if low else 82, 10, 8 if low else 16, 4, '#7f421f')
    if state == 'poop':
        ellipse(p, 34, 71, 37, 27, '#a75b2c')
        rounded(p, 52, 60, 70, 30, 13, '#a75b2c')
    else:
        rounded(p, 25, 77 if low else 64, 98, 20 if low else 26, 13, '#a75b2c')
    if eating:
        # Nose bobs into the food, forepaws remain on the support line.
        draw_head(p, 116, 59+math.sin(phase*7)*1.5, 26)
    else:
        draw_head(p, 99, 55 if low else 49, -6 if state == 'stretch' else 0)
    p.restore()
    if eating:
        rounded(p, 121, 88, 34, 10, 4, '#437d91')
        ellipse(p, 121, 85, 34, 7, '#e9b867')
        for x,y in ((129,87),(135,86),(142,88),(148,87)):
            ellipse(p, x, y, 3, 2, '#81562f')
