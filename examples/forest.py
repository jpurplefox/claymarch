"""Un lugar para el Caterpie: el suelo, el cielo, la rama y los árboles.

Para verlo:   python -m claymarch examples/forest.py --port 8772

El Caterpie se importa de caterpie.py tal cual: lo que cambies allá se ve
acá. Ejes: y es arriba, z es el frente (hacia donde mira), x es el costado.
"""
import math

import claymarch
from caterpie import Caterpie, Head


# ------------------------------------------------------------------- el cielo
# Dos colores: el de arriba y el del horizonte. No es un cielo celeste sino la
# luz que se filtra entre las hojas: verde arriba, amarillo pálido abajo.
# Arriba es la copa de los árboles: verde oscuro.
SKY_TOP = (0.17, 0.34, 0.18)
# Dorado: es también el color de la bruma del fondo.
SKY_HORIZON = (1.00, 0.88, 0.58)

# --------------------------------------------------------------------- la luz
# Sol de tarde: bajo (la y de la dirección es chica) y dorado.
# De dónde viene: (costado, altura, frente).
SUN_FROM = (0.9, 0.5, 0.2)
SUN_COLOR = (1.00, 0.80, 0.52)
# Luz de relleno: el tono de lo que queda en sombra. Verde-ámbar en vez del
# azul cielo por defecto, para que las sombras no se enfríen.
SHADE_COLOR = (0.78, 0.80, 0.48)


# ----------------------------------------------------- dónde están los hongos
# La lista va acá arriba porque la usan dos cosas: los hongos mismos y el
# resplandor que dejan sobre el piso y la rama.
# Cada uno: (x, z, tamaño, inclinación)
SHROOMS = [
    (1.00, -0.10, 1.00, (0, 0, -8)),
    (1.35, -0.42, 0.65, (6, 0, -14)),
    (1.22, 0.28, 0.50, (-8, 0, 6)),
    (0.62, -1.55, 0.80, (4, 0, -10)),
    (0.92, -1.90, 0.45, (-6, 0, -18)),
]
SHROOM_LIGHT = (0.30, 0.95, 0.85)  # el color del resplandor
HALO = 1.0  # cuánto resplandor: 0 lo apaga


def halo(p):
    """Cuánto resplandor de hongo llega al punto p (0 = nada).

    No es luz de verdad: es una mancha que se apaga con la distancia a cada
    sombrero, y los materiales la usan para teñirse y brillar un poco.
    """
    total = 0
    for x, z, size, _ in SHROOMS:
        reach = 0.30 + 1.0 * size  # hasta dónde llega
        cap = (x, 0.30 * size, z)
        near = claymarch.smoothstep(reach, 0.0, claymarch.length(p - cap))
        total = total + near ** 2 * size  # al cuadrado: se apaga más suave
    return total * HALO


def lit(color, p):
    """El color de una superficie, teñido por el resplandor."""
    tint = claymarch.clamp(halo(p) * 0.65, 0, 0.7)
    return claymarch.mix(color, SHROOM_LIGHT, tint)


# ------------------------------------------------------------------- el suelo
def terrain(p):
    """La altura del piso en cada punto.

    En vez de un número fijo, es una función de la posición: noise da lomas
    suaves.
    """
    # Solo importa dónde estás parado, no la altura.
    flat = claymarch.vec(p.x, 0, p.z)
    # Lomas grandes: hasta 0.8 arriba o abajo.
    hills = 1.6 * (claymarch.noise(flat * 0.16) - 0.5)
    # Bultos chicos.
    lumps = 0.16 * (claymarch.noise(flat * 1.1) - 0.5)
    # Cerca de la rama (el origen) el piso queda parejo; las lomas aparecen
    # de a poco entre 1.5 y 6 de distancia.
    away = claymarch.smoothstep(1.5, 6.0, claymarch.length(flat))
    return hills * away + lumps * (0.3 + 0.7 * away)


