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

    base = BLUE  # el color
    specular = 0.25  # qué tan fuerte es el brillo
    blotch = 0.08  # cuánto se aclaran y oscurecen las manchas
    blotch_size = 4.0  # más alto, manchas más chicas
    grain = 0.0012  # qué tan marcado es el grano de la superficie
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
    """La panza: crema, lisa, con manchas muy suaves."""

    base = CREAM
    specular = 0.15
    blotch = 0.15
    grain = 0.0008


class Horn(Skin):
    """El lomo: marrón, con vetas marcadas y áspero, como cuerno."""

    base = BROWN
    specular = 0.15
    blotch = 0.26
    blotch_size = 7.0
    grain = 0.004
    grain_size = 22.0


class Bone(Skin):
    """El borde del caparazón: blanco hueso, apenas manchado."""

    base = WHITE
    blotch = 0.04
    grain = 0.0015
    grain_size = 30.0


blue = Skin()
cream = Plate()
brown = Horn()
white = Bone()
# Los ojos son lisos: sin manchas ni grano.
eye_white = claymarch.Material(color=WHITE, specular=0.25)
maroon = claymarch.Material(color=MAROON, specular=0.6)
black = claymarch.Material(color=BLACK, specular=0.6)


class Eye(claymarch.Model):
    """Un ojo: un óvalo blanco en el fondo de la cavidad, con el iris, la
    pupila y un brillo apoyados encima, uno apenas delante del otro."""

    # Más grande que la cavidad, así la llena. Con z más negativo se
    # hunde más.
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

    # Cuánto se recuesta hacia atrás, en grados, para seguir la curva de
    # la cabeza.
    TILT = 12
    TURN = 30  # cuánto mira hacia el costado, en grados

    rotation = (-TILT, -TURN, 0)
    # Apenas por fuera de la superficie de la cabeza.
    position = (0.36, 0.05, 0.46)
    symmetry = "x"


class Socket(claymarch.Model):
    """La cavidad de un ojo: un óvalo con la base recta. La cara de abajo
    de una caja corta el óvalo y le deja esa base."""

    SOFT = 0.04  # qué tan redondeado queda el corte

    parts = [
        claymarch.Ellipsoid(0.17, 0.20, 0.10)
        # Con el segundo número de position más alto, la base corta más.
        .intersect(
            claymarch.Box(
                0.60, 0.40, 0.40,
                rotation=(0, 0, 0),
                position=(0, 0.07, 0),
            ),
            smooth=SOFT,
        )
    ]

    # Va donde va el ojo y gira lo mismo.
    rotation = Eye.rotation
    position = Eye.position
    symmetry = "x"


class Skull(claymarch.Model):
    """La forma de la cabeza: más ancha que alta, con cachetes abajo."""

    # Ancho, alto y fondo de la frente y de los cachetes.
    DOME = (0.60, 0.50, 0.55)
    CHEEKS = (0.56, 0.30, 0.46)
    CHEEKS_AT = (0, -0.19, 0.05)
    MOUTH_AT = (0, -0.20, 0.56)

    dome = claymarch.Ellipsoid(*DOME)
    cheeks = claymarch.Ellipsoid(*CHEEKS, position=CHEEKS_AT)
    # El hocico: sale hacia adelante un poco más que los cachetes.
    muzzle = claymarch.Ellipsoid(0.45, 0.20, 0.3, position=(0, -0.16, 0.30))
    sockets = Socket(carve=0.03)
    # La boca en forma de o: un hueco alargado hacia adentro.
    mouth = claymarch.Ellipsoid(
        0.075, 0.075, 0.14,
        position=MOUTH_AT,
        carve=0.02,
    )
    # La nariz: dos cápsulas muy finas que apenas rozan la cara. Con más
    # z marcan menos.
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

    # Dónde queda el borde, en grados: por encima o por debajo de las
    # cavidades.
    OPEN = 40
    SHUT = -30

    rotation = (-OPEN, 0, 0)  # abierto


class Lids(claymarch.Model):
    """Los párpados: una copia de la cabeza apenas más chica, que solo se
    ve por las cavidades de los ojos. De ella queda lo que está por
    encima de LidEdge."""

    DEEP = 0.006  # cuánto más chica que la cabeza es la copia

    def parts(self):
        return [
            claymarch.Ellipsoid(*(r - self.DEEP for r in Skull.DOME))
            .intersect(LidEdge())
            # Sin la franja del medio, para no tapar la nariz ni la
            # boca.
            .subtract(claymarch.Box(0.36, 3, 3))
        ]


