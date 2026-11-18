"""Squirtle, modelado con claymarch.

Para verlo:   python -m claymarch examples/squirtle.py

Solo la forma y dónde se articula cada pieza: no se mueve. Quien lo mueve
lo hace desde afuera (ver squirtle_alive.py).
Ejes: y es arriba, z es el frente (hacia donde mira), x es el costado.
"""
import math

import claymarch


BLUE = (0.50, 0.80, 0.90)
CREAM = (0.97, 0.86, 0.60)
BROWN = (0.70, 0.40, 0.24)
WHITE = (0.97, 0.97, 0.95)
MAROON = (0.42, 0.10, 0.20)
BLACK = (0.03, 0.03, 0.04)


def shade(color, amount):
    """El mismo color, más oscuro (amount menor que 1) o más claro."""
    return tuple(min(1.0, c * amount) for c in color)


class Skin(claymarch.Material):
    """La piel: manchas suaves y un grano fino. Las otras texturas del
    cuerpo heredan de esta y cambian los números."""

    base = BLUE
    specular = 0.25
    blotch = 0.08  # cuánto se aclaran y oscurecen las manchas
    blotch_size = 4.0  # más alto, manchas más chicas
    grain = 0.0012
    grain_size = 45.0  # más alto, grano más fino

    def color(self, p):
        blotches = claymarch.fbm(p * self.blotch_size)
        return claymarch.mix(
            shade(self.base, 1 - self.blotch),
            shade(self.base, 1 + self.blotch),
            blotches,
        )

    def bump(self, p):
        return self.grain * claymarch.fbm(p * self.grain_size)


class Plate(Skin):
    """La panza."""

    base = CREAM
    specular = 0.15
    blotch = 0.15
    grain = 0.0008


class Horn(Skin):
    """El lomo."""

    base = BROWN
    specular = 0.15
    blotch = 0.26
    blotch_size = 7.0
    grain = 0.004
    grain_size = 22.0


class Bone(Skin):
    """El borde del caparazón."""

    base = WHITE
    blotch = 0.04
    grain = 0.0015
    grain_size = 30.0


blue = Skin()
cream = Plate()
brown = Horn()
white = Bone()
eye_white = claymarch.Material(color=WHITE, specular=0.25)
maroon = claymarch.Material(color=MAROON, specular=0.6)
black = claymarch.Material(color=BLACK, specular=0.6)


class EyeSocket(claymarch.Model):
    """La cavidad de un ojo: un óvalo al que una caja le corta la base."""

    oval = claymarch.Ellipsoid(0.17, 0.20, 0.10)
    frame = claymarch.Box(
        0.60, 0.40, 0.40,
        rotation=(0, 0, 0),
        position=(0, 0.07, 0),
        clip=0.04,
    )

    TILT = 12  # se recuesta, para seguir la curva de la cabeza
    TURN = 30  # gira hacia el costado

    rotation = (-TILT, -TURN, 0)
    position = (0.36, 0.05, 0.46)
    symmetry = "x"


class Eye(claymarch.Model):
    # Más grande que la cavidad, así la llena.
    ball = claymarch.Ellipsoid(
        0.19, 0.21, 0.07, position=(0, 0, -0.13), material=eye_white
    )
    iris = claymarch.Ellipsoid(
        0.095, 0.145, 0.010, position=(-0.02, -0.01, -0.060), material=maroon
    )
    pupil = claymarch.Ellipsoid(
        0.055, 0.090, 0.010, position=(-0.02, 0.00, -0.055), material=black
    )
    shine = claymarch.Ellipsoid(
        0.038, 0.038, 0.010,
        position=(-0.037, 0.07, -0.050),
        material=eye_white,
    )

    rotation = EyeSocket.rotation
    position = EyeSocket.position
    symmetry = "x"


