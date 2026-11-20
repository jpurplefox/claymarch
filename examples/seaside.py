"""Un lugar para Squirtle: una roca en medio del mar, con un faro atrás.

Para verlo:   python -m claymarch examples/seaside.py --port 8775

Squirtle se importa tal cual: el modelo, de squirtle.py, y sus movimientos
de siempre, de squirtle_alive.py. Lo que cambies allá se ve acá.
La piel mojada, las gotas que tiene encima y el chorro de agua que tira por
la boca son de esta escena.
Ejes: y es arriba, z es el frente (hacia donde mira), x es el costado.
"""
import math

import claymarch
from squirtle import (
    BLUE, BROWN, CREAM, WHITE, Back, Body, Bone, Head, Horn, Plastron, Plate,
    Shell, Skin, Skull, blue, brown, cream, white,
)
from squirtle_alive import LOOP, AliveSquirtle, look


# La altura del mar en calma. Squirtle está parado en y = 0, sobre una roca
# que sobresale del agua.
SEA_LEVEL = -0.38
# Cuánto suben las olas por encima de esa altura, como mucho.
WAVE_TOP = 0.26
# El radio de la roca de Squirtle: alrededor de ella rompe la espuma.
PERCH_RADIUS = 1.7

# Las rocas sueltas que asoman del mar: dónde está cada una (hacia el
# costado y hacia el frente), qué tan grande es y cuánto está girada, para
# que no se vean todas iguales. Están de a grupos, como en una costa: una
# grande con otra chica al lado.
ROCKS = [
    (-3.6, -2.2, 1.3, 40),  # a la izquierda, la grande del grupo
    (-2.4, -1.1, 0.6, 150),  # su compañera chica
    (2.7, 1.3, 0.45, 260),  # una punta cerca de Squirtle
    (5.0, -8.5, 1.5, 200),  # atrás a la derecha, la grande
    (6.5, -7.4, 0.7, 20),  # y su compañera
]
# Dónde está el faro y qué tan grande es.
LIGHTHOUSE_AT = (-7.0, -18.0)
LIGHTHOUSE_SIZE = 1.3
# Dónde queda la luz del faro: 6.57 por encima de su base.
LAMP_AT = (
    LIGHTHOUSE_AT[0],
    SEA_LEVEL + 6.57 * LIGHTHOUSE_SIZE,
    LIGHTHOUSE_AT[1],
)
# De dónde viene la luz del sol: (costado, altura, frente).
SUN_FROM = (-0.15, 0.15, -0.97)
# Dónde rompe la espuma: alrededor de cada roca, a esa distancia de su
# centro. Cada renglón es (costado, frente, radio).
SHORES = [
    (0.0, 0.0, PERCH_RADIUS),
    *[(x, z, 0.55 * size) for x, z, size, turn in ROCKS],
    (*LIGHTHOUSE_AT, 2.6 * LIGHTHOUSE_SIZE),
]


def crests(along, height):
    """Un tren de olas: la cresta es más angosta que el valle, como en el
    mar de verdad, pero redondeada, sin filo. along dice en qué parte de
    la ola está cada punto; height, qué tan altas son.

    El último número es qué tan angosta es la cresta: 1 la deja igual de
    ancha que el valle (una onda pareja); más alto, más angosta.
    """
    return height * (0.5 + 0.5 * claymarch.sin(along)) ** 1.7


def waves(p):
    """La altura del agua en cada punto, por encima de SEA_LEVEL. Son dos
    trenes de olas que se cruzan y un vaivén más ancho y desparejo.

    Para que no se vea un dibujo repetido, cada zona del mar va un poco
    adelantada o atrasada respecto de las de al lado, y con las olas más
    altas o más bajas.
    """
    t = claymarch.T
    # Dos ruidos de manchas grandes, que cambian despacio de un lugar a
    # otro: uno corre las olas (las tuerce) y el otro les cambia el alto.
    # El número que multiplica a p.x y p.z es el tamaño de las manchas:
    # más chico, manchas más grandes.
    # No cambian con el tiempo: así las olas vuelven a quedar igual al
    # terminar el ciclo (ver LOOP en squirtle_alive.py).
    shift = claymarch.noise(claymarch.vec(p.x * 0.13, 0.0, p.z * 0.13))
    swell = 0.5 + claymarch.noise(
        claymarch.vec(p.x * 0.21 + 7.0, 0.0, p.z * 0.21)
    )
    # Los números que multiplican a p.x y p.z son hacia dónde va cada tren
    # y qué tan juntas están las olas; el que multiplica a t, la velocidad
    # (entera o terminada en .5, para que cierre el ciclo).
    # El que multiplica a shift es cuánto se tuercen: 0 las deja derechas.
    first = crests(
        p.x * 1.1 + p.z * 1.7 + t * 2.0 + shift * 9.0, 0.08 * swell
    )
    second = crests(
        p.z * 2.3 - p.x * 1.5 + t * 2.5 - shift * 12.0, 0.05 * swell
    )
    drift = 0.06 * claymarch.noise(
        claymarch.vec(p.x * 0.4 + t * 0.25, 0.0, p.z * 0.4)
    )
    return first + second + drift