def ground_at(x, z, sink=0.06):
    """La altura del piso en un punto fijo, como número.

    Es la misma cuenta que terrain, hecha en Python con noise_at. Sirve para
    apoyar cosas sobre las lomas. sink las hunde un poquito para que no
    queden flotando.
    """
    hills = 1.6 * (claymarch.noise_at(x * 0.16, 0, z * 0.16) - 0.5)
    lumps = 0.16 * (claymarch.noise_at(x * 1.1, 0, z * 1.1) - 0.5)
    k = min(1.0, max(0.0, (math.hypot(x, z) - 1.5) / (6.0 - 1.5)))
    away = k * k * (3 - 2 * k)  # lo mismo que smoothstep(1.5, 6.0, ...)
    return hills * away + lumps * (0.3 + 0.7 * away) - sink


def on_ground(x, z, sink=0.06):
    """Una position apoyada en el piso."""
    return (x, ground_at(x, z, sink), z)


class Meadow(claymarch.Material):
    """El piso: tierra, y encima el pasto (Grass), que toma este mismo
    material. Cada punto sabe a qué altura está sobre la tierra: al ras es
    marrón, y el pasto se va poniendo verde hacia arriba.

    color es un método de la posición p: noise(p) da manchas suaves entre 0
    y 1, y mix elige entre dos verdes según esa mancha.
    """

    specular = 0.03

    def color(self, p):
        patches = claymarch.noise(p * 1.3)  # manchas grandes
        speckle = claymarch.noise(p * 9.0)  # moteado fino
        green = claymarch.mix(
            (0.20, 0.42, 0.16), (0.44, 0.62, 0.22),
            patches * 0.75 + speckle * 0.25,
        )
        soil = claymarch.mix((0.20, 0.13, 0.08), (0.34, 0.24, 0.14), speckle)
        above = p.y - terrain(p)
        return lit(claymarch.mix(soil, green, claymarch.smoothstep(0.0, 0.07, above)), p)

    def glow(self, p, t):
        # Cerca de un hongo el piso brilla apenas, y late con él.
        return halo(p) * (0.45 + 0.10 * claymarch.sin(t * 1.8))

    def bump(self, p):
        # Un relieve apenas, para que no sea un espejo.
        return 0.004 * claymarch.fbm(p * 14)


class Grass(claymarch.Fuzz):
    """El pasto: hebras largas y casi paradas, que se mecen con la brisa.
    Sin material propio: toman el del piso (Meadow)."""

    length = 0.09
    spacing = 0.006
    lift = 82
    density = 1.5
    wind = (0.15, 0.0, 0.10)

    def grows(self, out, point):
        # A manchones: el noise grande dice dónde hay pasto, el chico le
        # desordena el borde. Donde no crece queda la tierra.
        flat = claymarch.vec(point.x, 0, point.z)
        patches = claymarch.noise(flat * 0.6)
        tufts = claymarch.noise(flat * 3.0)
        return claymarch.smoothstep(0.40, 0.65, patches * 0.7 + tufts * 0.3)


# ------------------------------------------------------------- el musgo alto
class MossFuzz(claymarch.Fuzz):
    """Musgo de verdad: hebras cortas, casi paradas y apretadas. No tienen
    material propio, así que toman el color de lo que cubren."""

    length = 0.035
    spacing = 0.006
    lift = 75
    density = 1.5


# -------------------------------------------------------------------- la rama
def bark_moss(p):
    """Dónde hay musgo en la rama: donde mira hacia arriba (p.y alto). El
    noise le desordena el borde para que no sea una línea recta."""
    edge = p.y + 0.35 * (claymarch.noise(p * 2.5) - 0.5)
    moss = claymarch.smoothstep(0.70, 0.86, edge)
    # ...pero no en la ramita, que está más alta.
    return moss * claymarch.smoothstep(1.15, 0.95, p.y)


