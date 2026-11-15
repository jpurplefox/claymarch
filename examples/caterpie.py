"""Caterpie: la cabeza, las secciones 2 a 6 del cuerpo y la cola.

Para verlo:   python -m claymarch examples/caterpie.py --port 8771

Ejes: y es arriba, z es el frente (hacia donde mira), x es el costado.

Cada pieza es una clase, escrita siempre en el mismo orden: primero sus
partes, después smooth, material, position y rotation. Las partes se aplican
en el orden en que están escritas, y cada una dice qué hace con lo anterior:
se suma (lo normal), se resta (carve), se funde (join) o se dibuja encima
(patch).
"""
import claymarch


# ------------------------------------------------------------------ colores
GREEN = (0.42, 0.80, 0.30)
LIGHT_GREEN = (0.66, 0.92, 0.45)
YELLOW = (1.00, 0.85, 0.15)
BLACK = (0.00, 0.00, 0.00)
RED = (0.90, 0.30, 0.38)
CREAM = (0.98, 0.90, 0.52)
WHITE = (1.00, 1.00, 1.00)


# --------------------------------------------------------------- materiales
# Cuánta textura tiene la piel: 0 la deja lisa, 2 la exagera.
TEXTURE = 1.0


def shade(color, k):
    """El mismo color, más oscuro (k < 1) o más claro (k > 1)."""
    return tuple(min(1.0, c * k) for c in color)


class Skin(claymarch.Material):
    """Piel con textura.

    En vez de un color parejo, manchas suaves entre un tono apenas más
    oscuro y uno apenas más claro, y un relieve fino que cambia cómo le
    pega la luz (bump no cambia la forma, solo el brillo).
    """

    base = GREEN
    specular = 0.25
    # Qué tan fino es el relieve: más grande, poros más chicos.
    grain = 45

    def color(self, p):
        blotches = claymarch.noise(p * 6)  # manchas grandes y suaves
        speckle = claymarch.noise(p * 28)  # moteado fino
        k = (blotches * 0.7 + speckle * 0.3 - 0.5) * TEXTURE
        dark = shade(self.base, 0.84)
        light = shade(self.base, 1.14)
        return claymarch.mix(dark, light, 0.5 + k)

    def bump(self, p):
        return 0.0025 * TEXTURE * claymarch.fbm(p * self.grain)


class BellySkin(Skin):
    """La panza: la misma idea, más suave y con el relieve más grueso."""

    base = CREAM
    specular = 0.20
    grain = 30


class AntennaSkin(Skin):
    """La antena: la misma textura sobre el rojo, con relieve más grueso."""

    base = RED
    grain = 35


green = Skin()
yellow = claymarch.Material(color=YELLOW, specular=0.25)
black = claymarch.Material(color=BLACK, specular=0.25)
red = AntennaSkin()
cream = BellySkin()
white = claymarch.Material(color=WHITE, specular=0.25)
# Los anillos.
light_green = claymarch.Material(color=LIGHT_GREEN, specular=0.25)


# ---------------------------------------------------------------- animación
# Borrador. La regla de claymarch: una propiedad es un valor fijo, o una
# función del tiempo t (en segundos) que devuelve el valor.
# sin(t * velocidad) va y viene entre -1 y 1; multiplicado por un número da
# cuánto se mueve.

# Cuánta animación: 0 lo deja quieto, 2 la exagera.
A = 1.0


def pulse(size, i):
    """El tamaño de la sección número i, latiendo.

    Cada sección late un poco después que la anterior (i * 0.9), así se ve
    una ola que baja por el cuerpo.
    """
    return lambda t: size * (1 + A * 0.03 * claymarch.sin(t * 3 - i * 0.9))


# ---------------------------------------------------------------- la cabeza
class Eye(claymarch.Drawing):
    """El ojo es un dibujo: discos apoyados uno sobre otro.

    No sobresalen de la cabeza. El ojo no sabe sobre qué va dibujado; la
    cabeza lo ubica con patch. Los discos se apilan en el orden en que
    están escritos: el primero queda abajo.
    """

    rim = claymarch.Disc(0.20, material=yellow)  # el borde
    pupil = claymarch.Disc(0.13, material=black)
    # El brillo: corrido del centro del ojo, hacia arriba y adelante.
    shine = claymarch.Disc(0.045, material=white, at=(-0.04, 0.06, 0.05))


class Antenna(claymarch.Model):
    """La antena en Y.

    Modelada con la base en el origen (donde toca la frente); position la
    lleva a su lugar. Son cápsulas: cada una va de un punto a otro, y con
    dos radios se engrosa hacia la punta.
    """

    # El tallo: sube pegado a la frente, apenas hacia adelante.
    stem = claymarch.Capsule(
        (0, 0, 0), (0, 0.28, 0.05), 0.050, 0.055,
        rotation=(30, 0, 0),
    )
    # Un brazo: sale de la punta del tallo hacia el costado y un poco atrás,
    # y termina más grueso. El otro brazo lo hace symmetry.
    arms = claymarch.Capsule(
        (0, 0.22, 0.19), (0.38, 0.34, 0.05), 0.050, 0.070,
        symmetry="x",
    )

    smooth = 0.04  # redondea la unión de la Y
    material = red
    position = (0, 0.05, 0.4)  # un punto sobre la frente, a media altura

    def rotation(self, t):
        # Se menea hacia los costados.
        return (0, 0, A * 6 * claymarch.sin(t * 4))


