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
    reflection: how much of the sky it mirrors: barely when seen from the
               front, fully at a grazing angle, like water or polished
               things (0 = none, 1 = a mirror at the edges).
    sheen:     the soft light that fur and velvet catch where the surface
               turns away from the eye (0 = none, 1 = a strong one).
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
    reflection = 0.0
    sheen = 0.0

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
        self.swaps = []          # the repaints we are inside of, outermost first (see _Repaint)
        self.hairs = []          # (depth, spacing) of each layer of fuzz (see _Fuzz)

    def repainted(self, m):
        """The material that m is drawn with here: each repaint we are inside
        of gets its say once, the innermost first."""
        for swap in reversed(self.swaps):
            m = swap.get(m, m)
        return m

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
    # ("clip", smooth) = only what is inside it is left of the parts before it;
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
    def fuzz(self, fuzz, center=(0.0, 0.0, 0.0)):
        """A soft layer of strands: a Fuzz, or a list of them (see Fuzz).
        center is added to the place on the skin that grows() is asked about."""
        layers = _some(fuzz, Fuzz, "Fuzz(length=0.04, spacing=0.01)")
        if not layers:
            return self
        if isinstance(self, _Bound):
            # the hair goes inside the bounding sphere, which grows to hold
            # it: outside, the hair's smooth shell would sit on the sphere's
            # edge, where the distance is the sphere's, and rays crawl there
            fuzzy = _Fuzz(self.child, layers, center)
            return _Bound(fuzzy, self.c, self.r + E(fuzzy.top))
        return _Fuzz(self, layers, center)
    def ripple(self, height, size=0.2, drift=(0.0, 0.0, 0.0)):
        """An uneven surface that moves (see Ripple)."""
        return _Ripple(self, height, size, drift)
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
        return with_hair([_as_shape(v) for v in explicit])
    found = {}
    for cls in reversed(type(obj).__mro__):
        for name, value in vars(cls).items():
            if not name.startswith("_") and (isinstance(value, Shape) or _is_model_class(value)):
                found[name] = _as_shape(value)
    return with_hair(list(found.values()))


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
    if isinstance(value, _Declared):
        value = value._built()
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


def is_part(value):
    """Something a Model can have as a part: a Shape, a Model class, or a
    drawing (Disc / Drawing) to patch on the parts before it."""
    return isinstance(value, Shape) or _is_model_class(value) or is_drawing(value)


def part_names(cls):
    """The names of the parts declared on a Model class, in the order they
    were written: a subclass's after its base's, and one that replaces a
    part of the base keeps its place."""
    names = {}
    for c in reversed(cls.__mro__):
        for name, value in vars(c).items():
            if not name.startswith("_") and is_part(value):
                names[name] = None
    return list(names)


def collect_parts(model, hair=None):
    """The parts of a Model, in the order they were written: an explicit
    `parts` list, or every part declared on its class, then the ones added
    to the instance (see Model.setup). A part set to None is left out.
    hair goes on the parts that have none of their own (see with_hair)."""
    explicit = getattr(model, "parts", None)
    if explicit is not None:
        return with_hair([_as_shape(v) for v in explicit], hair)
    names = part_names(type(model))
    names += [name for name, value in vars(model).items()
              if not name.startswith("_") and name not in names and is_part(value)]
    values = (getattr(model, name) for name in names)
    return with_hair([_as_shape(v) for v in values if is_part(v)], hair)


def with_hair(parts, hair=None):
    """The parts, and after them the hair that grows on them (see Hair).
    hair, the hair of the model they are in, goes on every shape that says
    nothing of its own, and is handed down to the models inside."""
    layers = []
    for part in parts:
        if isinstance(part, _Declared):
            layers += part._hairs(hair)
        elif hasattr(part, "_hand_down_hair"):
            part._hand_down_hair(hair)
    return parts + layers


def assemble(parts, smooth, who):
    """Put the parts of a Model together, one after another, in order. Each
    part says what it does to what came before it: it is added (blended with
    the model's smooth), joined with its own blend, carved out, used to clip,
    or drawn on the surface."""
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
            if role is not None and role[0] == "clip":
                raise ValueError(f"{who}: the first part has nothing before it to clip")
            whole = part
        elif role is None:
            whole = whole.union(part, smooth)
        elif role[0] == "carve":
            whole = whole.subtract(part, role[1])
        elif role[0] == "clip":
            whole = whole.intersect(part, role[1])
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
_DECLARED = ("material", "hair", "ripple", "fuzz", "size", "rotation", "pivot", "position", "bend", "symmetry", "carve", "clip", "join")


def _now(value):
    """A declared property: a value, or a function of t (time)."""
    if callable(value) and not isinstance(value, (Shape, Expr, Material, type)):
        return value(T) if inspect.signature(value).parameters else value()
    return value