class Sea(claymarch.Material):
    """El mar: oscuro en el fondo de las olas, turquesa hacia las
    crestas, con espuma donde rompen y alrededor de las rocas. Refleja el
    cielo, sobre todo hacia el horizonte."""

    specular = 1.0
    shininess = 70.0
    reflection = 0.75

    def foam(self, p, t):
        # Cuánto sobresale el agua en este punto: 0 en el fondo de la
        # ola, 1 en la cresta más alta.
        rise = (p.y - SEA_LEVEL) / WAVE_TOP
        # Manchas que se mueven, para que la espuma no sea pareja.
        patchy = claymarch.noise(
            claymarch.vec(p.x * 3.0, t * 0.6, p.z * 3.0 + t * 0.4)
        )
        # En las crestas: solo en lo más alto.
        on_crests = claymarch.smoothstep(0.72, 0.92, rise + 0.25 * patchy)
        # Alrededor de cada roca: un anillo que avanza y retrocede. Cada
        # una va a destiempo de las demás (el número que se suma a t).
        lapping = 0.0
        for i, (x, z, radius) in enumerate(SHORES):
            away = claymarch.length(claymarch.vec(p.x - x, 0.0, p.z - z))
            edge = radius + 0.25 + 0.15 * claymarch.sin(t * 1.5 + i * 1.7)
            ring = 1 - claymarch.smoothstep(
                edge - 0.35, edge, away - 0.4 * patchy
            )
            lapping = claymarch.maximum(lapping, ring)
        # La espuma de las rocas es rala: deja ver el agua entre medio.
        lapping = lapping * (0.35 + 0.65 * patchy)
        return claymarch.clamp(on_crests + lapping, 0.0, 1.0)

    def color(self, p, t):
        rise = claymarch.clamp((p.y - SEA_LEVEL) / WAVE_TOP, 0.0, 1.0)
        water = claymarch.mix((0.02, 0.14, 0.32), (0.07, 0.42, 0.56), rise)
        # La espuma, apenas tibia por la luz del atardecer.
        return claymarch.mix(water, (1.00, 0.93, 0.86), self.foam(p, t))

    def bump(self, p, t):
        # Rizado fino sobre las olas: es lo que hace brillar el sol.
        wide = 0.015 * claymarch.noise(p * 1.6 + t * 0.6)
        fine = 0.010 * claymarch.noise(p * 5.0 - t * 1.3)
        return wide + fine


class Stone(claymarch.Material):
    """La piedra de la costa: gris parda, en capas inclinadas, áspera.
    Cerca del agua está mojada (más oscura y brillante) y tiene verdín y
    algunos moluscos; hacia arriba se va secando.

    p se mide desde el centro de cada roca, así que cada una tiene que
    decir a qué altura le queda el mar: es waterline.
    """

    waterline = 0.0
    shininess = 40.0

    def wet(self, p):
        # 1 donde la roca está mojada, 0 donde está seca. Los dos números
        # son desde dónde y hasta dónde llega la humedad por encima del
        # mar; el borde es desparejo.
        damp = claymarch.noise(p * 3.0)
        height = p.y - self.waterline + 0.15 * damp
        return 1 - claymarch.smoothstep(0.10, 0.55, height)

    def layers(self, p):
        # Las capas de la piedra: franjas inclinadas y un poco torcidas.
        # El último número es qué tan juntas están.
        warp = 0.35 * claymarch.noise(p * 1.3)
        along = p.y + 0.45 * p.x + 0.25 * p.z + warp
        return 0.5 + 0.5 * claymarch.sin(along * 22.0)

    def color(self, p):
        tone = 0.6 * claymarch.noise(p * 2.5) + 0.4 * self.layers(p)
        rock = claymarch.mix((0.36, 0.34, 0.33), (0.62, 0.57, 0.50), tone)
        wet = self.wet(p)
        # Mojada es más oscura.
        rock = rock * (1 - 0.45 * wet)
        # Verdín, a manchones, solo en la parte mojada.
        patches = claymarch.noise(p * 5.0)
        algae = wet * claymarch.smoothstep(0.45, 0.70, patches)
        rock = claymarch.mix(rock, (0.16, 0.24, 0.14), 0.7 * algae)
        # Moluscos: puntitos claros, también abajo.
        specks = claymarch.smoothstep(0.80, 0.84, claymarch.noise(p * 45.0))
        return claymarch.mix(rock, (0.74, 0.72, 0.66), 0.8 * wet * specks)

    def specular(self, p):
        # Seca casi no brilla; mojada, sí.
        return 0.06 + 0.55 * self.wet(p)

    def bump(self, p):
        # Áspera, con las capas apenas marcadas en relieve.
        return 0.010 * claymarch.fbm(p * 9.0) + 0.004 * self.layers(p)


class PerchStone(Stone):
    """La piedra de la roca de Squirtle: su parte de arriba está en y = 0,
    así que el mar le queda por debajo."""

    waterline = SEA_LEVEL


class IsletStone(Stone):
    """La piedra del islote del faro: su centro está 0.7 bajo el mar."""

    waterline = 0.7


def cut(tilt, heading, depth):
    """Una caja enorme que sirve para cortarle una cara plana a una roca:
    todo lo que queda fuera de la caja se pierde.

    tilt es cuánto se inclina esa cara (0 mira hacia arriba, 90 hacia el
    costado), heading hacia qué lado mira, y depth a qué distancia del
    centro de la roca pasa: más chico corta más.
    """
    a, b = math.radians(tilt), math.radians(heading)
    # Hacia dónde mira la cara.
    facing = (
        -math.sin(b) * math.sin(a),
        math.cos(a),
        math.cos(b) * math.sin(a),
    )
    return claymarch.Box(
        4, 4, 4,
        rotation=(tilt, heading, 0),
        position=tuple(c * (depth - 2) for c in facing),
    )


def faceted(shape, cuts, soft=0.04):
    """Una forma con varias caras planas cortadas. soft es qué tan
    gastadas quedan las aristas: 0 las deja filosas."""
    for tilt, heading, depth in cuts:
        shape = shape.intersect(cut(tilt, heading, depth), smooth=soft)
    return shape


class Boulder(claymarch.Model):
    """Una roca suelta: un bulto al que se le cortaron varias caras
    planas, como las rocas partidas de la costa. Modelada con el centro
    en el origen; para que asome del agua hay que ubicarla a la altura de
    SEA_LEVEL."""

    parts = [
        faceted(
            claymarch.Ellipsoid(0.9, 0.65, 0.8),
            # Cada renglón es una cara: inclinación, hacia dónde mira y
            # a qué distancia del centro corta.
            [
                (38, 20, 0.40),  # la de arriba, inclinada
                (28, 205, 0.46),  # otra arriba, hacia el otro lado
                (58, 140, 0.50),
                (72, 250, 0.52),
                (65, 75, 0.60),
                (80, 330, 0.62),
            ],
        )
    ]

    material = Stone
    # La superficie despareja.
    ripple = claymarch.Ripple(height=0.10, size=0.30)