class Head(claymarch.Model):
    """La cabeza, con los ojos y los párpados."""

    skull = Skull
    eyes = Eye
    lids = Lids

    material = blue
    position = (0, 1.94, 0.35)  # apoyada sobre el caparazón, sin cuello
    TILT = 10  # cuánto mira hacia arriba, en grados
    rotation = (-TILT, 0, 0)


def rim_point(angle, forward, radius):
    """Un punto del anillo, a ese ángulo y corrido hacia adelante o atrás.
    Cuanto más se corre, más se cierra, para seguir apoyado sobre el
    caparazón."""
    radius = radius * math.sqrt(1 - (forward / 0.7) ** 2)
    turn = math.radians(angle)
    return (radius * math.sin(turn), radius * math.cos(turn), forward)


def middle(a, b):
    return tuple((p + q) / 2 for p, q in zip(a, b))


def mirrored(point):
    """El mismo punto, del otro costado."""
    x, y, z = point
    return (-x, y, z)


def rim_points(wave, radius):
    """Los puntos por los que va medio borde, de la nuca a la cola."""
    # Un poco más afuera que el anillo, para que el tubo no corte camino.
    pulls = [rim_point(a, f, radius * 1.06) for a, f in wave]
    # Los extremos cruzan al otro costado, así las dos mitades se
    # encuentran en curva y no en punta.
    start = mirrored(middle(pulls[0], pulls[1]))
    end = mirrored(middle(pulls[-2], pulls[-1]))
    return [start, *pulls, end]


class RimSide(claymarch.Model):
    """Medio borde blanco del caparazón, de la nuca a la cola: un tubo
    que dobla hacia cada punto de WAVE sin llegar a tocarlo."""

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
    RADIUS = 0.51  # el radio del anillo
    TUBE = 0.065  # el grosor del tubo

    tube = claymarch.Path(rim_points(WAVE, RADIUS), TUBE)

    material = white
    symmetry = "x"


def around(angle, radius):
    """El punto (x, y) a ese ángulo (0 es arriba) y esa distancia del
    centro del lomo."""
    turn = math.radians(angle)
    return (radius * math.sin(turn), radius * math.cos(turn))


class Grooves(claymarch.Drawing):
    """Lo que comparten las ranuras del lomo y las de la panza."""

    WIDTH = 0.014
    smooth = 0.02  # qué tan redondeado queda el canto
    symmetry = "x"


class BackGrooves(Grooves):
    """Las ranuras de medio lomo: medio hexágono y un rayo desde cada
    esquina hasta el borde. Las esquinas apuntan adonde el borde se va
    hacia atrás (los renglones negativos de RimSide.WAVE)."""

    HEX = 0.24  # el tamaño del hexágono

    def parts(self):
        angles = [
            angle for angle, forward in RimSide.WAVE if forward < 0
        ]
        corners = [around(angle, self.HEX) for angle in angles]
        sides = list(zip(corners, corners[1:]))
        # Se pasan de largo: el borde tapa lo que sobra.
        rays = [
            (corner, around(angle, 0.7))
            for corner, angle in zip(corners, angles)
        ]
        return [
            claymarch.Line(start, end, self.WIDTH)
            for start, end in sides + rays
        ]

    facing = "-z"  # se mira desde atrás
    depth = 0.012
    reach = 0.76  # todo el lomo, hasta debajo del borde


class Back(claymarch.Model):
    """El lomo marrón, con las placas marcadas por ranuras."""

    # Ancho, alto y cuánto sobresale hacia atrás: casi del tamaño del
    # anillo.
    DOME = (0.50, 0.52, 0.38)

    dome = claymarch.Ellipsoid(*DOME)
    # Talladas desde el punto que más sobresale.
    grooves = BackGrooves(engrave=(0, 0, -DOME[2]))

    material = brown
    position = (0, 0, -0.14)


class PlastronGrooves(Grooves):
    """Las ranuras de media panza."""

    # Cada renglón es una ranura, de un punto (x, y) a otro, medidos
    # desde el centro de la panza.
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

    facing = "z"  # se mira de frente
    depth = 0.015
    reach = 0.60  # toda la panza


class Plastron(claymarch.Model):
    """La panza crema, con las placas marcadas por ranuras."""

    # Ancho, alto y cuánto sobresale hacia adelante.
    BELLY = (0.48, 0.51, 0.30)

    belly = claymarch.Ellipsoid(*BELLY)
    # Talladas desde el punto que más sobresale.
    grooves = PlastronGrooves(engrave=(0, 0, BELLY[2]))

    material = cream
    position = (0, 0, 0.08)


