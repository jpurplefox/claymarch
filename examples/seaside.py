"""Un lugar para Squirtle: una roca en medio del mar, con un faro atrás.

Para verlo:   python -m claymarch examples/seaside.py --port 8775

Squirtle se importa de squirtle.py tal cual: lo que cambies allá se ve acá.
Ejes: y es arriba, z es el frente (hacia donde mira), x es el costado.
"""
import math

import claymarch
from squirtle import Squirtle, WaterJet, jet_start


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
# Dónde queda la linterna del faro: 6.5 por encima de su base.
LAMP_AT = (
    LIGHTHOUSE_AT[0],
    SEA_LEVEL + 6.5 * LIGHTHOUSE_SIZE,
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
    # terminar el ciclo (ver LOOP en squirtle.py).
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
    # La superficie despareja: cuánto sobresalen los bultos y de qué
    # tamaño son.
    ripple = (0.10, 0.30)


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
    ripple = (0.05, 0.35)


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
    ripple = (0.20, 0.80)


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


class Lighthouse(claymarch.Model):
    """El faro, sobre un islote de piedra. Modelado con la base de la
    torre en el origen."""

    islet = Islet(position=(0, -0.7, 0))
    # La torre: un cono sin punta, más ancho abajo. Los números son el
    # radio de abajo, el de arriba y el alto.
    tower = claymarch.CutCone(
        0.9, 0.6, 6.0, position=(0, 3.0, 0), material=Tower
    )
    # El balcón que rodea la linterna.
    gallery = claymarch.Cylinder(
        0.85, 0.16,
        position=(0, 6.05, 0),
        material=Iron,
    )
    # La linterna: el cuarto de vidrio de arriba, con luz propia.
    lantern = claymarch.Cylinder(
        0.45, 0.8,
        position=(0, 6.5, 0),
        material=Lamp,
    )
    roof = claymarch.Cone(
        0.62, 0.6,
        position=(0, 6.9, 0),
        material=RoofTiles,
    )


class SeaSquirtle(Squirtle):
    """El mismo Squirtle, con el chorro cayendo en el mar en vez de en el
    piso: el agua está más abajo que sus pies."""

    jet = WaterJet(position=jet_start, floor=SEA_LEVEL + 0.10)


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
