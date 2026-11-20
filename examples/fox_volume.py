"""El zorro sentado (_fox.py), con el pelo como un volumen suave de hebras:
la propiedad fuzz de cada parte. No hay pelos uno por uno; el rayo cruza el
pelo y junta las hebras que pasa.

- Se escribe igual que el pelo de fox.py: flow, lift, length, spacing.
- density dice cuánto tapa. La cola tiene el pelo casi tan largo como ella
  es gruesa; con 3 no parece humo.
- wind lo mueve en ráfagas que pasan de una parte a la siguiente.
- El pelo de atrás se ve a través del de adelante (la punta de la cola
  sobre el cuerpo, por ejemplo).

Para verlo:   python -m claymarch examples/fox_volume.py --port 8782
"""
import claymarch

import _fox
from _fox import Cream, Soot


class Windblown(claymarch.Fuzz):
    """Todo el pelo del zorro: el viento le sopla de derecha a izquierda."""

    wind = (0.5, 0.0, 0.0)


class Fox(_fox.Fox):
    def setup(self, t):
        self.torso.body.fuzz = Windblown(
            flow=(0, -0.4, -1), length=0.08, spacing=0.008
        )

        face = self.torso.head.face
        face.fuzz = Windblown(
            flow=(0, -0.3, -1), length=0.047, spacing=0.007
        )
        face.ears.tip = claymarch.Ellipsoid(
            0.07, 0.09, 0.052, position=(0, 0.19, 0), material=Soot, join=0.01
        )

        self.legs.fuzz = claymarch.Fuzz(
            flow=(0, -1, 0), length=0.028, spacing=0.006
        )
        self.haunches.fuzz = Windblown(
            flow=(0, -0.75, -1), length=0.07, spacing=0.008
        )

        tail = self.tail
        tail.tip = claymarch.Ellipsoid(
            0.09, 0.09, 0.14, position=(0, 0, -0.68), material=Cream
        )
        tail.smooth = 0.08
        # pelo largo sobre una cola fina: más denso, para que no parezca humo
        tail.fuzz = Windblown(
            flow=(0, 0, -1), lift=51, length=0.13, spacing=0.010, density=3
        )
        # un poco más alta que la pelada, así el pelo no se mete en el piso
        tail.position = (0.10, 0.25, -0.45)
        tail.rotation = (6, 115 + 8 * claymarch.sin(t * 1.5), 0)


class FoxScene(claymarch.Scene):
    fox = Fox
    camera = _fox.camera
    light = _fox.light
