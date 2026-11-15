import claymarch


GREEN = (0.42, 0.80, 0.3)
LIGHT_GREEN = (0.66, 0.92, 0.45)
YELLOW = (1, 0.85, 0.15)
BLACK = (0, 0, 0)
WHITE = (1, 1, 1)
RED = (0.9, 0.3, 0.38)
CREAM = (0.98, 0.9, 0.52)


class Skin(claymarch.Material):
    color = GREEN

green = Skin()
yellow = Skin(color=YELLOW)
black = Skin(color=BLACK)
white = Skin(color=WHITE)
red = Skin(color=RED)
cream = Skin(color=CREAM)
light_green = Skin(color=LIGHT_GREEN)


def pulse(size, i):
    return lambda t: size * (1 + 0.03 * claymarch.sin(t * 3 - i * 0.9))


class Eye(claymarch.Drawing):
    rim = claymarch.Disc(0.20, material=yellow)
    pupil = claymarch.Disc(0.13, material=black)
    shine = claymarch.Disc(
        0.045,
        material=white,
        at=(-0.04, 0.06, 0.05)
    )


class Mouth(claymarch.Model):
    cone = claymarch.CutCone(0.25, 0.21, 0.28, rounding=0.09)
    lip = claymarch.Torus(
        0.17, 0.012,
        position=(0, 0.114, 0),
        carve=0.01
    )

    position = (0, -0.30, 0.30)
    rotation = (140, 0, 0)


class Antenna(claymarch.Model):
    stem = claymarch.Capsule(
        (0, 0, 0), (0, 0.28, 0.05), 0.05, 0.055,
        rotation=(30, 0, 0)
    )
    arms = claymarch.Capsule(
        (0, 0.22, 0.19), (0.38, 0.34, 0.05), 0.050, 0.070,
        symmetry='x',
    )

    smooth = 0.04
    material = red
    position = (0, 0.05, 0.4)

    def rotation(self, t):
        return (0, 0, 6 * claymarch.sin(t * 4))

class Head(claymarch.Model):
    body = claymarch.Ellipsoid(0.5, 0.45, 0.5)
    eyes = Eye(patch=(0.44, 0.06, 0.22), symmetry="x")
    hole = claymarch.Ellipsoid(
        0.26, 0.26, 0.5,
        position=(0, -0.34, 0.34),
        carve=0.06
    )
    mouth = Mouth()
    antenna = Antenna()

    position = (0, 1.3, 0)
    rotation = (0, -15, 0)
    material = green

    def rotation(self, t):
        nod = 3 * claymarch.sin(t * 1.5)
        turn = 8 * claymarch.sin(t * 0.9)
        return (-15 + nod, turn, 0)


class RoundBelly(claymarch.Model):
    belly = claymarch.Ellipsoid(0.29, 0.27, 0.17)
    legs = claymarch.Ellipsoid(
        0.07, 0.07, 0.044,
        rotation=(30, -20, 0),
        position=(0.18, -0.07, 0.123),
        symmetry='x'
    )

    smooth = 0.02
    material = cream
    position = (0, -0.03, 0.10)


class RoundSection(claymarch.Model):
    back = claymarch.Ellipsoid(0.39, 0.33, 0.34)
    ring = claymarch.Disc(
        0.12, inner=0.08,
        material=light_green,
        patch=(0.36, 0, -0.1),
        symmetry='x',
    )
    socket = claymarch.Ellipsoid(
        0.3, 0.28, 0.18,
        position=(0, -0.03, 0.2),
        carve=0.05
    )
    belly = RoundBelly(join=0.05)
    material = green
    position = (0, 0.75, -0.2)


class ConeBelly(claymarch.Model):
    belly = claymarch.CutCone(0.17, 0.21, 0.55, rounding=0.1)
    groove = claymarch.Torus(0.19, 0.012, carve=0.01)

    material = cream


class ConeSection(claymarch.Model):
    cone = claymarch.CutCone(
        0.25, 0.29, 0.6,
        rounding=0.16,
        bend=(-15, 0),
    )
    ring = claymarch.Disc(
        0.1, inner=0.065,
        material=light_green,
        patch=(0.26, 0, -0.07),
        symmetry='x',
    )
    socket = claymarch.CutCone(
        0.19, 0.26, 0.55, rounding=0.1,
        position=(0, 0, 0.13),
        bend=(-15, 0),
        carve=0.05,
    )
    belly = ConeBelly(bend=(-15, 0))

    material = green
    position = (0, 0.1, -0.72)
    rotation = (67, 0, 0)


class Tail(claymarch.Model):
    dot = claymarch.Sphere(0.06, position=(0, 0.05, 0))
    stroke = claymarch.Capsule(
        (0, 0.1, 0), (0, 0.45, 0), 0.035, 0.075
    )
    material = cream
    position = (0, 0.05, -1.66)
    rotation = (-35, 0, 0)

    def rotation(self, t):
        return (-35, 0, 14 * claymarch.sin(t * 5))


class Caterpie(claymarch.Model):
    head = Head()
    section_2 = RoundSection(size=pulse(1, 0))
    section_3 = RoundSection(
        size=pulse(0.88, 1),
        position=(0, 0.38, -0.38),
        rotation=(35, 0, 0)
    )
    section_4 = ConeSection(size=pulse(1, 2))
    section_5 = ConeSection(
        size=pulse(0.78, 3),
        position=(0, -0.02, -1.17),
        rotation=(84, 0, 0)
    )
    section_6 = ConeSection(
        size=pulse(0.57, 4),
        position=(0, 0, -1.53),
        rotation=(105, 0, 0)
    )
    tail = Tail()

    position = (0, 0.3, 0)
    smooth = 0.02


class Scene(claymarch.Scene):
    caterpie = Caterpie()
    camera = claymarch.Camera(
        target=(0, 1.15, 0),
        distance=3.8,
        yaw=45, pitch=8
    )
    light = claymarch.Light(direction=(0.8, 0.8, 0.5))