STUB_BASE = (0.30, 0.50, 1.70)  # donde el gajo cortado sale de la rama


class BarkMoss(MossFuzz):
    def grows(self, out, point):
        # ni alrededor del gajo: ahí el musgo de la rama quedaría como un
        # aro alrededor de su base
        stub = claymarch.length(point - STUB_BASE)
        return bark_moss(point) * claymarch.smoothstep(0.35, 0.55, stub)


def cracks(p):
    """Las grietas de la corteza: 0 en el fondo de una grieta, 1 lejos.

    Donde el noise cruza el 0.5 queda una línea; estirado a lo largo de la
    rama (z cambia poco), esas líneas son grietas largas que se cruzan.
    """
    # un noise grande las tuerce un poco, para que no sean paralelas
    wander = 0.4 * claymarch.noise(p * (3.0, 3.0, 0.4))
    lines = abs(claymarch.noise(p * (26.0, 26.0, 0.9) + wander) * 2 - 1)
    return claymarch.smoothstep(0.0, 0.35, lines)


class Bark(claymarch.Material):
    """Corteza con musgo arriba.

    El ruido se estira a lo largo de la rama (z) multiplicando menos esa
    coordenada: así salen vetas y grietas en vez de manchas.
    """

    specular = 0.04

    def color(self, p):
        grain = claymarch.fbm(p * (10.0, 10.0, 1.4))
        wood = claymarch.mix((0.28, 0.18, 0.11), (0.56, 0.41, 0.25), grain)
        # el fondo de las grietas, más oscuro
        wood = claymarch.mix((0.20, 0.13, 0.08), wood, cracks(p))
        # un moteado fino, para que de cerca no quede liso
        wood = wood * (0.85 + 0.3 * claymarch.noise(p * 45))
        moss = bark_moss(p)
        return lit(claymarch.mix(wood, (0.33, 0.50, 0.17), moss * 0.85), p)

    def glow(self, p, t):
        return halo(p) * (0.40 + 0.08 * claymarch.sin(t * 1.8))

    def bump(self, p):
        # las grietas se hunden; encima, la veta y el moteado
        return (
            0.02 * cracks(p)
            + 0.008 * claymarch.fbm(p * (20.0, 20.0, 2.5))
            + 0.002 * claymarch.noise(p * 45)
        )


class LeafGreen(claymarch.Material):
    """Verde de hoja: más amarillento que el del Caterpie."""

    specular = 0.18

    def color(self, p):
        return claymarch.mix(
            (0.30, 0.58, 0.14), (0.56, 0.76, 0.22), claymarch.noise(p * 5)
        )


# La nervadura, más clara.
rib_green = claymarch.Material(color=(0.74, 0.86, 0.40), specular=0.10)

# Hacia dónde miran las hojas (grados; el yaw de la cámara con el signo
# cambiado).
FACING = -50


class HalfLeaf(claymarch.Model):
    """Media hoja, acostada: cabito cerca del origen, punta hacia +z.

    Es lo que comparten dos discos aplastados corridos hacia los costados
    (donde se cruzan quedan las puntas). rotation la levanta un poco y
    symmetry hace la otra mitad: la hoja queda plegada en V.
    """

    # & es la intersección: lo que está dentro de los dos discos a la vez.
    parts = [
        claymarch.Ellipsoid(0.30, 0.022, 0.30, position=(0.17, 0, 0.247))
        & claymarch.Ellipsoid(0.30, 0.022, 0.30, position=(-0.17, 0, 0.247))
    ]

    rotation = (0, 0, 14)  # cuánto se pliega por el medio; 0 es plana
    symmetry = "x"


class Blade(claymarch.Model):
    """La hoja entera: se arma acostada, se para y se arquea a lo largo."""

    halves = HalfLeaf
    # La nervadura y el cabito: una cápsula fina de punta a punta, en el
    # pliegue.
    rib = claymarch.Capsule(
        (0, 0.0, -0.10), (0, 0.004, 0.46), 0.014, 0.006,
        material=rib_green,
    )

    rotation = (90, 0, 0)  # la para: la cara mira al frente
    curl = 55  # cuánto se arquea (grados por unidad); 0 es recta

    def bend(self):
        return (self.curl, 0)