class Perch(claymarch.Model):
    """La roca donde está parado Squirtle: chata arriba, con la parte de
    arriba en y = 0, bultos alrededor y los costados cortados en caras."""

    parts = [
        faceted(
            claymarch.union(
                # La base: un cilindro bajo de bordes redondeados. Los
                # números son el radio, el alto y cuánto se redondea.
                claymarch.Cylinder(
                    1.5, 1.0, rounding=0.35, position=(0, -0.5, 0)
                ),
                # Los bultos de alrededor.
                claymarch.Ellipsoid(
                    0.9, 0.5, 0.8, position=(-0.9, -0.45, -1.1)
                ),
                claymarch.Ellipsoid(
                    0.8, 0.45, 0.9, position=(1.3, -0.50, 0.3)
                ),
                claymarch.Ellipsoid(
                    0.7, 0.35, 0.6, position=(-0.8, -0.50, 1.2)
                ),
                smooth=0.30,
            ),
            [
                (0, 0, 0.0),  # la de arriba: chata, para apoyar los pies
                (68, 30, 1.45),
                (75, 120, 1.55),
                (64, 200, 1.60),
                (72, 285, 1.45),
                (60, 340, 1.65),
            ],
            soft=0.06,
        )
    ]

    material = PerchStone
    ripple = claymarch.Ripple(height=0.05, size=0.35)


class Islet(claymarch.Model):
    """El islote del faro: una roca grande y baja, cortada en caras.
    Modelado con el centro en el origen."""

    parts = [
        faceted(
            claymarch.Ellipsoid(3.2, 1.3, 2.6),
            [
                (32, 10, 1.08),
                (40, 230, 1.15),
                (50, 120, 1.55),
                (62, 180, 2.10),
                (70, 300, 2.55),
                (75, 60, 2.75),
            ],
            soft=0.10,
        )
    ]

    material = IsletStone
    ripple = claymarch.Ripple(height=0.20, size=0.80)


class Tower(claymarch.Material):
    """La pared del faro: revoque pintado a franjas rojas y blancas,
    gastado por el mar. Tiene chorreaduras, verdín cerca de la base y las
    hiladas de piedra marcadas debajo de la pintura.

    p se mide desde el centro de la torre: la base está en y = -3.
    """

    specular = 0.08

    def color(self, p):
        # El segundo número es el alto de cada franja.
        band = claymarch.stripes(p.y, 1.0)
        paint = claymarch.mix((0.93, 0.92, 0.87), (0.78, 0.17, 0.14), band)
        # Chorreaduras: manchas estiradas a lo alto que oscurecen la
        # pintura. El último número es cuánto oscurecen.
        streaks = claymarch.noise(
            claymarch.vec(p.x * 5.0, p.y * 0.6, p.z * 5.0)
        )
        paint = paint * (1 - 0.30 * claymarch.smoothstep(0.45, 0.85, streaks))
        # Pintura descascarada: manchones donde asoma el revoque gris.
        flakes = claymarch.smoothstep(0.68, 0.74, claymarch.fbm(p * 2.2))
        paint = claymarch.mix(paint, (0.62, 0.60, 0.56), 0.8 * flakes)
        # Verdín: sube desde la base hasta poco más de un metro, desparejo.
        damp = claymarch.noise(p * 3.0)
        moss = 1 - claymarch.smoothstep(-3.0, -1.6, p.y - 0.8 * damp)
        return claymarch.mix(paint, (0.30, 0.36, 0.26), 0.75 * moss)

    def bump(self, p):
        # Las hiladas: una ranura horizontal cada 0.4 de alto.
        course = abs(claymarch.fract(p.y * 2.5) - 0.5)
        joints = 0.006 * claymarch.smoothstep(0.44, 0.5, course)
        # Y el revoque, que es áspero.
        return joints + 0.004 * claymarch.fbm(p * 14.0)


class Iron(claymarch.Material):
    """El hierro del balcón: oscuro, con óxido."""

    specular = 0.3

    def color(self, p):
        rust = claymarch.smoothstep(0.5, 0.8, claymarch.noise(p * 9.0))
        return claymarch.mix((0.18, 0.19, 0.21), (0.42, 0.22, 0.12), rust)

    def bump(self, p):
        return 0.003 * claymarch.fbm(p * 30.0)


class RoofTiles(claymarch.Material):
    """El techo: chapa roja, más gastada hacia abajo."""

    specular = 0.2

    def color(self, p):
        worn = claymarch.noise(p * 6.0)
        return claymarch.mix((0.72, 0.15, 0.12), (0.50, 0.14, 0.12), worn)

    def bump(self, p):
        return 0.003 * claymarch.fbm(p * 20.0)


class Lamp(claymarch.Material):
    """La luz del faro: amarilla, con un lado mucho más brillante que va
    dando la vuelta, como la lámpara que gira adentro."""

    color = (1.0, 0.92, 0.55)

    def glow(self, p, t):
        # Hacia dónde apunta la lámpara en este momento. El número que
        # multiplica a t es la velocidad a la que gira.
        turn = t * 1.0
        facing = p.x * claymarch.sin(turn) + p.z * claymarch.cos(turn)
        # 0.45 es el radio de la linterna: facing / 0.45 vale 1 justo
        # donde apunta la lámpara y -1 del lado opuesto.
        beam = claymarch.smoothstep(0.55, 1.0, facing / 0.45)
        # El primer número es el brillo de siempre; el otro, cuánto más
        # brilla el lado iluminado.
        return 0.35 + 2.5 * beam


def lamp_flare(t=claymarch.T):
    """Qué tan fuerte es el resplandor de la linterna en cada momento:
    tenue casi siempre, con un destello cuando el lado brillante de la
    lámpara pasa mirando hacia la cámara."""
    # El 0.4 es hacia dónde queda la cámara vista desde el faro, y el 1.0
    # la velocidad a la que gira la lámpara: la misma que en Lamp.
    toward = claymarch.maximum(claymarch.cos(t * 1.0 - 0.4), 0.0)
    # El primer número es el brillo de siempre; el otro, el del destello.
    return 0.18 + 0.75 * toward ** 6


def around(count, radius):
    """count puntos (x, z) repartidos en una vuelta, a esa distancia del
    centro."""
    turns = [math.radians(360 * i / count) for i in range(count)]
    return [(radius * math.sin(a), radius * math.cos(a)) for a in turns]


def bars(count, radius, low, high, thick):
    """Barrotes verticales repartidos en una vuelta, de low a high."""
    return claymarch.union(*[
        claymarch.Capsule((x, low, z), (x, high, z), thick)
        for x, z in around(count, radius)
    ])


