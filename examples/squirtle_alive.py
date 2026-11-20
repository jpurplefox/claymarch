"""Squirtle vivo: el modelo de squirtle.py, moviéndose solo.

Para verlo:   python -m claymarch examples/squirtle_alive.py

Cada movimiento le dice a una pieza del modelo cómo girar (en setup), sin
tocar el modelo.
"""
import math

import claymarch
from squirtle import (
    Head, LidEdge, Squirtle, SquirtleScene, Tail,
)

# Los segundos que tarda la animación en repetirse. Con velocidades
# enteras o terminadas en .5 (sin(t * 2.5)) el ciclo cierra en 4 veces pi.
LOOP = 4 * math.pi


def blink(t):
    """Cuánto están cerrados los ojos: 0 abiertos, 1 cerrados."""
    every = LOOP / 3  # tres veces por ciclo
    phase = claymarch.fract(t / every)
    # Cuánto dura cerrado y cuánto tarda en cerrar y abrir, como fracción
    # de ese tiempo.
    return 1 - claymarch.smoothstep(0.015, 0.045, abs(phase - 0.5))


def look(squirtle, degrees):
    """Mirar hacia un costado: la cabeza gira esos grados y el cuerpo la
    acompaña, girando y ladeándose una parte."""
    squirtle.head.rotation = (-Head.TILT, degrees, 0)
    squirtle.body.rotation = (0, 0.35 * degrees, 0.15 * degrees)


class AliveSquirtle(Squirtle):
    def setup(self, t):
        lid = LidEdge.OPEN + (LidEdge.SHUT - LidEdge.OPEN) * blink(t)
        self.head.lids.edge.rotation = (-lid, 0, 0)
        self.body.tail.rotation = (
            0, Tail.SWING + 7 * claymarch.sin(t * 3.0), 0
        )
        self.body.arms.rotation = (0, 0, 9 * claymarch.sin(t * 4.0))


class AliveScene(SquirtleScene):
    squirtle = AliveSquirtle