class Leaf(claymarch.Model):
    """Una hoja con punta, de cara al frente, abierta como en un abanico.

    fan es cuánto gira dentro de ese abanico (0 cuelga, 90 y -90 salen
    hacia los costados, 180 apunta hacia arriba). curl es cuánto se arquea.
    """

    fan = 0
    curl = 55

    def parts(self, t):
        # Un vaivén suave; cada hoja arranca en otro momento según su fan.
        sway = 5 * claymarch.sin(t * 1.6 + self.fan * 0.05)
        # El giro del abanico va después de arquearla y antes de orientarla
        # (rotation), por eso no entra en las propiedades de la hoja.
        return [Blade(curl=self.curl).rotate_z(self.fan + sway)]

    material = LeafGreen
    rotation = (0, FACING, 0)
    bounds = 0.75  # una esfera que la contiene: acelera el dibujo


BRANCH_TOP = 0.89  # altura del lomo de la rama donde se apoya el Caterpie
TWIG_TIP = (0.35, 2.00, -3.20)  # donde termina la ramita


class Branch(claymarch.Model):
    """Una rama caída, a lo largo del eje z (de adelante hacia atrás).

    Curve(inicio, control, fin, radio, radio2): un arco que va de inicio a
    fin y se comba hacia el punto de control; con radio2 se afina hacia el
    fin.
    """

    trunk = claymarch.Curve(
        (0.5, 0.35, 2.6), (0.0, 0.62, 0.0), (-0.6, 0.45, -4.2), 0.42, 0.34,
        fuzz=BarkMoss(),
    )
    # Nudos: bultos sobre los costados, para que no sea un caño parejo.
    knot_1 = claymarch.Ellipsoid(0.17, 0.15, 0.22, position=(0.36, 0.60, 0.95))
    knot_2 = claymarch.Ellipsoid(
        0.14, 0.13, 0.18, position=(-0.42, 0.50, -1.20)
    )
    # Un gajo cortado, corto y grueso.
    stub = claymarch.Capsule(STUB_BASE, (0.88, 0.64, 1.95), 0.15, 0.13)
    # Una ramita viva: sale cerca del extremo de atrás, sube y se afina.
    twig = claymarch.Curve(
        (-0.30, 0.55, -2.60), (-0.35, 1.55, -2.85), TWIG_TIP, 0.12, 0.04
    )
    # Las hojas. join=0 las suma sin fundirlas con la madera: si no, el
    # smooth de la rama las engordaría.
    # rotation = (cuánto se vuelca hacia adelante o atrás, hacia dónde mira,
    # 0): cada una un poco distinta, para que no queden en el mismo plano.
    leaf_1 = Leaf(
        fan=170,
        size=1.5,
        position=TWIG_TIP,
        rotation=(-25, FACING + 10, 0),
        join=0,
    )
    leaf_2 = Leaf(
        fan=95,
        curl=75,
        size=1.3,
        position=TWIG_TIP,
        rotation=(15, FACING - 25, 0),
        join=0,
    )
    leaf_3 = Leaf(
        fan=-105,
        curl=40,
        size=1.3,
        position=TWIG_TIP,
        rotation=(20, FACING + 30, 0),
        join=0,
    )
    leaf_4 = Leaf(
        fan=70,
        size=1.1,
        position=(-0.12, 1.50, -2.93),
        rotation=(10, FACING - 15, 0),
        join=0,
    )

    smooth = 0.12  # funde la madera: tronco, nudos, gajo y ramita
    material = Bark
    # Una esfera (centro, radio) que envuelve la rama entera, con la ramita y
    # las hojas: lejos de ella no se calcula nada. La rama es larga, así que
    # la esfera es grande. Si algo se ve cortado, hay que agrandar el radio.
    bounds = ((0, 0.9, -0.8), 4.0)