class Gallery(claymarch.Model):
    """El balcón que rodea la linterna: un piso sostenido por una
    ménsula, con baranda. Modelado con el piso en el origen."""

    WIDE = 0.95
    RAIL = 0.34  # el alto de la baranda

    bracket = claymarch.CutCone(0.60, 0.90, 0.28, position=(0, -0.19, 0))
    deck = claymarch.Cylinder(WIDE, 0.10, position=(0, -0.05, 0))
    handrail = claymarch.Torus(WIDE - 0.05, 0.022, position=(0, RAIL, 0))
    midrail = claymarch.Torus(WIDE - 0.05, 0.012, position=(0, RAIL / 2, 0))
    posts = bars(12, WIDE - 0.05, 0, RAIL, 0.016)

    material = Iron


class Cupola(claymarch.Model):
    """El techo de la linterna: media esfera achatada."""

    whole = claymarch.Ellipsoid(0.54, 0.42, 0.54)
    upper = claymarch.Box(2, 1, 2, position=(0, 0.5, 0), clip=True)

    material = RoofTiles


class Lantern(claymarch.Model):
    """El cuarto de vidrio de arriba, con luz propia: sobre un zócalo,
    entre parantes y bajo una cúpula. Modelada con el piso en el
    origen."""

    GLASS = 0.45  # el radio del vidrio: el mismo que usa Lamp

    plinth = claymarch.Cylinder(0.50, 0.24, position=(0, 0.12, 0))
    glass = claymarch.Cylinder(
        GLASS, 0.66, position=(0, 0.57, 0), material=Lamp
    )
    frames = bars(8, GLASS + 0.01, 0.24, 0.90, 0.022)
    eave = claymarch.Cylinder(0.57, 0.05, position=(0, 0.92, 0))
    cupola = Cupola(position=(0, 0.94, 0))
    ball = claymarch.Sphere(0.07, position=(0, 1.36, 0))
    spike = claymarch.Capsule((0, 1.36, 0), (0, 1.72, 0), 0.022, 0.006)

    material = Iron


class DarkGlass(claymarch.Material):
    """El vidrio de las ventanas, visto de afuera: oscuro, con reflejo."""

    color = (0.05, 0.07, 0.10)
    specular = 0.8
    reflection = 0.4


class Planks(claymarch.Material):
    """La madera de la puerta: tablas verticales, oscuras."""

    specular = 0.1

    def color(self, p):
        plank = claymarch.stripes(p.x, 0.07)
        return claymarch.mix((0.20, 0.12, 0.07), (0.27, 0.17, 0.10), plank)


class Arch(claymarch.Model):
    """Una forma de puerta o de ventana: un rectángulo con medio círculo
    arriba. De frente, con el centro del rectángulo en el origen."""

    wide = 0.2
    tall = 0.3
    deep = 0.5

    def parts(self):
        return [
            claymarch.Box(self.wide, self.tall, self.deep),
            claymarch.Cylinder(
                self.wide / 2, self.deep,
                rotation=(90, 0, 0),
                position=(0, self.tall / 2, 0),
            ),
        ]


class Masonry(claymarch.Material):
    """La piedra labrada de la escalera: gris, despareja."""

    specular = 0.1

    def color(self, p):
        tone = claymarch.noise(p * 6.0)
        return claymarch.mix((0.42, 0.40, 0.38), (0.62, 0.59, 0.54), tone)

    def bump(self, p):
        return 0.004 * claymarch.fbm(p * 14.0)


class Entrance(claymarch.Model):
    """Por dónde se llega a la puerta: un rellano y una escalera que baja
    hasta la piedra. De frente, con el umbral de la puerta en el
    origen."""

    STEPS = 3
    RISE = 0.13  # cuánto baja cada escalón
    RUN = 0.20  # cuánto avanza

    def parts(self):
        landing = claymarch.Box(
            0.70, 0.90, 0.50, position=(0, -0.45, 0.25), material=Masonry
        )
        # Cada escalón es un bloque que llega hasta abajo.
        steps = [
            claymarch.Box(
                0.56, 1.0, self.RUN,
                position=(
                    0,
                    -0.5 - self.RISE * (i + 1),
                    0.50 + self.RUN * (i + 0.5),
                ),
                material=Masonry,
            )
            for i in range(self.STEPS)
        ]
        return [landing, *steps]


class Shaft(claymarch.Model):
    """La torre del faro, con la puerta, las ventanas y la escalera que
    llega a la puerta. Modelada con la base en el origen."""

    BOTTOM = 0.9  # el radio abajo
    NECK = 0.6  # el radio arriba
    TOP = 6.0  # el alto
    SUNK = 0.10  # cuánto se hunden la puerta y los vidrios en la pared
    # Cada renglón es una abertura: a qué altura está su centro, hacia
    # dónde mira (0 es adelante), el ancho, el alto y de qué es.
    OPENINGS = [
        (1.00, 20, 0.36, 0.70, Planks),  # la puerta: va primera
        (2.45, 20, 0.16, 0.26, DarkGlass),
        (3.65, 20, 0.16, 0.26, DarkGlass),
        (4.85, 20, 0.16, 0.26, DarkGlass),
    ]

    def on_wall(self, height, heading, sunk=0.0):
        """Dónde poner algo sobre la pared, y cómo girarlo para que mire
        hacia afuera."""
        slope = (self.BOTTOM - self.NECK) / self.TOP
        radius = self.BOTTOM - slope * height - sunk
        turn = math.radians(heading)
        return {
            "position": (
                radius * math.sin(turn), height, radius * math.cos(turn)
            ),
            "rotation": (0, -heading, 0),
        }

    def parts(self):
        wall = claymarch.CutCone(
            self.BOTTOM, self.NECK, self.TOP,
            position=(0, self.TOP / 2, 0),
            material=Tower,
        )
        holes = [
            Arch(
                wide=wide, tall=tall, carve=0.01,
                **self.on_wall(height, heading),
            )
            for height, heading, wide, tall, fill in self.OPENINGS
        ]
        # Lo que tapa cada hueco, un poco hundido: la puerta y los
        # vidrios.
        fills = [
            Arch(
                wide=wide + 0.04, tall=tall + 0.04, deep=0.04,
                material=fill,
                **self.on_wall(height, heading, self.SUNK),
            )
            for height, heading, wide, tall, fill in self.OPENINGS
        ]
        height, heading, wide, tall, fill = self.OPENINGS[0]
        entrance = Entrance(**self.on_wall(height - tall / 2, heading))
        return [wall, *holes, *fills, entrance]


