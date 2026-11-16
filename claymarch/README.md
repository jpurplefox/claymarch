# claymarch

Describe 3D scenes in Python and translate them to a GLSL shader (raymarching
of signed distance functions).

```bash
python -m claymarch my_scene.py
```

Open `http://localhost:8770`. When the file is saved, the page updates itself.

---

## Contents

1. [Minimal example](#minimal-example)
2. [The central rule](#the-central-rule)
3. [Shapes](#shapes)
4. [Properties](#properties)
5. [Model](#model)
6. [Drawings on a surface](#drawings-on-a-surface)
7. [Material](#material)
8. [Expressions](#expressions)
9. [Scene, Camera, Light, Ground](#scene-camera-light-ground)
10. [The viewer](#the-viewer)
11. [Common pitfalls](#common-pitfalls)
12. [What cannot be declared](#what-cannot-be-declared)
13. [What does not exist yet](#what-does-not-exist-yet)

---

## Minimal example

```python
import claymarch


class Red(claymarch.Material):
    color = (0.9, 0.3, 0.2)


class Ball(claymarch.Model):
    body = claymarch.Sphere(0.5, position=(0, 0.5, 0))

    material = Red

    def position(self, t):
        # It bounces.
        return (0, 0.3 * abs(claymarch.sin(t * 3)), 0)


class MyScene(claymarch.Scene):
    ball = Ball
```

Everything is described with classes and properties: which pieces there are,
where each one goes and what it is made of. Nothing has to be called to put
the scene together.

## The central rule

**Every property is a value, or a method that returns the value.**

| In a...    | the method receives     | to                 |
|------------|-------------------------|--------------------|
| `Model`    | `t` (time in seconds)   | animate            |
| `Material` | `p` (position), and `t` if it asks for a second parameter | draw on the object |

```python
class Thing(claymarch.Model):
    size = 1.0  # a fixed value


class Thing(claymarch.Model):
    def size(self, t):  # or a method of time
        return 1 + 0.1 * claymarch.sin(t * 4)
```

Coordinate system: `y` is up, `z` points towards the camera by default, `x`
to the right. Units are arbitrary; the examples here are about 1 unit tall.
Angles are **in degrees**.

---

## Shapes

All of them are centered at the origin unless noted.

| Shape | Parameters (default) | Notes |
|---|---|---|
| `Sphere(radius=0.5)` | | |
| `Ellipsoid(rx=0.5, ry=0.5, rz=0.5)` | one radius per axis | the base for rounded, irregular volumes |
| `Box(width=1, height=1, depth=1, rounding=0)` | full sizes | `rounding` rounds the edges without growing the box |
| `Capsule(start=(0,0,0), end=(0,1,0), radius=0.2, radius2=None)` | a thick segment | with `radius2` it tapers towards `end` |
| `Curve(start=(0,0,0), control=(0,1,0), end=(1,1,0), radius=0.2, radius2=None)` | a thick curved line | a parabola arc from `start` to `end`; `control` is where it bulges towards (the curve does not pass through it). With `radius2` it tapers |
| `Path(points, radius=0.1, closed=False, radius2=None)` | a tube that follows a list of points | a chain of `Curve`s. With `radius2` it tapers from the first point to the last, the same amount on every bend (not on a closed one); without it the thickness is the same all along. `points` is a list of `(x, y, z)`, two or more. The tube starts at the first point and ends at the last; each point in between is where it is pulled towards, one bend for each (like the `control` of a `Curve`, it does not pass through them). With three points it is exactly a `Curve`. `closed=True` makes a loop (three or more points): every point pulls and none is touched. The points are plain numbers: they cannot change with `t` |
| `Cylinder(radius=0.5, height=1, rounding=0)` | vertical | |
| `Torus(radius=0.5, thickness=0.15)` | lying flat (vertical axis) | |
| `Cone(radius=0.3, height=1)` | base at the origin, tip pointing up | the base is rounded |
| `CutCone(radius=0.5, radius2=0.25, height=1, rounding=0)` | a cone without its tip, vertical and centered | `radius` is the bottom, `radius2` the top; both faces are flat. `rounding` rounds the edges without growing it |

After its own measures, every shape accepts the [properties](#properties) as
keyword arguments:

```python
claymarch.Torus(0.15, 0.03, rotation=(90, 0, 0), position=(0.44, 0, 0))
claymarch.Box(
    0.08, 0.7, 0.08,
    position=(0.4, 0.35, 0.25),
    symmetry="x",
)
```

---

## Properties

They are the same for a shape and for a `Model`. On a shape they are keyword
arguments; on a `Model` they are class attributes (or keyword arguments when
it is used: `Lamp(position=(1, 0, 0))`).

| Property | Default | What it is |
|---|---|---|
| `material` | `None` | what it is painted with (a `Material`, instance or class) |
| `size` | `1.0` | uniform scale |
| `rotation` | `(0, 0, 0)` | degrees around x, y, z (applied in that order) |
| `position` | `(0, 0, 0)` | where it goes |
| `bend` | `(0, 0)` | curvature of a vertical piece: degrees per unit of height, `(around x, around z)`. For gentle curves; large values distort the piece |
| `symmetry` | `None` | `"x"`, `"y"` or `"z"`: whatever is on the positive side of that axis is copied to the negative side. Model one of a pair and get both |
| `carve` | `None` | the role of the piece inside a model: it is cut out (see [The role of each part](#the-role-of-each-part)) |
| `join` | `None` | the role of the piece inside a model: it is added, blended |

**They are always applied in that order**, no matter how they are written:
first it is painted, then `size`, `rotation`, `position`, `bend` and
`symmetry`.

- Painting comes before placing: textures stay glued to the piece and move
  with it.
- `size` and `rotation` act around the origin of the piece. For something to
  turn from its base (a lever, a lid), model it with the base at the origin
  and take it to its place with `position`.
- `bend` comes after `position`: it curves the piece once placed, according
  to its height.
- For `symmetry`, the piece has to end up on the **positive** side of the
  axis.

Any of them can be a function of time:

```python
def wobble(size, i):
    return lambda t: size * (1 + 0.03 * claymarch.sin(t * 3 - i * 0.9))


ball = Ball(size=wobble(0.88, 1))
```

---

## Model

A thing made of parts, described as a class.

```python
class Lamp(claymarch.Model):
    base = claymarch.Cylinder(0.3, 0.06, position=(0, 0.03, 0))
    pole = claymarch.Capsule((0, 0, 0), (0, 1, 0), 0.03)
    shade = claymarch.CutCone(0.25, 0.12, 0.3, position=(0, 1.1, 0))

    smooth = 0.02
    material = brass

    def rotation(self, t):
        return (0, 0, 4 * claymarch.sin(t * 2))
```

### Parts

Every class attribute that is a shape, a model or a drawing becomes a part,
**in the order it is written**. A model can be a part of another one, with or
without parentheses:

```python
class Desk(claymarch.Model):
    table = Table  # the class itself
    lamp = Lamp(position=(0.3, 0.75, 0))  # or an instance, to change something
```

Attributes that start with `_` never count as parts.

### Model properties

Besides the common [properties](#properties), a `Model` has:

| Property | Default | What it is |
|---|---|---|
| `smooth` | `0.0` | the radius the parts blend into each other with: with `0` they meet at a sharp edge, with `0.1` they melt together like clay |
| `material` | `None` | the material for the parts that have none of their own |
| `bounds` | `None` | a speed-up: a sphere that contains the whole model (in its own space, before `size`/`rotation`/`position`). Far from the sphere the model is not computed. Left at `None` the sphere is worked out from the parts, so there is nothing to write. A radius, or `(center, radius)`, sets it by hand: it does not change the picture if the sphere really contains the model; if it is too small, the model is clipped. `False` leaves the model without a sphere. Shadows and occlusion ignore the sphere |

Internal order: the parts are put together → painted → `bounds` → `size` →
`rotation` → `position` → `bend` → `symmetry`.

The sphere is worked out on its own when:

- every measure of the parts is a plain number. A part whose `position` or
  `size` changes with `t`, a `bend` or a repetition leaves the model (and
  the models that contain it) without a sphere; a `rotation` that changes
  with `t` does not, because the part stays inside the sphere it sweeps;
- the model is simply added to its neighbors. A model that blends with them
  (the `smooth` of the model it is a part of, or its own `join`) or that is
  carved out of them gets none: the sphere would show in the blend;
- it is worth it: a model made of one or two simple shapes gets none.

For a model the library cannot measure, a `bounds` written by hand still
works as before.

### The role of each part

Parts are applied in the order they are written, and each one says what it
does to what came before it:

```python
class Mug(claymarch.Model):
    # The first one: the base.
    body = claymarch.Cylinder(0.3, 0.6, rounding=0.03)
    # Drawn on what came before.
    logo = Badge(patch=(0, 0, 0.3))
    # Cut out of what came before.
    hollow = claymarch.Cylinder(
        0.26, 0.6,
        position=(0, 0.06, 0),
        carve=0.01,
    )
    # Added, blended.
    handle = claymarch.Torus(
        0.15, 0.03,
        rotation=(90, 0, 0),
        position=(0.44, 0, 0),
        join=0.03,
    )
```

| The part has | What it does |
|---|---|
| nothing | it is added to what came before, with the model's `smooth` |
| `carve=0.01` | it is cut out of everything before it. The number softens the edge of the cut; `carve=True` leaves it sharp |
| `join=0.03` | it is added, blended with what came before, with that radius instead of the model's `smooth`. `join=0` adds it without blending |
| `patch=(x, y, z)` | only for `Disc` and `Drawing`: it is drawn on what came before, at that point (see [Drawings on a surface](#drawings-on-a-surface)) |
| `engrave=(x, y, z)` | only for `Drawing`: it is sunk into what came before, at that point (see [Drawings on a surface](#drawings-on-a-surface)) |

- **Order matters.** In `Mug` the handle comes after the hollow: if it came
  before, the hollow would cut into it too.
- `carve` and `join` act on **everything** before them in that model, and
  nothing else. If a cut has to affect a single piece, that piece and its cut
  go in a model of their own.
- `join=0` is for a model that has `smooth` but where one part must not
  blend: otherwise the blend would fatten it.

### Parameters of your own

Any class attribute is a parameter that can be changed when the model is
used. Properties read it from a method:

```python
class Lamp(claymarch.Model):
    pole = claymarch.Capsule((0, 0, 0), (0, 1, 0), 0.03)

    tilt = 0  # how far it leans, in degrees

    def rotation(self, t):
        return (0, 0, self.tilt + 4 * claymarch.sin(t * 2))


lamp = Lamp(tilt=20)
```

Only a name the class already has can be passed: `Lamp(tlit=20)` is an error.

### Variants without another class

```python
Lamp(position=(-1.5, 0, 0.5), size=1.6, rotation=(0, 40, 0))
```

To change parts, inherit and redefine only what changes:

```python
class TallLamp(Lamp):
    pole = claymarch.Capsule((0, 0, 0), (0, 1.6, 0), 0.03)
    shade = claymarch.CutCone(0.25, 0.12, 0.3, position=(0, 1.7, 0))
```

---

## Drawings on a surface

For a mark, a ring or a spot that must not stick out: instead of resting
another shape on top, a drawing is pasted on the surface. The drawing is
defined on its own, without knowing what it goes on; the model that uses it
says where.

```python
class Badge(claymarch.Drawing):
    rim = claymarch.Disc(0.20, material=yellow)
    # Written later: it ends up on top.
    center = claymarch.Disc(0.13, material=black)
    # Shifted from the center of the drawing.
    dot = claymarch.Disc(0.045, material=white, at=(-0.04, 0.06, 0.05))


class Mug(claymarch.Model):
    body = claymarch.Cylinder(0.3, 0.6, rounding=0.03)
    logo = Badge(patch=(0, 0, 0.3))


class Buoy(claymarch.Model):
    body = claymarch.Ellipsoid(0.39, 0.33, 0.34)
    ring = claymarch.Disc(
        0.12, inner=0.08,
        material=white,
        patch=(0.36, 0, -0.10),
        symmetry="x",
    )
```

| | |
|---|---|
| `Disc(radius, inner=0, material=None, at=(0, 0, 0))` | one layer: a disc of that radius. `inner` leaves a hole in the middle (a ring). `at` shifts it from the center of the drawing |
| `Line(start, end, width=0.02, material=None)` | one layer: a straight stroke with round ends. `start` and `end` are measured from the center of the drawing: `(x, y, z)`, or `(x, y)` for `z = 0`. Only in a drawing that has a `facing` |
| `Path(points, radius)` | one layer: a curved stroke, the same `Path` of the shapes table used inside a drawing. Its points are measured from the center of the drawing and `radius` is half the width of the stroke (one plain number, no `radius2`). Like a `Line`, only in a drawing that has a `facing` |
| `Drawing` | a class to inherit from: its `Disc`, `Line` and `Path` attributes are the layers, stacked in the order they are written (the first one at the bottom). When the layers are easier to compute, a `parts` list (or a method that returns it) replaces the attributes |

Used as a part of a model, `Disc` and `Drawing` accept:

| Property | What it is |
|---|---|
| `patch=(x, y, z)` | the point of the surface where the center of the drawing goes |
| `symmetry="x"` | repeats it on the other side |
| `lift=0.006` | how far each layer rises above the previous one. In a `Drawing` it can also be set on the class (`lift = 0.004`) |
| `size=0.8` | `Drawing` only: shrinks or enlarges the whole drawing |

### Engraving

The same drawing can be sunk into the surface instead of painted on it: a
groove with a floor that follows the surface.

```python
class Cross(claymarch.Drawing):
    ring = claymarch.Disc(0.30, inner=0.27)
    down = claymarch.Line((0, -0.45), (0, 0.45), 0.03)
    across = claymarch.Line((-0.45, 0), (0.45, 0), 0.03)

    facing = "z"
    depth = 0.02
    smooth = 0.01


class Lid(claymarch.Model):
    top = claymarch.Ellipsoid(0.6, 0.5, 0.4)
    mark = Cross(engrave=(0, 0, 0.4))
```

A `Drawing` accepts these as well, as keywords or set on the class:

| Property | What it is |
|---|---|
| `engrave=(x, y, z)` | instead of `patch`: the point of the surface where the center of the drawing goes, sunk in. The materials of the layers are not used: the groove keeps the color of the piece |
| `symmetry="x"` | repeats it on the other side. Like the other properties, it can be set on the class |
| `depth=0.01` | how deep the groove is |
| `smooth=0` | rounds the edge of the groove |
| `facing=None` | the direction the drawing looks at, away from the surface: `(x, y, z)`, or one of `"x"`, `"-x"`, `"y"`, `"-y"`, `"z"`, `"-z"`. It works for `patch` too |
| `reach=None` | with `facing`: how far behind its point the drawing still marks the surface. Left out, it reaches the origin of the piece |

- **Without `facing`** only discs can be drawn. A disc is whatever of the
  surface is closer to its center than its radius, so it needs no direction
  and it sits well on any surface.
- **With `facing`** the drawing is flat and it is stamped on the surface
  along that direction, like a slide projector would. Lines and paths need it: a
  drawing with a `Line` or a `Path` and no `facing` is an error. The part of a point
  that runs along `facing` is ignored.
- `reach` keeps the drawing from coming out on the other side of the piece.
  The default suits a piece centered on its origin with the drawing in
  front of it; in any other case set it (it is an error to leave it out when
  the point is not in front of the origin).
- A stamped drawing stretches where the surface turns away from `facing`:
  a line near the silhouette gets wider.

- It is drawn on **everything** before it in that model, and nothing else.
  That is why it is best written right after its base and not at the end: it
  renders faster and the `smooth` of the pieces that come later does not
  affect it.
- Each disc is a piece of the same surface, barely raised: it follows the
  surface even if the piece changes size, and its edge stays crisp.
- `patch` has to be on the surface or very close to it; if it is far, the
  drawing does not show.
- **How much it sticks out** is decided by `lift`. The first layer rises
  `lift` above the surface, the second one twice that, the third one three
  times. Smaller looks more painted on; larger looks more like a plate
  resting on it. If it is too small (below 0.002, roughly) the layers show
  holes.

---

## Material

```python
class Clay(claymarch.Material):
    specular = 0.30

    def color(self, p):
        base = claymarch.mix(
            (0.26, 0.66, 0.58), (0.34, 0.76, 0.64), claymarch.noise(p * 5.0)
        )
        specks = claymarch.smoothstep(0.70, 0.76, claymarch.noise(p * 38.0))
        return claymarch.mix(base, (0.16, 0.45, 0.42), 0.7 * specks)

    def bump(self, p):
        fine = 0.0022 * claymarch.fbm(p * 60.0)
        return fine + 0.003 * claymarch.noise(p * 14.0)
```

For plain materials the values are enough, on the class or when creating it:

```python
class Paint(claymarch.Material):
    color = (0.42, 0.80, 0.30)


green = Paint()
yellow = Paint(color=(1, 0.85, 0.15))
dark = claymarch.Material(color=(0.10, 0.10, 0.13), specular=0.9, shininess=80)
```

| Property | Default | What it is |
|---|---|---|
| `color` | `(0.8, 0.8, 0.8)` | `(r, g, b)` between 0 and 1, as seen on screen |
| `specular` | `0.2` | strength of the light's highlight (`0` = matte) |
| `shininess` | `32.0` | how small and sharp that highlight is |
| `glow` | `0.0` | light of its own |
| `bump` | `None` | relief: how much the surface sinks (+) or rises (−) |

A material only knows those names. Any other attribute (`base = ...`) is
yours: a method can read it with `self.base`, but on its own it changes
nothing.

**`bump`** only changes how light hits the surface, not the silhouette (it is
the equivalent of a normal map). Use small values, between `0.001` and
`0.01`. The number that multiplies `p` is the grain size (larger = finer);
the one that multiplies the noise is the depth.

**`p`** is the position in the space of the piece or model that carries the
material, before it is placed. All the parts of a model painted by its
`material` share that space: a texture shows no seams between them.

A method can also ask for time:

```python
class Pulse(claymarch.Material):
    def glow(self, p, t):
        return 0.5 + 0.5 * claymarch.sin(t * 4)
```

---

## Expressions

Arithmetic with `t` or `p` does not compute a number: it builds a formula
that the graphics card evaluates on every frame and at every point. That is
why these functions are used instead of the ones in `math`.

### Variables

| Name | What it is |
|---|---|
| `claymarch.T` | time, in seconds (the same as the `t` of the methods) |
| `claymarch.P` | the position on the object (the same as the `p` of the methods) |
| `p.x`, `p.y`, `p.z` | one component of the position |

### Operations

`+  -  *  /`, `-x`, `abs(x)` and `x ** n` work directly. Tuples of 3 numbers
become vectors on their own.

### Functions

All of them are used as `claymarch.sin(...)`.

| Function | Returns |
|---|---|
| `sin(x)`, `cos(x)` | sine and cosine (in radians) |
| `minimum(a, b)`, `maximum(a, b)` | the smaller / the larger |
| `clamp(x, lo, hi)` | `x` limited to that range |
| `fract(x)` | the fractional part (useful for repeating) |
| `floor(x)` | the integer part |
| `length(v)` | the length of a vector |
| `vec(x, y, z)` | builds a vector from three formulas |
| `mix(a, b, k)` | blend: `k=0` gives `a`, `k=1` gives `b` |
| `smoothstep(a, b, x)` | smooth transition: `0` if `x<a`, `1` if `x>b` (if `a>b`, the other way round) |
| `step(edge, x)` | hard transition: `0` if `x<edge`, `1` otherwise |
| `noise(p)` | smooth noise between 0 and 1 |
| `noise_at(x, y, z)` | the same noise, but computed in Python for a fixed point: it returns a plain number. Useful to place things on something made with `noise` (for example, to know the height of a hilly ground) |
| `fbm(p)` | noise with more fine detail, between 0 and 1 |
| `checker(p, size=1.0)` | a checkerboard on the xz plane: `0` or `1` |
| `stripes(x, width=0.2)` | stripes along one coordinate: `0` or `1` |

### Recipes

```python
0.1 * abs(claymarch.sin(t * 3))  # bounce
12 * claymarch.sin(t * 3)  # sway (in degrees, for rotation)
claymarch.mix(color_a, color_b, claymarch.noise(p * 5))  # soft color variation
claymarch.smoothstep(0.70, 0.76, claymarch.noise(p * 38))  # spots
claymarch.mix(color_a, color_b, claymarch.stripes(p.x, 0.03))  # stripes
claymarch.smoothstep(0.0, 0.2, p.y)  # gradient from the bottom up
```

---

## Scene, Camera, Light, Ground

```python
class DeskScene(claymarch.Scene):
    desk = Desk  # every model or shape is drawn
    camera = claymarch.Camera(
        target=(0, 0.75, 0), distance=4.2, yaw=25, pitch=12
    )
    light = claymarch.Light(direction=(0.6, 0.8, 0.5))
```

A scene with no models yet also works: it shows the ground and the sky.
Useful to start a file from scratch with the viewer already open.

| `Scene` property | Default | What it is |
|---|---|---|
| `camera` | `Camera()` | |
| `light` | `Light()` | |
| `ground` | a grey checkerboard at `y=0` | `None` removes it; `Ground(height=..., material=...)` changes it |
| `background` | light blue | `(top_color, bottom_color)` |
| `ambient` | sky blue `(0.60, 0.75, 1.00)` | the color of the fill light: the tone of whatever is in shadow. Warm for interiors |
| `quality` | `1` | `2` smooths the edges (4 times slower) |

| Class | Parameters (default) |
|---|---|
| `Camera` | `target=(0, 0.5, 0)` (the point it looks at), `distance=4.0`, `yaw=25` (turn around that point, sideways), `pitch=15` (elevation: 0 looks straight on, higher looks from above), `lens=2.0` (larger = more zoom, less perspective) |
| `Light` | `direction=(0.5, 0.7, 0.5)` (where it comes from), `color=(1.0, 0.95, 0.85)`, `intensity=1.0` |
| `Ground` | `height=0.0`, `material=None`. `height` can also be a function of the position, for a hilly ground: `Ground(height=lambda p: 0.5 * claymarch.noise(p * 0.2))` (use `p.x` and `p.z`, gentle slopes). With hills, `top=` is an optional speed-up: a height the hills never exceed; above it they are not computed. If it is too low, the hilltops look cut off |

Besides the main light, the render adds on its own: sky light, bounce from
the ground, soft shadows and ambient occlusion. They are not configurable.

---

## The viewer

```bash
python -m claymarch file.py [--port 8770] [--out folder] [--once]
```

- It takes the last `Scene` subclass defined in the file.
- It writes `build/<name>/`. The shader is in `scene.glsl`, readable: useful
  to compare what was written in Python with the GLSL that came out.
- It is generated again when the file, the `.py` files in its folder or the
  library are saved.
- `--once` generates the files and exits, without a server.

| Control | Action |
|---|---|
| drag | orbit the camera |
| wheel | zoom |
| space | pause |
| `R` | reset time and camera |
| `1` `2` `3` | low / medium / full resolution |

If the scene has a Python error, it shows in the terminal and the viewer keeps
showing the last version that worked. If the error is in the GLSL, it shows
in red over the page.

### Exporting a video

```bash
python -m claymarch file.py --video out.mp4 [--size 1080x1920] [--seconds 8] [--fps 30] [--zoom 1.0] [--sway 0]
```

It opens a browser tab that draws the video and saves it to `out.mp4`. By
default it is vertical (1080x1920), meant for a phone.

| Option | What it does |
|---|---|
| `--size WIDTHxHEIGHT` | size of the video; `1920x1080` makes it horizontal |
| `--seconds` | duration |
| `--fps` | frames per second |
| `--zoom` | moves the camera away from (above 1) or closer to (below 1) the scene. Vertical videos usually need it further away, for example `1.5` |
| `--sway` | degrees the camera swings sideways, there and back, along the video |
| `--no-open` | does not open the browser: prints the link to open it by hand |

How it works: first it draws every frame at its exact instant, however long
that takes (so the video is smooth even if the viewer runs slowly); then it
plays them back at real speed while recording. The tab has to stay visible
until it says `saved`. Nothing needs to be installed: the browser does the
encoding (MP4 with H.264 if supported, WebM otherwise).

---

## Common pitfalls

- **A name claymarch does not know is not an error.** `base = GREEN` in a
  `Material` does not paint it: the color is called `color`. And if a class
  defines the same property twice (`rotation = ...` and further down
  `def rotation`), the last one wins.
- **The order of the parts changes the result.** A `carve` cuts everything
  written before it; a drawing is pasted on everything written before it.
- **The order of the properties changes nothing.** They are always applied
  the same way: `size`, `rotation`, `position`, `bend`, `symmetry`.
- **`if` does not work with formulas.** `if p.y > 0:` fails because `p.y` is
  not a number. Use `step` or `smoothstep` together with `mix` instead.
- **Neither do `min`, `max` and `math.sin`.** Use `claymarch.minimum`,
  `claymarch.maximum`, `claymarch.sin` and `claymarch.cos`.
- **Color does not blend in a smooth union.** The shape does; the material
  changes abruptly at the edge. For a color transition, paint everything
  with a single material and do the blend inside `color` with `p`.
- **`symmetry` needs the piece on the positive side.** If it ends up at
  `x < 0`, it disappears.
- **`size` is uniform.** To stretch along one axis, change the measures of
  the shape (`Ellipsoid`, `Box`).
- **A large `bump` looks wrong.** Above `0.02` artifacts appear: it is fake
  relief, not geometry.
- **Very thin shapes can show holes.** It happens with very flat ellipsoids;
  making them a little thicker fixes it.

---

## What cannot be declared

Four things do not have a property yet.

### Repeating

`repeat` splits space into cells and puts one copy in each. The piece is
computed only once, so a thousand copies cost the same as one. It is a
method: it is called on the shape or the model.

```python
def away_from_center(c):
    # c is the center of the cell: no copies closer than 14 to the origin.
    return claymarch.step(14, claymarch.length(c))


class Hall(claymarch.Scene):
    columns = Column().repeat(
        x=22, z=22,
        jitter=2.0,
        size=(0.8, 1.5),
        spin=True,
        where=away_from_center,
    )
```

| Option | What it does |
|---|---|
| `x`, `y`, `z` | distance between copies along each axis (0 = not repeated along that axis) |
| `limit` | how many copies on each side of the middle one (`limit=2` is 5); without `limit` they never end |
| `jitter` | each copy is shifted from its place by a random distance, up to that value |
| `size` | `(minimum, maximum)`: each copy gets a random size between those two |
| `spin` | `True` turns each copy a random angle around the vertical |
| `where` | a function of the center of each cell: above 0.5 there is a copy, otherwise the cell stays empty |
| `seed` | another number gives another random layout |

- **Each copy has to fit in its cell**, which reaches half the distance to
  each side. Count the `jitter` and the maximum size, and leave a margin of
  0.1. If it does not fit, it looks cut at the edge of the cell.
- The piece is repeated around the origin: there is a copy at the origin,
  another one a distance away, another one two distances away. To shift the
  whole grid, add `.move(y=-0.4)` after the `repeat`.
- The randomness is always the same for the same cell: it does not change
  from one frame to the next.
- All the copies are animated alike and carry the same texture.

### Intersection

What two shapes have in common is written with `&`, inside a `parts` list:

```python
class Lens(claymarch.Model):
    parts = [
        claymarch.Sphere(0.5, position=(0.3, 0, 0))
        & claymarch.Sphere(0.5, position=(-0.3, 0, 0))
    ]
```

When `parts` is defined, the other attributes of the class do not count as
parts.

### Parts that depend on a parameter

A part written as an attribute cannot read `self`. If its measures depend on
a parameter of the model, `parts` is written as a method:

```python
class Plank(claymarch.Model):
    length = 1.0

    def parts(self):
        half = self.length / 2
        return [claymarch.Box(0.2, self.length, 0.04, position=(0, half, 0))]
```

`parts` can also receive `t`, like any property.

### Another order of turns

Properties are applied in a fixed order. When another one is needed (turning
after bending, for example), the piece is wrapped in a model: the inner one
bends, the outer one turns.

---

## What does not exist yet

- Blending of materials in smooth unions.
- Deformations: twisting, repeating in a ring (around an axis), stretching
  along one axis, bending pieces that are not vertical.
- A `Path` with a different thickness at each point, or whose points
  move with `t`, and flat ribbons.
- Additional or configurable lights beyond the main one.
- Several passes: depth of field, outlines.
- Image textures (there are only computed patterns).

---

## Files

| File | What it has |
|---|---|
| `expr.py` | expressions: `T`, `P` and the functions |
| `shapes.py` | shapes, properties, drawings and `Material` |
| `model.py` | `Model` |
| `scene.py` | `Scene`, `Camera`, `Light`, `Ground` and the GLSL generator |
| `__main__.py` | the viewer command |
| `template/` | the viewer page and the fixed GLSL library |
