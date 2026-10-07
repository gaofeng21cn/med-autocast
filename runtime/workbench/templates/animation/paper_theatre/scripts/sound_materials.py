"""Original procedural accents for style studies, not recording-quality guarantees."""
import array
import math
import random

PALETTE = {
    'tap': (.12, 210, .030), 'paper': (.55, 0, .035),
    'brush': (.68, 0, .025), 'pencil': (.48, 0, .024),
    'marker': (.35, 0, .027), 'wipe': (.70, 0, .027),
    'print': (.26, 94, .025),
}

def material_sound(kind, rate, seed):
    if kind not in PALETTE:
        return None
    duration, tone, gain = PALETTE[kind]
    rng = random.Random(seed)
    low = slow = 0.
    output = array.array('f')
    for k in range(round(duration * rate)):
        t = k / rate
        noise = rng.uniform(-1, 1)
        cutoff = .06 if kind in ('brush', 'wipe') else .32
        low += cutoff * (noise - low)
        slow += .025 * (low - slow)
        band = low - slow
        envelope = math.sin(math.pi * t / duration) ** 2
        if kind == 'tap':
            value = (math.sin(t*math.tau*tone) + band*.12) * math.exp(-t*48)
        elif kind == 'print':
            value = (math.sin(t*math.tau*tone)*.5 + band) * math.exp(-t*18)
        elif kind == 'pencil':
            value = band * envelope * (.4 + .6*math.sin(t*math.tau*29)**2)
        elif kind == 'marker':
            value = band * envelope + .03*math.sin(t*math.tau*730)*envelope
        elif kind == 'paper':
            value = band * envelope * (.5 + .5*math.sin(t*math.tau*11)**2)
        else:
            value = band * envelope
        output.append(value * gain)
    return output