class Causeway(claymarch.Model):
    """La escollera: una lengua ancha de piedra baja que arranca frente
    a la puerta del faro, dobla y se pierde hacia un costado, fuera de
    cuadro. Por ahí se llega al faro. Modelada con el islote en el
    origen y el mar en y = 0."""

    HEADING = -62  # hacia dónde se va: a la izquierda de la cámara
    WIDE = 2.0
    SUNK = 0.9  # cuánto queda su centro bajo el mar
    TOP = 0.40  # la altura del camino, sobre el mar
    FOAM = 0.6  # qué tan ancha es la franja de espuma a su alrededor
    # Después de doblar, cada renglón: qué tan lejos sigue y cuánto se
    # corre hacia un costado.
    COURSE = [
        (3.5, 0.6),
        (7.5, -0.5),
        (11.5, 0.8),
        (15.5, 0.1),
        (19.5, -0.6),
        (23.5, 0.3),
        (27.5, 0.0),
    ]

    @classmethod
    def points(cls):
        """Por dónde pasa, como puntos (costado, frente)."""
        door = math.radians(Shaft.OPENINGS[0][1])
        turn = math.radians(cls.HEADING)
        # Sale derecho desde la puerta y recién después dobla.
        start = [
            (math.sin(door) * far, math.cos(door) * far)
            for far in (1.0, 3.0)
        ]
        bend_x, bend_z = start[-1]
        return start + [
            (
                bend_x + math.sin(turn) * far + math.cos(turn) * side,
                bend_z + math.cos(turn) * far - math.sin(turn) * side,
            )
            for far, side in cls.COURSE
        ]

    def parts(self):
        return [
            claymarch.Path(
                [(x, -self.SUNK, z) for x, z in self.points()],
                self.WIDE,
                ripple=claymarch.Ripple(height=0.30, size=0.90),
            ),
            # Chata arriba, para caminar.
            claymarch.Box(
                80, 4, 80, position=(0, self.TOP - 2, 0), clip=0.08
            ),
        ]

    material = Stone

    @classmethod
    def shores(cls):
        """Dónde rompe la espuma a lo largo de la escollera, ya en la
        escena: un círculo en cada punto y otro entre cada dos."""
        points = cls.points()
        between = [
            ((a + c) / 2, (b + d) / 2)
            for (a, b), (c, d) in zip(points, points[1:])
        ]
        # El ancho de la escollera a la altura del agua.
        reach = math.sqrt(cls.WIDE ** 2 - cls.SUNK ** 2)
        return [
            (
                LIGHTHOUSE_AT[0] + LIGHTHOUSE_SIZE * x,
                LIGHTHOUSE_AT[1] + LIGHTHOUSE_SIZE * z,
                LIGHTHOUSE_SIZE * reach + cls.FOAM,
            )
            for x, z in points + between
        ]


SHORES += Causeway.shores()


class Lighthouse(claymarch.Model):
    """El faro, sobre un islote de piedra. Modelado con la base de la
    torre en el origen."""

    islet = Islet(position=(0, -0.7, 0))
    causeway = Causeway
    shaft = Shaft
    gallery = Gallery(position=(0, Shaft.TOP, 0))
    lantern = Lantern(position=(0, Shaft.TOP, 0))


# Qué tan mojado está Squirtle: 0 es seco; más alto, el color se oscurece
# más.
WET = 1.0


def soaked(color):
    """El mismo color, mojado: más oscuro y más intenso."""
    return tuple(c ** (1 + 0.45 * WET) for c in color)


class Wet:
    """Lo que cambia en una piel cuando está mojada: los brillos son chicos
    y fuertes, y refleja un poco el cielo. Cada piel de más abajo es la de
    squirtle.py con esto encima y su color oscurecido."""

    specular = 0.9  # qué tan fuerte es el brillo
    shininess = 70.0  # más alto, brillo más chico y nítido
    reflection = 0.25  # cuánto refleja el cielo


class WetSkin(Wet, Skin):
    base = soaked(BLUE)


class WetPlate(Wet, Plate):
    base = soaked(CREAM)
    specular = 0.7


class WetHorn(Wet, Horn):
    base = soaked(BROWN)
    specular = 0.8
    shininess = 90.0
    reflection = 0.5


class WetBone(Wet, Bone):
    base = soaked(WHITE)


class Droplet(claymarch.Material):
    """Una gota de agua apoyada en el cuerpo: casi transparente, deja ver
    la piel de abajo, con un brillo chico y muy fuerte."""

    color = (0.80, 0.93, 1.0)
    opacity = 0.08  # 0 es invisible y 1 es sólido
    specular = 2.5
    shininess = 260.0
    reflection = 0.6


def outward(heading, height):
    """Hacia dónde queda un punto de un elipsoide, visto desde su centro.

    heading es hacia dónde, en grados alrededor: 0 es el frente, 90 un
    costado, 180 atrás. height es qué tan arriba: 0 es el medio, 90
    arriba de todo, negativo hacia abajo. height puede ser una fórmula
    (algo que cambia con el tiempo); heading, solo un número.
    """
    around, up = math.radians(heading), claymarch.radians(height)
    flat = claymarch.cos(up)
    return (
        flat * math.sin(around),
        claymarch.sin(up),
        flat * math.cos(around),
    )


def on_surface(radii, heading, height, centre=(0, 0, 0)):
    """Un punto sobre un elipsoide de ese tamaño (radii) y ese centro,
    hacia donde dice outward."""
    out = outward(heading, height)
    return tuple(
        round(c + r * o, 4) for c, r, o in zip(centre, radii, out)
    )


