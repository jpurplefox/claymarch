"""Shapes and operations. Every object knows how to write its piece of GLSL.

A scene is a tree: the leaves are primitives (Sphere, Box...) and the inner
nodes are transforms (move, rotate) and combinations (union, subtract). To
generate the shader the tree is walked and every node adds lines to map(), the
distance function (SDF) of the whole scene.
"""
import inspect
import math
import re

from .expr import E, Expr, P, T, _num


class Material:
    """How a surface looks. Use it directly or, better, as a class:

        skin = Material(color=(0.3, 0.7, 0.6), specular=0.3)

        class Skin(Material):
            specular = 0.3                       # a fixed value...

            def color(self, p):                  # ...or a method of the position p
                return mix((0.26, 0.66, 0.58), (0.34, 0.76, 0.64), noise(p * 5))

            def bump(self, p):
                return 0.002 * fbm(p * 60)

    The rule is the same as for Model: every property is either a VALUE, or a
    METHOD. A material method receives p (the position on the object) and, if
    it asks for a second parameter, t (time).

    color:     (r,g,b) between 0 and 1, as seen on screen.
    specular:  strength of the light reflection (0 = matte).
    shininess: how small and sharp that reflection is.
    glow:      light of its own (0 = none).
    bump:      relief texture: how much the surface sinks (positive) or sticks
               out (negative). Use small values (0.001 to 0.01). It only changes
               how light hits, not the silhouette: the equivalent of a "normal map".
    opacity:   1 = solid; less lets what is behind show through, tinted with
               the color and a little bent, like water or glass (0 = only the
               highlights are seen). Only the first see-through surface a
               ray meets is drawn: what is behind it is seen as if the other
               see-through things were not there.
    """
    color = (0.8, 0.8, 0.8)
    specular = 0.2
    shininess = 32.0
    glow = 0.0
    bump = None
    opacity = 1.0

    def __init__(self, color=None, **overrides):
        if color is not None:
            overrides["color"] = color
        for name, value in overrides.items():
            if not hasattr(Material, name):
                raise TypeError(f"Material has no property '{name}'")
            setattr(self, name, value)

    def value(self, name):
        """A property resolved: methods are called with (p) or (p, t)."""
        v = getattr(self, name)
        if callable(v):
            v = v(*(P, T)[:len(inspect.signature(v).parameters)])
        return v


def _see_through(m):
    """Does this material let what is behind it show?"""
    return m is not None and not (isinstance(m.opacity, (int, float)) and m.opacity >= 1)


def as_material(m):
    """Accept a Material instance or a Material subclass (used as a singleton)."""
    if isinstance(m, type) and issubclass(m, Material):
        if "_instance" not in vars(m):
            m._instance = m()
        return m._instance
    if isinstance(m, Material):
        return m
    raise TypeError(f"expected a Material or a Material subclass, got {m!r}")


class Context:
    """What accumulates while the tree is walked."""
    def __init__(self, base_material):
        self.lines, self.n = [], 0
        self.materials = [base_material]
        self.space = None        # coordinates of the innermost paint() (see _Paint)
        self.turned = 0          # >0 inside a rotation, bend or mirror (see _Repeat)

    def emit_turned(self, child, p, mat):
        """Emit a child whose axes no longer point the way the world's do."""
        self.turned += 1
        try:
            return child.emit(self, p, mat)
        finally:
            self.turned -= 1

    def var(self, prefix):
        self.n += 1
        return f"{prefix}{self.n}"

    def line(self, text):
        self.lines.append("    " + text)

    def material_id(self, m):
        if m is None:
            return 0
        for i, x in enumerate(self.materials):
            if x is m:
                return i
        self.materials.append(m)
        return len(self.materials) - 1


# ============================================================ how big it is
# Every shape can say how much room it takes: spheres() is a handful of
# spheres (center, radius) that together contain it, or None when that
# cannot be known ahead of time (it goes on forever, it is bent, or it moves
# with t). extent() is one sphere around them all. Models use it to wrap
# themselves in a bounding sphere without being told (see _Bound).
def _const(expr):
    """The plain number (or tuple of numbers) an Expr stands for, or None if
    it depends on something only known while drawing (t, the point...)."""
    code = expr.code
    if not re.fullmatch(r"[-+*/().,\s\deE]*", code.replace("vec3", "").replace("vec2", "")):
        return None
    try:
        return eval(code, {"__builtins__": {}}, {"vec3": lambda *c: c, "vec2": lambda *c: c})
    except Exception:
        return None


def _length(v):
    return math.sqrt(sum(c * c for c in v))


def _enclose(spheres):
    """One sphere around several: start in the middle of the box that holds
    them and keep stepping, less each time, toward whichever sticks out."""
    if not spheres:
        return None
    lows = [min(c[i] - r for c, r in spheres) for i in range(3)]
    highs = [max(c[i] + r for c, r in spheres) for i in range(3)]
    center = [(a + b) / 2 for a, b in zip(lows, highs)]
    def reach(center):
        return max((_length([a - b for a, b in zip(c, center)]) + r, c) for c, r in spheres)
    best = (reach(center)[0], tuple(center))
    for step in range(1, 60):
        _, far = reach(center)
        center = [a + (b - a) / (step + 1) for a, b in zip(center, far)]
        best = min(best, (reach(center)[0], tuple(center)))
    return best[1], best[0]


def _along(a, c, b, r1, r2, pieces=8):
    """Spheres that cover a parabola arc from a to b pulled toward c."""
    bulge = _length([p - 2 * q + r for p, q, r in zip(a, c, b)]) / (4 * pieces * pieces)
    found = []
    for i in range(pieces + 1):
        t = i / pieces
        point = tuple((1 - t) ** 2 * p + 2 * t * (1 - t) * q + t * t * r for p, q, r in zip(a, c, b))
        found.append((point, r1 + (r2 - r1) * t + bulge))
    return found


