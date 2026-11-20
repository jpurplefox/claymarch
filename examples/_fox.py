"""El zorro sentado, sin pelo: sus formas, cómo se mueve, el color de la
piel y la cámara. Lo comparten fox.py y fox_volume.py, que solo le agregan
el pelaje, cada uno a su manera (el _ del nombre dice que no es un ejemplo
para ver solo).

Ejes: y es arriba, z es el frente (hacia donde mira), x es el costado.
"""
import claymarch


class Fur(claymarch.Material):
    """La piel bajo el pelo: hebras finas estiradas a lo largo de z. Cada
    color de abajo dice solo su tono."""

    base = (0.5, 0.5, 0.5)
    specular = 0.06
    shininess = 8.0
    sheen = 0.1

    def strands(self, p):
        return claymarch.noise(claymarch.vec(p.x * 90, p.y * 90, p.z * 14))

    def color(self, p):
        dark = tuple(0.6 * c for c in self.base)
        return claymarch.mix(dark, self.base, self.strands(p))

    def bump(self, p):
        return 0.006 * self.strands(p) + 0.002 * claymarch.noise(p * 40)


class Rust(Fur):
    base = (0.86, 0.42, 0.16)


class Cream(Fur):
    base = (0.96, 0.90, 0.80)
    sheen = 0.4


class Soot(Fur):
    base = (0.16, 0.12, 0.10)


black = claymarch.Material(color=(0.03, 0.03, 0.04), specular=0.9)


class Body(claymarch.Model):
    chest = claymarch.Ellipsoid(0.26, 0.28, 0.40, position=(0, 0.62, 0.15))
    hips = claymarch.Ellipsoid(0.25, 0.27, 0.36, position=(0, 0.63, -0.28))
    neck = claymarch.Capsule((0, 0.70, 0.30), (0, 0.92, 0.50), 0.15)
    bib = claymarch.Ellipsoid(
        0.17, 0.24, 0.14, position=(0, 0.66, 0.44), material=Cream, join=0.01
    )

    smooth = 0.06
    material = Rust
    pivot = (0, 0.62, 0.15)

    def size(self, t):
        # respira
        return 1 + 0.012 * claymarch.sin(t * 2.4)


class Ear(claymarch.Model):
    """Media elipse chata: la mitad de abajo queda dentro de la cabeza."""

    flap = claymarch.Ellipsoid(0.10, 0.26, 0.05)

    material = Rust
    pivot = (0, -0.1, 0)
    position = (0.11, 1.05, 0.48)
    symmetry = "x"

    def rotation(self, t):
        # de vez en cuando, una sacudida rápida hacia afuera
        twitch = claymarch.maximum(0.0, claymarch.sin(t * 1.7)) ** 12
        return (-12, 0, -18 - 14 * twitch)


class Face(claymarch.Model):
    """La cabeza, menos los ojos y la nariz, que no llevan pelo."""

    skull = claymarch.Ellipsoid(0.20, 0.18, 0.20, position=(0, 0.97, 0.55))
    # con poco relleno en las uniones, así el pelo no queda tapado
    snout = claymarch.Ellipsoid(
        0.075, 0.065, 0.17, position=(0, 0.905, 0.76), join=0.015
    )
    cheeks = claymarch.Ellipsoid(
        0.18, 0.10, 0.17,
        position=(0, 0.89, 0.62),
        material=Cream,
        join=0.015,
    )
    ears = Ear(join=0.004)

    smooth = 0.06
    material = Rust


class Head(claymarch.Model):
    face = Face
    eyes = claymarch.Ellipsoid(
        0.035, 0.025, 0.02,
        rotation=(0, 30, 0),
        position=(0.09, 1.00, 0.72),
        symmetry="x",
        material=black,
    )
    nose = claymarch.Sphere(0.035, position=(0, 0.88, 0.94), material=black)

    pivot = (0, 0.92, 0.50)  # donde se apoya en el cuello

    def rotation(self, t):
        # mira alrededor, sin apuro; el 28 la endereza, porque el torso
        # está inclinado hacia arriba
        return (
            28 + 4 * claymarch.sin(t * 0.9),
            18 * claymarch.sin(t * 0.45),
            3 * claymarch.sin(t * 0.6),
        )


class Legs(claymarch.Model):
    """Las patas de adelante, derechas del hombro al piso."""

    front = claymarch.Capsule(
        (0.13, 0.56, 0.22), (0.13, 0.03, 0.30), 0.065, 0.04
    )

    material = Soot
    symmetry = "x"


class Haunches(claymarch.Model):
    """Las ancas apoyadas en el piso, con la pata de atrás hacia adelante."""

    haunch = claymarch.Ellipsoid(
        0.13, 0.17, 0.22, position=(0.17, 0.17, -0.20)
    )
    paw = claymarch.Capsule(
        (0.19, 0.07, -0.08), (0.18, 0.04, 0.12), 0.05, 0.04, material=Soot
    )

    material = Rust
    symmetry = "x"


class Tail(claymarch.Model):
    """La cola: un huso que nace en el origen y va hacia atrás (-z)."""

    core = claymarch.Ellipsoid(0.12, 0.12, 0.40, position=(0, 0, -0.40))

    material = Rust
    position = (0.10, 0.15, -0.45)

    def rotation(self, t):
        # apoyada en el piso, rodeando al zorro; la punta se mueve un poco
        return (-4, 115 + 8 * claymarch.sin(t * 1.5), 0)


class Torso(claymarch.Model):
    """Cuerpo y cabeza, inclinados hacia arriba desde la cadera y bajados
    hasta que la cadera toca el piso: el zorro está sentado."""

    body = Body
    head = Head

    pivot = (0, 0.63, -0.28)
    rotation = (-35, 0, 0)
    position = (0, -0.30, 0)


class Fox(claymarch.Model):
    torso = Torso
    haunches = Haunches
    legs = Legs
    tail = Tail


camera = claymarch.Camera(target=(0, 0.5, 0), distance=3.2, yaw=40, pitch=8)
light = claymarch.Light(direction=(-0.4, 0.8, 0.6))