class Arm(claymarch.Model):
    """Un brazo: corto y gordito, con dos dedos y un pulgar. El hombro
    está en el origen, así gira desde ahí."""

    # Del hombro, adentro de la cavidad, a la mano.
    limb = claymarch.Capsule(
        (-0.08, -0.01, -0.06), (0.26, -0.26, 0.10), 0.145, 0.09
    )
    # La palma: una esfera que apenas muerde la mano. Va antes que los
    # dedos, así no los corta.
    palm = claymarch.Sphere(
        0.12, position=(0.38, -0.38, 0.2), carve=0.08
    )
    # Dos dedos juntos, de la mano a la punta, del lado del dorso.
    finger_up = claymarch.Capsule(
        (0.29, -0.27, 0.06), (0.39, -0.32, 0.03), 0.040, 0.012
    )
    finger_down = claymarch.Capsule(
        (0.27, -0.30, 0.06), (0.35, -0.37, 0.03), 0.040, 0.012
    )
    # El pulgar: el número del medio de la punta dice cuánto se abre.
    thumb = claymarch.Capsule(
        (0.30, -0.25, 0.12), (0.40, -0.24, 0.15), 0.040, 0.012
    )

    smooth = 0.03
    material = blue
    # Dónde sale del caparazón. Su cavidad va en el mismo lugar.
    position = (0.40, 0.19, 0.18)
    symmetry = "x"


class Leg(claymarch.Model):
    """Una pierna: corta y gruesa, con un pie de tres dedos. La cadera
    está en el origen.

    El pie llega a y = -0.43, donde está el piso visto desde la cadera.
    Si la pierna se alarga, hay que subir el cuerpo lo mismo por su size.
    """

    # De la cadera al tobillo, doblándose hacia el punto del medio, que
    # es hacia dónde apunta la rodilla.
    thigh = claymarch.Curve(
        (-0.05, 0.03, -0.05), (0.06, -0.13, 0.10), (0.0, -0.32, 0.04),
        0.17, 0.13,
        rotation=(10, 0, 0),
    )
    foot = claymarch.Capsule(
        (0.0, -0.35, 0.00), (0.02, -0.36, 0.04), 0.08, 0.07
    )
    toe_in = claymarch.Capsule(
        (-0.04, -0.38, 0.06), (-0.07, -0.41, 0.16), 0.040, 0.012
    )
    toe_mid = claymarch.Capsule(
        (0.01, -0.38, 0.07), (0.02, -0.41, 0.18), 0.040, 0.012
    )
    toe_out = claymarch.Capsule(
        (0.06, -0.38, 0.07), (0.10, -0.41, 0.15), 0.040, 0.012
    )

    smooth = 0.08
    material = blue
    position = (0.33, -0.30, 0.18)
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
    """La cola: un cuello fino que pasa por debajo del borde del
    caparazón, engorda y termina en una bola. El rulo es una ranura
    cavada a cada costado. El centro de la bola está en el origen."""

    # La bola: el ancho y el radio visto de perfil. No tiene que pasar
    # del piso.
    WIDTH = 0.22
    ROUND = 0.30
    # El cuello: nace adentro de la panza y pasa por debajo del borde. Si
    # engorda mucho toca el borde o el piso.
    NECK = (
        (0, -0.03, 0.93), (0, -0.24, 0.85), (0, -0.2, 0.63), 0.09, 0.10
    )
    # El tallo: sigue desde el cuello y engorda hasta la bola.
    STEM = (
        (0, -0.2, 0.63), (0, -0.15, 0.40), (0, -0.15, 0.05), 0.10, 0.15
    )
    # La ranura, vista de perfil: cada renglón es un punto (adelante,
    # arriba) hacia el que tira, medido desde el centro de la bola.
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
    GROOVE_TUBE = 0.022  # el grosor del tubo que cava la ranura
    SWING = 50  # cuánto se va hacia un costado, en grados

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
    """El caparazón: la panza adelante, el lomo atrás y un borde blanco
    entre los dos."""

    plastron = Plastron
    back = Back
    # Las cavidades de donde salen los brazos y las piernas.
    arm_holes = claymarch.Ellipsoid(
        0.13, 0.15, 0.13,
        position=Arm.position,
        symmetry="x",
        carve=0.02,
    )
    leg_holes = claymarch.Ellipsoid(
        0.16, 0.16, 0.14,
        position=Leg.position,
        symmetry="x",
        carve=0.02,
    )
    # El borde va al final, así los huecos no lo cavan.
    rim = RimSide


class Body(claymarch.Model):
    """El cuerpo: el caparazón, los brazos, las piernas y la cola."""

    shell = Shell
    arms = Arm
    legs = Leg
    tail = Tail

    size = 1.4  # respecto de la cabeza
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