class Skull(claymarch.Model):
    DOME = (0.60, 0.50, 0.55)
    CHEEKS = (0.56, 0.30, 0.46)
    CHEEKS_AT = (0, -0.19, 0.05)
    MOUTH_AT = (0, -0.20, 0.56)

    dome = claymarch.Ellipsoid(*DOME)
    cheeks = claymarch.Ellipsoid(*CHEEKS, position=CHEEKS_AT)
    muzzle = claymarch.Ellipsoid(0.45, 0.20, 0.3, position=(0, -0.16, 0.30))
    eye_sockets = EyeSocket(carve=0.03)
    mouth = claymarch.Ellipsoid(
        0.075, 0.075, 0.14,
        position=MOUTH_AT,
        carve=0.02,
    )
    # Apenas rozan la cara: con más z marcan menos.
    nostrils = claymarch.Capsule(
        (0.045, -0.04, 0.565), (0.030, -0.06, 0.58), 0.004,
        symmetry="x",
        carve=0.01,
    )

    smooth = 0.10


class LidEdge(claymarch.Model):
    """Hasta dónde baja el párpado: una caja cuya cara de abajo pasa por
    el centro de la cabeza. Al inclinarse hacia adelante, el borde baja
    por los ojos."""

    box = claymarch.Box(3, 3, 3, position=(0, 1.5, 0))

    OPEN = 40
    SHUT = -30

    rotation = (-OPEN, 0, 0)


def shrunk(radii, by):
    return tuple(r - by for r in radii)


class Lids(claymarch.Model):
    """Los párpados: una copia de la cabeza apenas más chica, que solo se
    ve por las cavidades de los ojos. De ella queda lo que está por
    encima de LidEdge."""

    DEEP = 0.006  # cuánto más chica que la cabeza es la copia

    dome = claymarch.Ellipsoid(*shrunk(Skull.DOME, DEEP))
    edge = LidEdge(clip=True)
    # Sin la franja del medio, para no tapar la nariz ni la boca.
    gap = claymarch.Box(0.36, 3, 3, carve=True)


class Head(claymarch.Model):
    skull = Skull
    eyes = Eye
    lids = Lids

    material = blue
    position = (0, 1.94, 0.35)
    TILT = 10  # mira hacia arriba
    rotation = (-TILT, 0, 0)


def ring(angle, radius):
    """El punto (x, y) a ese ángulo (0 es arriba) y esa distancia del
    centro del caparazón."""
    turn = math.radians(angle)
    return (radius * math.sin(turn), radius * math.cos(turn))


def rim_points(wave, radius, depth):
    points = []
    for angle, forward in wave:
        # Cuanto más se corre hacia adelante o atrás, más se cierra,
        # para seguir apoyado sobre el caparazón.
        closer = math.sqrt(1 - (forward / depth) ** 2)
        points.append((*ring(angle, radius * closer), forward))
    return points


class RimSide(claymarch.Model):
    """Medio borde blanco del caparazón, de la nuca a la cola."""

    # Cada renglón: el ángulo alrededor del caparazón (0 es arriba, 180
    # abajo) y cuánto se va hacia adelante (+) o hacia atrás (-). Tienen
    # que alternar.
    WAVE = [
        (0, -0.25),  # la nuca
        (35, 0.10),  # adelante, sobre el hombro
        (65, -0.08),  # atrás: donde sale el brazo
        (95, 0.10),  # adelante: la axila
        (130, -0.10),  # atrás: donde sale la pierna
        (160, 0.10),  # adelante
        (180, -0.12),  # atrás: donde sale la cola
    ]
    RADIUS = 0.51
    TUBE = 0.065
    DEPTH = 0.7  # más chico, el borde se cierra más al correrse
    PULL = 1.06  # los puntos van más afuera, así el tubo no corta camino

    tube = claymarch.Path(
        rim_points(WAVE, RADIUS * PULL, DEPTH), TUBE, symmetry="x"
    )

    material = white


class Grooves(claymarch.Drawing):
    """Lo que comparten las ranuras del lomo y las de la panza."""

    WIDTH = 0.014
    smooth = 0.02
    symmetry = "x"