def bead(radii, heading, height, size, centre=(0, 0, 0), run=30):
    """Una gota sobre un elipsoide (ver on_surface): una bolita medio
    hundida en la superficie, así asoma solo un casquete.

    No se queda quieta: aparece chiquita, crece, se queda un rato,
    resbala hacia abajo cada vez más rápido y se pierde; después vuelve a
    aparecer en su lugar. run es cuánto baja, en grados.
    """
    # Cada gota va a destiempo de las demás. Cuánto se atrasa sale de su
    # lugar, así que no hay que escribirlo.
    late = (heading * 0.137 + height * 0.291) % 1

    def along(t):
        # De 0 a 1 una vez por ciclo.
        return claymarch.fract(t / LOOP + late)

    def slide(t):
        # La primera parte del tiempo no se mueve (0); después resbala.
        k = claymarch.maximum(along(t) - 0.45, 0.0) / 0.55
        return k * k

    def position(t):
        out = outward(heading, height - run * slide(t))
        keep = 1 - 0.45 * size / min(radii)
        return tuple(c + r * keep * o for c, r, o in zip(centre, radii, out))

    def scale(t):
        k = along(t)
        grown = claymarch.smoothstep(0.0, 0.30, k)
        gone = claymarch.smoothstep(0.85, 1.0, k)
        return grown * (1 - gone)

    return claymarch.Sphere(size, size=scale, position=position)


class Drip(claymarch.Model):
    """La gota que cae de un costado de la cara: se junta abajo del
    cachete, se suelta, cae y, después de un rato, vuelve a empezar."""

    # De dónde cuelga: hacia dónde (90 es el costado, negativo el otro
    # lado) y qué tan abajo del cachete.
    HANGS_AT = on_surface(Skull.CHEEKS, 72, -48, Skull.CHEEKS_AT)
    EVERY = 2  # cuántas gotas caen por ciclo (un número entero)

    def along(self, t):
        # De 0 a 1 una y otra vez.
        return claymarch.fract(t * self.EVERY / LOOP)

    def fall(self, t):
        # Casi todo el tiempo no cae (0); al final se suelta.
        return claymarch.maximum(self.along(t) - 0.8, 0.0) * 5

    STRETCH = 0.04  # cuánto se estira al caer
    WOBBLE = 0.005  # cuánto se bambolea hacia los costados

    def drop(self, t):
        # Dónde está la gota: colgada en su lugar y, al soltarse, cada
        # vez más abajo.
        x, y, z = self.HANGS_AT
        fall = self.fall(t)
        return (x, y - 0.9 * fall * fall, z)

    def trail(self, t):
        # La parte de arriba de la gota: quieta está escondida adentro;
        # al caer se queda atrás, y la gota se estira. También se mueve
        # un poco de lado a lado.
        x, y, z = self.drop(t)
        pull = claymarch.smoothstep(0.0, 0.35, self.fall(t))
        sideways = self.WOBBLE * pull * claymarch.sin(t * 24.0)
        return (x + sideways, y + self.STRETCH * pull, z)

    def scale(self, t):
        # No está, crece mientras se junta y se pierde al final de la
        # caída.
        grown = claymarch.smoothstep(0.40, 0.80, self.along(t))
        gone = claymarch.smoothstep(0.75, 1.0, self.fall(t))
        return grown * (1 - gone)

    def parts(self):
        return [
            claymarch.Sphere(0.032, size=self.scale, position=self.drop),
            claymarch.Sphere(0.020, size=self.scale, position=self.trail),
        ]

    smooth = 0.04  # funde las dos partes en una sola gota
    material = Droplet
    bounds = ((HANGS_AT[0], HANGS_AT[1] - 0.45, HANGS_AT[2]), 0.55)


class HeadDrops(claymarch.Model):
    """Las gotas de la cabeza. Cada renglón es una: hacia dónde está (0
    es el frente, 90 un costado), qué tan arriba (0 es el medio de la
    cabeza) y el tamaño. Se pueden mover, agregar o sacar renglones."""

    parts = [
        # En la frente, la coronilla y los costados.
        bead(Skull.DOME, -8, 40, 0.042),
        bead(Skull.DOME, 22, 54, 0.031),
        bead(Skull.DOME, -36, 50, 0.036),
        bead(Skull.DOME, 4, 64, 0.025),
        bead(Skull.DOME, 0, 24, 0.028),
        bead(Skull.DOME, 64, 30, 0.039),
        bead(Skull.DOME, -66, 20, 0.031),
        bead(Skull.DOME, -84, 42, 0.028),
        bead(Skull.DOME, -50, 30, 0.036),
        bead(Skull.DOME, 38, 46, 0.031),
        bead(Skull.DOME, 88, 8, 0.034),
        # En los cachetes.
        bead(Skull.CHEEKS, 58, -22, 0.036, Skull.CHEEKS_AT),
        bead(Skull.CHEEKS, -44, -34, 0.031, Skull.CHEEKS_AT),
        bead(Skull.CHEEKS, -70, -30, 0.031, Skull.CHEEKS_AT),
    ]

    material = Droplet
    # Como las gotas se mueven, la esfera que las contiene va a mano:
    # toda la cabeza.
    bounds = 0.72


class ShellDrops(claymarch.Model):
    """Las gotas del caparazón, renglón por renglón como en la cabeza:
    180 es el medio del lomo."""

    parts = [
        # En la panza.
        bead(Plastron.BELLY, 14, 34, 0.020, Plastron.position),
        bead(Plastron.BELLY, -24, 6, 0.018, Plastron.position),
        bead(Plastron.BELLY, 28, -22, 0.016, Plastron.position),
        bead(Plastron.BELLY, -8, -38, 0.020, Plastron.position),
        bead(Plastron.BELLY, -30, 24, 0.020, Plastron.position),
        bead(Plastron.BELLY, 6, -6, 0.017, Plastron.position),
        # En el lomo.
        bead(Back.DOME, 170, 42, 0.022, Back.position),
        bead(Back.DOME, 205, 20, 0.018, Back.position),
        bead(Back.DOME, 150, -8, 0.020, Back.position),
        bead(Back.DOME, 188, -30, 0.016, Back.position),
        bead(Back.DOME, 196, 44, 0.022, Back.position),
        bead(Back.DOME, 160, 14, 0.020, Back.position),
        bead(Back.DOME, 215, -14, 0.018, Back.position),
    ]

    material = Droplet
    bounds = ((0, 0, -0.05), 0.62)  # todo el caparazón


class WetHead(Head):
    """La cabeza de Squirtle, con gotas encima y una que cae del cachete."""

    drops = HeadDrops
    drip = Drip


class WetShell(Shell):
    """El caparazón, con gotas en la panza y en el lomo."""

    drops = ShellDrops


