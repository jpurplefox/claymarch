"""Squirtle vivo: el modelo de squirtle.py, moviéndose solo.

Para verlo:   python -m claymarch examples/squirtle_alive.py

squirtle.py dice cómo es Squirtle y dónde se articula; acá está cómo se
mueve: parpadea, menea la cola y aletea con los brazos. Cada movimiento
le dice a una pieza del modelo cómo girar (pose), sin tocar el modelo.
"""
import math

import claymarch
from squirtle import (
    Arm, Body, Head, LidEdge, Squirtle, SquirtleScene, Tail,
)

# Cuántos segundos tarda toda la animación en volver a empezar igual. Los
# movimientos de más abajo dan una cantidad entera de vueltas en ese
# tiempo, así un video de esa duración se puede repetir sin salto.
# Con velocidades enteras o terminadas en .5 (sin(t * 2.0), sin(t * 2.5))
# el ciclo cierra justo en 4 veces pi: unos 12,57 segundos.
LOOP = 4 * math.pi


def blink(t):
    """Cuánto están cerrados los ojos en cada momento: 0 abiertos, 1
    cerrados. Casi siempre vale 0, y cada tanto sube a 1 y vuelve
    enseguida."""
    # Parpadea una vez cada tantos segundos: tres veces por ciclo.
    every = LOOP / 3
    # De 0 a 1 una y otra vez; el parpadeo cae en la mitad.
    phase = claymarch.fract(t / every)
    # Los dos números son cuánto dura cerrado y cuánto tarda en cerrar y
    # abrir, como fracción de ese tiempo.
    return 1 - claymarch.smoothstep(0.015, 0.045, abs(phase - 0.5))


def looking(degrees):
    """La pose de mirar hacia un costado: la cabeza gira esos grados (0
    es derecho al frente) y el cuerpo la acompaña, girando un poco hacia
    el mismo lado y ladeándose apenas, como pasando el peso de una pierna
    a la otra. Los dos números son qué parte del giro de la cabeza hace
    el cuerpo."""
    return {
        Head: {"rotation": (-Head.TILT, degrees, 0)},
        Body: {"rotation": (0, 0.35 * degrees, 0.15 * degrees)},
    }


class AliveSquirtle(Squirtle):
    """Squirtle con sus movimientos de siempre."""

    def pose(self, t):
        # El borde del párpado baja cuando parpadea.
        lid = LidEdge.OPEN + (LidEdge.SHUT - LidEdge.OPEN) * blink(t)
        return {
            LidEdge: {"rotation": (-lid, 0, 0)},
            # Menea la cola alrededor de su lugar. El primer número es
            # cuántos grados se va hacia cada lado; el otro, la velocidad.
            Tail: {
                "rotation": (0, Tail.SWING + 7 * claymarch.sin(t * 3.0), 0)
            },
            # Aletea: sube y baja los brazos. El primer número es cuántos
            # grados; el otro, la velocidad.
            Arm: {"rotation": (0, 0, 9 * claymarch.sin(t * 4.0))},
        }


class AliveScene(SquirtleScene):
    squirtle = AliveSquirtle
