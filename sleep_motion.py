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

def draw_sleeping(p, artist, elapsed):
    from artwork import path
    amount = sleep_roll(elapsed)
    p.save()
    p.translate(80,77)
    p.scale(1-.10*math.sin(math.pi*amount), math.cos(math.pi*amount))
    p.translate(-80,-77)
    artist.curled(show_head=amount<=.5)
    p.restore()
    if amount > .5:
        # Four relaxed bent legs point upward, outside the curled silhouette.
        p.save();p.setOpacity((amount-.5)*2)
        for i,x in enumerate((48,61,76,89)):
            wobble=math.sin(elapsed*1.8+i)*1.1
            y=62+(i%2)*4
            # Raised elbow, then a relaxed wrist hanging inward/downward.
            artist.fill(path([(x-3,y+10),
                              (x-1,y+3,x+5,y-5,x+2,y-10),
                              (x,y-14,x-5,y-13,x-7,y-9),
                              (x-10+wobble,y-5,x-12+wobble,y+1,x-8+wobble,y+3),
                              (x-4+wobble,y+5,x-3,y,x-3,y-2),
                              (x,y+2,x+4,y+8,x+3,y+11)]),10,
                        tone=artist.shade if i%2==0 else artist.base)
        p.restore()

        # The head is independent of the body's vertical roll. Keep the nose
        # gently raised and the eyelids shut; paws remain left of the face.
        p.save()
        p.setOpacity((amount-.5)*2)
        p.translate(103,77)
        p.scale(.70,.70)
        old_angle=getattr(artist,'ear_angle',0)
        artist.ear_angle=0
        artist.head(0,0,tilt=-22,sleeping=True)
        artist.ear_angle=old_angle
        p.restore()