# ---------------------------------------------------------------- los árboles
class TreeBark(claymarch.Material):
    """Corteza de árbol grande.

    Vetas verticales (el ruido se estira en y) y musgo en la base, que se
    va perdiendo al subir.
    """

    specular = 0.03

    def color(self, p):
        grain = claymarch.fbm(p * (1.6, 0.18, 1.6))
        wood = claymarch.mix((0.17, 0.11, 0.07), (0.40, 0.29, 0.18), grain)
        edge = p.y + 3.0 * claymarch.noise(p * 0.5)
        moss = claymarch.smoothstep(4.5, 0.5, edge)
        return claymarch.mix(wood, (0.24, 0.40, 0.14), moss * 0.8)

    def bump(self, p):
        return 0.03 * claymarch.fbm(p * (3.0, 0.3, 3.0))


TREE_GAP = 22  # distancia entre un árbol y el siguiente
# Radio del claro: más cerca que esto de la rama no hay árboles.
CLEARING = 14


def in_the_woods(c):
    """¿Va un árbol en esta celda? c es el centro de la celda.

    step da 1 si está más lejos que CLEARING del origen (donde está la
    rama), y 0 si no.
    """
    return claymarch.step(CLEARING, claymarch.length(c))


class Tree(claymarch.Model):
    """Un tronco enorme, de radio 2.

    Sube hasta salirse del cuadro: no se le ve la copa, y eso lo hace
    parecer más alto.
    """

    trunk = claymarch.Capsule((0, -1, 0), (0, 45, 0), 2.0, 1.6)
    # La base se ensancha: un cono sin punta fundido con el tronco.
    flare = claymarch.CutCone(3.8, 1.8, 6.0, position=(0, 2.4, 0))
    # Dos raíces que asoman.
    root_1 = claymarch.Ellipsoid(1.2, 1.0, 2.6, position=(1.8, 0, 3.0))
    root_2 = claymarch.Ellipsoid(2.4, 0.9, 1.2, position=(-3.2, 0, 0.8))

    smooth = 1.4
    material = TreeBark


# ----------------------------------------------------------------- los hongos
class GlowCap(claymarch.Material):
    """El sombrero: turquesa con luz propia.

    glow es cuánta luz emite (0 = nada); como método de (p, t) puede latir
    con el tiempo.
    """

    specular = 0.30

    def color(self, p):
        # Más claro hacia arriba del sombrero, con unas manchas.
        top = claymarch.smoothstep(0.30, 0.48, p.y)
        return claymarch.mix(
            (0.10, 0.62, 0.60), (0.55, 1.00, 0.85),
            top * 0.7 + claymarch.noise(p * 14) * 0.3,
        )

    def glow(self, p, t):
        # Late despacio.
        return 0.50 + 0.18 * claymarch.sin(t * 1.8 + p.x * 3.0)


stem_white = claymarch.Material(
    color=(0.86, 0.90, 0.78), specular=0.10, glow=0.25
)


class Mushroom(claymarch.Model):
    """Un hongo, modelado con el pie en el origen. size lo agranda."""

    # El sombrero: una cúpula. Es un elipsoide al que se le cava otro más
    # chato por debajo, así queda hueco y con borde.
    cap = claymarch.Ellipsoid(0.22, 0.16, 0.22, position=(0.02, 0.36, 0))
    hollow = claymarch.Ellipsoid(
        0.24, 0.12, 0.24,
        position=(0.02, 0.25, 0),
        carve=True,
    )
    # El tallo: una cápsula que se afina hacia arriba. Va después del hueco
    # para que el hueco no se lo coma.
    stem = claymarch.Capsule(
        (0, -0.05, 0), (0.02, 0.34, 0), 0.055, 0.035,
        material=stem_white,
    )

    # El material del hongo es el del sombrero; el tallo trae el suyo.
    material = GlowCap
    bounds = ((0, 0.22, 0), 0.5)  # una esfera que lo contiene


