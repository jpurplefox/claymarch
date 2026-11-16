"""Squirtle, modelado con claymarch.

Para verlo:   python -m claymarch examples/squirtle.py

Por ahora solo la cabeza.
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


class Skin(claymarch.Material):
    color = BLUE
    specular = 0.25


blue = Skin()
cream = Skin(color=CREAM, specular=0.15)
brown = Skin(color=BROWN, specular=0.15)
white = Skin(color=WHITE)
maroon = Skin(color=MAROON, specular=0.6)
black = Skin(color=BLACK, specular=0.6)


# Dónde va cada ojo sobre la cabeza. Lo usan la cavidad y el ojo, para que
# se muevan juntos. El punto queda apenas por fuera de la superficie de la
# cúpula.
EYE_AT = (0.36, 0.05, 0.46)
# Cuánto se recuesta el ojo hacia atrás, en grados, para seguir la curva
# de la cabeza. Con 0 queda vertical, y se ve más hundido abajo que
# arriba; con más, se hunde más arriba y menos abajo.
EYE_TILT = 12
# Cuánto mira el ojo hacia el costado, en grados: 0 mira derecho al frente;
# 90, al costado. Lo usan la cavidad y el ojo, así quedan alineados.
EYE_TURN = 30


class Socket(claymarch.Model):
    """La cavidad de un ojo: un óvalo grande y redondo arriba, con la
    base recta.

    Es un óvalo chato al que se le deja solo lo que queda dentro de una
    caja (intersect es la intersección): la cara de abajo de la caja
    corta el óvalo y le deja la base recta.
    """

    # Qué tan redondeadas quedan las esquinas donde la caja corta el
    # óvalo: 0 las deja filosas.
    SOFT = 0.04

    parts = [
        # Los dos primeros números son el ancho y el alto del ojo.
        claymarch.Ellipsoid(0.17, 0.20, 0.10)
        # position: con el segundo número más alto la base corta más;
        # más bajo, el ojo queda más redondo. rotation la inclina.
        .intersect(
            claymarch.Box(
                0.60, 0.40, 0.40,
                rotation=(0, 0, 0),
                position=(0, 0.07, 0),
            ),
            smooth=SOFT,
        )
    ]

    # Girada para que mire hacia afuera, y apoyada sobre la cúpula: el
    # centro queda apenas por fuera de la superficie, así el hueco es poco
    # profundo.
    rotation = (-EYE_TILT, -EYE_TURN, 0)
    position = EYE_AT
    symmetry = "x"


class Eye(claymarch.Model):
    """Un ojo: un óvalo chato y blanco metido en el fondo de la cavidad,
    con el iris, la pupila y un brillo apoyados encima.

    El blanco es más grande que la cavidad, así la llena entera; lo que
    sobra queda escondido dentro de la cabeza. El iris y la pupila son
    elipsoides muy chatos, más altos que anchos, uno apenas delante del
    otro (el tercer número de position).
    """

    # position: qué tan hundido queda. Con z más negativo se mete más.
    ball = claymarch.Ellipsoid(
        0.19, 0.21, 0.07, position=(0, 0, -0.13), material=white
    )
    iris = claymarch.Ellipsoid(
        0.095, 0.145, 0.010, position=(-0.02, -0.01, -0.060), material=maroon
    )
    pupil = claymarch.Ellipsoid(
        0.055, 0.090, 0.010, position=(-0.02, 0.00, -0.055), material=black
    )
    # El brillo: grande y arriba, le da la mirada simpática.
    shine = claymarch.Ellipsoid(
        0.038, 0.038, 0.010, position=(-0.037, 0.07, -0.050), material=white
    )

    # Girado para que mire hacia afuera de la cabeza: 0 mira derecho al
    # frente; -90, al costado.
    rotation = (-EYE_TILT, -EYE_TURN, 0)
    position = EYE_AT
    symmetry = "x"


class Skull(claymarch.Model):
    """La forma de la cabeza: más ancha que alta, con cachetes abajo."""

    dome = claymarch.Ellipsoid(0.60, 0.50, 0.55)
    cheeks = claymarch.Ellipsoid(0.56, 0.30, 0.46, position=(0, -0.19, 0.05))
    # La zona de la boca: sale hacia adelante un poco más que los cachetes
    # (llega a z = 0.58; los cachetes, a 0.51).
    muzzle = claymarch.Ellipsoid(0.45, 0.20, 0.3, position=(0, -0.16, 0.30))
    # Las cavidades de los ojos.
    sockets = Socket(carve=0.03)
    # La boca en forma de o: un hueco redondo en la punta del hocico. Es
    # un elipsoide alargado hacia adentro (el tercer número es el fondo).
    mouth = claymarch.Ellipsoid(
        0.075, 0.075, 0.14,
        position=(0, -0.20, 0.56),
        carve=0.02,
    )
    # La nariz: dos rayitas apenas marcadas arriba de la boca. Cada una es
    # una cápsula muy fina, casi toda afuera de la cara: solo roza la
    # superficie. Más z la saca (marca menos); menos z la hunde.
    nostrils = claymarch.Capsule(
        (0.045, -0.04, 0.565), (0.030, -0.06, 0.58), 0.004,
        symmetry="x",
        carve=0.01,
    )

    smooth = 0.10


class Head(claymarch.Model):
    """La cabeza: la forma, con los ojos metidos en sus cavidades."""

    skull = Skull
    eyes = Eye

    material = blue
    position = (0, 0.60, 0)


# El recorrido del borde blanco, de la nuca a la cola, por un costado.
# Cada renglón es un punto: el ángulo alrededor del caparazón (0 es arriba
# de todo, 90 el costado, 180 abajo de todo) y cuánto se va el borde hacia
# adelante (+) o hacia atrás (-) en ese punto.
# Para cambiar la onda alcanza con tocar esta tabla: se pueden mover los
# puntos, agregar o sacar renglones. Tienen que alternar adelante y atrás.
RIM_WAVE = [
    (0, -0.25),  # la nuca
    (35, 0.10),  # adelante, sobre el hombro
    (65, -0.08),  # atrás: donde sale el brazo
    (95, 0.10),  # adelante: la axila
    (130, -0.10),  # atrás: donde sale la pierna
    (160, 0.10),  # adelante
    (180, -0.12),  # atrás: donde sale la cola
]
RIM_RADIUS = 0.51  # el radio del anillo
RIM_TUBE = 0.065  # el grosor del tubo


def rim_point(angle, forward, radius):
    """Un punto del anillo: a ese ángulo y corrido hacia adelante o atrás.

    Cuanto más se corre, más se cierra el anillo: así sigue apoyado sobre
    el caparazón, que es redondeado, y no queda flotando.
    """
    radius = radius * math.sqrt(1 - (forward / 0.7) ** 2)
    turn = math.radians(angle)
    return (radius * math.sin(turn), radius * math.cos(turn), forward)


def middle(a, b):
    return tuple((p + q) / 2 for p, q in zip(a, b))


def mirrored(point):
    """El mismo punto, del otro costado."""
    x, y, z = point
    return (-x, y, z)


def rim_points():
    """Los puntos por los que va medio borde, de la nuca a la cola."""
    # Los puntos de la tabla van un poco más afuera que el anillo, para
    # que el tubo no corte camino y quede redondo.
    pulls = [rim_point(a, f, RIM_RADIUS * 1.06) for a, f in RIM_WAVE]
    # Los dos extremos cruzan al otro costado: el tubo empieza y termina
    # en el espejo de su primer y su último empalme. Así las dos mitades
    # del anillo se encuentran en curva y no en punta.
    start = mirrored(middle(pulls[0], pulls[1]))
    end = mirrored(middle(pulls[-2], pulls[-1]))
    return [start, *pulls, end]


class RimSide(claymarch.Model):
    """Medio borde blanco del caparazón: de la nuca a la cola por un
    costado. symmetry hace el otro, y entre los dos cierran el anillo.

    Es un Path: un tubo que dobla una vez por cada ida o vuelta de
    RIM_WAVE. Los puntos de la tabla son hacia dónde tira (no pasa por
    ahí, se queda a mitad de camino); cada doblez empieza donde termina
    el anterior, en el punto medio entre dos de la tabla, y por eso
    empalman sin quiebre.
    """

    tube = claymarch.Path(rim_points(), RIM_TUBE)

    material = white
    symmetry = "x"


HEX_RADIUS = 0.24  # el tamaño del hexágono del lomo
GROOVE_WIDTH = 0.014  # el ancho de las ranuras del lomo y de la panza
GROOVE_SOFT = 0.02  # qué tan redondeado queda el canto de las ranuras


def around(angle, radius):
    """El punto (x, y) a ese ángulo y esa distancia del centro del lomo.
    Los ángulos son los mismos de RIM_WAVE: 0 es arriba."""
    turn = math.radians(angle)
    return (radius * math.sin(turn), radius * math.cos(turn))


class BackGrooves(claymarch.Drawing):
    """Las ranuras de medio lomo: medio hexágono y un rayo desde cada
    esquina hasta el borde blanco. symmetry hace la otra mitad.

    Las esquinas apuntan a los lugares donde el borde se va hacia atrás
    (los renglones negativos de RIM_WAVE): la nuca, el brazo, la pierna y
    la cola. Si se mueven en la tabla, las ranuras los siguen.
    """

    def parts(self):
        angles = [angle for angle, forward in RIM_WAVE if forward < 0]
        corners = [around(angle, HEX_RADIUS) for angle in angles]
        sides = list(zip(corners, corners[1:]))
        # Los rayos se pasan de largo: el borde blanco tapa lo que sobra.
        rays = [
            (corner, around(angle, 0.7))
            for corner, angle in zip(corners, angles)
        ]
        return [
            claymarch.Line(start, end, GROOVE_WIDTH)
            for start, end in sides + rays
        ]

    # El dibujo se mira desde atrás y se talla hasta esa profundidad.
    facing = "-z"
    depth = 0.012
    smooth = GROOVE_SOFT
    # Hasta dónde llega el dibujo desde su punto: todo el lomo, para que
    # los rayos sigan por debajo del borde blanco.
    reach = 0.76
    symmetry = "x"


class Back(claymarch.Model):
    """El lomo marrón, con las placas marcadas por ranuras."""

    # Casi del tamaño del anillo, que queda medio hundido en él. Los dos
    # primeros números son el ancho y el alto; el tercero, cuánto
    # sobresale hacia atrás.
    dome = claymarch.Ellipsoid(0.50, 0.52, 0.38)
    # Las ranuras, talladas desde el punto del lomo que más sobresale.
    grooves = BackGrooves(engrave=(0, 0, -0.38))

    material = brown
    position = (0, 0, -0.14)


# El dibujo de la panza, de un costado: cada renglón es una ranura, de un
# punto (x, y) a otro. x es hacia el costado (0 es el medio) e y hacia
# arriba (0 es el centro de la panza). symmetry copia el otro costado.
# Las que llegan al borde se pasan de largo: el anillo tapa lo que sobra.
PLASTRON_GROOVES = [
    ((0, 0.20), (0.60, 0.20)),  # la raya de arriba, de lado a lado
    ((0, 0.20), (0, -0.28)),  # la del medio, de arriba hacia abajo
    ((0.43, 0.20), (0.25, -0.05)),  # diagonal de arriba: baja cerrándose
    ((0, -0.05), (0.25, -0.05)),  # la raya corta del centro
    ((0.25, -0.05), (0.40, -0.34)),  # diagonal de abajo: baja abriéndose
    ((0, -0.28), (0.40, -0.5)),  # la v invertida de abajo de todo
]


class PlastronGrooves(claymarch.Drawing):
    """Las ranuras de media panza, según PLASTRON_GROOVES."""

    def parts(self):
        return [
            claymarch.Line(start, end, GROOVE_WIDTH)
            for start, end in PLASTRON_GROOVES
        ]

    # El dibujo se mira de frente y se talla hasta esa profundidad.
    facing = "z"
    depth = 0.015
    smooth = GROOVE_SOFT
    # Hasta dónde llega el dibujo desde su punto: toda la panza.
    reach = 0.60
    symmetry = "x"


class Plastron(claymarch.Model):
    """La panza crema, con las placas marcadas por ranuras."""

    belly = claymarch.Ellipsoid(0.48, 0.51, 0.30)
    # Las ranuras, talladas desde el punto de la panza que más sobresale.
    grooves = PlastronGrooves(engrave=(0, 0, 0.30))

    material = cream
    position = (0, 0, 0.08)


# Dónde sale cada brazo del caparazón: hacia el costado, hacia arriba y
# hacia adelante. Lo usan la cavidad y el brazo, para que se muevan juntos.
ARM_AT = (0.40, 0.19, 0.18)
# Lo mismo para cada pierna.
LEG_AT = (0.33, -0.30, 0.18)


class Arm(claymarch.Model):
    """Un brazo: corto y gordito, con dos dedos y un pulgar. Modelado con
    el hombro en el origen, saliendo hacia el costado (x).

    Cada pieza es una cápsula: va de un punto a otro, con un grosor al
    empezar y otro al terminar.
    """

    # Del hombro a la mano. Empieza adentro de la cavidad, así no se ve
    # dónde nace. El segundo punto es la mano: hacia el costado, hacia
    # abajo (negativo) y hacia adelante.
    limb = claymarch.Capsule(
        (-0.08, -0.01, -0.06), (0.26, -0.26, 0.10), 0.145, 0.09
    )
    # La palma: un hueco suave del lado de adelante de la mano, para
    # que no quede redonda. Es una esfera que apenas muerde la mano; va
    # antes que los dedos, así no los corta. El primer número es el
    # tamaño del hueco; con position más cerca de la mano muerde más.
    palm = claymarch.Sphere(
        0.12, position=(0.38, -0.38, 0.2), carve=0.08
    )
    # Dos dedos juntos, que siguen la dirección del brazo y terminan en
    # punta. El primer punto de cada uno está en la mano; el segundo es
    # la punta. Salen del lado del dorso, que es el de atrás: con el
    # tercer número más chico se van más hacia el dorso.
    finger_up = claymarch.Capsule(
        (0.29, -0.27, 0.06), (0.39, -0.32, 0.03), 0.040, 0.012
    )
    finger_down = claymarch.Capsule(
        (0.27, -0.30, 0.06), (0.35, -0.37, 0.03), 0.040, 0.012
    )
    # El pulgar: sale del costado de arriba de la mano, separado de los
    # otros dos. El número del medio de la punta dice cuánto se abre:
    # más alto apunta más hacia arriba, más bajo se acuesta sobre el brazo.
    thumb = claymarch.Capsule(
        (0.30, -0.25, 0.12), (0.40, -0.24, 0.15), 0.040, 0.012
    )

    smooth = 0.03
    material = blue


class Leg(claymarch.Model):
    """Una pierna: corta y gruesa, con un pie de tres dedos en punta.
    Modelada con la cadera en el origen, igual que el brazo.

    El pie tiene que llegar a y = -0.43: ahí está el piso, visto desde
    la cadera. Para alargar la pierna hay que bajar el tobillo, el pie y
    los dedos, y subir el cuerpo lo mismo por 1.4 (su size) en Squirtle.
    """

    # De la cadera al tobillo, flexionada en la rodilla. Es una Curve:
    # va del primer punto (la cadera, adentro de la cavidad) al tercero
    # (el tobillo) doblándose hacia el del medio, que es hacia dónde
    # apunta la rodilla. No pasa por ahí: se queda a mitad de camino.
    # Con el tercer número de la rodilla más alto, se flexiona más hacia
    # adelante; con el primero, hacia el costado. Los dos últimos
    # números son el grosor arriba y abajo.
    thigh = claymarch.Curve(
        (-0.05, 0.03, -0.05), (0.06, -0.13, 0.10), (0.0, -0.32, 0.04),
        0.17, 0.13,
        rotation = (10, 0, 0)
    )
    # El pie: del tobillo hacia adelante, apoyado en el piso.
    foot = claymarch.Capsule(
        (0.0, -0.35, 0.00), (0.02, -0.36, 0.04), 0.08, 0.07
    )
    # Los tres dedos: salen de la punta del pie y terminan en punta.
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


# Dónde está la bola de la punta de la cola: en el medio, a esa altura y
# así de atrás. Las demás medidas de la cola se toman desde ahí.
TAIL_AT = (0, -0.36, -0.85)
# El tamaño de la bola: el ancho (de costado a costado) y el radio visto
# de perfil. No tiene que pasar del piso, que está 0.31 por debajo.
TAIL_WIDTH = 0.22
TAIL_ROUND = 0.30
# La cola sale de la panza en dos tramos, porque entre el borde blanco y
# el piso hay poco lugar. Cada tramo va del primer punto al tercero,
# doblándose hacia el del medio; los dos últimos números son el grosor
# donde empieza y donde termina.
# El cuello: fino, nace adentro de la panza, baja y pasa por debajo del
# borde. No puede ser más grueso que 0.08 o toca el borde o el piso.
NECK = (
    (0, -0.03, 0.93), (0, -0.24, 0.85), (0, -0.2, 0.63), 0.09, 0.10
)
# El tallo: sigue desde donde termina el cuello y engorda hasta la bola.
STEM = ((0, -0.2, 0.63), (0, -0.15, 0.40), (0, -0.15, 0.05), 0.10, 0.15)

# La ranura de la cola, vista de perfil: cada renglón es un punto por el
# que tira, (adelante, arriba), medido desde el centro de la bola. Empieza
# abajo de todo, donde cruza de un costado al otro, sube y engancha hacia
# atrás. Para cambiarle la forma alcanza con tocar esta tabla: mover
# puntos, agregar o sacar renglones.
# La ranura empieza en el primer punto y termina en el último; por los del
# medio no pasa, se queda a mitad de camino.
TAIL_GROOVE = [
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


def tail_side(forward, up):
    """Cuánto sale la cola hacia el costado en ese punto del perfil: lo
    que más salga entre la bola y el tallo. 0 si el punto cae afuera."""
    side = 1 - (forward ** 2 + up ** 2) / TAIL_ROUND ** 2
    widest = TAIL_WIDTH * math.sqrt(side) if side > 0 else 0.0
    start, control, end, thick, thin = STEM
    for i in range(41):
        t = i / 40
        # El punto del tallo a esa altura del recorrido, y su grosor ahí.
        x, y, z = (
            (1 - t) ** 2 * a + 2 * t * (1 - t) * c + t * t * b
            for a, c, b in zip(start, control, end)
        )
        radius = thick + (thin - thick) * t
        side = radius ** 2 - (up - y) ** 2 - (forward - z) ** 2
        if side > 0:
            widest = max(widest, math.sqrt(side))
    return widest


def groove_points():
    """Los puntos de la ranura apoyados sobre la superficie de la cola."""
    return [
        (tail_side(forward, up), up, forward)
        for forward, up in TAIL_GROOVE
    ]


class Tail(claymarch.Model):
    """La cola: sale de la panza por un cuello fino que pasa por debajo
    del borde del caparazón, engorda y termina en una bola. Lo que parece
    un rulo es una ranura cavada a cada costado de la bola.

    Modelada con el centro de la bola en el origen.
    """

    # La bola: un poco más angosta de costado que de perfil.
    ball = claymarch.Ellipsoid(TAIL_WIDTH, TAIL_ROUND, TAIL_ROUND)
    stem = claymarch.Curve(*STEM, join=0.08)
    neck = claymarch.Curve(*NECK, join=0.03)
    # La ranura: un tubo fino apoyado sobre la superficie, que se le
    # resta a la cola. Sigue TAIL_GROOVE; symmetry hace el otro costado y
    # los dos se encuentran abajo, en el medio.
    groove = claymarch.Path(
        groove_points(), GROOVE_TUBE,
        symmetry="x",
        carve=0.02,
    )

    material = blue


# Cuánto se va la cola hacia un costado, en grados: 0 sale derecho hacia
# atrás; positivo va para un lado y negativo para el otro.
TAIL_SWING = 50


class SwungTail(claymarch.Model):
    """La cola, girada hacia un costado desde donde nace.

    El origen de este modelo es el punto de la panza de donde sale el
    cuello: la cola gira alrededor de ahí, así no se despega del
    caparazón. La cola va corrida para que su cuello empiece en ese
    origen.
    """

    tail = Tail(position=tuple(-c for c in NECK[0]))

    position = tuple(a + b for a, b in zip(TAIL_AT, NECK[0]))
    rotation = (0, TAIL_SWING, 0)


class Shell(claymarch.Model):
    """El caparazón: la panza crema adelante, el lomo marrón atrás y un
    borde blanco entre los dos. Modelado con el centro en el origen.
    """

    # La panza, con sus placas.
    plastron = Plastron
    # El lomo, con sus placas.
    back = Back
    # Las cavidades de donde salen los brazos: un hueco redondo en el
    # costado, justo delante de donde el borde se va hacia atrás. Cava la
    # panza y el lomo, pero no el borde, que va después.
    # Los tres primeros números son el tamaño del hueco; position, dónde
    # está: hacia el costado, hacia arriba y hacia adelante.
    arm_holes = claymarch.Ellipsoid(
        0.13, 0.15, 0.13,
        position=ARM_AT,
        symmetry="x",
        carve=0.02,
    )
    # Las de las piernas: lo mismo más abajo, y un poco más grandes.
    leg_holes = claymarch.Ellipsoid(
        0.16, 0.16, 0.14,
        position=LEG_AT,
        symmetry="x",
        carve=0.02,
    )
    # El borde: un anillo blanco que rodea el caparazón, con las ondas de
    # RIM_WAVE.
    rim = RimSide


class Body(claymarch.Model):
    """El cuerpo: el caparazón con los brazos y las piernas saliendo de
    sus cavidades, y la cola atrás."""

    shell = Shell
    arms = Arm(position=ARM_AT, symmetry="x")
    legs = Leg(position=LEG_AT, symmetry="x")
    tail = SwungTail


class Squirtle(claymarch.Model):
    # size agranda el cuerpo entero respecto de la cabeza.
    body = Body(size=1.4, position=(0, 1.02, 0))
    # La cabeza apoya directo sobre el caparazón, sin cuello.
    head = Head(position=(0, 1.94, 0.35))


class SquirtleScene(claymarch.Scene):
    squirtle = Squirtle
    camera = claymarch.Camera(
        target=(0, 1.25, 0), distance=4.8, yaw=30, pitch=4
    )
    light = claymarch.Light(direction=(-0.5, 0.8, 0.6))