def _zero(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0


def role_of(carve, clip, join, who):
    """Turn the carve= / clip= / join= properties into a role (see Shape._role)."""
    given = [(name, value) for name, value in (("carve", carve), ("clip", clip), ("join", join))
             if value is not None and value is not False]
    if len(given) > 1:
        raise TypeError(f"{who}: a part has one role (carve, clip or join), not "
                        + " and ".join(name for name, _ in given))
    if not given:
        return None
    name, value = given[0]
    return (name, 0.0 if value is True else value)


class _Combed:
    """What Fuzz and Hair have in common: strands `length` long, about
    `spacing` apart, rising `lift` degrees off the skin and combed toward
    `flow`. Their properties are given when they are made, or in a subclass.

    grows(out) says how thick they grow, 1 all of them and 0 none, where the
    skin looks toward out (of length 1). It can also ask for the place on
    the skin: grows(out, point). Both are in the coordinates of the model
    the shape is in.

    `material` is drawn in each strand's own coordinates: x is a random
    number of that strand (0 to 1), y how far it is out of the skin, and z
    how far along it from its root. With none, the strands look like the
    skin under them.

    `wind`, (x, y, z), pushes the strands its way: it lays them over and
    turns them, but never stands them up past their lift; 1 pushes as hard
    as the combing pulls. It comes in gusts about `gusts` across that travel with
    it at one unit per second, measured where the strands are, so they run
    on from one shape into the next."""
    flow = (0.0, 0.0, -1.0)
    length = 0.10
    spacing = 0.011
    lift = 12
    material = None
    wind = None
    gusts = 0.5

    def __init__(self, **changes):
        for name, value in changes.items():
            if name.startswith("_") or not hasattr(type(self), name):
                raise TypeError(f"{type(self).__name__} has no property '{name}'")
            setattr(self, name, value)
        for name in ("flow", "wind"):
            value = _now(getattr(self, name))
            if value is not None and len(value) != 3:
                raise TypeError(f"{type(self).__name__}: {name} is a direction, (x, y, z)")
        if not 0 < self.lift <= 90:
            raise TypeError(f"{type(self).__name__}: lift is in degrees, more than 0 and up to 90")

    def grows(self, out):
        return 1.0

    def _grows(self):
        """The grows formula, or None when they grow everywhere."""
        if "grows" not in vars(self) and type(self).grows is _Combed.grows:
            return None
        return self.grows


class Fuzz(_Combed):
    """A soft layer of strands around a surface: fur, moss, felt, a peach.
    There are no single strands to find: a ray that reaches the layer walks
    through it and gathers the strands it passes, so it costs about the same
    however thin they are, and the skin is seen through them.

        chest = Ellipsoid(0.26, 0.28, 0.40, fuzz=Fuzz(flow=(0, -0.3, -1)))

    The strands grow in locks, some longer than others. `density` says how
    much they hide of what is behind: long strands on a thin body look like
    smoke at the edges, and 2 or 3 makes them full. They rise 45 degrees
    unless told otherwise: lying flatter, the layer would be too thin to
    see. The rest is as in Hair (see _Combed)."""
    lift = 45
    density = 1.0


class Ripple:
    """An uneven surface that moves: lumps about `size` across that rise and
    sink up to height / 2, drifting `drift` units per second, (x, y, z)."""
    def __init__(self, height, size=0.2, drift=(0.0, 0.0, 0.0)):
        if len(drift) != 3:
            raise TypeError("Ripple: drift is a speed in each direction, (x, y, z)")
        self.height, self.size, self.drift = height, size, drift


class Hair(_Combed):
    """Single hairs over a shape, thousands of them, all combed toward
    `flow`. However many there are, each point of space only looks at the
    few that grow next to it, so they cost about the same as a handful of
    shapes.

        chest = Ellipsoid(0.26, 0.28, 0.40, hair=Hair(flow=(0, -0.3, -1)))

    A hair is `width` thick at the root and ends in a point. Lengths vary a
    little from hair to hair; `seed` picks another set of them. The rest is
    as in Fuzz (see _Combed).

    On an Ellipsoid the hairs are worked out exactly. On any other shape the
    skin is taken to be flat around each point, which costs more and goes
    wrong where the shape is thinner than the hairs are apart."""
    width = 0.005
    seed = 1

    def _on(self, skin, declared):
        """The hairs over skin (a primitive and how it was declared), placed
        and painted, in the coordinates of the model it is in."""
        placement = {k: _now(declared[k]) for k in ("size", "rotation", "pivot", "position", "bend", "symmetry")
                     if k in declared}
        flow, wind, gusts, own = _now(self.flow), _now(self.wind), _now(self.gusts), _now(self.material)
        common = (flow, self.length, self.width, self.spacing, self.lift, self.seed, self._grows())
        radii = _const(skin.r) if type(skin) is Ellipsoid else None
        if radii is not None:
            position = placement.get("position", (0.0, 0.0, 0.0))
            hairs = place(_Hairs(radii, *common, center=position, wind=wind, gusts=gusts, skin_look=own is None),
                          **placement)
        else:
            hairs = _HairsOn(place(skin, **placement), *common, wind=wind, gusts=gusts, skin_look=own is None)
        material = own if own is not None else _now(declared.get("material"))
        return hairs.paint(material) if material is not None else hairs


def _some(value, kind, example):
    """Fuzz or Hair as it was given: one, a list of them, or none ([] too).
    A subclass counts as one made with its own properties."""
    if value is None:
        return []
    found = []
    for one in value if isinstance(value, (list, tuple)) else [value]:
        if isinstance(one, type) and issubclass(one, kind):
            one = one()
        found.append(_given(one, kind, example))
    return found


def _given(value, kind, example):
    if value is not None and not isinstance(value, kind):
        raise TypeError(f"{kind.__name__.lower()} is a {kind.__name__}: {example}, not {value!r}")
    return value


def place(shape, size=1.0, rotation=(0.0, 0.0, 0.0), position=(0.0, 0.0, 0.0),
          bend=(0.0, 0.0), symmetry=None, ripple=None, pivot=(0.0, 0.0, 0.0), fuzz=None):
    """Fuzz, then ripple, then size, then rotation (x, y, z), then position, then bend
    (around x, around z), then symmetry. Anything left at its neutral value
    adds no code to the shader.

    pivot is the point of the shape that size and rotation leave where it
    is: they act around it instead of around the origin."""
    bend_x, bend_z = bend
    mirror = symmetry
    ripple = _given(ripple, Ripple, "Ripple(height=0.1, size=0.3)")
    if fuzz is not None:
        shape = shape.fuzz(fuzz, center=position)
    if ripple is not None:
        shape = shape.ripple(ripple.height, ripple.size, ripple.drift)
    rx, ry, rz = rotation
    grows = not (isinstance(size, (int, float)) and size == 1)
    turns = not (_zero(rx) and _zero(ry) and _zero(rz))
    if len(pivot) != 3:
        raise TypeError("pivot is a point: three numbers, (x, y, z)")
    # the pivot is taken to the origin, and put back afterwards together
    # with position; with nothing to turn or grow it changes nothing
    around = (grows or turns) and not all(_zero(c) for c in pivot)
    if around:
        shape = shape.move(tuple(-c for c in pivot))
        position = tuple(a + b for a, b in zip(pivot, position))
    if grows:
        shape = shape.scale(size)
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


_NEUTRAL = {"material": None, "hair": None, "ripple": None, "fuzz": None, "size": 1.0, "rotation": (0.0, 0.0, 0.0),
            "pivot": (0.0, 0.0, 0.0), "position": (0.0, 0.0, 0.0), "bend": (0.0, 0.0), "symmetry": None,
            "carve": None, "clip": None, "join": None}


class _Declarative(type):
    """Lets a primitive be written with its placement as properties instead
    of chained calls: the extra keywords are taken out before the primitive
    sees them, and kept, so they can still be changed (see _Declared)."""
    def __call__(cls, *args, **kw):
        declared = {k: kw.pop(k) for k in list(kw) if k in _DECLARED}
        return _Declared(cls, args, kw, declared)


class _Declared(Shape):
    """A primitive and the properties it was declared with. Changing one
    (part.material = rust) puts the shape together again, the same as if it
    had been written that way; the measures of the primitive itself are
    read (part.r) but not changed: for those, the part is replaced."""
    def __init__(self, cls, args, kw, declared):
        self.__dict__.update(_cls=cls, _args=args, _kw=kw, _declared=declared, _shape=None, _bare=None)
        self._check()

    def __setattr__(self, name, value):
        if name not in _DECLARED:
            raise AttributeError(
                f"{self._cls.__name__}: '{name}' cannot be changed (it can be given {', '.join(_DECLARED)}); "
                "to change its measures, put a new one in its place")
        self._declared[name] = value
        self.__dict__.update(_shape=None, _bare=None)
        self._check()

    def _check(self):
        """Put together now, so a wrong value is told where it is written."""
        self._built()
        self._role
        self._hairs()

    def __getattr__(self, name):
        if name.startswith("__") or name in ("_cls", "_declared"):
            raise AttributeError(name)
        if name in _DECLARED:
            return self._declared.get(name, _NEUTRAL[name])
        return getattr(self._primitive(), name)

    def __copy__(self):
        twin = _Declared.__new__(_Declared)
        twin.__dict__.update(self.__dict__, _declared=dict(self._declared), _shape=None)
        return twin

    def _primitive(self):
        if self._bare is None:
            kw = dict(self._kw)
            symmetry = _now(self._declared.get("symmetry"))
            if symmetry is not None and self._cls._meets_its_copy:
                kw["_symmetry"] = symmetry
            self.__dict__["_bare"] = type.__call__(self._cls, *self._args, **kw)
        return self._bare

    def _built(self):
        if self._shape is None:
            declared = {k: _now(v) for k, v in self._declared.items()}
            for name in ("material", "hair", "carve", "clip", "join"):
                declared.pop(name, None)
            shape = self._primitive()
            material = _now(self._declared.get("material"))
            if material is not None:
                shape = shape.paint(material)
            self.__dict__["_shape"] = place(shape, **declared) if declared else shape
        return self._shape

    @property
    def _role(self):
        return role_of(*(_now(self._declared.get(k)) for k in ("carve", "clip", "join")), self._cls.__name__)

    def _hairs(self, above=None):
        """The hair over the shape (see Hair), each one a part of its own
        that the model it is in adds after the others. above is the hair of
        that model, for a shape that says nothing of its own."""
        if "hair" in self._declared:
            hair = _now(self._declared["hair"])
        elif self._role is None or self._role[0] == "join":
            hair = above
        else:
            hair = None     # a shape that carves or clips has no skin to grow on
        hairs = _some(hair, Hair, "Hair(flow=(0, -1, 0))")
        layers = [h._on(self._primitive(), self._declared) for h in hairs]
        for layer in layers:
            # joined to what is before it with a blend just wide enough to
            # soften the roots: the model's own smooth would bury the hairs
            layer._role = ("join", 0.004)
        return layers

    def emit(self, ctx, p, mat):
        return self._built().emit(ctx, p, mat)

    def spheres(self):
        return self._built().spheres()

    def extent(self):
        return self._built().extent()

    def weight(self):
        return self._built().weight()


class _Primitive(Shape, metaclass=_Declarative):
    _meets_its_copy = False     # True: the primitive is told its symmetry (see Path)
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


def _unit(v):
    n = _length(v)
    return tuple(c / n for c in v)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


class Curve(_Primitive):
    """Thick curved line: a parabola arc from start to end that bends toward
    control (without touching it). With radius2 it tapers toward the end.

    With `up` (which way is out of the skin under it, for a lock of hair) it
    can be flattened against the skin: `flat` is how thick it is compared to
    how wide (1 = round). `grooves` carves that many lines along it. Its
    material is then drawn in its own coordinates: z runs along it, from 0
    at the start to its length at the end, y out of the skin and x across,
    so a texture stretched along z follows each lock."""
    def __init__(self, start=(0, 0, 0), control=(0, 1, 0), end=(1, 1, 0), radius=0.2, radius2=None,
                 up=None, flat=1.0, grooves=0):
        self.a, self.c, self.b = E(start), E(control), E(end)
        self.r1 = E(radius)
        self.r2 = E(radius if radius2 is None else radius2)
        self.up = up
        if up is None:
            if flat != 1 or grooves:
                raise TypeError("Curve: flat and grooves need up, the way out of the skin under it")
            return
        a, c, b, r1, r2 = (_const(v) for v in (self.a, self.c, self.b, self.r1, self.r2))
        if None in (a, c, b, r1, r2) or not all(isinstance(v, (int, float)) for v in (*up, flat, grooves)):
            raise TypeError("Curve: with up, every measure is a plain number")
        along = _unit([y - x for x, y in zip(a, b)])
        out = [u - _dot(up, along) * w for u, w in zip(up, along)]
        if _length(out) < 1e-6:
            raise ValueError("Curve: up cannot point along the curve")
        out = _unit(out)
        across = (along[1] * out[2] - along[2] * out[1],
                  along[2] * out[0] - along[0] * out[2],
                  along[0] * out[1] - along[1] * out[0])
        self.frame = (a, across, out, along)
        bent = [y - x for x, y in zip(a, c)]
        self.bent = (_dot(bent, across), _dot(bent, out) / flat, _dot(bent, along))
        self.long = _length([y - x for x, y in zip(a, b)])
        self.flat, self.grooves = flat, grooves
    def sdf(self, p):
        return (f"sdCurve({p}, {self.a.code}, {self.c.code}, {self.b.code}, "
                f"{self.r1.code}, {self.r2.code})")
    def emit(self, ctx, p, mat):
        if self.up is None:
            return super().emit(ctx, p, mat)
        root, across, out, along = self.frame
        v, q, d = ctx.var("p"), ctx.var("p"), ctx.var("d")
        ctx.line(f"vec3 {v} = {p}-{E(tuple(root)).code};")
        ctx.line(f"vec3 {q} = vec3(dot({v},{E(tuple(across)).code}), dot({v},{E(tuple(out)).code}), "
                 f"dot({v},{E(tuple(along)).code}));")
        squash = f"{q}*vec3(1.0,{_num(1 / self.flat)},1.0)"
        width = _const(self.r1)
        ctx.line(f"float {d} = sdCurve({squash}, vec3(0.0), {E(self.bent).code}, "
                 f"vec3(0.0,0.0,{_num(self.long)}), {self.r1.code}, {self.r2.code})"
                 f"*{_num(self.flat)};")
        if self.grooves:
            # lines along it, shallower toward the end; the distance is
            # shrunk by how steep they are, so no step goes through them
            k = math.pi * self.grooves / width
            depth = 0.10 * width * self.flat
            careful = 1.0 / (1.0 + depth * k * 0.5)
            ctx.line(f"{d} = ({d} + {_num(depth)}*(0.5+0.5*cos({q}.x*{_num(k)}))"
                     f"*(1.0-0.6*clamp({q}.z/{_num(self.long)},0.0,1.0)))*{_num(careful)};")
        if _see_through(mat):
            ctx.line(f"if( gSolid ) {d} = 1e4;")
        return d, f"{ctx.material_id(mat)}.0", q
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
    which is why the bends meet without a corner.

    With symmetry=, an end that lies on the mirror plane meets its copy in
    a curve too: that end is pulled toward instead of touched."""
    _meets_its_copy = True

    def __init__(self, points, radius=0.1, closed=False, radius2=None, _symmetry=None):
        points = [tuple(float(c) for c in point) for point in points]
        if len(points) < 2 or any(len(point) != 3 for point in points):
            raise ValueError("Path needs two or more points, each one (x, y, z)")
        if closed and len(points) < 3:
            raise ValueError("a closed Path needs three or more points")
        if closed and radius2 is not None:
            raise ValueError("a closed Path has no end to taper toward: leave radius2 out")
        if _symmetry in ("x", "y", "z") and not closed:
            points = _met("xyz".index(_symmetry), points)
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


def _met(axis, points):
    """The points of a Path that is mirrored across axis, with one more
    before an end that lies on the mirror plane: halfway to its neighbor,
    on the other side. The tube then crosses the plane straight, pulled by
    that end, and its copy carries on where it leaves off."""
    def across(end, neighbor):
        point = list(_halfway(end, neighbor))
        point[axis] = -point[axis]
        return tuple(point)

    def on_plane(point):
        return abs(point[axis]) < 1e-9

    first, last = points[0], points[-1]
    if on_plane(first):
        points = [across(first, points[1]), *points]
    if on_plane(last):
        points = [*points, across(last, points[-2])]
    return points


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


_GONE = 0.0001  # a size this small or smaller: the piece is not there


class _Scale(Shape):
    def __init__(self, child, factor):
        self.child, self.s = child, E(factor)
    def emit(self, ctx, p, mat):
        q, d2 = ctx.var("p"), ctx.var("d")
        k = _const(self.s)
        if k is not None and k > _GONE:
            ctx.line(f"vec3 {q} = {p}/{self.s.code};")
            d, m, u = self.child.emit(ctx, q, mat)
            ctx.line(f"float {d2} = {d}*{self.s.code};")     # the distance is scaled too
            return d2, m, u
        # A size that changes may reach zero, and dividing by zero spoils the
        # whole picture, not only this piece. At zero (or below) the piece is
        # not there: it is as far away as anything can be.
        s = ctx.var("s")
        ctx.line(f"float {s} = {self.s.code}; vec3 {q} = {p}/max({s}, {_num(_GONE)});")
        d, m, u = self.child.emit(ctx, q, mat)
        ctx.line(f"float {d2} = {s} > {_num(_GONE)} ? {d}*{s} : 1e4;")
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


def _push(wind, gusts, where):
    """GLSL for how the wind pushes the strands at `where`: in gusts `gusts`
    across that travel with it at one unit per second."""
    if wind is None:
        return "vec3(0.0)"
    wind, g = E(tuple(wind)).code, E(gusts).code
    travel = f"{wind}/max(length({wind}),1e-4)*iTime"
    return f"({wind}*(0.2+1.6*noise3(({where}-{travel})/{g})))"


def _combing(flow):
    """GLSL for a flow, made length 1: in Python when it is plain numbers."""
    if all(isinstance(c, (int, float)) for c in flow):
        return E(_unit(flow)).code
    return f"normalize({E(tuple(flow)).code})"


def _thickness(grows, out, point):
    """GLSL for how thick the strands grow where the skin looks toward out,
    at point (see _Combed.grows)."""
    if grows is None:
        return "1.0"
    asked = (Expr(out, "vec3"), Expr(point, "vec3"))
    return E(grows(*asked[:len(inspect.signature(grows).parameters)])).code


def _strand_number(root, spacing):
    """GLSL for a random number (0 to 1) of the fuzz strand that grows at
    root: each strand is a bump of the noise around one point of its
    lattice, so the nearest of those points tells it from the others."""
    return f"cellRand(floor({root}/{spacing}+0.5),7.0).x"


class _Fuzz(Shape):
    """A shape with fuzz: soft layers of strands around its surface, one
    for each Fuzz (see there). `center` is added to the place on the skin
    that grows() is asked about.

    The hair is not a surface. While a ray looks for what it hits, the
    outside of the hair is (a smooth shell, as far out from the skin as the
    tallest layer reaches). When it gets there, the render walks through the
    hair in short steps, gathering the strands it passes (gHair, see
    render), and sees the skin or what is behind through whatever they let
    pass."""
    def __init__(self, child, layers, center=(0.0, 0.0, 0.0)):
        self.child, self.layers, self.center = child, list(layers), tuple(center)
        for layer in self.layers:
            for name in ("length", "spacing", "lift", "density"):
                if not isinstance(getattr(layer, name), (int, float)):
                    raise TypeError(f"Fuzz: {name} is a number")
        self.tops = [f.length * math.sin(math.radians(f.lift)) for f in self.layers]
        self.top = max(self.tops)
    def emit(self, ctx, p, mat):
        d, m, u = self.child.emit(ctx, p, mat)
        for f, top in zip(self.layers, self.tops):
            ctx.hairs.append((E(top), E(f.spacing)))
        top = _num(self.top)
        r, n, skin = ctx.var("d"), ctx.var("n"), ctx.var("skin")
        # m<0: d is a bounding sphere's (see _Bound), not the skin's
        ctx.line(f"if( {m}>-0.5 ) gHairRoot = min(gHairRoot,{d});")
        ctx.line(f"float {r} = gHairy==0 ? {d}-{top} : {d};")
        ctx.line(f"if( gHairy==2 && {d}<{top} ) {{")
        # which way is out: the slope of the shape, measured around p
        taps = []
        for v in ("1,-1,-1", "-1,-1,1", "-1,1,-1", "1,1,1"):
            dv, _, _ = self.child.emit(ctx, f"({p}+vec3({v})*0.003)", mat)
            taps.append(f"vec3({v})*{dv}")
        ctx.line(f"  vec3 {n} = normalize({'+'.join(taps)});")
        ctx.line(f"  vec3 {skin} = {p}-{n}*{d};")
        for f, layer_top in zip(self.layers, self.tops):
            self._emit_layer(ctx, f, layer_top, d, m, u, n, skin)
        ctx.line("}")
        return r, m, u
    def _emit_layer(self, ctx, f, top, d, m, u, n, skin):
        """The strands of one Fuzz: how far up its strand the point is, and
        where on the skin that strand grows from: straight down, then back
        the way the strands lie, as far as they lean at this height."""
        way, up, h, root, s, k = (ctx.var(x) for x in ("way", "up", "h", "root", "s", "k"))
        c = _num(f.spacing)
        push = _push(_now(f.wind), _now(f.gusts), "p0")
        ctx.line(f"  vec3 {way} = strand({_combing(_now(f.flow))},{push},{n},{_num(math.radians(f.lift))});")
        # how far up the strand rises for each unit of its length
        ctx.line(f"  float {up} = max(dot({way},{n}),0.05);")
        ctx.line(f"  float {h} = clamp({d}/({_num(f.length)}*{up}),0.0,1.0);")
        ctx.line(f"  vec3 {root} = {skin}-({way}-{n}*{up})*clamp({d},0.0,{_num(top)})/{up};")
        # a strand grows where the fine noise is high; how long it is, the
        # coarse one decides, so the hair comes in locks
        ctx.line(f"  float {s} = noise3({root}/({c}*6.0)+3.7);")
        thick = _thickness(f._grows(), n, f"({skin}+{E(self.center).code})")
        dense = "" if f.density == 1 else f"{_num(f.density)}*"
        ctx.line(f"  float {k} = {dense}{thick}*smoothstep(0.45,0.65,noise3({root}/{c}))"
                 f"*clamp((0.3+0.7*{s}-{h})/0.15,0.0,1.0);")
        own = _now(f.material)
        if own is None:
            mid, uvw = m, u
        else:
            mid = f"{ctx.material_id(as_material(own))}.0"
            uvw = f"vec3({_strand_number(root, c)},{d},{h}*{_num(f.length)})"
        ctx.line(f"  if( {k}>gHair ) {{ gHair = {k}; gHairMat = {mid}; gHairUvw = {uvw}; gHairUp = {h}; }}")
    def spheres(self):
        inner = self.child.spheres()
        if inner is None:
            return None
        return [(center, radius + self.top) for center, radius in inner]
    def weight(self):
        return self.child.weight() + 3


class _Hairs(Shape):
    """Single hairs all over an ellipsoid (radii, centered), for the price of
    a few: the skin is cut into cells `spacing` apart, one hair grows in
    each, and every point only looks at the hairs of the cells around it.

    A hair rises `lift` degrees off the skin, combed toward `flow` (where
    the flow goes straight into or out of the skin, it falls downward), so the
    one passing through a point grew from a root further back along the
    flow: the higher the point, the further back. That root is found
    first, and only the 8 cells around it are asked.

    Where a pixel is wider than a hair, whether it lands on one or between
    two is chance, and flickers. So as the pixels widen the hairs thin out,
    a few at a time, and the fur turns into fuzz (see _Fuzz and _emit_fuzz)
    just as thick: far away there are no hairs left to look for.

    `grows(out)` or `grows(out, point)`, if given, says how thick the hair
    is (0 to 1) where the skin looks toward out; point is that place on the
    skin, `center` added. `wind`, a direction, bends the hair its way in
    gusts (see _strand). Hairs get their material in their own
    coordinates: x is a random number of each hair (0 to 1), y how far out
    of the skin, z along the hair from its root; with skin_look, in the
    coordinates the skin would have there."""
    fade = (0.7, 3.0)  # the hairs thin out from a pixel this many hairs wide to that one
    density = 2.0  # how much the fuzz hides, where it has taken over
    def __init__(self, radii, flow, length, width, spacing, lift, seed, grows=None,
                 center=(0.0, 0.0, 0.0), wind=None, gusts=0.5, skin_look=False):
        if len(radii) != 3 or len(flow) != 3:
            raise TypeError("hair: radii and flow have three numbers, (x, y, z)")
        if wind is not None and len(wind) != 3:
            raise TypeError("hair: wind is a direction, (x, y, z)")
        self.radii, self.flow = tuple(radii), tuple(flow)
        self.length, self.width, self.spacing = length, width, spacing
        self.lift, self.seed, self.grows = math.radians(lift), seed, grows
        self.center, self.wind, self.gusts = tuple(center), wind, gusts
        self.skin_look = skin_look
    def _combing(self):
        return _combing(self.flow)
    def _strand(self, at, out):
        """GLSL for which way a hair at `at` goes (see strand in the GLSL),
        the wind's gusts measured with `center` added, so they run on from
        one shape into the next."""
        push = _push(self.wind, self.gusts, f"({at}+{E(self.center).code})")
        return f"strand({self._combing()},{push},{out},{_num(self.lift)})"
    def emit(self, ctx, p, mat):
        F = self._combing()
        L, W, c = self.length, self.width, self.spacing
        rise = self.lift
        top = L * math.sin(rise * 1.1) + W
        v = {name: ctx.var(name) for name in (
            "h", "d", "m", "u", "n", "t", "rc", "cell", "ra", "rb", "j", "k",
            "root", "out", "dir", "a", "way", "side", "q", "up", "dc", "far")}
        h, d, m, u, far = v["h"], v["d"], v["m"], v["u"], v["far"]
        lo, hi = (k * W for k in self.fade)
        ctx.line(f"float {h} = {self._skin(ctx, p, mat)};")
        ctx.line(f"float {d} = {h}-{_num(top)}; float {m} = -1.0; vec3 {u} = {(ctx.space or p) if self.skin_look else p};")
        # how far the hairs have given way to the fuzz
        ctx.line(f"float {far} = smoothstep({_num(lo)},{_num(hi)},gFoot);")
        ctx.line(f"if( {d}<{_num(0.4 * c)} ) {{")
        # past the hairs that were found, the next one is at least this far
        ctx.line(f"  {d} = {_num(0.4 * c)};")
        # the root of the hair that would pass through p: down to the skin,
        # then back the way the hair lies, as far as it leans at this height
        n, t, rc = v["n"], v["t"], v["rc"]
        ctx.line(f"  vec3 {n} = {self._out(ctx, p, mat)};")
        ctx.line(f"  vec3 {t} = {self._strand(p, n)};")
        ctx.line(f"  vec3 {rc} = {p}-{n}*{h}-({t}-{n}*dot({t},{n}))*clamp({h},0.0,{_num(top)})"
                 f"/max(dot({t},{n}),0.05);")
        self._onto(ctx, rc, n, mat)
        ctx.line(f"  vec3 {v['cell']} = floor({rc}/{_num(c)}-0.5);")
        # once the fuzz has taken over, there are no hairs left to look for
        ctx.line(f"  for( int i=0; i<({far}<1.0 ? 8 : 0); i++ ) {{")
        cell, ra, rb, j, k = v["cell"], v["ra"], v["rb"], v["j"], v["k"]
        ctx.line(f"    vec3 cc = {cell}+vec3(float(i&1),float((i>>1)&1),float((i>>2)&1));")
        ctx.line(f"    vec3 {ra} = cellRand(cc,{_num(self.seed)}); vec3 {rb} = cellRand(cc,{_num(self.seed + 1)});")
        # one hair per cell, if the cell's random point is next to the skin
        ctx.line(f"    vec3 {j} = (cc+{ra})*{_num(c)};")
        root, out, way, side = v["root"], v["out"], v["way"], v["side"]
        self._root(ctx, j, k, root, out, n, c, mat)
        if self.grows is not None:
            ctx.line(f"    if( {self._thickness(out, root)}<={rb}.z ) continue;")
        # the farther, the fewer hairs: the fuzz takes the place of the rest
        ctx.line(f"    if( cellRand(cc,{_num(self.seed + 2)}).x<{far} ) continue;")
        # the way it lies along the skin, and how far it rises off it (a
        # hair straight up still has a way, the combing's)
        dr, a = v["dir"], v["a"]
        ctx.line(f"    vec3 {dr} = {self._strand(root, out)};")
        ctx.line(f"    float {a} = asin(clamp(dot({dr},{out}),0.05,1.0));")
        ctx.line(f"    vec3 {way} = normalize({dr}-{out}*dot({dr},{out})+combed({F},{out})*1e-3);")
        ctx.line(f"    vec3 {side} = cross({out},{way});")
        ctx.line(f"    float turn = ({rb}.x-0.5)*0.15;")
        ctx.line(f"    {way} = {way}*cos(turn)+{side}*sin(turn); {side} = cross({out},{way});")
        q, up, dc = v["q"], v["up"], v["dc"]
        ctx.line(f"    vec3 {q} = vec3(dot({p}-{root},{way}), dot({p}-{root},{side}), dot({p}-{root},{out}));")
        ctx.line(f"    vec2 {up} = vec2(cos({a}*(0.92+0.16*{rb}.y)), sin({a}*(0.92+0.16*{rb}.y)));")
        ctx.line(f"    float span = {_num(L)}*(0.6+0.4*{ra}.y);")
        ctx.line(f"    float {dc} = sdCapsule2({q}, vec3(0.0,0.0,-{_num(W)}), vec3({up}.x,0.0,{up}.y)*span, "
                 f"{_num(0.5 * W)}, {_num(0.15 * W)});")
        own = "" if self.skin_look else f"{u} = vec3({rb}.x, {q}.z, dot({q}.xz,{up})); "
        ctx.line(f"    if( {dc}<{d} ) {{ {d} = {dc}; {m} = {ctx.material_id(mat)}.0; {own}}}")
        ctx.line("  }")
        ctx.line("}")
        self._emit_fuzz(ctx, p, mat, v, top)
        if _see_through(mat):
            ctx.line(f"if( gSolid ) {d} = 1e4;")
        return d, m, u
    def _emit_fuzz(self, ctx, p, mat, v, top):
        """The fur as fuzz (see _Fuzz), as thick as the hairs that are gone:
        a smooth shell `top` out from the skin while a ray looks for what it
        hits, and strands to gather while it walks through. The strands lean
        as the hairs do and get the coordinates a hair would have there, so
        they take the same color. Close up, where every hair is still there,
        there is no shell and no walk."""
        L, c = self.length, self.spacing
        ctx.hairs.append((E(top), E(c)))
        h, d, m, far = v["h"], v["d"], v["m"], v["far"]
        mid = ctx.material_id(mat)
        n, way, hh, root, s, k, skin = (ctx.var(x) for x in ("n", "way", "hh", "root", "s", "k", "skin"))
        ctx.line(f"if( {far}>0.0 ) {{")
        ctx.line(f"  gHairRoot = min(gHairRoot,{h});")
        ctx.line(f"  if( gHairy==0 ) {{ if( {h}-{_num(top)}<{d} ) {{ {d} = {h}-{_num(top)}; {m} = {mid}.0; }} }}")
        ctx.line(f"  else if( gHairy==2 && {h}<{_num(top)} ) {{")
        ctx.line(f"    vec3 {n} = {self._out(ctx, p, mat)};")
        ctx.line(f"    vec3 {way} = {self._strand(p, n)};")
        ctx.line(f"    float {hh} = clamp({h}/{_num(top)},0.0,1.0);")
        ctx.line(f"    vec3 {skin} = {p}-{n}*{h};")
        self._onto(ctx, skin, n, mat)
        ctx.line(f"    vec3 {root} = {skin}-({way}-{n}*dot({way},{n}))*clamp({h},0.0,{_num(top)})"
                 f"/max(dot({way},{n}),0.05);")
        ctx.line(f"    float {s} = noise3({root}/({_num(c)}*6.0)+3.7);")
        ctx.line(f"    float {k} = {far}*{_num(self.density)}*{self._thickness(n, skin)}"
                 f"*smoothstep(0.45,0.65,noise3({root}/{_num(c)}))"
                 f"*clamp((0.3+0.7*{s}-{hh})/0.15,0.0,1.0);")
        uvw = v["u"] if self.skin_look else f"vec3({_strand_number(root, _num(c))},{h},{hh}*{_num(L)})"
        ctx.line(f"    if( {k}>gHair ) {{ gHair = {k}; gHairMat = {mid}.0; gHairUvw = {uvw}; gHairUp = {hh}; }}")
        ctx.line("  }")
        ctx.line("}")
    # --- the skin: an ellipsoid here, any shape in _HairsOn
    def _skin(self, ctx, at, mat):
        """GLSL for how far a point is from the skin."""
        return f"sdEllipsoid({at}, {E(self.radii).code})"
    def _out(self, ctx, at, mat):
        """GLSL for which way is out of the skin, near a point."""
        R = E(self.radii).code
        return f"normalize({at}/({R}*{R}))"
    def _onto(self, ctx, point, out, mat):
        """Put a point that is near the skin on it."""
        ctx.line(f"  {point} /= length({point}/{E(self.radii).code});")
    def _root(self, ctx, j, k, root, out, n, c, mat):
        """The hair of a cell grows from root, looking toward out, if the
        cell's random point j is next to the skin."""
        R = E(self.radii).code
        ctx.line(f"    float {k} = length({j}/{R});")
        ctx.line(f"    if( abs({k}-1.0)*{k}/length({j}/({R}*{R}))>{_num(0.5 * c)} ) continue;")
        ctx.line(f"    vec3 {root} = {j}/{k}; vec3 {out} = normalize({root}/({R}*{R}));")
    def _thickness(self, out, root):
        """GLSL for how thick the hair is at a place on the skin."""
        return _thickness(self.grows, out, f"({root}+{E(self.center).code})")
    def spheres(self):
        pad = self.length + self.width
        return [(center, radius + pad) for center, radius in Ellipsoid(*self.radii).spheres()]
    def weight(self):
        return 8


class _HairsOn(_Hairs):
    """_Hairs on any shape (the skin), in the skin's own space. Near a point
    the skin is taken to be flat: the 8 cells around it are asked how far
    their random point is from the skin, and the hair grows from there
    straight down, the way out of the skin at that point."""
    def __init__(self, skin, flow, length, width, spacing, lift, seed, grows=None, wind=None, gusts=0.5,
                 skin_look=False):
        super().__init__((1.0, 1.0, 1.0), flow, length, width, spacing, lift, seed, grows,
                         wind=wind, gusts=gusts, skin_look=skin_look)
        self.skin = skin
    def _skin(self, ctx, at, mat):
        d, _, _ = self.skin.emit(ctx, at, mat)
        return d
    def _out(self, ctx, at, mat):
        # four points around it: the skin rises toward out
        e = 0.0005
        ks = ((1, -1, -1), (-1, -1, 1), (-1, 1, -1), (1, 1, 1))
        ds = [self._skin(ctx, f"({at}+vec3({k[0] * e},{k[1] * e},{k[2] * e}))", mat) for k in ks]
        return "normalize(" + "+".join(f"vec3({k[0]}.0,{k[1]}.0,{k[2]}.0)*{d}" for k, d in zip(ks, ds)) + ")"
    def _onto(self, ctx, point, out, mat):
        pass
    def _root(self, ctx, j, k, root, out, n, c, mat):
        ctx.line(f"    float {k} = {self._skin(ctx, j, mat)};")
        ctx.line(f"    if( abs({k})>{_num(0.5 * c)} ) continue;")
        ctx.line(f"    vec3 {root} = {j}-{n}*{k}; vec3 {out} = {n};")
    def spheres(self):
        inner = self.skin.spheres()
        pad = self.length + self.width
        return None if inner is None else [(center, radius + pad) for center, radius in inner]


class _Ripple(Shape):
    """A shape with a lumpy, moving surface: smooth noise added to its
    distance. Skipped far from it, where it changes nothing worth the cost."""
    def __init__(self, child, height, size, drift):
        if len(drift) != 3:
            raise TypeError("ripple: drift is a speed in each direction, (x, y, z)")
        self.child, self.h, self.size, self.drift = child, E(height), E(size), E(tuple(drift))
    def emit(self, ctx, p, mat):
        d, m, u = self.child.emit(ctx, p, mat)
        r = ctx.var("d")
        ctx.line(f"float {r} = {d};")
        ctx.line(f"if( {d}<2.0*{self.h.code} ) {r} += {self.h.code}*"
                 f"(noise3(({p}-{self.drift.code}*iTime)/{self.size.code})-0.5);")
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
            return self.child.emit(ctx, p, ctx.repainted(self.material))
        finally:
            ctx.space = previous
    def spheres(self):
        return self.child.spheres()
    def weight(self):
        return self.child.weight()


class _Repaint(Shape):
    """The same shape with some of its materials swapped for others, however
    deep inside they were set: {this material: is drawn with this one}."""
    def __init__(self, child, swap):
        if not isinstance(swap, dict):
            raise TypeError("repaint is a dictionary: {a material: the one that replaces it}")
        self.child = child
        self.swap = {as_material(old): as_material(new) for old, new in swap.items()}
    def emit(self, ctx, p, mat):
        ctx.swaps.append(self.swap)
        try:
            return self.child.emit(ctx, p, mat)
        finally:
            ctx.swaps.pop()
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
            paint = (f" {rm} = {ctx.material_id(ctx.repainted(material))}.0; {ru} = {p};"
                     if material is not None else "")
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