class WetBody(Body):
    shell = WetShell


# Hacia dónde y qué tan rápido corre el agua del chorro: hacia adelante
# y hacia abajo. Lo usan el dibujo del agua y las ondas de la superficie.
JET_FLOW = (0, -1.5, 2.5)


def flowing(p, t, grain):
    """Ruido que viaja con el agua. grain es qué tan fino es el dibujo."""
    return claymarch.noise(
        claymarch.vec(
            p.x * grain,
            (p.y - JET_FLOW[1] * t) * grain,
            (p.z - JET_FLOW[2] * t) * grain,
        )
    )


class Water(claymarch.Material):
    """El agua: celeste, brillante y transparente, con vetas apenas más
    claras y más densas que corren con el chorro."""

    specular = 1.0
    shininess = 90.0

    def foam(self, p, t):
        # Entre 0 (agua limpia) y 1 (veta). Los dos primeros números
        # dicen cuántas vetas hay: más bajos, más vetas.
        return claymarch.smoothstep(0.50, 0.75, flowing(p, t, 7.0))

    def color(self, p, t):
        return claymarch.mix(
            (0.40, 0.75, 0.98), (0.60, 0.87, 1.0), self.foam(p, t)
        )

    def opacity(self, p, t):
        # 0 es invisible y 1 es sólido: el agua limpia deja ver lo de
        # atrás y las vetas lo tapan un poco más.
        return 0.30 + 0.20 * self.foam(p, t)

    def bump(self, p, t):
        return 0.008 * flowing(p, t, 16.0)


class Foam(claymarch.Material):
    """La espuma de donde cae el chorro: casi blanca y sólida."""

    color = (0.90, 0.96, 1.0)
    specular = 0.6


JET_REACH = 2.40  # qué tan lejos de la boca cae el chorro, hacia adelante

# Las gotas que saltan de la salpicadura. Cada renglón es una:
# - hacia dónde sale, en grados (0 es hacia adelante, para donde empuja
#   el chorro; 90 un costado; 180 hacia atrás, hacia Squirtle)
# - qué tan lejos llega y qué tan alto salta
# - el tamaño
# - cuántas veces salta por ciclo (un número entero, para que la
#   animación empalme) y cuánto se atrasa respecto de las demás (de 0 a 1)
# Hay más hacia adelante que hacia atrás. Se pueden mover, agregar o
# sacar renglones.
SPATTER = [
    (10, 0.70, 0.55, 0.070, 14, 0.00),
    (-35, 0.55, 0.80, 0.055, 17, 0.37),
    (50, 0.60, 0.45, 0.060, 12, 0.71),
    (-75, 0.45, 0.70, 0.045, 19, 0.13),
    (95, 0.40, 0.90, 0.050, 15, 0.55),
    (-130, 0.35, 0.55, 0.040, 13, 0.86),
    (160, 0.30, 0.75, 0.045, 18, 0.24),
    (-12, 0.90, 0.35, 0.040, 16, 0.62),
    (28, 0.50, 1.00, 0.035, 11, 0.45),
]


class Spray(Droplet):
    """El agua de las gotas que saltan: limpia como la de las gotas del
    cuerpo, un poco menos transparente para que se vea contra el mar."""

    opacity = 0.40


class Spatter(claymarch.Model):
    """Una gota de la salpicadura: nace chiquita en la espuma, salta
    haciendo un arco hacia afuera, y vuelve a empezar. En el aire se
    estira hacia donde va: más cuando va rápido (al salir y al caer) y
    casi nada en lo más alto, donde frena."""

    lands = (0, 0, 0)  # dónde cae el chorro: de ahí sale
    heading = 0
    far = 0.5
    high = 0.5
    big = 0.05
    jumps = 16
    late = 0.0

    def along(self, t):
        # De 0 a 1 una y otra vez: en qué parte del salto está.
        return claymarch.fract(t * self.jumps / LOOP + self.late)

    def point(self, k):
        """Dónde está la gota en esa parte del salto."""
        turn = math.radians(self.heading)
        return (
            self.lands[0] + math.sin(turn) * self.far * k,
            self.lands[1] + 4 * self.high * k * (1 - k),
            self.lands[2] + math.cos(turn) * self.far * k,
        )

    def scale(self, t):
        # Crece al salir de la espuma y se achica mientras vuela.
        k = self.along(t)
        born = claymarch.smoothstep(0.0, 0.15, k)
        return born * (1 - 0.6 * k)

    def front(self, t):
        return self.point(self.along(t))

    def back(self, t):
        # La parte de atrás va por el mismo camino, un instante después:
        # cuanto más rápido va la gota, más lejos queda.
        return self.point(claymarch.maximum(self.along(t) - 0.035, 0.0))

    def parts(self):
        return [
            claymarch.Sphere(self.big, size=self.scale, position=self.front),
            claymarch.Sphere(
                0.6 * self.big, size=self.scale, position=self.back
            ),
        ]

    smooth = 0.04  # funde las dos partes en una sola gota
    material = Spray


def mouth_point():
    """Dónde queda la boca con la cabeza ya ubicada e inclinada, mirando
    al frente."""
    turn = math.radians(Head.TILT)
    x, y, z = Skull.MOUTH_AT
    # Al mirar hacia arriba, la boca sube y se va un poco hacia atrás.
    up = y * math.cos(turn) + z * math.sin(turn)
    forward = z * math.cos(turn) - y * math.sin(turn)
    return tuple(a + b for a, b in zip(Head.position, (x, up, forward)))


def mouth_turned(look):
    """Dónde queda la boca cuando la cabeza gira look grados hacia un
    costado (un número, o una fórmula si se mueve). Sirve para que algo
    salga de ella o la siga."""
    x, up, forward = (a - b for a, b in zip(mouth_point(), Head.position))
    turn = claymarch.radians(look)
    return (
        Head.position[0] - claymarch.sin(turn) * forward,
        Head.position[1] + up,
        Head.position[2] + claymarch.cos(turn) * forward,
    )


def sway(t):
    """Cuánto gira la cabeza hacia los costados en cada momento, en
    grados: va y viene, como jugando con el chorro. El primer número es
    cuánto gira hacia cada lado; el otro, la velocidad."""
    return 10 * claymarch.sin(t * 2.0)


