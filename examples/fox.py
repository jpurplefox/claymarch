"""El zorro sentado (_fox.py), cubierto de pelos sueltos: cada forma lleva
su hair, con su largo, su peinado y dónde crece.

- Cada pelo se ve de cerca, y el viento los mueve en ráfagas que pasan de
  un pelaje al siguiente.
- De lejos, donde un pixel es más ancho que un pelo, los pelos se ralean de
  a poco y en su lugar aparece pelo volumétrico (el de fox_volume.py), con
  el mismo peinado y color: el pelaje no titila y no hay que hacer nada.

Para verlo:   python -m claymarch examples/fox.py --port 8781
"""
import claymarch

import _fox
from _fox import Cream, Rust, Soot


class Strand(_fox.Fur):
    """Cada pelo: oscuro en la raíz, claro en la punta, y cada uno de un
    tono un poco distinto (x es un número al azar de cada pelo)."""

    reach = 0.08
    shade = 0.9  # qué tan oscura es la raíz
    bump = None

    def color(self, p):
        tip = claymarch.smoothstep(0.0, self.reach, p.z)
        root = tuple(self.shade * c for c in self.base)
        light = tuple(min(1.0, 1.15 * c) for c in self.base)
        return claymarch.mix(root, light, tip) * (0.8 + 0.4 * p.x)


class RustHair(Strand):
    base = Rust.base


class SootHair(Strand):
    base = Soot.base
    shade = 0.8
    sheen = 0.3


class CreamHair(Strand):
    base = Cream.base
    shade = 0.8
    sheen = 0.4


class Windblown(claymarch.Hair):
    """Todo el pelo del zorro: el viento le sopla de derecha a izquierda."""

    wind = (0.6, 0.0, 0.0)
    material = RustHair


class EarHair(Windblown):
    """El dorso de la oreja, peinado hacia la punta."""

    flow = (0, 1, 0)
    length = 0.06
    lift = 8


class TailHair(Windblown):
    flow = (0, 0, -1)
    length = 0.06
    lift = 16


# Dónde crece cada pelaje: out es hacia dónde mira la piel, point dónde está.

def no_belly(out):
    return claymarch.smoothstep(-0.75, -0.55, out.y)


def no_bib(out):
    # la panza sí, que sentado se ve
    return claymarch.smoothstep(0.7, 0.5, out.z)


def front(out):
    return claymarch.smoothstep(-0.4, -0.2, out.z)


def back_of_neck(out):
    # adelante sigue la pechera
    return claymarch.smoothstep(0.6, 0.4, out.z)


def ear_tuft(out, point):
    """Los mechones claros de adentro de la oreja."""
    inside = claymarch.smoothstep(0.3, 0.6, out.z)
    middle = claymarch.smoothstep(0.07, 0.04, abs(point.x))
    return inside * middle * claymarch.smoothstep(0.15, 0.10, point.y)


def ear_tip(out, point):
    return claymarch.smoothstep(0.16, 0.19, point.y)


def ear_back(out, point):
    return (1 - ear_tip(out, point)) * (1 - ear_tuft(out, point))


def around_eyes(out):
    """Nada de pelo sobre los ojos: out apunta hacia el ojo (a cualquiera de
    los dos lados) cerca de (0.45, 0.19, 0.86)."""
    toward = abs(out.x) * 0.45 + out.y * 0.19 + out.z * 0.86
    return claymarch.smoothstep(0.985, 0.96, toward)


def crown(out):
    return claymarch.smoothstep(0.4, 0.2, out.z)


def forehead(out):
    return claymarch.smoothstep(0.2, 0.4, out.z) * around_eyes(out)


def no_nose(out):
    return claymarch.smoothstep(0.9, 0.75, out.z)


def tail_root(out):
    return claymarch.smoothstep(-0.45, -0.3, out.z)


def tail_end(out):
    return claymarch.smoothstep(-0.3, -0.45, out.z)


class Fox(_fox.Fox):
    def setup(self):
        body = self.torso.body
        body.chest.hair = Windblown(
            flow=(0, -0.3, -1), spacing=0.015, grows=no_bib
        )
        body.hips.hair = Windblown(
            flow=(0, -0.4, -1), spacing=0.015, grows=no_belly
        )
        body.bib.hair = Windblown(
            flow=(0, -1, 0.3), length=0.08, material=CreamHair, grows=front
        )
        body.neck.hair = Windblown(flow=(0, -0.6, -1), grows=back_of_neck)

        face = self.torso.head.face
        face.skull.hair = [
            Windblown(flow=(0, 0.3, -1), length=0.06, grows=crown),
            # pelo corto en la frente, peinado hacia atrás
            Windblown(
                flow=(0, 0.1, -1), length=0.035, seed=2, grows=forehead
            ),
        ]
        face.snout.hair = Windblown(
            flow=(0, 0, -1), length=0.03, grows=no_nose
        )
        # la gorguera: pelos claros que caen de las mejillas
        face.cheeks.hair = Windblown(
            flow=(0, -0.5, -1), length=0.09, lift=20, material=CreamHair
        )

        face.ears.flap.hair = [
            EarHair(grows=ear_back),
            EarHair(material=SootHair, grows=ear_tip),
            Windblown(
                flow=(0, 1, 0.3), length=0.05, lift=15, material=CreamHair,
                grows=ear_tuft,
            ),
        ]

        self.haunches.haunch.hair = Windblown(flow=(0, -0.6, -1))

        self.tail.core.hair = [
            TailHair(grows=tail_root),
            TailHair(flow=(0, 0.15, -1), material=CreamHair, grows=tail_end),
        ]


class FoxScene(claymarch.Scene):
    fox = Fox
    camera = _fox.camera
    light = _fox.light