class Mushrooms(claymarch.Model):
    """Los hongos de la lista SHROOMS, del lado que ve la cámara."""

    parts = [
        Mushroom(position=(x, 0, z), size=size, rotation=tilt)
        for x, z, size, tilt in SHROOMS
    ]


# -------------------------------------------------------------- el sotobosque
class FrondGreen(claymarch.Material):
    """Verde de helecho.

    stripes dibuja rayas a lo largo de cada hoja: de lejos se leen como los
    foliolos del helecho sin tener que modelarlos.
    """

    specular = 0.10

    def color(self, p):
        leaflets = claymarch.stripes(p.y + 0.3 * abs(p.x), 0.035)
        return claymarch.mix(
            (0.13, 0.36, 0.12), (0.34, 0.60, 0.20), 0.25 + 0.6 * leaflets
        )


class Frond(claymarch.Model):
    """Una hoja de helecho: larga, con el pie en el origen, arqueada.

    length es el largo. rotation = (cuánto se vuelca hacia afuera, hacia
    dónde apunta alrededor del centro, 0).
    """

    length = 1.0
    droop = 36  # cuánto se arquea (grados por unidad de largo)

    def parts(self):
        half = self.length / 2
        return [
            claymarch.Ellipsoid(
                0.11, half, 0.02,
                position=(0, half, 0),
                bend=(self.droop, 0),
            )
        ]


class Fern(claymarch.Model):
    """Una mata de helecho: seis hojas que salen del centro hacia afuera.

    Cada una con otro largo y otra caída, repartidas en ronda. Modelada con
    el pie en el origen.
    """

    frond_1 = Frond(length=0.85, rotation=(14, 0, 0))
    frond_2 = Frond(length=1.0, rotation=(38, 75, 0))
    frond_3 = Frond(length=1.15, rotation=(30, 120, 0))
    frond_4 = Frond(length=0.925, rotation=(22, 195, 0))
    frond_5 = Frond(length=1.075, rotation=(14, 240, 0))
    frond_6 = Frond(length=0.85, rotation=(38, 315, 0))

    material = FrondGreen
    bounds = ((0, 0.45, 0), 1.35)  # una esfera que contiene la mata


def stone_moss(p):
    """Dónde hay musgo en una piedra: arriba (donde p.y es alto)."""
    edge = p.y + 0.25 * (claymarch.noise(p * 5) - 0.5)
    return claymarch.smoothstep(0.05, 0.30, edge)


class StoneMoss(MossFuzz):
    def grows(self, out, point):
        return stone_moss(point)


class Stone(claymarch.Material):
    """Piedra con musgo arriba (donde p.y es alto)."""

    specular = 0.06

    def color(self, p):
        rock = claymarch.mix(
            (0.30, 0.29, 0.25), (0.52, 0.50, 0.42), claymarch.fbm(p * 4)
        )
        return claymarch.mix(rock, (0.26, 0.44, 0.15), stone_moss(p) * 0.9)

    def bump(self, p):
        return 0.012 * claymarch.fbm(p * 9)


class Rock(claymarch.Model):
    """Una piedra redondeada: dos bultos fundidos."""

    big = claymarch.Ellipsoid(0.62, 0.42, 0.50)
    small = claymarch.Ellipsoid(0.40, 0.30, 0.44, position=(0.36, -0.04, 0.12))

    smooth = 0.18
    material = Stone
    fuzz = StoneMoss()
    bounds = ((0.12, 0, 0.04), 0.95)