class WaterJet(claymarch.Model):
    """El chorro de agua: sale de la boca hacia adelante, sube un poco y
    cae hasta el mar, donde salpica. Modelado con la boca en el origen.
    """

    # A qué altura cae el agua: 0 es donde está parado Squirtle, y el mar
    # queda más abajo que sus pies.
    floor = SEA_LEVEL + 0.10

    def parts(self):
        # Dónde cae, medido desde la boca.
        lands = (0, self.floor - mouth_point()[1], JET_REACH)
        # El chorro es una Curve: va del primer punto (adentro de la
        # boca) al tercero (donde cae) doblándose hacia el del medio, que
        # marca qué tan alto y qué tan lejos llega antes de caer. Los dos
        # últimos números son el grosor al salir y al caer.
        # ripple le da una superficie despareja que corre con el agua.
        stream = claymarch.Curve(
            (0, 0, -0.06), (0, 0.35, 1.10), lands,
            0.06, 0.13,
            ripple=claymarch.Ripple(height=0.07, size=0.16, drift=JET_FLOW),
        )
        # La espuma donde cae: un montículo chato que se mueve.
        splash = claymarch.Ellipsoid(
            0.32, 0.10, 0.32,
            position=lands,
            ripple=claymarch.Ripple(height=0.08, size=0.12, drift=(0, 1.2, 0)),
            material=Foam,
        )
        drops = [
            Spatter(
                lands=lands, heading=heading, far=far, high=high,
                big=big, jumps=jumps, late=late,
            )
            for heading, far, high, big, jumps, late in SPATTER
        ]
        return [stream, splash, *drops]

    material = Water
    # Una esfera que contiene el chorro, la espuma y las gotas: lejos de
    # ella no hace falta calcularlos. Como las gotas se mueven, no se
    # puede calcular sola: es (centro, radio), medido desde la boca.
    bounds = ((0, -0.85, 1.5), 2.2)

    def position(self, t):
        # Sale de la boca, y la sigue cuando la cabeza gira.
        return mouth_turned(sway(t))

    def rotation(self, t):
        # Gira lo mismo que la cabeza, así sale siempre derecho.
        return (0, sway(t), 0)


class SeaSquirtle(AliveSquirtle):
    """El mismo Squirtle, mojado, salpicado y tirando un chorro de agua al
    mar."""

    # Las cuatro pieles de Squirtle, cambiadas por las mojadas.
    repaint = {
        blue: WetSkin,
        cream: WetPlate,
        brown: WetHorn,
        white: WetBone,
    }
    # El cuerpo y la cabeza, con las gotas.
    body = WetBody
    head = WetHead

    jet = WaterJet

    def setup(self, t):
        # Lo de siempre (parpadea, menea la cola, aletea), más mover la
        # cabeza de un lado a otro.
        super().setup(t)
        look(self, sway(t))


class Seaside(claymarch.Scene):
    # Todo lo que hay en la escena: Squirtle, su roca, las rocas sueltas
    # de ROCKS y el faro, atrás y hacia un costado.
    models = [
        SeaSquirtle,
        Perch,
        *[
            Boulder(
                size=size, rotation=(0, turn, 0), position=(x, SEA_LEVEL, z)
            )
            for x, z, size, turn in ROCKS
        ],
        Lighthouse(
            size=LIGHTHOUSE_SIZE,
            position=(LIGHTHOUSE_AT[0], SEA_LEVEL, LIGHTHOUSE_AT[1]),
        ),
    ]

    # El mar: un piso que no es plano, sino que sube y baja con waves.
    # top es una altura que las olas nunca pasan: más arriba no hace falta
    # calcularlas.
    ground = claymarch.Ground(
        height=lambda p: SEA_LEVEL + waves(p),
        material=Sea,
        top=SEA_LEVEL + WAVE_TOP + 0.05,
    )
    # El cielo de atardecer: (arriba, horizonte). Azul profundo arriba y
    # naranja contra el mar.
    background = ((0.20, 0.33, 0.66), (1.00, 0.70, 0.44))
    # Las nubes: cover es cuánto cielo tapan (de 0 a 1), size el tamaño
    # de cada una y speed la velocidad con que las lleva el viento. color
    # es el lado al que le da el sol (dorado) y shade el otro (violáceo).
    clouds = claymarch.Clouds(
        cover=0.45, size=1.2, speed=0.03,
        color=(1.00, 0.84, 0.66), shade=(0.46, 0.38, 0.54),
    )
    # Qué tan rápido se pierde lo lejano en la bruma: menos que lo normal,
    # para que el mar llegue hasta el horizonte.
    haze = 0.25
    camera = claymarch.Camera(
        target=(0, 1.2, 0), distance=6.5, yaw=28, pitch=5
    )
    # El sol: bajo, naranja, atrás y a la derecha de Squirtle visto desde
    # la cámara, así se ve en el cielo y deja un camino de luz en el mar.
    # direction es de dónde viene: (costado, altura, frente); con la
    # altura más chica el sol baja. sun lo dibuja en el cielo (el número
    # es su tamaño) y halo es el resplandor a su alrededor.
    light = claymarch.Light(
        direction=SUN_FROM,
        color=(1.00, 0.66, 0.38),
        intensity=1.35,
        sun=1.0,
        halo=0.9,
    )
    # Una segunda luz, de frente: el resplandor de una ciudad portuaria
    # que queda fuera de cuadro, del lado de la cámara. Es baja y de un
    # amarillo anaranjado, como el alumbrado de un puerto. No hace
    # sombras. intensity es qué tan fuerte llega.
    fill = claymarch.Light(
        direction=(0.25, 0.22, 1.0),
        color=(1.00, 0.74, 0.42),
        intensity=0.55,
    )
    # La luz de relleno: el tono de lo que queda en sombra. Como Squirtle
    # está a contraluz, es fuerte y un poco rosada, para que no quede
    # oscuro.
    ambient = (1.25, 1.05, 1.20)
    # La luz que rebota desde abajo: del mar, verde azulada.
    bounce = (0.45, 0.85, 0.95)
    # El resplandor de la linterna del faro.
    halos = [
        claymarch.Halo(
            LAMP_AT, color=(1.00, 0.85, 0.50), size=1.6, strength=lamp_flare()
        )
    ]
