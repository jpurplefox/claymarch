"""Shapes and operations. Every object knows how to write its piece of GLSL.

A scene is a tree: the leaves are primitives (Sphere, Box...) and the inner
nodes are transforms (move, rotate) and combinations (union, subtract). To
generate the shader the tree is walked and every node adds lines to map(), the
distance function (SDF) of the whole scene.
"""
import inspect

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
    """
    color = (0.8, 0.8, 0.8)
    specular = 0.2
    shininess = 32.0
    glow = 0.0
    bump = None

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


class Shape:
    """Base of everything that can be drawn."""

    # what this shape does when it is a part of a Model: None = it is added;
    # ("carve", smooth) = it is cut out of the parts before it;
    # ("join", smooth) = it is added, blended with the parts before it
    _role = None

    def emit(self, ctx, p, mat):
        """Write GLSL into ctx. Returns (distance, material, coords) as text."""
        raise NotImplementedError

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
        layers = []
        for i, disc in enumerate(_discs(drawing)):
            center = tuple(a + b for a, b in zip(at, disc.at))
            height = lift * (i + 1)
            if isinstance(height, float):
                height = round(height, 9)        # 0.006 * 3 is 0.018, not 0.018000000000000002
            layer = self.round(height) & Sphere(disc.radius).move(center)
            if disc.inner:
                layer = layer - Sphere(disc.inner).move(center)
            if disc.material is not None:
                layer = layer.paint(disc.material)
            layers.append(layer)
        return union(*layers)

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


class Drawing:
    """Several discs, one on top of another, to draw on a surface: an eye, a
    spot. It knows nothing about the shape it goes on; that shape puts it in
    place with patch():

        class Eye(Drawing):
            rim   = Disc(0.20, material=yellow)
            pupil = Disc(0.13, material=black)       # written later: goes on top

        eyes = skull.patch(Eye(), at=(0.44, 0.06, 0.22)).mirror("x")

    size makes the whole drawing bigger or smaller: Eye(size=0.8).
    lift is how far each disc is raised above the one below it (and the
    first one above the surface): smaller looks more painted on, bigger
    looks more like a sticker. Too small and the layers show holes.
    """
    size = 1.0
    lift = 0.006

    def __init__(self, size=None, patch=None, symmetry=None, lift=None):
        if size is not None:
            self.size = size
        if lift is not None:
            self.lift = lift
        # as a part of a Model: where it is drawn on the parts before it
        self.patch_at, self.symmetry = patch, symmetry

    def discs(self):
        found = {}
        for cls in reversed(type(self).__mro__):
            for name, value in vars(cls).items():
                if not name.startswith("_") and isinstance(value, Disc):
                    found[name] = value
        if not found:
            raise ValueError(f"{type(self).__name__} has no discs: add Disc attributes")
        k = self.size
        return [Disc(d.radius * k, d.inner * k, d.material, tuple(c * k for c in d.at))
                for d in found.values()]


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
    whole = None
    for part in parts:
        if is_drawing(part):
            if whole is None:
                raise ValueError(f"{who}: a drawing needs a part before it to be drawn on")
            if part.patch_at is None:
                raise ValueError(f"{who}: a drawing used as a part needs patch=(x, y, z), the point where it goes")
            drawn = whole.patch(part, at=part.patch_at)
            whole = whole.union(drawn if part.symmetry is None else drawn.mirror(part.symmetry))
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


def _lift(drawing):
    if isinstance(drawing, type) and issubclass(drawing, Drawing):
        return drawing.lift
    lift = getattr(drawing, "lift", None)
    return 0.006 if lift is None else lift


def _discs(drawing):
    if isinstance(drawing, type) and issubclass(drawing, Drawing):
        drawing = drawing()
    if isinstance(drawing, Drawing):
        return drawing.discs()
    if isinstance(drawing, Disc):
        return [drawing]
    raise TypeError(f"patch expects a Disc or a Drawing, got {drawing!r}")


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
_DECLARED = ("material", "size", "rotation", "position", "bend", "symmetry", "carve", "join")


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
          bend=(0.0, 0.0), symmetry=None):
    """Size, then rotation (x, y, z), then position, then bend (around x,
    around z), then symmetry. Anything left at its neutral value adds no
    code to the shader."""
    bend_x, bend_z = bend
    mirror = symmetry
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
        return d, f"{ctx.material_id(mat)}.0", ctx.space or p


class Sphere(_Primitive):
    def __init__(self, radius=0.5):
        self.r = E(radius)
    def sdf(self, p):
        return f"length({p})-{self.r.code}"


class Ellipsoid(_Primitive):
    """Stretched sphere: one radius per axis."""
    def __init__(self, rx=0.5, ry=0.5, rz=0.5):
        self.r = E((rx, ry, rz))
    def sdf(self, p):
        return f"sdEllipsoid({p}, {self.r.code})"


class Box(_Primitive):
    def __init__(self, width=1.0, height=1.0, depth=1.0, rounding=0.0):
        r = E(rounding)
        self.b = [E(width) * 0.5 - r, E(height) * 0.5 - r, E(depth) * 0.5 - r]
        self.rounding = r
    def sdf(self, p):
        b = ", ".join(c.code for c in self.b)
        return f"sdBox({p}, vec3({b}))-{self.rounding.code}"


class Capsule(_Primitive):
    """Thick segment between two points. With radius2 it tapers toward the end."""
    def __init__(self, start=(0, 0, 0), end=(0, 1, 0), radius=0.2, radius2=None):
        self.a, self.b = E(start), E(end)
        self.r1 = E(radius)
        self.r2 = E(radius if radius2 is None else radius2)
    def sdf(self, p):
        return f"sdCapsule2({p}, {self.a.code}, {self.b.code}, {self.r1.code}, {self.r2.code})"


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


class Cylinder(_Primitive):
    """Vertical cylinder centered at the origin."""
    def __init__(self, radius=0.5, height=1.0, rounding=0.0):
        r = E(rounding)
        self.radius, self.half, self.rounding = E(radius) - r, E(height) * 0.5 - r, r
    def sdf(self, p):
        return f"sdRoundCyl({p}, {self.radius.code}, {self.half.code}, {self.rounding.code})"


class Torus(_Primitive):
    """Donut lying flat (its axis is the vertical one)."""
    def __init__(self, radius=0.5, thickness=0.15):
        self.R, self.r = E(radius), E(thickness)
    def sdf(self, p):
        return f"sdTorus({p}, {self.R.code}, {self.r.code})"


class Cone(_Primitive):
    """Rounded cone: base at the origin, tip pointing up."""
    def __init__(self, radius=0.3, height=1.0):
        self.r, self.h = E(radius), E(height)
    def sdf(self, p):
        return f"sdCapsule2({p}, vec3(0.0), vec3(0.0,{self.h.code},0.0), {self.r.code}, 0.0)"


class CutCone(_Primitive):
    """Cone with its tip cut off: vertical, centered at the origin, flat ends.
    radius is the bottom, radius2 the top. rounding softens the edges."""
    def __init__(self, radius=0.5, radius2=0.25, height=1.0, rounding=0.0):
        r = E(rounding)
        self.r1, self.r2, self.half, self.rounding = E(radius) - r, E(radius2) - r, E(height) * 0.5 - r, r
    def sdf(self, p):
        return (f"sdCutCone({p}, {self.half.code}, {self.r1.code}, {self.r2.code}, "
                f"{self.rounding.code})")


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


class _Rotate(Shape):
    def __init__(self, child, plane, degrees):
        self.child, self.plane, self.g = child, plane, E(degrees)
    def emit(self, ctx, p, mat):
        q = ctx.var("p")
        ctx.line(f"vec3 {q} = {p}; {q}.{self.plane} = rot2(radians({self.g.code}))*{q}.{self.plane};")
        return ctx.emit_turned(self.child, q, mat)


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


# =================================================================== modifiers
class _Round(Shape):
    def __init__(self, child, radius):
        self.child, self.r = child, E(radius)
    def emit(self, ctx, p, mat):
        d, m, u = self.child.emit(ctx, p, mat)
        d2 = ctx.var("d")
        ctx.line(f"float {d2} = {d}-{self.r.code};")
        return d2, m, u


class _Shell(Shape):
    def __init__(self, child, thickness):
        self.child, self.g = child, E(thickness)
    def emit(self, ctx, p, mat):
        d, m, u = self.child.emit(ctx, p, mat)
        d2 = ctx.var("d")
        ctx.line(f"float {d2} = abs({d})-{self.g.code};")
        return d2, m, u


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


# ================================================================ combinations
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
