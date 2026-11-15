# sculpt

Describir escenas 3D en Python y traducirlas a un shader GLSL (raymarching de
funciones de distancia).

```bash
python -m sculpt examples/caterpie.py
```

Abrí `http://localhost:8770`. Al guardar el archivo, la página se actualiza sola.

---

## Índice

1. [Ejemplo mínimo](#ejemplo-mínimo)
2. [La regla central](#la-regla-central)
3. [Formas](#formas)
4. [Transformar, modificar y combinar](#transformar-modificar-y-combinar)
5. [Model](#model)
6. [Material](#material)
7. [Expresiones](#expresiones)
8. [Scene, Camera, Light, Ground](#scene-camera-light-ground)
9. [El visor](#el-visor)
10. [Cosas que suelen confundir](#cosas-que-suelen-confundir)
11. [Lo que todavía no existe](#lo-que-todavía-no-existe)

---

## Ejemplo mínimo

```python
from sculpt import *

class Red(Material):
    color = (0.9, 0.3, 0.2)

class Ball(Model):
    body = Sphere(0.5).move(y=0.5)
    material = Red

    def position(self, t):                  # rebota
        return (0, 0.3 * abs(sin(t * 3)), 0)

class MyScene(Scene):
    ball = Ball
```

## La regla central

**Cada propiedad es un valor, o un método que devuelve el valor.**

| En un...   | el método recibe         | para                         |
|------------|--------------------------|------------------------------|
| `Model`    | `t` (tiempo en segundos) | animar                       |
| `Material` | `p` (posición), y `t` si pide un segundo parámetro | dibujar sobre el objeto |

```python
class Thing(Model):
    size = 1.0                       # valor fijo

class Thing(Model):
    def size(self, t):               # o método del tiempo
        return 1 + 0.1 * sin(t * 4)
```

Sistema de coordenadas: `y` es arriba, `z` apunta hacia la cámara por defecto,
`x` a la derecha. Las unidades son arbitrarias; el ejemplo mide ~1.5 de alto.
Los ángulos van **en grados**.

---

## Formas

Todas quedan centradas en el origen salvo que se indique.

| Forma | Parámetros (valor por defecto) | Notas |
|---|---|---|
| `Sphere(radius=0.5)` | | |
| `Ellipsoid(rx=0.5, ry=0.5, rz=0.5)` | un radio por eje | la base para cuerpos orgánicos |
| `Box(width=1, height=1, depth=1, rounding=0)` | tamaños totales | `rounding` redondea aristas sin agrandar |
| `Capsule(start=(0,0,0), end=(0,1,0), radius=0.2, radius2=None)` | segmento grueso | con `radius2` se afina hacia `end` (colas, brazos) |
| `Curve(start=(0,0,0), control=(0,1,0), end=(1,1,0), radius=0.2, radius2=None)` | línea gruesa curva | un arco de parábola de `start` a `end`; `control` es hacia dónde se comba (la curva no pasa por ahí). Con `radius2` se afina (colas, cuernos, tentáculos) |
| `Cylinder(radius=0.5, height=1, rounding=0)` | vertical | |
| `Torus(radius=0.5, thickness=0.15)` | acostado (eje vertical) | |
| `Cone(radius=0.3, height=1)` | base en el origen, punta hacia arriba | la base es redondeada |
| `CutCone(radius=0.5, radius2=0.25, height=1, rounding=0)` | cono sin punta, vertical y centrado | `radius` es abajo, `radius2` arriba; las dos caras son planas. `rounding` redondea aristas sin agrandar |

## Transformar, modificar y combinar

Todos los métodos devuelven una forma nueva, así que se encadenan:

```python
Cone(0.16, 0.45).rotate_z(-25).move(x=0.25, y=1.32).mirror("x")
```

Se aplican **en el orden en que se leen**: primero rota, después mueve, después espeja.

### Transformaciones

| Método | Qué hace |
|---|---|
| `.move(x=0, y=0, z=0)` | traslada. También acepta un punto: `.move((0.4, 0.1, 0.2))`, cómodo cuando el punto tiene nombre (`EYE_AT = (0.44, 0.06, 0.22)`) y se usa en varias formas |
| `.rotate_x(degrees)` `.rotate_y(degrees)` `.rotate_z(degrees)` | rota alrededor de ese eje, pasando por el origen |
| `.scale(factor)` | escala uniforme (un solo número) |
| `.mirror(axis="x")` | simetría: lo que está del lado positivo se copia al negativo |
| `.bend_x(degrees)` `.bend_z(degrees)` | curva una forma vertical: un giro alrededor de ese eje que crece con la altura (`degrees` por cada unidad de `y`). Para curvas suaves; con valores grandes la forma se deforma |

| `.repeat(x=0, y=0, z=0, ...)` | copias de la forma en una grilla, al costo de una sola (ver abajo) |

Para `mirror`, la forma tiene que estar del lado **positivo** del eje (`x > 0`).
Se modela un ojo, una oreja o una pata, y se obtiene el par.

#### Repetir

`repeat` parte el espacio en celdas y pone una copia de la forma en cada una.
La forma se calcula una sola vez, así que mil copias cuestan lo mismo que una.

```python
Sphere(0.3).repeat(x=1.2, limit=2)            # una fila de 5 bolitas, una cada 1.2

Tree(radius=2).repeat(                        # un bosque sin fin
    x=22, z=22,                               # un árbol cada 22, hacia los costados y hacia el fondo
    jitter=2.3, size=(0.8, 1.5), spin=True,   # cada uno corrido, de otro tamaño y girado distinto
    where=lambda c: step(14, length(c)),      # sin árboles a menos de 14 del origen
)
```

| Opción | Qué hace |
|---|---|
| `x`, `y`, `z` | distancia entre copias en cada eje (0 = no se repite en ese eje) |
| `limit` | cuántas copias a cada lado de la del medio (`limit=2` son 5); sin `limit` no terminan nunca |
| `jitter` | cada copia se corre de su lugar una distancia al azar, hasta ese valor |
| `size` | `(mínimo, máximo)`: cada copia sale de un tamaño al azar entre esos dos |
| `spin` | `True` gira cada copia un ángulo al azar alrededor de la vertical |
| `where` | función del centro de cada celda: si da más de 0.5 hay copia, si no la celda queda vacía |
| `seed` | otro número da otro reparto del azar |

- **Cada copia tiene que entrar en su celda**, que mide la mitad de la distancia
  hacia cada lado. Hay que contar el `jitter` y el tamaño máximo, y dejar un
  margen de 0.1. Si no entra, se ve cortada en el borde de la celda.
- La forma se repite alrededor del origen: hay una copia en el origen, otra a
  una distancia, otra a dos. Un `.move()` después del `repeat` corre la grilla entera.
- El azar es siempre el mismo para la misma celda: no cambia de un cuadro a otro.
- Todas las copias se animan igual y llevan la misma textura.

### Modificadores

| Método | Qué hace |
|---|---|
| `.round(radius)` | infla la forma ese radio (redondea aristas, engorda) |
| `.shell(thickness)` | la vuelve una cáscara hueca de ese grosor |
| `.patch(drawing, at, lift=None)` | pega un dibujo sobre la superficie, sin que sobresalga (un ojo, un anillo, una mancha). `drawing` es un `Disc` o un `Drawing`; `at` es un punto sobre la superficie (ver "Dibujos sobre una superficie") |
| `.paint(material)` | le asigna un material (instancia o clase) |

### Dibujos sobre una superficie

Para un ojo, un anillo o una mancha que no sobresalga: en vez de apoyar otra
forma encima, se pega un dibujo sobre la superficie. El dibujo se define solo,
sin saber sobre qué va, y la forma lo ubica con `patch`.

```python
class Eye(Drawing):
    rim   = Disc(0.20, material=yellow)
    pupil = Disc(0.13, material=black)                             # escrito después: queda encima
    shine = Disc(0.045, material=white, at=(-0.04, 0.06, 0.05))    # corrido del centro del dibujo

skull = Ellipsoid(0.50, 0.45, 0.50)
eyes  = skull.patch(Eye(), at=(0.44, 0.06, 0.22)).mirror("x")     # at: un punto sobre el cráneo

ring  = back.patch(Disc(0.12, inner=0.08, material=light_green), at=(0.36, 0, -0.10))
```

| | |
|---|---|
| `Disc(radius, inner=0, material=None, at=(0, 0, 0))` | una capa: un disco de ese radio. `inner` le deja un agujero en el medio (un anillo). `at` lo corre respecto del centro del dibujo. Usado suelto (sin `Drawing`) también acepta `lift=` |
| `Drawing` | clase para heredar: sus atributos `Disc` son las capas, apiladas en el orden en que están escritas (la primera abajo). `Eye(size=0.8)` achica el dibujo entero. `lift` (por defecto `0.006`) es cuánto se levanta cada capa sobre la anterior: se pone en la clase (`lift = 0.004`) o al usarla (`Eye(lift=0.004)`) |
| `forma.patch(drawing, at, lift=None)` | pega un `Disc` o un `Drawing` sobre `forma`, centrado en el punto `at`. `lift`, si se pasa, reemplaza al del dibujo |

Dentro de un `Model` no hace falta llamar a `patch`: el dibujo se declara como
una parte más, con `patch=` (el punto) y, si va de los dos lados, `symmetry=`.
Se dibuja sobre las partes que están escritas antes que él:

```python
class Head(Model):
    bone = Ellipsoid(0.50, 0.45, 0.50)
    eyes = Eye(patch=(0.44, 0.06, 0.22), symmetry="x")        # sobre el hueso
    ...

class RoundSection(Model):
    back = Ellipsoid(0.39, 0.33, 0.34)
    ring = Disc(0.12, inner=0.08, material=light_green, patch=(0.36, 0, -0.10), symmetry="x")
    ...
```

- Cada disco es un pedazo de la misma forma, apenas levantado: sigue la
  superficie aunque la forma cambie de tamaño.
- El resultado de `patch` es una forma aparte. Va al lado de la original y
  **fuera** de cualquier unión con `smooth`, para que el borde quede nítido.
- `at` tiene que estar sobre la superficie o muy cerca; si queda lejos, el
  dibujo no aparece.
- **Cuánto sobresale** lo decide `lift`. La primera capa se levanta `lift`
  sobre la superficie, la segunda el doble, la tercera el triple. Más chico
  se ve más pintado; más grande, más como una chapita apoyada. Si es
  demasiado chico (menos de 0.002, más o menos) las capas muestran agujeros.

### Combinaciones

| Forma larga | Operador | Qué hace |
|---|---|---|
| `a.union(b, smooth=0)` | `a \| b`, `a + b` | junta las dos |
| `a.subtract(b, smooth=0)` | `a - b` | le quita `b` a `a` |
| `a.intersect(b, smooth=0)` | `a & b` | deja solo lo que comparten |
| `union(a, b, c, ..., smooth=0)` | | junta varias de una vez |

`smooth` es el radio de la transición: con `0` las formas se cortan en seco, con
`0.1` se funden como plastilina. Es la herramienta principal para modelar
criaturas. Los operadores no permiten `smooth`.

---

## Model

Una cosa hecha de partes, descrita como clase.

```python
class Sprout(Model):
    stem = Capsule((0, 0, 0), (0, 0.22, 0), 0.025)       # cada forma es una parte
    leaf = Ellipsoid(0.16, 0.025, 0.10).move(x=0.14, y=0.24)

    smooth = 0.03
    material = LeafGreen
    position = (0, 1.42, 0)

    def rotation(self, t):
        return (0, 0, 12 * sin(t * 3))
```

### Partes

Todo atributo de la clase que sea una forma o un modelo pasa a ser una parte, en
el orden en que está escrito. Un modelo puede ser parte de otro, con o sin
paréntesis:

```python
class Critter(Model):
    body = Body                      # la clase directamente
    sprout = Sprout(size=0.8)        # o una instancia, para cambiarle algo
```

Si preferís una lista explícita, definí `parts = [a, b, c]` y se ignoran los
demás atributos. Los atributos que empiezan con `_` nunca cuentan como parte.

### Propiedades

| Propiedad | Por defecto | Qué es |
|---|---|---|
| `smooth` | `0.0` | radio con que se funden las partes entre sí |
| `material` | `None` | material para las partes que no tienen uno propio |
| `size` | `1.0` | escala uniforme |
| `rotation` | `(0, 0, 0)` | grados alrededor de x, y, z (se aplican en ese orden) |
| `position` | `(0, 0, 0)` | dónde va |
| `bend` | `(0, 0)` | curvatura: grados por unidad de altura, `(alrededor de x, alrededor de z)`. Es lo mismo que `.bend_x()` / `.bend_z()`, y se aplica después de `position` |
| `symmetry` | `None` | `"x"`, `"y"` o `"z"`: copia el modelo al otro lado. Es lo mismo que `.mirror()` |
| `carve` | `None` | como parte de otro modelo: se **resta** de las partes anteriores. Un número es el `smooth` del corte; `True` lo deja con borde filoso |
| `join` | `None` | como parte de otro modelo: se suma **fundiéndose** con las partes anteriores, con ese radio |
| `bounds` | `None` | acelerador opcional: el radio, o `(centro, radio)`, de una esfera que contenga al modelo entero (en su propio espacio, antes de `size`/`rotation`/`position`). Lejos de la esfera el modelo no se calcula. No cambia la imagen si la esfera lo contiene de verdad; si queda chica, el modelo se recorta. Las sombras y la oclusión ignoran la esfera (no oscurece nada por sí misma). No usarlo en partes que se funden con `smooth` con otras |
| `parts` | `None` | lista explícita de partes (opcional) |

Orden interno: se unen las partes → se pinta → `size` → `rotation` → `position`.
Como se pinta antes de ubicar, las texturas quedan pegadas al modelo y se mueven
con él.

`size` y `rotation` actúan alrededor del origen del modelo. Para que algo gire
desde su base (una hoja, un brazo), modelalo con la base en el origen y llevalo
a su lugar con `position`.

### Declarar en vez de encadenar

Toda forma acepta las mismas propiedades que un modelo, como argumentos con
nombre. Así una pieza se declara en una línea, sin encadenar llamadas:

```python
# encadenando                                       # declarando
Torus(0.17, 0.012).move(y=0.114)                    Torus(0.17, 0.012, position=(0, 0.114, 0))
Ellipsoid(0.07, 0.07, 0.04).rotate_x(30)            Ellipsoid(0.07, 0.07, 0.04, rotation=(30, 0, 0),
    .move(x=0.18).mirror("x")                                 position=(0.18, 0, 0), symmetry="x")
```

Valen `material`, `size`, `rotation`, `position`, `bend`, `symmetry`, `carve`
y `join`, y se aplican en ese orden (el mismo que en un `Model`). Las dos
formas de escribir hacen lo mismo y se pueden mezclar.

### El papel de cada parte

Las partes de un modelo se aplican **en el orden en que están escritas**, y
cada una dice qué hace con lo anterior:

```python
class Head(Model):
    bone  = Ellipsoid(0.50, 0.45, 0.50)                                        # la primera: la base
    eyes  = Eye(patch=(0.44, 0.06, 0.22), symmetry="x")                        # se dibuja sobre lo anterior
    hole  = Ellipsoid(0.26, 0.26, 0.5, position=(0, -0.34, 0.34), carve=0.06)  # se resta de lo anterior
    mouth = Mouth(join=0.03)                                                   # se suma, fundiéndose
```

| La parte lleva | Qué hace |
|---|---|
| nada | se suma a lo anterior, con el `smooth` del modelo |
| `carve=0.06` | se resta de todo lo anterior (el número suaviza el borde del corte) |
| `join=0.03` | se suma fundiéndose con lo anterior, con ese radio |
| `patch=(x, y, z)` | solo para `Disc` y `Drawing`: se dibuja sobre lo anterior, en ese punto (ver "Dibujos sobre una superficie") |

- **El orden importa.** En `Head` la boca va después del hueco: si fuera
  antes, el hueco también la cavaría a ella.
- Un dibujo se pega sobre **todo** lo que está antes en ese modelo, y nada
  más. Por eso conviene escribirlo justo después de su base (los ojos después
  del hueso) y no al final: dibuja más rápido y no lo afectan los `smooth` de
  las piezas que vienen después.
- Con esto casi nunca hace falta `parts`.

### Variantes sin otra clase

```python
Critter(position=(1.5, 0, 0), size=0.6)
```

---

## Material

```python
class Skin(Material):
    specular = 0.30

    def color(self, p):
        base = mix((0.26, 0.66, 0.58), (0.34, 0.76, 0.64), noise(p * 5.0))
        freckles = smoothstep(0.70, 0.76, noise(p * 38.0))
        return mix(base, (0.16, 0.45, 0.42), 0.7 * freckles)

    def bump(self, p):
        return 0.0022 * fbm(p * 60.0) + 0.003 * noise(p * 14.0)
```

Forma corta, para materiales lisos:

```python
dark = Material(color=(0.10, 0.10, 0.13), specular=0.9, shininess=80)
```

| Propiedad | Por defecto | Qué es |
|---|---|---|
| `color` | `(0.8, 0.8, 0.8)` | `(r, g, b)` entre 0 y 1, tal como se ve en pantalla |
| `specular` | `0.2` | fuerza del reflejo de la luz (`0` = mate) |
| `shininess` | `32.0` | qué tan chico y definido es ese reflejo |
| `glow` | `0.0` | luz propia |
| `bump` | `None` | relieve: cuánto se hunde (+) o sobresale (−) la superficie |

**`bump`** solo cambia cómo pega la luz, no la silueta (equivale a un "normal
map"). Usá valores chicos, entre `0.001` y `0.01`. El número que multiplica a
`p` es el tamaño del grano (más grande = más fino); el que multiplica al ruido
es la profundidad.

**`p`** es la posición en el punto donde se pintó, compartida por todas las
piezas pintadas juntas: una textura no muestra costuras entre partes unidas.

Un método puede pedir también el tiempo:

```python
class Pulse(Material):
    def glow(self, p, t):
        return 0.5 + 0.5 * sin(t * 4)
```

---

## Expresiones

Las cuentas con `t` o `p` no calculan un número: arman una fórmula que la placa
de video evalúa en cada cuadro y en cada punto. Por eso se usan estas funciones
y no las de `math`.

### Variables

| Nombre | Qué es |
|---|---|
| `T` | el tiempo, en segundos (lo mismo que el `t` de los métodos) |
| `P` | la posición sobre el objeto (lo mismo que el `p` de los métodos) |
| `p.x`, `p.y`, `p.z` | un componente de la posición |

### Operaciones

`+  -  *  /`, `-x`, `abs(x)` y `x ** n` funcionan directamente. Las tuplas de 3
números se convierten solas en vectores.

### Funciones

| Función | Devuelve |
|---|---|
| `sin(x)`, `cos(x)` | seno y coseno (en radianes) |
| `minimum(a, b)`, `maximum(a, b)` | el menor / el mayor |
| `clamp(x, lo, hi)` | `x` limitado a ese rango |
| `fract(x)` | la parte decimal (sirve para repetir) |
| `floor(x)` | la parte entera |
| `length(v)` | el largo de un vector |
| `vec(x, y, z)` | arma un vector a partir de tres fórmulas |
| `mix(a, b, k)` | mezcla: `k=0` da `a`, `k=1` da `b` |
| `smoothstep(a, b, x)` | transición suave: `0` si `x<a`, `1` si `x>b` (si `a>b`, al revés) |
| `step(edge, x)` | transición dura: `0` si `x<edge`, `1` si no |
| `noise(p)` | ruido suave entre 0 y 1 |
| `noise_at(x, y, z)` | el mismo ruido, pero calculado en Python para un punto fijo: devuelve un número común. Sirve para ubicar cosas sobre algo hecho con `noise` (por ejemplo, saber la altura de un piso con lomas) |
| `fbm(p)` | ruido con más detalle fino, entre 0 y 1 |
| `checker(p, size=1.0)` | damero sobre el plano xz: `0` o `1` |
| `stripes(x, width=0.2)` | rayas a lo largo de una coordenada: `0` o `1` |

### Recetas

```python
0.1 * abs(sin(t * 3))                       # rebote
12 * sin(t * 3)                             # vaivén (en grados, para rotation)
mix(color_a, color_b, noise(p * 5))         # variación suave de color
smoothstep(0.70, 0.76, noise(p * 38))       # manchas o pecas (máscara 0..1)
mix(color_a, color_b, stripes(p.x, 0.03))   # rayas
smoothstep(0.0, 0.2, p.y)                   # degradé de abajo hacia arriba
```

---

## Scene, Camera, Light, Ground

```python
class CritterScene(Scene):
    critter = Critter                                  # todo modelo o forma se dibuja
    camera = Camera(target=(0, 0.75, 0), distance=4.2, yaw=25, pitch=12)
    light = Light(direction=(0.6, 0.8, 0.5))
```

Forma corta: `scene = Scene(shape1, shape2, camera=Camera(...))`.

Una escena todavía sin modelos también funciona: muestra el piso y el cielo.
Sirve para arrancar un archivo desde cero con el visor ya abierto.

| Propiedad de `Scene` | Por defecto | Qué es |
|---|---|---|
| `camera` | `Camera()` | |
| `light` | `Light()` | |
| `ground` | damero gris en `y=0` | `None` lo quita; `Ground(height=..., material=...)` lo cambia |
| `background` | celeste | `(color_arriba, color_abajo)` |
| `ambient` | azul cielo `(0.60, 0.75, 1.00)` | color de la luz de relleno: el tono que toma lo que queda en sombra. Cálido para interiores o bosques |
| `quality` | `1` | `2` suaviza los bordes (4 veces más lento) |
| `models` | `None` | lista explícita de lo que se dibuja (opcional) |

| Clase | Parámetros (valor por defecto) |
|---|---|
| `Camera` | `target=(0, 0.5, 0)`, `distance=4.0`, `yaw=25` (giro), `pitch=15` (elevación), `lens=2.0` (más grande = más zoom, menos perspectiva) |
| `Light` | `direction=(0.5, 0.7, 0.5)` (desde dónde viene), `color=(1.0, 0.95, 0.85)`, `intensity=1.0` |
| `Ground` | `height=0.0`, `material=None`. `height` también puede ser una función de la posición, para un piso con lomas: `Ground(height=lambda p: 0.5 * noise(p * 0.2))` (usar `p.x` y `p.z`, pendientes suaves). Con lomas, `top=` es un acelerador opcional: una altura que las lomas nunca superan; por encima de ella no se calculan. Si queda baja, las cimas se ven cortadas |

Además de la luz principal, el render agrega solo: luz de cielo, rebote del
suelo, sombras suaves y oclusión ambiental. No se configuran.

---

## El visor

```bash
python -m sculpt archivo.py [--port 8770] [--out carpeta] [--once]
```

- Toma la última subclase de `Scene` definida en el archivo, o una variable `scene`.
- Escribe `build/<nombre>/`. El shader queda en `scene.glsl`, legible: sirve para
  comparar lo escrito en Python con el GLSL que salió.
- Se regenera al guardar el archivo, los `.py` de su carpeta o la librería.
- `--once` genera los archivos y sale, sin servidor.

| Control | Acción |
|---|---|
| arrastrar | girar la cámara |
| rueda | zoom |
| espacio | pausa |
| `R` | reiniciar tiempo y cámara |
| `1` `2` `3` | resolución baja / media / completa |

Si la escena tiene un error de Python, aparece en la terminal y el visor sigue
mostrando la última versión que funcionó. Si el error es de GLSL, aparece en
rojo sobre la página.

### Exportar a video

```bash
python -m sculpt archivo.py --video salida.mp4 [--size 1080x1920] [--seconds 8] [--fps 30] [--zoom 1.0] [--sway 0]
```

Abre una pestaña del navegador que dibuja el video y lo guarda en `salida.mp4`.
Por defecto es vertical (1080x1920), pensado para el celular.

| Opción | Qué hace |
|---|---|
| `--size ANCHOxALTO` | tamaño del video; `1920x1080` lo hace horizontal |
| `--seconds` | duración |
| `--fps` | cuadros por segundo |
| `--zoom` | aleja (más de 1) o acerca (menos de 1) la cámara de la escena. En vertical suele hacer falta alejarla, por ejemplo `1.5` |
| `--sway` | grados que la cámara se hamaca hacia los costados, ida y vuelta, a lo largo del video |
| `--no-open` | no abre el navegador: imprime el link para abrirlo a mano |

Cómo funciona: primero dibuja cada cuadro en su instante exacto, tarde lo que
tarde (por eso el video sale fluido aunque el visor ande lento); después los
reproduce a velocidad real mientras los graba. La pestaña tiene que quedar
visible hasta que diga `saved`. No necesita instalar nada: codifica el
navegador (MP4 con H.264 si lo soporta, WebM si no).

---

## Cosas que suelen confundir

- **`if` no funciona con fórmulas.** `if p.y > 0:` falla porque `p.y` no es un
  número. Se reemplaza por `step` o `smoothstep` más `mix`.
- **`min`, `max` y `math.sin` tampoco.** Usar `minimum`, `maximum`, y `sin`/`cos`
  de esta librería.
- **El color no se funde en una unión suave.** La forma sí; el material cambia
  de golpe en el borde. Para una transición de color, pintá todo con un solo
  material y hacé la mezcla adentro de `color` con `p`.
- **`mirror` necesita la forma del lado positivo.** Si queda en `x < 0`, desaparece.
- **`scale` es uniforme.** Para estirar en un solo eje, cambiá los tamaños de la
  forma (`Ellipsoid`, `Box`).
- **Las rotaciones pasan por el origen.** Rotá antes de mover.
- **Un `bump` grande se ve mal.** Por encima de `0.02` aparecen artefactos: es
  relieve falso, no geometría.
- **Formas muy finas pueden mostrar agujeros.** Pasa con elipsoides muy chatos;
  engrosarlos un poco lo resuelve.

## Lo que todavía no existe

- Fundido de materiales en uniones suaves.
- Deformaciones: torcer, repetir en ronda (alrededor de un eje), estirar en un eje, doblar formas que no sean verticales (para eso: `bend` primero, `rotate` después).
- Curvas con más de un doblez (una `Curve` dobla una sola vez; se encadenan varias) y mechones chatos como los del pelo.
- Luces adicionales o configurables más allá de la principal.
- Varios pases: desenfoque por profundidad, contornos de dibujo.
- Texturas de imagen (solo hay patrones calculados).

---

## Archivos

| Archivo | Qué tiene |
|---|---|
| `expr.py` | expresiones: `T`, `P` y las funciones |
| `shapes.py` | formas, transformaciones, combinaciones y `Material` |
| `model.py` | `Model` |
| `scene.py` | `Scene`, `Camera`, `Light`, `Ground` y el generador de GLSL |
| `__main__.py` | el comando del visor |
| `template/` | la página del visor y la biblioteca GLSL fija |

Para extender la librería también se exportan tres piezas internas: `Shape` (la
clase base de toda forma), `Expr` (una fórmula) y `E(x)` (convierte un número o
una tupla en fórmula). No hacen falta para modelar.