class Shape:
    """Base of everything that can be drawn."""

    # what this shape does when it is a part of a Model: None = it is added;
    # ("carve", smooth) = it is cut out of the parts before it;
    # ("join", smooth) = it is added, blended with the parts before it
    _role = None

    def emit(self, ctx, p, mat):
        """Write GLSL into ctx. Returns (distance, material, coords) as text."""
        raise NotImplementedError

    def spheres(self):
        """Spheres (center, radius) that together contain this shape, or None."""
        return None

    def extent(self):
        """One sphere (center, radius) that contains this shape, or None."""
        found = self.spheres()
        return None if found is None else _enclose(found)

    def weight(self):
        """Roughly how much work this shape is to compute."""
        return 1

    # --- transforms (return a new shape; they can be chained)
    def move(self, x=0.0, y=0.0, z=0.0):
        """Move by x, y, z. Also takes one point: move((0.4, 0.1, 0.2))."""
        if isinstance(x, (tuple, list)):
            if len(x) != 3:
                raise TypeError("move: a point has three numbers, (x, y, z)")
            if not (isinstance(y, (int, float)) and y == 0 and isinstance(z, (int, float)) and z == 0):
                raise TypeError("move takes a point OR x, y, z, not both")
            x, y, z = x
        return _Move(self, (x, y, z))
    def rotate_x(self, degrees):          return _Rotate(self, "yz", degrees)
    def rotate_y(self, degrees):          return _Rotate(self, "xz", degrees)
    def rotate_z(self, degrees):          return _Rotate(self, "xy", degrees)
    def scale(self, factor):              return _Scale(self, factor)
    def ripple(self, height, size=0.2, flow=(0.0, 0.0, 0.0)):
        """Uneven surface that moves: lumps about `size` across that rise and
        sink up to height/2, traveling at `flow` units per second."""
        return _Ripple(self, height, size, flow)
    def mirror(self, axis="x"):           return _Mirror(self, axis)
    def bend_x(self, degrees):            return _Bend(self, "yz", degrees)
    def bend_z(self, degrees):            return _Bend(self, "xy", degrees)

    def repeat(self, x=0.0, y=0.0, z=0.0, limit=None, jitter=0.0, size=None,
               spin=False, where=None, seed=0):
        """Copies of the shape on a grid, for the price of one.

        x, y, z: distance between copies along each axis (0 = not repeated).
        limit:   how many copies to each side of the middle one (None = endless).
        jitter:  each copy is pushed a random distance, up to this much.
        size:    (smallest, biggest): each copy gets a random size in between.
        spin:    True turns each copy a random angle around the vertical.
        where:   function of the middle of each cell that says if there is a
                 copy there (more than 0.5) or not: lambda c: step(10, length(c))
        seed:    another number gives another set of random values.

        Each copy must fit inside its cell (half the distance to each side),
        jitter and biggest size included, or it shows cut at the cell border.
        """
        return _Repeat(self, (x, y, z), limit, jitter, size, spin, where, seed)

    # --- modifiers
    def round(self, radius):              return _Round(self, radius)
    def shell(self, thickness):           return _Shell(self, thickness)
    def paint(self, material):            return _Paint(self, material)

    def patch(self, drawing, at, lift=None):
        """A drawing on this shape's surface that does not stick out.

        drawing: a Disc, or a Drawing (several discs, one on top of another).
        at:      a point on the surface (or near it): the middle of the drawing.
        lift:    how far each layer is raised above the one below. Left out,
                 it is the drawing's own lift (0.006 unless it says otherwise).

        Each disc is a piece of this very shape, barely raised and painted
        with the disc's material, so it follows the surface. The result is a
        separate shape: add it next to the original, outside any smooth
        union, so its edge stays sharp.
        """
        if lift is None:
            lift = _lift(drawing)
        facing = _facing_of(drawing)
        layers = []
        for i, disc in enumerate(_layers(drawing, facing)):
            height = lift * (i + 1)
            if isinstance(height, float):
                height = round(height, 9)        # 0.006 * 3 is 0.018, not 0.018000000000000002
            if facing is not None:
                # a flat drawing, stamped along its facing
                layer = self.round(height) & _front(_stamp(disc, at, facing), at, facing, drawing)
                if disc.material is not None:
                    layer = layer.paint(disc.material)
                layers.append(layer)
                continue
            center = tuple(a + b for a, b in zip(at, disc.at))
            layer = self.round(height) & Sphere(disc.radius).move(center)
            if disc.inner:
                layer = layer - Sphere(disc.inner).move(center)
            if disc.material is not None:
                layer = layer.paint(disc.material)
            layers.append(layer)
        return union(*layers)

    def engrave(self, drawing, at, symmetry=None):
        """This shape with a drawing sunk into its surface: a groove as deep
        as the drawing's depth, with a floor that follows the surface.

        Where the drawing falls, the shape is cut away, but only down to
        that depth: what is deeper stays. smooth (of the drawing) rounds
        the edge of the groove."""
        facing = _facing_of(drawing)
        stamp = union(*[_stamp(layer, at, facing) for layer in _layers(drawing, facing)])
        if facing is not None:
            stamp = _front(stamp, at, facing, drawing)
        if symmetry is not None:
            stamp = stamp.mirror(symmetry)
        widest = max(layer.width / 2 if isinstance(layer, Line) else layer.radius
                     for layer in _layers(drawing, facing))
        return _Engrave(self, stamp, drawing.depth, drawing.smooth, widest)

    # --- combinations. smooth > 0 blends the shapes with that transition radius
    def union(self, other, smooth=0.0):     return _Combine("union", self, other, smooth)
    def subtract(self, other, smooth=0.0):  return _Combine("subtract", self, other, smooth)
    def intersect(self, other, smooth=0.0): return _Combine("intersect", self, other, smooth)

    def __or__(self, other):  return self.union(other)
    def __add__(self, other): return self.union(other)
    def __sub__(self, other): return self.subtract(other)
    def __and__(self, other): return self.intersect(other)


def union(*shapes, smooth=0.0):
    """Join several shapes at once."""
    if not shapes:
        raise ValueError("union() needs at least one shape")
    r = shapes[0]
    for s in shapes[1:]:
        r = r.union(s, smooth)
    return r


def collect_shapes(obj, list_name):
    """Shapes declared on a class: an explicit list attribute, or every class
    attribute that is a Shape, in the order they were written. A Model class
    (not instantiated) also counts, so `body = Body` and nested classes work."""
    explicit = getattr(obj, list_name, None)
    if explicit is not None:
        return [_as_shape(v) for v in explicit]
    found = {}
    for cls in reversed(type(obj).__mro__):
        for name, value in vars(cls).items():
            if not name.startswith("_") and (isinstance(value, Shape) or _is_model_class(value)):
                found[name] = _as_shape(value)
    return list(found.values())


# ================================================================== drawings
class Disc:
    """One layer of a drawing made on a surface (see Shape.patch).

    radius:   how big the disc is.
    inner:    more than 0 leaves a hole in the middle: a ring.
    material: what it is painted with.
    at:       where its middle is, measured from the middle of the drawing.
    lift:     for a disc used on its own (not inside a Drawing): how far it
              is raised above the surface. Left out, 0.006.
    """
    def __init__(self, radius, inner=0.0, material=None, at=(0.0, 0.0, 0.0), patch=None, symmetry=None,
                 lift=None):
        self.lift = lift
        if len(at) != 3:
            raise TypeError("Disc: at is a point, (x, y, z)")
        self.radius, self.inner, self.at = radius, inner, tuple(at)
        self.material = as_material(material) if material is not None else None
        # as a part of a Model: where it is drawn on the parts before it
        self.patch_at, self.symmetry = patch, symmetry


class Line:
    """A straight stroke of a drawing, from start to end, with round ends.

    start, end: points measured from the middle of the drawing: (x, y, z),
                or (x, y) for z = 0.
    width:      how thick the stroke is.
    material:   what it is painted with (when the drawing is patched).

    A line only exists in a drawing that has a facing: it is flat, and it
    is stamped on the surface along that direction.
    """
    def __init__(self, start, end, width=0.02, material=None):
        self.start, self.end, self.width = _point(start), _point(end), width
        self.material = as_material(material) if material is not None else None


class _Stroke:
    """A Path used as a layer of a drawing: a curved stroke."""
    def __init__(self, arcs, radius, material):
        self.arcs, self.radius, self.material = arcs, radius, material