class BackGrooves(Grooves):
    """Medio hexágono y un rayo desde cada esquina hasta el borde. Las
    esquinas apuntan adonde el borde se va hacia atrás."""

    HEX = 0.24
    RAYS = 0.76  # hasta dónde llegan los rayos, desde el centro

    def parts(self):
        angles = [
            angle for angle, forward in RimSide.WAVE if forward < 0
        ]
        corners = [ring(angle, self.HEX) for angle in angles]
        sides = list(zip(corners, corners[1:]))
        # Se pasan de largo: el borde tapa lo que sobra.
        rays = [
            (corner, ring(angle, self.RAYS))
            for corner, angle in zip(corners, angles)
        ]
        return [
            claymarch.Line(start, end, self.WIDTH)
            for start, end in sides + rays
        ]

    facing = "-z"
    depth = 0.012
    reach = 0.76


class Back(claymarch.Model):
    DOME = (0.50, 0.52, 0.38)

    dome = claymarch.Ellipsoid(*DOME)
    # Talladas desde el punto que más sobresale.
    grooves = BackGrooves(engrave=(0, 0, -DOME[2]))

    material = brown
    position = (0, 0, -0.14)


class PlastronGrooves(Grooves):
    # Cada renglón: de un punto (x, y) a otro, desde el centro de la panza.
    LINES = [
        ((0, 0.20), (0.60, 0.20)),  # la raya de arriba, de lado a lado
        ((0, 0.20), (0, -0.28)),  # la del medio, de arriba hacia abajo
        ((0.43, 0.20), (0.25, -0.05)),  # diagonal de arriba: se cierra
        ((0, -0.05), (0.25, -0.05)),  # la raya corta del centro
        ((0.25, -0.05), (0.40, -0.34)),  # diagonal de abajo: se abre
        ((0, -0.28), (0.40, -0.5)),  # la v invertida de abajo de todo
    ]

    def parts(self):
        return [
            claymarch.Line(start, end, self.WIDTH)
            for start, end in self.LINES
        ]

    facing = "z"
    depth = 0.015
    reach = 0.60


class Plastron(claymarch.Model):
    BELLY = (0.48, 0.51, 0.30)

    belly = claymarch.Ellipsoid(*BELLY)
    grooves = PlastronGrooves(engrave=(0, 0, BELLY[2]))

    material = cream
    position = (0, 0, 0.08)


class Claw(claymarch.Capsule):
    """Un dedo de la mano o del pie: termina en punta."""

    def __init__(self, base, tip):
        super().__init__(base, tip, 0.040, 0.012)


class ArmHole(claymarch.Model):
    """El hueco del caparazón por donde sale un brazo."""

    hole = claymarch.Ellipsoid(0.13, 0.15, 0.13)

    position = (0.40, 0.19, 0.18)
    symmetry = "x"


class Arm(claymarch.Model):
    """El hombro está en el origen, así gira desde ahí."""

    limb = claymarch.Capsule(
        (-0.08, -0.01, -0.06), (0.26, -0.26, 0.10), 0.145, 0.09
    )
    # Va antes que los dedos, así no los corta.
    palm = claymarch.Sphere(
        0.12, position=(0.38, -0.38, 0.2), carve=0.08
    )
    finger_up = Claw((0.29, -0.27, 0.06), (0.39, -0.32, 0.03))
    finger_down = Claw((0.27, -0.30, 0.06), (0.35, -0.37, 0.03))
    thumb = Claw((0.30, -0.25, 0.12), (0.40, -0.24, 0.15))

    smooth = 0.03
    material = blue
    position = ArmHole.position
    symmetry = "x"


class LegHole(claymarch.Model):
    """El hueco del caparazón por donde sale una pierna."""

    hole = claymarch.Ellipsoid(0.16, 0.16, 0.14)

    position = (0.33, -0.30, 0.18)
    symmetry = "x"


class Leg(claymarch.Model):
    """La cadera está en el origen. El pie llega a y = -0.43, donde está
    el piso: si la pierna se alarga, hay que subir el cuerpo lo mismo por
    su size."""

    thigh = claymarch.Curve(
        (-0.05, 0.03, -0.05), (0.06, -0.13, 0.10), (0.0, -0.32, 0.04),
        0.17, 0.13,
        rotation=(10, 0, 0),
    )
    foot = claymarch.Capsule(
        (0.0, -0.35, 0.00), (0.02, -0.36, 0.04), 0.08, 0.07
    )
    toe_in = Claw((-0.04, -0.38, 0.06), (-0.07, -0.41, 0.16))
    toe_mid = Claw((0.01, -0.38, 0.07), (0.02, -0.41, 0.18))
    toe_out = Claw((0.06, -0.38, 0.07), (0.10, -0.41, 0.15))

    smooth = 0.08
    material = blue
    position = LegHole.position
    symmetry = "x"


