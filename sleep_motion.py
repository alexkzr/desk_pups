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
    artist.curled()
    p.restore()
    if amount > .5:
        # Four relaxed bent legs point upward, outside the curled silhouette.
        p.save();p.setOpacity((amount-.5)*2)
        for i,x in enumerate((62,75,88,100)):
            wobble=math.sin(elapsed*1.8+i)*1.1
            y=62+(i%2)*4
            artist.fill(path([(x-3,y+10),(x-5,y,x-4,y-8,x+wobble,y-10),
                              (x+6+wobble,y-12,x+8+wobble,y-7,x+3,y-5),
                              (x+3,y+3,x+5,y+7,x+3,y+11)]),10,
                        tone=artist.shade if i%2==0 else artist.base)
        p.restore()