def _stroke(value, k=1.0):
    """The layer a Path stands for in a drawing (None if it is not one),
    k times bigger."""
    material = None
    if isinstance(value, _Paint):
        value, material = value.child, value.material
    if not isinstance(value, Path):
        return None
    radius = _const(value.r)
    if value.r2 is not None or radius is None:
        raise ValueError("a Path in a drawing has one thickness, a plain number")
    arcs = [tuple(tuple(c * k for c in point) for point in arc) for arc in value.arcs]
    return _Stroke(arcs, radius * k, material)


def _point(point):
    if len(point) == 2:
        return (point[0], point[1], 0.0)
    if len(point) != 3:
        raise TypeError("Line: a point is (x, y, z), or (x, y) for z = 0")
    return tuple(point)


_AXES = {"x": (1.0, 0.0, 0.0), "-x": (-1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0),
         "-y": (0.0, -1.0, 0.0), "z": (0.0, 0.0, 1.0), "-z": (0.0, 0.0, -1.0)}


class Drawing:
    """Several discs, lines and paths, one on top of another, to draw on a surface:
    an eye, a spot, a pattern of grooves. It knows nothing about the shape
    it goes on; as a part of a Model it says where it goes and how:

        class Eye(Drawing):
            rim   = Disc(0.20, material=yellow)
            pupil = Disc(0.13, material=black)       # written later: goes on top

        eyes = Eye(patch=(0.44, 0.06, 0.22), symmetry="x")     # painted on
        mark = Cross(engrave=(0, 0, 0.5), facing="z")          # sunk in

    size makes the whole drawing bigger or smaller: Eye(size=0.8).
    lift (patch) is how far each layer is raised above the one below it (and
    the first one above the surface): smaller looks more painted on, bigger
    looks more like a sticker. Too small and the layers show holes.
    depth (engrave) is how deep the groove is, and smooth rounds its edge.

    facing is the direction the drawing looks at, away from the surface:
    (x, y, z), or "x", "-x", "y", "-y", "z", "-z". With it the drawing is
    flat and it is stamped on the surface along that direction, like a
    slide projector would; lines need it. Without it only discs can be
    drawn: each one is whatever of the surface is closer to its middle than
    its radius, so it needs no direction.

    reach is how far behind its point a drawing with facing still marks the
    surface, so that it does not come out on the other side. Left out, it
    reaches the middle of the piece (its origin).

    The layers are the Disc, Line and Path attributes, or a `parts` list
    (or a method that returns it) when they are easier to compute. A Path
    is a curved stroke: like a Line it is flat and needs a facing, and its
    radius is half the width of the stroke.
    """
    size = 1.0
    lift = 0.006
    depth = 0.01
    smooth = 0.0
    facing = None
    reach = None
    symmetry = None
    parts = None

    def __init__(self, size=None, patch=None, symmetry=None, lift=None, engrave=None,
                 depth=None, smooth=None, facing=None, reach=None):
        for name, value in (("size", size), ("lift", lift), ("depth", depth),
                            ("smooth", smooth), ("facing", facing), ("reach", reach)):
            if value is not None:
                setattr(self, name, value)
        if patch is not None and engrave is not None:
            raise TypeError(f"{type(self).__name__}: a drawing is patched OR engraved, not both")
        # as a part of a Model: where it is drawn on the parts before it
        self.patch_at, self.engrave_at = patch, engrave
        if symmetry is not None:
            self.symmetry = symmetry

    def layers(self):
        """The discs and lines, at their final size."""
        found = self.parts() if callable(self.parts) else self.parts
        if found is None:
            named = {}
            for cls in reversed(type(self).__mro__):
                for name, value in vars(cls).items():
                    if not name.startswith("_") and (isinstance(value, (Disc, Line))
                                                     or _stroke(value) is not None):
                        named[name] = value
            found = list(named.values())
        if not found:
            raise ValueError(f"{type(self).__name__} has nothing to draw: add Disc, Line or Path "
                             "attributes")
        k = self.size
        layers = []
        for d in found:
            if isinstance(d, Disc):
                layers.append(Disc(d.radius * k, d.inner * k, d.material, tuple(c * k for c in d.at)))
            elif isinstance(d, Line):
                layers.append(Line(tuple(c * k for c in d.start), tuple(c * k for c in d.end),
                                   d.width * k, d.material))
            elif _stroke(d) is not None:
                layers.append(_stroke(d, k))
            else:
                raise TypeError(f"{type(self).__name__}: a drawing is made of Disc, Line and Path, "
                                f"not {d!r}")
        return layers

    discs = layers


def is_drawing(value):
    return isinstance(value, (Disc, Drawing))


def collect_parts(model):
    """The parts of a Model, in the order they were written: an explicit
    `parts` list, or every class attribute that is a Shape, a Model class, or
    a drawing (Disc / Drawing) to patch on the parts before it."""
    explicit = getattr(model, "parts", None)
    if explicit is not None:
        return [_as_shape(v) for v in explicit]
    found = {}
    for cls in reversed(type(model).__mro__):
        for name, value in vars(cls).items():
            if name.startswith("_"):
                continue
            if isinstance(value, Shape) or _is_model_class(value) or is_drawing(value):
                found[name] = _as_shape(value)
    return list(found.values())


def assemble(parts, smooth, who):
    """Put the parts of a Model together, one after another, in order. Each
    part says what it does to what came before it: it is added (blended with
    the model's smooth), joined with its own blend, carved out, or drawn on
    the surface."""
    # A model used as a part wraps itself in a bounding sphere when it can
    # (see Model.build), which is only right if it is simply added. One that
    # melts into its neighbors or cuts them is built without the sphere, and
    # so is every part when some blend is wide enough to reach a sphere.
    wide = not _zero(smooth) or any(
        not is_drawing(part) and part._role is not None and part._role[0] == "join"
        and not (isinstance(part._role[1], (int, float)) and part._role[1] < 0.1)
        for part in parts)
    whole = None
    for part in parts:
        if getattr(part, "_is_model", False):
            role = part._role
            if wide or (role is not None and not (role[0] == "join" and _zero(role[1]))):
                part = _unbounded(part, role)
        if is_drawing(part):
            if whole is None:
                raise ValueError(f"{who}: a drawing needs a part before it to be drawn on")
            if getattr(part, "engrave_at", None) is not None:
                whole = whole.engrave(part, at=part.engrave_at, symmetry=part.symmetry)
                continue
            if part.patch_at is None:
                raise ValueError(f"{who}: a drawing used as a part needs patch=(x, y, z) or "
                                 "engrave=(x, y, z), the point where it goes")
            whole = _patched(whole, part, part.patch_at, part.symmetry)
            continue
        role = part._role
        if whole is None:
            if role is not None and role[0] == "carve":
                raise ValueError(f"{who}: the first part cannot be carved out of anything")
            whole = part
        elif role is None:
            whole = whole.union(part, smooth)
        elif role[0] == "carve":
            whole = whole.subtract(part, role[1])
        else:
            whole = whole.union(part, role[1])
    return whole


def _unbounded(model, role):
    """A model as a plain shape with no bounding sphere of its own, keeping
    what it does as a part."""
    shape = _Plain()
    shape.model, shape._role = model, role
    return shape