class Mouth(claymarch.Model):
    """La boca: un cono sin punta, redondeado, con un surco en el borde.

    Modelada parada, con el centro en el origen; rotation la da vuelta y la
    inclina, y position la lleva al hueco de la cabeza: la parte ancha
    queda enterrada y la cara angosta asoma hacia abajo y adelante.
    """

    cone = claymarch.CutCone(0.25, 0.21, 0.28, rounding=0.09)
    # El surco: un aro fino sobre el borde redondeado de la punta angosta.
    # Torus(radio, grosor); position lo sube hasta ese borde, y carve lo
    # resta del cono (el número es qué tan suave queda el borde del corte).
    lip = claymarch.Torus(0.170, 0.012, position=(0, 0.114, 0), carve=0.01)

    position = (0, -0.30, 0.30)  # relativa a la cabeza: abajo y adelante
    rotation = (140, 0, 0)


class Head(claymarch.Model):
    """Sección 1: el hueso, los ojos, el hueco, la boca y la antena.

    Las piezas se aplican en el orden en que están escritas: primero el
    hueso, sobre él se dibujan los ojos, después se cava el hueco donde
    encaja la boca, se le suma la boca y por último la antena. Modelada con
    el centro en el origen; position la sube.
    """

    bone = claymarch.Ellipsoid(0.50, 0.45, 0.50)
    # Los ojos van justo después del hueso: un dibujo se pega sobre lo que
    # está escrito antes que él. patch es el punto de la superficie donde va
    # (de costado, apenas arriba y adelante). Solo x > 0: el otro ojo sale
    # con symmetry.
    eyes = Eye(patch=(0.44, 0.06, 0.22), symmetry="x")
    # El hueco: un elipsoide centrado cerca de la superficie, abajo y
    # adelante. carve lo resta de lo anterior, con el borde suavizado.
    hole = claymarch.Ellipsoid(
        0.26, 0.26, 0.5,
        position=(0, -0.34, 0.34),
        carve=0.06,
    )
    # join: se suma fundiéndose con lo anterior (el número es cuánto).
    mouth = Mouth(join=0.03)
    antenna = Antenna()

    material = green  # la antena tiene su propio rojo
    position = (0, 1.3, 0)
    # Grados: hacia qué costado tiene girada la cabeza (0 = de frente).
    look = 0

    def rotation(self, t):
        # -15 es la pose (mira hacia arriba); lo demás es el movimiento.
        nod = A * 3 * claymarch.sin(t * 1.5)  # asiente apenas
        turn = A * 8 * claymarch.sin(t * 0.9)  # mira a un lado y al otro
        return (-15 + nod, self.look + turn, 0)


# ---------------------------------------------------------------- el cuerpo
# Hay dos formas de sección. La redonda (RoundSection) se usa en las
# secciones 2 y 3; la de cono (ConeSection), en las 4, 5 y 6. Cada una
# tiene su panza crema: RoundBelly y ConeBelly.
class RoundBelly(claymarch.Model):
    """La panza crema de una sección redonda, con sus patas."""

    # El tercer radio es cuánto sale hacia adelante.
    belly = claymarch.Ellipsoid(0.29, 0.27, 0.17)
    # Una pata: una bolita aplastada (menos alta que ancha), centrada sobre
    # la superficie de la panza, así asoma solo la mitad. symmetry hace la
    # otra.
    legs = claymarch.Ellipsoid(
        0.070, 0.07, 0.044,
        rotation=(30, -20, 0),
        position=(0.18, -0.07, 0.123),
        symmetry="x",
    )

    smooth = 0.02
    material = cream
    position = (0, -0.03, 0.10)  # relativa a la sección: adelante


class RoundSection(claymarch.Model):
    """Una sección redonda (la 2 y la 3).

    El lomo hace de pinza sobre la panza: se le cava el lugar de la panza,
    así sus costados quedan abrazándola, y después se le suma la panza.
    """

    back = claymarch.Ellipsoid(0.39, 0.33, 0.34)
    # El anillo: un disco con agujero (inner), dibujado sobre el lomo en un
    # punto del costado (patch) y copiado al otro lado (symmetry).
    ring = claymarch.Disc(
        0.12, inner=0.08,
        material=light_green,
        patch=(0.36, 0.00, -0.10),
        symmetry="x",
    )
    # El lugar que ocupa la panza, apenas agrandado: es lo que se cava.
    socket = claymarch.Ellipsoid(
        0.30, 0.28, 0.18,
        position=(0, -0.03, 0.20),
        carve=0.05,
    )
    belly = RoundBelly(join=0.05)

    material = green
    position = (0, 0.75, -0.2)  # debajo de la cabeza, un poco atrás
    # Grados en x: positivo inclina el frente hacia abajo.
    rotation = (15, 0, 0)