def tail_side(forward, up, width, roundness, stem):
    """Cuánto sale la cola hacia el costado en ese punto del perfil: lo
    que más salga entre la bola y el tallo. 0 si el punto cae afuera."""
    side = 1 - (forward ** 2 + up ** 2) / roundness ** 2
    widest = width * math.sqrt(side) if side > 0 else 0.0
    start, control, end, thick, thin = stem
    for i in range(41):
        t = i / 40
        # El punto del tallo a esa altura, y su grosor ahí.
        x, y, z = (
            (1 - t) ** 2 * a + 2 * t * (1 - t) * c + t * t * b
            for a, c, b in zip(start, control, end)
        )
        radius = thick + (thin - thick) * t
        side = radius ** 2 - (up - y) ** 2 - (forward - z) ** 2
        if side > 0:
            widest = max(widest, math.sqrt(side))
    return widest


def groove_points(groove, width, roundness, stem):
    """Los puntos de la ranura apoyados sobre la superficie de la cola."""
    return [
        (tail_side(forward, up, width, roundness, stem), up, forward)
        for forward, up in groove
    ]


class Tail(claymarch.Model):
    """El centro de la bola está en el origen. El rulo es una ranura
    cavada a cada costado."""

    # La bola no tiene que pasar del piso.
    WIDTH = 0.22
    ROUND = 0.30
    # Si el cuello engorda mucho, toca el borde o el piso.
    NECK = (
        (0, -0.03, 0.93), (0, -0.24, 0.85), (0, -0.2, 0.63), 0.09, 0.10
    )
    STEM = (
        (0, -0.2, 0.63), (0, -0.15, 0.40), (0, -0.15, 0.05), 0.10, 0.15
    )
    # Cada renglón: un punto (adelante, arriba) desde el centro de la bola.
    GROOVE = [
        (0.12, -0.32),  # abajo de todo: donde se unen los dos costados
        (0.12, -0.27),
        (0.12, -0.18),  # sube por adelante
        (0.14, -0.04),
        (0.13, 0.10),  # dobla hacia atrás
        (0.02, 0.17),  # arriba
        (-0.10, 0.12),
        (-0.13, 0.00),  # baja por atrás
        (-0.06, -0.06),  # la punta del gancho
    ]
    GROOVE_TUBE = 0.022
    SWING = 50  # se va hacia un costado

    ball = claymarch.Ellipsoid(WIDTH, ROUND, ROUND)
    stem = claymarch.Curve(*STEM, join=0.08)
    neck = claymarch.Curve(*NECK, join=0.03)
    groove = claymarch.Path(
        groove_points(GROOVE, WIDTH, ROUND, STEM), GROOVE_TUBE,
        symmetry="x",
        carve=0.02,
    )

    material = blue
    position = (0, -0.36, -0.85)
    # Gira desde donde nace el cuello, así no se despega del caparazón.
    pivot = NECK[0]
    rotation = (0, SWING, 0)


class Shell(claymarch.Model):
    plastron = Plastron
    back = Back
    arm_holes = ArmHole(carve=0.02)
    leg_holes = LegHole(carve=0.02)
    # El borde va al final, así los huecos no lo cavan.
    rim = RimSide


class Body(claymarch.Model):
    shell = Shell
    arms = Arm
    legs = Leg
    tail = Tail

    size = 1.4
    position = (0, 1.02, 0)


class Squirtle(claymarch.Model):
    """Squirtle entero, quieto. Se articulan Head, Body, Arm, Tail y
    LidEdge: cada una gira alrededor de su origen o de su pivot."""

    body = Body
    head = Head


class SquirtleScene(claymarch.Scene):
    squirtle = Squirtle
    camera = claymarch.Camera(
        target=(0, 1.25, 0), distance=4.8, yaw=30, pitch=4
    )
    light = claymarch.Light(direction=(-0.5, 0.8, 0.6))