def _lift(drawing):
    if isinstance(drawing, type) and issubclass(drawing, Drawing):
        return drawing.lift
    lift = getattr(drawing, "lift", None)
    return 0.006 if lift is None else lift


def _layers(drawing, facing):
    if isinstance(drawing, type) and issubclass(drawing, Drawing):
        drawing = drawing()
    if isinstance(drawing, Disc):
        return [drawing]
    if not isinstance(drawing, Drawing):
        raise TypeError(f"expected a Disc or a Drawing, got {drawing!r}")
    layers = drawing.layers()
    if facing is None and any(isinstance(layer, (Line, _Stroke)) for layer in layers):
        raise ValueError(
            f"{type(drawing).__name__} has lines or paths, so it needs a facing: the direction it "
            'looks at, away from the surface, like facing="z" or facing=(0, 1, 1)')
    return layers


def _facing_of(drawing):
    """The facing of a drawing as a direction of length 1, or None."""
    facing = getattr(drawing, "facing", None)
    if facing is None:
        return None
    if isinstance(facing, str):
        if facing not in _AXES:
            raise ValueError(f"facing: {facing!r} is not a direction; use (x, y, z) or one of "
                             + ", ".join(repr(a) for a in _AXES))
        return _AXES[facing]
    if len(facing) != 3:
        raise TypeError("facing is a direction: (x, y, z)")
    length = math.sqrt(sum(c * c for c in facing))
    if length == 0:
        raise ValueError("facing cannot be (0, 0, 0)")
    return tuple(c / length for c in facing)


def _flat(vector, facing):
    """The vector without its part along facing: its shadow on the drawing."""
    along = sum(a * b for a, b in zip(vector, facing))
    return tuple(round(a - along * b, 9) for a, b in zip(vector, facing))


def _stamp(layer, at, facing):
    """One layer of a flat drawing as a shape that goes on forever along
    facing: what it cuts out of a surface is the layer, seen from there."""
    if isinstance(layer, Line):
        start = tuple(a + b for a, b in zip(at, layer.start))
        across = _flat(tuple(b - a for a, b in zip(layer.start, layer.end)), facing)
        return _Flat(start, across, facing, layer.width / 2)
    if isinstance(layer, _Stroke):
        arcs = [tuple(_flat(tuple(a + b for a, b in zip(at, point)), facing) for point in arc)
                for arc in layer.arcs]
        return _FlatPath(arcs, facing, layer.radius)
    center = tuple(a + b for a, b in zip(at, layer.at))
    if facing is None:
        # no direction: whatever is closer to the middle than the radius
        stamp = Sphere(layer.radius).move(center)
        return stamp - Sphere(layer.inner).move(center) if layer.inner else stamp
    stamp = _Flat(center, (0.0, 0.0, 0.0), facing, layer.radius)
    if layer.inner:
        stamp = stamp - _Flat(center, (0.0, 0.0, 0.0), facing, layer.inner)
    return stamp


def _front(stamp, at, facing, drawing):
    """Keep a stamp from coming out on the other side of the piece: it only
    counts from its point back to `reach`."""
    reach = getattr(drawing, "reach", None)
    if reach is None:
        reach = sum(a * b for a, b in zip(at, facing))
        if reach <= 0:
            raise ValueError(
                "this drawing's point is not in front of the middle of the piece, so say "
                "how far behind the point it still marks the surface: reach=0.3")
    return stamp & _Behind(at, facing, reach)


def _is_model_class(value):
    return isinstance(value, type) and issubclass(value, Shape) and getattr(value, "_is_model", False)


def _as_shape(value):
    return value() if _is_model_class(value) else value


# ===================================================================== leaves
# The properties any shape can be declared with, besides its own measures:
#     Torus(0.17, 0.012, position=(0, 0.114, 0), carve=0.01)
# They mean the same as in a Model and are applied in this order.
# (bend and symmetry are the bend_x / bend_z and mirror methods, under names
# that do not clash with them.)
_DECLARED = ("material", "ripple", "size", "rotation", "position", "bend", "symmetry", "carve", "join")


def _now(value):
    """A declared property: a value, or a function of t (time)."""
    if callable(value) and not isinstance(value, (Shape, Expr, Material, type)):
        return value(T) if inspect.signature(value).parameters else value()
    return value