class ConeBack(claymarch.Model):
    """El lomo verde de una sección de cono, con su anillo dibujado encima.

    CutCone(radio de abajo, radio de arriba, alto): ancho arriba (donde se
    une con la sección anterior) y angosto abajo (hacia la cola).
    """

    shell = claymarch.CutCone(0.25, 0.29, 0.60, rounding=0.16)
    ring = claymarch.Disc(
        0.10, inner=0.065,
        material=light_green,
        patch=(0.26, 0.00, -0.07),
        symmetry="x",
    )


class ConeBelly(claymarch.Model):
    """La panza crema de una sección de cono: el mismo cono, más chico."""

    belly = claymarch.CutCone(0.17, 0.21, 0.55, rounding=0.10)
    # El surco: un aro acostado y muy fino que muerde apenas la superficie.
    # Torus(radio del aro, grosor): el radio es el de la panza a esa altura
    # (en el medio, el promedio de sus dos radios); el grosor es cuánto cava.
    groove = claymarch.Torus(0.19, 0.012, carve=0.01)

    material = cream
    position = (0, 0, 0.02)  # relativa a la sección: adelante


class ConeSection(claymarch.Model):
    """Una sección de cono (la 4, la 5 y la 6).

    La pinza es la misma idea que en la redonda: al lomo se le cava el
    lugar de la panza.

    bend es la curvatura: gira la pieza cada vez más a medida que sube, así
    el cono se arquea. Son los grados por unidad de altura, (alrededor de x,
    alrededor de z): 0 es recto, y el signo cambia hacia qué lado se arquea.
    El lomo y el lugar de la panza llevan el mismo bend, para seguir
    encajando; la panza lleva más.
    """

    back = ConeBack(bend=(-15, 0))
    # El lugar de la panza, apenas agrandado: es lo que se cava.
    socket = claymarch.CutCone(
        0.19, 0.26, 0.55, rounding=0.10,
        position=(0, 0, 0.13),
        bend=(-15, 0),
        carve=0.05,
    )
    belly = ConeBelly(bend=(-30, 0))

    material = green
    position = (0, 0.10, -0.72)  # debajo y atrás de la sección 3
    rotation = (67, 0, 0)  # más volcada que la 3: la panza mira al piso


# ------------------------------------------------------------------ la cola
class Tail(claymarch.Model):
    """La cola: un signo de exclamación.

    Modelada parada, con la base en el origen (donde toca el cuerpo);
    rotation la vuelca hacia atrás.
    """

    # El punto: una bolita, la parte más cercana al cuerpo.
    dot = claymarch.Sphere(0.06, position=(0, 0.05, 0))
    # El palito: una cápsula de dos radios, fina cerca del punto y gruesa
    # en la punta. Entre los dos queda un espacio, como en el signo.
    stroke = claymarch.Capsule((0, 0.10, 0), (0, 0.45, 0), 0.035, 0.075)

    material = cream
    position = (0, 0.05, -1.66)  # la punta de la sección 6

    def rotation(self, t):
        # -35 la vuelca hacia atrás; el tercero la menea.
        return (-35, 0, A * 14 * claymarch.sin(t * 5))


# ----------------------------------------------------------- todo el bicho
class Caterpie(claymarch.Model):
    """Todo el bicho.

    Como las secciones van una debajo de otra, position sirve para subirlo
    entero cuando haga falta lugar abajo.
    """

    head = Head().rotate_z(0.1)
    section2 = RoundSection(size=pulse(1.00, 0))
    # Sección 3: la misma clase que la 2, con otros valores. size la achica
    # entera (verde, panza y patas); position y rotation la ubican.
    section3 = RoundSection(
        size=pulse(0.88, 1),
        position=(0, 0.38, -0.38),
        rotation=(35, 0, 0),
    )
    section4 = ConeSection(size=pulse(1.00, 2))
    # Sección 5: la misma clase que la 4, más chica y más acostada. Su lado
    # ancho (0.29 x 0.78 = 0.23) queda parecido al lado angosto de la 4
    # (0.25).
    section5 = ConeSection(
        size=pulse(0.78, 3),
        position=(0, -0.02, -1.17),
        rotation=(84, 0, 0),
    )
    # Sección 6: otra vez la misma clase, más chica todavía y ya acostada
    # del todo (90 es horizontal; más de 90 levanta la punta).
    section6 = ConeSection(
        size=pulse(0.57, 4),
        position=(0, 0.00, -1.53),
        rotation=(105, 0, 0),
    )
    tail = Tail()

    smooth = 0.02
    position = (0, 0.30, 0)
    # Para que dibuje más rápido: una esfera (centro, radio) que envuelve al
    # bicho entero, antenas y cola incluidas. Lejos de ella no se calcula
    # ninguna pieza. Si algo se ve cortado, hay que agrandar el radio.
    bounds = ((0, 0.8, -0.6), 1.7)


class CaterpieScene(claymarch.Scene):
    caterpie = Caterpie()
    camera = claymarch.Camera(
        target=(0, 1.15, 0), distance=3.8, yaw=45, pitch=8
    )
    light = claymarch.Light(direction=(0.8, 0.8, 0.5))
