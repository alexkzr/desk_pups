"""Sleep roll timing shared by rendering and behavior; elapsed seconds, never frame count."""
import math
ROLL_INTERVAL = 7 * 60
ROLL_HOLD = 40
ROLL_TRANSITION = 1.4

def sleep_roll(elapsed):
    if elapsed < ROLL_INTERVAL:
        return 0.
    t = elapsed % ROLL_INTERVAL
    if t < ROLL_TRANSITION:
        x = t / ROLL_TRANSITION
    elif t < ROLL_TRANSITION + ROLL_HOLD:
        return 1.
    elif t < 2 * ROLL_TRANSITION + ROLL_HOLD:
        x = 1 - (t - ROLL_TRANSITION - ROLL_HOLD) / ROLL_TRANSITION
    else:
        return 0.
    return x*x*(3-2*x)


def draw_back_sleep(p, artist, elapsed):
    """A separate belly-up anatomy, viewed obliquely from above."""
    from artwork import path
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPainterPath, QColor
    dragon=hasattr(artist,'membrane')
    p.save()
    p.translate(0,math.sin(elapsed*1.6)*.45)
    # The far legs and folded wings sit behind the solid torso.
    if dragon:
        artist.fill(path([(50,57),(38,48,42,42,57,50),
                          (70,43,86,44,100,54),(79,52,63,57,50,57)]),40,tone=artist.membrane)
    artist.fill(path([(50,67),(37,65,30,55,39,51),
                      (47,48,58,58,64,63),(62,70,55,72,50,67)]),10,tone=artist.shade)
    body=path([(43,79),(35,61,51,47,73,48),
               (94,45,111,54,117,69),(124,88,105,99,81,98),
               (58,100,41,92,43,79)])
    artist.fill(body,1)
    belly=path([(58,66),(64,53,88,52,103,63),
                (116,77,105,92,86,94),(67,97,49,85,58,66)])
    belly_color=artist.light if not dragon else artist.horn
    artist.fill(belly,41,tone=QColor(belly_color).lighter(114).name(),patterned=False,outline=False)
    # Tail wraps the rump without cutting a hole through the belly.
    artist.fill(path([(46,81),(32,82,34,103,64,99),
                      (77,99,83,95,87,92),(64,99,43,94,46,81)]),5,tone=artist.shade)
    if dragon:
        for x,y in ((37,87),(41,96),(52,99)):
            artist.fill(path([(x,y),(x-5,y-5),(x+4,y+1)]),6,tone=artist.horn)
        artist.fill(path([(105,91),(113,82,110,64,104,59),
                          (110,65,119,70,122,78),(115,78,119,85,117,89),
                          (110,86,110,92,105,91)]),40,tone=artist.membrane)
    # Near hind thigh is flexed outward; its foot rests inward on the belly.
    artist.fill(path([(46,79),(33,76,32,91,46,94),
                      (56,96,67,87,64,81),(61,76,56,80,53,85),
                      (49,89,42,85,46,79)]),11)
    paw_color=getattr(artist,'tan',artist.light) if artist.look.coat else artist.light
    artist.fill(path([(57,80),(62,77,67,80,66,84),
                      (65,89,58,90,56,86),(54,83,55,81,57,80)]),42,tone=paw_color,patterned=False)
    # The forelegs fold over the chest, with wrists hanging toward the abdomen.
    for near in (False,True):
        p.save()
        if near:p.translate(0,17)
        else:p.translate(1,-1)
        p.translate(0,math.sin(elapsed*1.5+(1 if near else 0))*.35)
        artist.fill(path([(103,59),(97,53,86,54,82,60),
                          (79,64,82,70,88,72),(93,74,97,71,94,68),
                          (91,66,89,65,91,63),(96,65,101,67,104,64)]),
                    11 if near else 10,tone=artist.base if near else artist.shade)
        artist.fill(path([(86,64),(81,65,80,69,85,72),
                          (90,76,96,72,94,69),(92,66,89,66,86,64)]),43,
                    tone=paw_color,patterned=False)
        p.restore()
    # Head rests beside the shoulder, rather than on an extended neck.
    p.save();p.translate(106,62);p.scale(.72,.72)
    previous=getattr(artist,'ear_angle',0);artist.ear_angle=0
    artist.head(0,0,tilt=25,sleeping=True)
    artist.ear_angle=previous;p.restore()
    p.restore()

def draw_sleeping(p, artist, elapsed):
    amount=sleep_roll(elapsed)
    if amount<1:
        p.save();p.setOpacity(p.opacity()*(1-amount));artist.curled();p.restore()
    if amount>0:
        p.save();p.setOpacity(p.opacity()*amount)
        # A small lateral sway accompanies the change of pose; no sprite flip.
        p.translate(math.sin(amount*math.pi)*2,0)
        draw_back_sleep(p,artist,elapsed)
        p.restore()