def _zero(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0


def role_of(carve, join, who):
    """Turn the carve= / join= properties into a role (see Shape._role)."""
    for name, value in (("carve", carve), ("join", join)):
        if value is None or value is False:
            continue
        if carve not in (None, False) and join not in (None, False):
            raise TypeError(f"{who}: a part is carved OR joined, not both")
        return (name, 0.0 if value is True else value)
    return None


def place(shape, size=1.0, rotation=(0.0, 0.0, 0.0), position=(0.0, 0.0, 0.0),
          bend=(0.0, 0.0), symmetry=None, ripple=None):
    """Ripple, then size, then rotation (x, y, z), then position, then bend
    (around x, around z), then symmetry. Anything left at its neutral value
    adds no code to the shader."""
    bend_x, bend_z = bend
    mirror = symmetry
    if ripple is not None:
        shape = shape.ripple(*ripple)
    if not (isinstance(size, (int, float)) and size == 1):
        shape = shape.scale(size)
    rx, ry, rz = rotation
    if not _zero(rx): shape = shape.rotate_x(rx)
    if not _zero(ry): shape = shape.rotate_y(ry)
    if not _zero(rz): shape = shape.rotate_z(rz)
    if not all(_zero(c) for c in position):
        shape = shape.move(*position)
    if not _zero(bend_x): shape = shape.bend_x(bend_x)
    if not _zero(bend_z): shape = shape.bend_z(bend_z)
    if mirror is not None:
        shape = shape.mirror(mirror)
    return shape


class _Declarative(type):
    """Lets a primitive be written with its placement as properties instead
    of chained calls: the extra keywords are taken out before the primitive
    sees them, and applied to the finished shape."""
    def __call__(cls, *args, **kw):
        declared = {k: _now(kw.pop(k)) for k in list(kw) if k in _DECLARED}
        shape = super().__call__(*args, **kw)
        if not declared:
            return shape
        material = declared.pop("material", None)
        role = role_of(declared.pop("carve", None), declared.pop("join", None), cls.__name__)
        if material is not None:
            shape = shape.paint(material)
        shape = place(shape, **declared)
        if role is not None:
            shape._role = role
        return shape


class _Primitive(Shape, metaclass=_Declarative):
    def sdf(self, p):
        raise NotImplementedError

    def emit(self, ctx, p, mat):
        d = ctx.var("d")
        ctx.line(f"float {d} = {self.sdf(p)};")
        if _see_through(mat):
            # gSolid: the ray already went through a see-through surface and
            # now looks for what is behind, so these are not there
            ctx.line(f"if( gSolid ) {d} = 1e4;")
        return d, f"{ctx.material_id(mat)}.0", ctx.space or p


class Sphere(_Primitive):
    def __init__(self, radius=0.5):
        self.r = E(radius)
    def sdf(self, p):
        return f"length({p})-{self.r.code}"
    def spheres(self):
        r = _const(self.r)
        return None if r is None else [((0.0, 0.0, 0.0), r)]


class Ellipsoid(_Primitive):
    """Stretched sphere: one radius per axis."""
    def __init__(self, rx=0.5, ry=0.5, rz=0.5):
        self.r = E((rx, ry, rz))
    def sdf(self, p):
        return f"sdEllipsoid({p}, {self.r.code})"
    def spheres(self):
        r = _const(self.r)
        if r is None:
            return None
        # points all over its surface, each padded by how far the surface
        # can bulge between one point and the next
        pad = max(r) * (1 - math.cos(math.radians(15)))
        found = [((0.0, r[1], 0.0), pad), ((0.0, -r[1], 0.0), pad)]
        for up in (-60, -30, 0, 30, 60):
            for turn in range(0, 360, 30):
                u, v = math.radians(up), math.radians(turn)
                found.append(((r[0] * math.cos(u) * math.cos(v), r[1] * math.sin(u),
                               r[2] * math.cos(u) * math.sin(v)), pad))
        return found
    def weight(self):
        return 2


class Box(_Primitive):
    def __init__(self, width=1.0, height=1.0, depth=1.0, rounding=0.0):
        r = E(rounding)
        self.b = [E(width) * 0.5 - r, E(height) * 0.5 - r, E(depth) * 0.5 - r]
        self.rounding = r
    def sdf(self, p):
        b = ", ".join(c.code for c in self.b)
        return f"sdBox({p}, vec3({b}))-{self.rounding.code}"
    def spheres(self):
        b, r = [_const(c) for c in self.b], _const(self.rounding)
        if r is None or None in b:
            return None
        return [((x * b[0], y * b[1], z * b[2]), r)
                for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]


class Capsule(_Primitive):
    """Thick segment between two points. With radius2 it tapers toward the end."""
    def __init__(self, start=(0, 0, 0), end=(0, 1, 0), radius=0.2, radius2=None):
        self.a, self.b = E(start), E(end)
        self.r1 = E(radius)
        self.r2 = E(radius if radius2 is None else radius2)
    def sdf(self, p):
        return f"sdCapsule2({p}, {self.a.code}, {self.b.code}, {self.r1.code}, {self.r2.code})"
    def spheres(self):
        a, b, r1, r2 = _const(self.a), _const(self.b), _const(self.r1), _const(self.r2)
        if None in (a, b, r1, r2):
            return None
        return [(a, r1), (b, r2)]


class Curve(_Primitive):
    """Thick curved line: a parabola arc from start to end that bends toward
    control (without touching it). With radius2 it tapers toward the end."""
    def __init__(self, start=(0, 0, 0), control=(0, 1, 0), end=(1, 1, 0), radius=0.2, radius2=None):
        self.a, self.c, self.b = E(start), E(control), E(end)
        self.r1 = E(radius)
        self.r2 = E(radius if radius2 is None else radius2)
    def sdf(self, p):
        return (f"sdCurve({p}, {self.a.code}, {self.c.code}, {self.b.code}, "
                f"{self.r1.code}, {self.r2.code})")
    def spheres(self):
        a, c, b, r1, r2 = (_const(v) for v in (self.a, self.c, self.b, self.r1, self.r2))
        if None in (a, c, b, r1, r2):
            return None
        return _along(a, c, b, r1, r2)
    def weight(self):
        return 4


class Path(_Primitive):
    """Tube that follows a list of points: a chain of Curves. With radius2
    it tapers from the first point to the last, the same amount on every
    bend. It starts at the first point and ends at the last; the points in
    between are where it is pulled toward, one bend for each (like the
    control of a Curve, it does not touch them). closed=True makes a loop:
    every point pulls, and none is touched.

    Each bend starts and ends halfway between its point and the neighbors,
    which is why the bends meet without a corner."""
    def __init__(self, points, radius=0.1, closed=False, radius2=None):
        points = [tuple(float(c) for c in point) for point in points]
        if len(points) < 2 or any(len(point) != 3 for point in points):
            raise ValueError("Path needs two or more points, each one (x, y, z)")
        if closed and len(points) < 3:
            raise ValueError("a closed Path needs three or more points")
        if closed and radius2 is not None:
            raise ValueError("a closed Path has no end to taper toward: leave radius2 out")
        self.r = E(radius)
        self.r2 = None if radius2 is None else E(radius2)
        self.arcs = _arcs(points, closed)
    def _radius(self, i):
        """Code of the thickness where bend number i starts."""
        share = i / len(self.arcs)
        r1, r2 = _const(self.r), _const(self.r2)
        if r1 is None or r2 is None:
            return f"mix({self.r.code}, {self.r2.code}, {E(share).code})"
        return E(round(r1 + (r2 - r1) * share, 5)).code
    def sdf(self, p):
        d = None
        for i, (start, control, end) in enumerate(self.arcs):
            radii = "0.0, 0.0" if self.r2 is None else f"{self._radius(i)}, {self._radius(i + 1)}"
            arc = (f"sdCurve({p}, {E(start).code}, {E(control).code}, "
                   f"{E(end).code}, {radii})")
            d = arc if d is None else f"min({d}, {arc})"
        return d if self.r2 is not None else f"{d}-{self.r.code}"
    def spheres(self):
        r = _const(self.r)
        r2 = r if self.r2 is None else _const(self.r2)
        if r is None or r2 is None:
            return None
        n = len(self.arcs)
        return [sphere for i, (a, c, b) in enumerate(self.arcs)
                for sphere in _along(a, c, b, r + (r2 - r) * i / n, r + (r2 - r) * (i + 1) / n, pieces=4)]
    def weight(self):
        return 4 * len(self.arcs)


def _halfway(a, b):
    return tuple((p + q) / 2 for p, q in zip(a, b))


def _arcs(points, closed):
    """The (start, control, end) of each Curve of a Path."""
    if closed:
        n = len(points)
        return [(_halfway(points[i - 1], points[i]), points[i],
                 _halfway(points[i], points[(i + 1) % n])) for i in range(n)]
    if len(points) == 2:
        return [(points[0], _halfway(*points), points[1])]
    pulls = points[1:-1]
    stops = [points[0], *map(_halfway, pulls, pulls[1:]), points[-1]]
    return list(zip(stops, pulls, stops[1:]))


class _Flat(_Primitive):
    """A layer of a flat drawing (a disc, or a line when across is not
    zero), stretched forever along facing."""
    def __init__(self, start, across, facing, radius):
        self.a, self.ba, self.f, self.r = E(start), E(across), E(facing), E(radius)
    def sdf(self, p):
        return f"sdFlat({p}, {self.a.code}, {self.ba.code}, {self.f.code})-{self.r.code}"


class _FlatPath(_Primitive):
    """A Path of a flat drawing, stretched forever along facing. Its points
    are already flat: they have nothing along facing."""
    def __init__(self, arcs, facing, radius):
        self.arcs, self.f, self.r = arcs, E(facing), E(radius)
    def sdf(self, p):
        d = None
        for start, control, end in self.arcs:
            arc = (f"sdFlatCurve({p}, {E(start).code}, {E(control).code}, "
                   f"{E(end).code}, {self.f.code})")
            d = arc if d is None else f"min({d}, {arc})"
        return f"{d}-{self.r.code}"


class _Behind(_Primitive):
    """Everything from `reach` behind a point (against facing) to the front."""
    def __init__(self, at, facing, reach):
        self.at, self.f, self.reach = E(at), E(facing), E(reach)
    def sdf(self, p):
        return f"-(dot({p}-{self.at.code}, {self.f.code})+{self.reach.code})"


class _Engrave(Shape):
    """A shape with a groove: the stamp is cut out of it, but no deeper than
    depth below its surface.

    A groove changes nothing farther out than it is wide (widest is half
    the width of its thickest stroke), so out there the stamp is skipped."""
    def __init__(self, child, stamp, depth, smooth, widest):
        self.child, self.stamp, self.depth, self.k = child, stamp, E(depth), E(smooth)
        self.near = E(widest) + self.k
    def emit(self, ctx, p, mat):
        d, m, u = self.child.emit(ctx, p, mat)
        r = ctx.var("d")
        ctx.line(f"float {r} = {d};")
        ctx.line(f"if( {d}<{self.near.code} ) {{")
        s, _, _ = self.stamp.emit(ctx, p, mat)
        cut = ctx.var("d")
        ctx.line(f"float {cut} = max({s}, -({d}+{self.depth.code}));")
        smooth = self.k.code not in ("0.0", "0")
        ctx.line(f"{r} = " + (f"smax({d},-({cut}),{self.k.code});" if smooth
                               else f"max({d},-({cut}));"))
        ctx.line("}")
        return r, m, u
    def spheres(self):
        return self.child.spheres()               # a groove only takes away
    def weight(self):
        return self.child.weight() + self.stamp.weight()


class Cylinder(_Primitive):
    """Vertical cylinder centered at the origin."""
    def __init__(self, radius=0.5, height=1.0, rounding=0.0):
        r = E(rounding)
        self.radius, self.half, self.rounding = E(radius) - r, E(height) * 0.5 - r, r
    def sdf(self, p):
        return f"sdRoundCyl({p}, {self.radius.code}, {self.half.code}, {self.rounding.code})"
    def spheres(self):
        radius, half, r = _const(self.radius), _const(self.half), _const(self.rounding)
        if None in (radius, half, r):
            return None
        return [((0.0, 0.0, 0.0), _length([radius, half]) + r)]


class Torus(_Primitive):
    """Donut lying flat (its axis is the vertical one)."""
    def __init__(self, radius=0.5, thickness=0.15):
        self.R, self.r = E(radius), E(thickness)
    def sdf(self, p):
        return f"sdTorus({p}, {self.R.code}, {self.r.code})"
    def spheres(self):
        R, r = _const(self.R), _const(self.r)
        return None if None in (R, r) else [((0.0, 0.0, 0.0), R + r)]


class Cone(_Primitive):
    """Rounded cone: base at the origin, tip pointing up."""
    def __init__(self, radius=0.3, height=1.0):
        self.r, self.h = E(radius), E(height)
    def sdf(self, p):
        return f"sdCapsule2({p}, vec3(0.0), vec3(0.0,{self.h.code},0.0), {self.r.code}, 0.0)"
    def spheres(self):
        r, h = _const(self.r), _const(self.h)
        if None in (r, h):
            return None
        return [((0.0, 0.0, 0.0), r), ((0.0, h, 0.0), 0.0)]


class CutCone(_Primitive):
    """Cone with its tip cut off: vertical, centered at the origin, flat ends.
    radius is the bottom, radius2 the top. rounding softens the edges."""
    def __init__(self, radius=0.5, radius2=0.25, height=1.0, rounding=0.0):
        r = E(rounding)
        self.r1, self.r2, self.half, self.rounding = E(radius) - r, E(radius2) - r, E(height) * 0.5 - r, r
    def sdf(self, p):
        return (f"sdCutCone({p}, {self.half.code}, {self.r1.code}, {self.r2.code}, "
                f"{self.rounding.code})")
    def spheres(self):
        r1, r2, half, r = _const(self.r1), _const(self.r2), _const(self.half), _const(self.rounding)
        if None in (r1, r2, half, r):
            return None
        return [((0.0, 0.0, 0.0), _length([max(r1, r2), half]) + r)]


# ================================================================== transforms
# The central SDF trick: to move an object you do NOT move the object, you move
# the point where the distance is asked, in the opposite direction.
class _Move(Shape):
    def __init__(self, child, t):
        self.child, self.t = child, E(t)
    def emit(self, ctx, p, mat):
        q = ctx.var("p")
        ctx.line(f"vec3 {q} = {p}-{self.t.code};")
        return self.child.emit(ctx, q, mat)
    def spheres(self):
        inner, t = self.child.spheres(), _const(self.t)
        if inner is None or t is None:
            return None
        return [(tuple(a + b for a, b in zip(center, t)), radius) for center, radius in inner]
    def weight(self):
        return self.child.weight()


class _Rotate(Shape):
    def __init__(self, child, plane, degrees):
        self.child, self.plane, self.g = child, plane, E(degrees)
    def emit(self, ctx, p, mat):
        q = ctx.var("p")
        ctx.line(f"vec3 {q} = {p}; {q}.{self.plane} = rot2(radians({self.g.code}))*{q}.{self.plane};")
        return ctx.emit_turned(self.child, q, mat)
    def spheres(self):
        inner, degrees = self.child.spheres(), _const(self.g)
        if inner is None:
            return None
        if degrees is None:
            # it turns with t, around the origin: wherever it is, it stays
            # inside the sphere it sweeps
            return [((0.0, 0.0, 0.0), max(_length(center) + radius for center, radius in inner))]
        i, j = ("xyz".index(axis) for axis in self.plane)
        c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
        found = []
        for center, radius in inner:
            turned = list(center)
            turned[i], turned[j] = c * center[i] - s * center[j], s * center[i] + c * center[j]
            found.append((tuple(turned), radius))
        return found
    def weight(self):
        return self.child.weight()


class _Scale(Shape):
    def __init__(self, child, factor):
        self.child, self.s = child, E(factor)
    def emit(self, ctx, p, mat):
        q = ctx.var("p")
        ctx.line(f"vec3 {q} = {p}/{self.s.code};")
        d, m, u = self.child.emit(ctx, q, mat)
        d2 = ctx.var("d")
        ctx.line(f"float {d2} = {d}*{self.s.code};")     # the distance is scaled too
        return d2, m, u
    def spheres(self):
        inner, k = self.child.spheres(), _const(self.s)
        if inner is None or k is None:
            return None
        return [(tuple(c * k for c in center), radius * abs(k)) for center, radius in inner]
    def weight(self):
        return self.child.weight()


class _Bend(Shape):
    """Bends a vertical shape: a rotation that grows with height. degrees is
    how much it turns per unit of y, so y=0 stays put and the two ends lean
    opposite ways. The distance is no longer exact: keep the bend gentle."""
    def __init__(self, child, plane, degrees):
        self.child, self.plane, self.g = child, plane, E(degrees)
    def emit(self, ctx, p, mat):
        q = ctx.var("p")
        ctx.line(f"vec3 {q} = {p}; {q}.{self.plane} = rot2(radians({self.g.code})*{p}.y)*{q}.{self.plane};")
        return ctx.emit_turned(self.child, q, mat)
    def weight(self):
        return self.child.weight()


class _Repeat(Shape):
    """Domain repetition: space is cut into cells and every point is moved to
    the middle cell before asking the child for its distance, so the child is
    computed once and shows up in every cell.

    A ray inside one cell knows nothing about the copy in the next one, so the
    distance never reaches beyond the wall of the cell (plus a little, to get
    across). While the wall is what is closest the material is -1, the same
    mark _Bound uses: it is not a surface, and it must not cast shadows.

    How far is the wall? The render says which way the ray is going (gRd), so
    it is measured ALONG the ray: a ray running beside a wall is not slowed
    down by it. That only works while the axes still point the way the
    world's do; inside a rotation, bend or mirror (and when there is no ray,
    as when normals are computed) the plain distance to the wall is used."""
    def __init__(self, child, spacing, limit, jitter, size, spin, where, seed):
        for s in spacing:
            if isinstance(s, bool) or not isinstance(s, (int, float)) or s < 0:
                raise TypeError("repeat: x, y and z are distances (plain numbers, 0 = not repeated)")
        if not any(spacing):
            raise ValueError("repeat needs a distance along at least one axis: repeat(x=4)")
        if size is not None and (not isinstance(size, (tuple, list)) or len(size) != 2):
            raise TypeError("repeat: size is (smallest, biggest)")
        self.child, self.spacing, self.limit = child, spacing, limit
        self.jitter, self.size, self.spin, self.where, self.seed = jitter, size, spin, where, seed

    def emit(self, ctx, p, mat):
        c, q, w = ctx.var("c"), ctx.var("p"), ctx.var("w")
        ctx.line(f"vec3 {c} = vec3(0.0); vec3 {q} = {p}; float {w} = 1e4;")
        axes = [(a, _num(s)) for a, s in zip("xyz", self.spacing) if s]
        for a, s in axes:
            cell = f"round({p}.{a}/{s})"
            if self.limit is not None:
                cell = f"clamp({cell}, {_num(-self.limit)}, {_num(self.limit)})"
            # which cell, the point as seen from the middle of that cell, and
            # how far the wall is (beyond the last copy there is no wall)
            plain = f"0.5*{s}-abs({q}.{a})"
            along = (f"(dot(gRd,gRd)<0.5 ? {plain} : abs(gRd.{a})<1e-5 ? 1e4 : "
                     f"(sign(gRd.{a})*0.5*{s}-{q}.{a})/gRd.{a})")
            ctx.line(f"{c}.{a} = {cell}; {q}.{a} -= {s}*{c}.{a}; "
                     f"if( abs({q}.{a})<=0.5*{s} ) {w} = min({w}, {plain if ctx.turned else along});")

        k = None
        if self.jitter or self.size is not None or self.spin:
            r, r2 = ctx.var("r"), ctx.var("r")
            ctx.line(f"vec3 {r} = cellRand({c}, {_num(self.seed)}); vec3 {r2} = cellRand({c}, {_num(self.seed + 1)});")
            if self.jitter:
                for a, _ in axes:
                    ctx.line(f"{q}.{a} -= {E(self.jitter).code}*(2.0*{r}.{a}-1.0);")
            if self.spin:
                ctx.line(f"{q}.xz = rot2(6.2832*{r2}.y)*{q}.xz;")
            if self.size is not None:
                k = ctx.var("k")
                ctx.line(f"float {k} = mix({E(self.size[0]).code}, {E(self.size[1]).code}, {r2}.x); {q} /= {k};")

        d, m, u = ctx.var("d"), ctx.var("m"), ctx.var("u")
        ctx.line(f"float {d} = {w}+0.1; float {m} = -1.0; vec3 {u} = {p};")
        if self.where is not None:
            middle = Expr(f"({c}*vec3({', '.join(_num(s) for s in self.spacing)}))", "vec3")
            ctx.line(f"if( {E(self.where(middle)).code}>0.5 ) {{")
        else:
            ctx.line("{")
        if self.spin:
            cd, cm, cu = ctx.emit_turned(self.child, q, mat)
        else:
            cd, cm, cu = self.child.emit(ctx, q, mat)
        if k is not None:
            cd = f"({cd})*{k}"
        ctx.line(f"float dc = {cd}; if( dc<{d} ) {{ {d} = dc; {m} = {cm}; {u} = {cu}; }}")
        ctx.line("}")
        return d, m, u
    def weight(self):
        return self.child.weight()


class _Bound(Shape):
    """Speed-up: a sphere that contains the child. Far from the sphere the
    distance to the sphere is returned and the child is not evaluated at all;
    only near it is the real shape computed. The picture does not change.

    While the child is skipped the material is -1: that tells the render that
    this distance is the sphere's, not a real surface's, so soft shadows and
    ambient occlusion do not darken things as if the sphere were solid."""
    def __init__(self, child, center, radius):
        self.child, self.c, self.r = child, E(center), E(radius)
    def emit(self, ctx, p, mat):
        d, m, u = ctx.var("d"), ctx.var("m"), ctx.var("u")
        ctx.line(f"float {d} = length({p}-{self.c.code})-{self.r.code}; float {m} = -1.0; vec3 {u} = {p};")
        ctx.line(f"if( {d}<0.1 ) {{")
        cd, cm, cu = self.child.emit(ctx, p, mat)
        ctx.line(f"{d} = {cd}; {m} = {cm}; {u} = {cu};")
        ctx.line("}")
        return d, m, u
    def spheres(self):
        c, r = _const(self.c), _const(self.r)
        return None if None in (c, r) else [(c, r)]
    def weight(self):
        return 1                                  # from afar it costs one sphere


class _Mirror(Shape):
    """Symmetry: with abs() one half is copied onto the other, for free."""
    def __init__(self, child, axis):
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be 'x', 'y' or 'z'")
        self.child, self.axis = child, axis
    def emit(self, ctx, p, mat):
        q = ctx.var("p")
        ctx.line(f"vec3 {q} = {p}; {q}.{self.axis} = abs({q}.{self.axis});")
        return ctx.emit_turned(self.child, q, mat)
    def spheres(self):
        inner = self.child.spheres()
        if inner is None:
            return None
        i = "xyz".index(self.axis)
        # the copy on the other side
        return inner + [(tuple(-c if k == i else c for k, c in enumerate(center)), radius)
                        for center, radius in inner]
    def weight(self):
        return self.child.weight()


# =================================================================== modifiers
class _Round(Shape):
    def __init__(self, child, radius):
        self.child, self.r = child, E(radius)
    def emit(self, ctx, p, mat):
        d, m, u = self.child.emit(ctx, p, mat)
        d2 = ctx.var("d")
        ctx.line(f"float {d2} = {d}-{self.r.code};")
        return d2, m, u
    def spheres(self):
        inner, r = self.child.spheres(), _const(self.r)
        if inner is None or r is None:
            return None
        return [(center, radius + max(r, 0.0)) for center, radius in inner]
    def weight(self):
        return self.child.weight()


class _Shell(Shape):
    def __init__(self, child, thickness):
        self.child, self.g = child, E(thickness)
    def emit(self, ctx, p, mat):
        d, m, u = self.child.emit(ctx, p, mat)
        d2 = ctx.var("d")
        ctx.line(f"float {d2} = abs({d})-{self.g.code};")
        return d2, m, u
    def spheres(self):
        inner, g = self.child.spheres(), _const(self.g)
        if inner is None or g is None:
            return None
        return [(center, radius + abs(g)) for center, radius in inner]
    def weight(self):
        return self.child.weight()


class _Ripple(Shape):
    """A shape with a lumpy, moving surface: smooth noise added to its
    distance. Skipped far from it, where it changes nothing worth the cost."""
    def __init__(self, child, height, size, flow):
        if len(flow) != 3:
            raise TypeError("ripple: flow is a speed in each direction, (x, y, z)")
        self.child, self.h, self.size, self.flow = child, E(height), E(size), E(tuple(flow))
    def emit(self, ctx, p, mat):
        d, m, u = self.child.emit(ctx, p, mat)
        r = ctx.var("d")
        ctx.line(f"float {r} = {d};")
        ctx.line(f"if( {d}<2.0*{self.h.code} ) {r} += {self.h.code}*"
                 f"(noise3(({p}-{self.flow.code}*iTime)/{self.size.code})-0.5);")
        return r, m, u
    def spheres(self):
        inner, h = self.child.spheres(), _const(self.h)
        if inner is None or h is None:
            return None
        return [(center, radius + abs(h) / 2) for center, radius in inner]
    def weight(self):
        return self.child.weight() + 2


class _Paint(Shape):
    def __init__(self, child, material):
        self.child, self.material = child, as_material(material)
    def emit(self, ctx, p, mat):
        # P (the coordinates used to draw the material) is the position at the
        # point where paint() was called, shared by every piece inside: that way
        # a texture shows no seams between joined pieces. So paint BEFORE you
        # animate: the texture stays glued to the object and moves with it.
        # The material closest to the leaf wins: one set deeper is not overridden.
        previous, ctx.space = ctx.space, p
        try:
            return self.child.emit(ctx, p, self.material)
        finally:
            ctx.space = previous
    def spheres(self):
        return self.child.spheres()
    def weight(self):
        return self.child.weight()


# ================================================================ combinations
class _Patch(Shape):
    """A shape with a drawing on it. Each layer is a piece of the shape
    itself, raised a little and painted: (stamp, height, material).

    The shape is computed once for all the layers, and the layers only near
    it: farther out than `near` the answer is the shape's own distance
    minus the tallest layer, which is never too long a step."""
    near = 0.2

    def __init__(self, child, layers):
        self.child, self.layers = child, layers
    def emit(self, ctx, p, mat):
        d, m, u = self.child.emit(ctx, p, mat)
        tallest = max((E(height) for _, height, _ in self.layers), key=lambda h: _const(h) or 0.0)
        r, rm, ru = ctx.var("d"), ctx.var("m"), ctx.var("u")
        ctx.line(f"float {r} = {d}-{tallest.code}; float {rm} = {m}; vec3 {ru} = {u};")
        ctx.line(f"if( {d}<{_num(self.near)} ) {{")
        ctx.line(f"{r} = {d};")
        for stamp, height, material in self.layers:
            s, _, _ = stamp.emit(ctx, p, mat)
            layer = ctx.var("d")
            paint = f" {rm} = {ctx.material_id(material)}.0; {ru} = {p};" if material is not None else ""
            ctx.line(f"float {layer} = max({d}-{E(height).code}, {s}); "
                     f"if( {layer}<{r} ) {{ {r} = {layer};{paint} }}")
        ctx.line("}")
        return r, rm, ru
    def spheres(self):
        inner = self.child.spheres()
        if inner is None:
            return None
        tallest = max((_const(E(height)) or 0.0) for _, height, _ in self.layers)
        return [(center, radius + tallest) for center, radius in inner]
    def weight(self):
        return self.child.weight() + sum(stamp.weight() for stamp, _, _ in self.layers)


def _patched(whole, drawing, at, symmetry):
    """whole with the drawing on its surface (see Shape.patch)."""
    lift, facing = _lift(drawing), _facing_of(drawing)
    layers = []
    for i, layer in enumerate(_layers(drawing, facing)):
        height = lift * (i + 1)
        if isinstance(height, float):
            height = round(height, 9)
        stamp = _stamp(layer, at, facing)
        if facing is not None:
            stamp = _front(stamp, at, facing, drawing)
        if symmetry is not None:
            stamp = stamp.mirror(symmetry)
        layers.append((stamp, height, layer.material))
    return _Patch(whole, layers)


class _Plain(Shape):
    """A model built without its bounding sphere (see assemble)."""
    def emit(self, ctx, p, mat):
        return self.model.build(blended=True).emit(ctx, p, mat)
    def spheres(self):
        return self.model.spheres()
    def weight(self):
        return self.model.weight()


class _Combine(Shape):
    def __init__(self, op, a, b, smooth):
        if not isinstance(b, Shape):
            raise TypeError("shapes can only be combined with shapes")
        self.op, self.a, self.b, self.k = op, a, b, E(smooth)

    def emit(self, ctx, p, mat):
        da, ma, ua = self.a.emit(ctx, p, mat)
        db, mb, ub = self.b.emit(ctx, p, mat)
        d = ctx.var("d")
        smooth = self.k.code not in ("0.0", "0")
        k = self.k.code
        if self.op == "union":
            ctx.line(f"float {d} = " + (f"smin({da},{db},{k});" if smooth else f"min({da},{db});"))
            if ma == mb and ua == ub:
                return d, ma, ua
            # material and coordinates are those of the closest shape
            s, m, u = ctx.var("s"), ctx.var("m"), ctx.var("u")
            ctx.line(f"bool {s} = {db}<{da}; float {m} = {s}?{mb}:{ma}; vec3 {u} = {s}?{ub}:{ua};")
            return d, m, u
        if self.op == "subtract":
            ctx.line(f"float {d} = " + (f"smax({da},-({db}),{k});" if smooth else f"max({da},-({db}));"))
        else:
            ctx.line(f"float {d} = " + (f"smax({da},{db},{k});" if smooth else f"max({da},{db});"))
        return d, ma, ua
    def spheres(self):
        a, b, k = self.a.spheres(), self.b.spheres(), _const(self.k)
        if self.op == "subtract":
            return a                              # cutting only takes away
        if self.op == "intersect":
            # what is left is inside both: either side will do
            if a is None or b is None:
                return a or b
            return a if _enclose(a)[1] <= _enclose(b)[1] else b
        if a is None or b is None or k is None:
            return None
        found = a + b
        if len(found) > 3000:                     # too many to carry around
            found = [_enclose(found)]
        # a blend swells the shapes a little: a quarter of its radius at most
        return [(center, radius + abs(k) / 4) for center, radius in found] if k else found
    def weight(self):
        return self.a.weight() + self.b.weight()