class Undergrowth(claymarch.Model):
    """Lo que crece entre la rama y los árboles.

    on_ground(x, z) apoya cada cosa sobre las lomas; x y z negativos es
    "atrás" desde la cámara inicial.
    """

    fern_1 = Fern(position=on_ground(-4.6, -0.5), size=1.6)
    fern_2 = Fern(
        position=on_ground(-1.8, -5.4), size=1.8, rotation=(0, 40, 0)
    )
    fern_3 = Fern(
        position=on_ground(-5.3, -4.4), size=2.0, rotation=(0, 80, 0)
    )
    fern_4 = Fern(
        position=on_ground(-7.3, -3.5), size=2.2, rotation=(0, 130, 0)
    )
    fern_5 = Fern(
        position=on_ground(-2.6, 1.6), size=1.0, rotation=(0, 60, 0)
    )
    rock_1 = Rock(
        position=on_ground(-3.0, -0.9, sink=0.12),
        size=1.0,
        rotation=(0, 30, 0),
    )
    rock_2 = Rock(
        position=on_ground(-3.4, -4.6, sink=0.20),
        size=1.6,
        rotation=(0, 140, 0),
    )
    rock_3 = Rock(
        position=on_ground(1.1, -3.3, sink=0.08),
        size=0.6,
        rotation=(0, 250, 0),
    )


class ForestCaterpie(Caterpie):
    """El mismo Caterpie, con la cabeza girada hacia la cámara y el cuerpo
    acomodado sobre la rama."""

    # Negativo gira hacia la cámara inicial; 0 es de frente.
    head = Head(look=-40)

    # El cuerpo sigue la dirección de la rama: en ese tramo la rama se va
    # torciendo unos 9 grados hacia un costado, y el cuerpo gira lo mismo.
    rotation = (0, -9, 0)
    # El 0.17: más chico lo hunde, más grande lo levanta.
    position = (0.04, BRANCH_TOP + 0.17, 0)

    def setup(self):
        # En caterpie.py la parte de atrás se va levantando. Acá las
        # secciones 5 y 6 y la cola se acuestan sobre la rama: más abajo y
        # más horizontales (90 es acostada del todo).
        self.section5.position = (0, -0.05, -1.17)
        self.section5.rotation = (86, 0, 0)
        self.section6.position = (0, -0.11, -1.53)
        self.section6.rotation = (92, 0, 0)
        self.tail.position = (0, -0.07, -1.68)


class Forest(claymarch.Scene):
    branch = Branch
    # Los árboles: UN solo Tree repetido en una grilla sin fin (ver TREE_GAP
    # y CLEARING más arriba). Cuanto más lejos, más los tapa la bruma.
    # repeat no tiene forma declarativa: es un método de la forma.
    trees = Tree().repeat(
        # Un árbol cada tanto, hacia los costados y hacia el fondo.
        x=TREE_GAP, z=TREE_GAP,
        # Cada uno corrido hasta 2 de su lugar: rompe la grilla.
        jitter=2.0,
        # Cada uno de un tamaño distinto, entre 0.8 y 1.5 veces.
        size=(0.8, 1.5),
        # Cada uno girado distinto: las raíces no apuntan todas igual.
        spin=True,
        # Deja libre el claro donde está la rama.
        where=in_the_woods,
    ).move(y=-0.4)  # un poco hundidos, para que no floten en las lomas bajas
    caterpie = ForestCaterpie

    shrooms = Mushrooms
    undergrowth = Undergrowth

    # top: una altura que las lomas nunca pasan (terrain llega a 0.88). Por
    # encima de eso el piso no calcula las lomas, y dibuja más rápido.
    ground = claymarch.Ground(
        height=terrain, material=Meadow, top=0.9, fuzz=Grass()
    )
    background = (SKY_TOP, SKY_HORIZON)
    camera = claymarch.Camera(
        target=(0, 1.55, -0.6), distance=4.6, yaw=50, pitch=9
    )
    light = claymarch.Light(
        direction=SUN_FROM, color=SUN_COLOR, intensity=1.15
    )
    ambient = SHADE_COLOR
