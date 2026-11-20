"""Expressions: math written in Python that is translated to GLSL.

An Expr does not compute anything: it stores the TEXT of the computation. So
    0.1 * sin(T * 3)
is not a number, it is the GLSL expression "(0.1*sin((iTime*3.0)))", which the
graphics card evaluates every frame. This is how positions and angles are
animated, and how colors that depend on position are defined.
"""
import math


def _num(x):
    s = repr(float(x))
    if s in ("inf", "-inf", "nan"):
        raise ValueError(f"not a valid GLSL number: {x}")
    return s


class Expr:
    def __init__(self, code, kind="float"):
        self.code = code
        self.kind = kind            # "float", "vec2", "vec3"

    def __repr__(self):
        return f"Expr<{self.kind}>({self.code})"

    # --- arithmetic
    def __add__(self, o):      return _bin("+", self, o)
    def __radd__(self, o):     return _bin("+", o, self)
    def __sub__(self, o):      return _bin("-", self, o)
    def __rsub__(self, o):     return _bin("-", o, self)
    def __mul__(self, o):      return _bin("*", self, o)
    def __rmul__(self, o):     return _bin("*", o, self)
    def __truediv__(self, o):  return _bin("/", self, o)
    def __rtruediv__(self, o): return _bin("/", o, self)
    def __neg__(self):         return Expr(f"(-{self.code})", self.kind)
    def __abs__(self):         return Expr(f"abs({self.code})", self.kind)       # abs(x) works
    def __pow__(self, n):      return Expr(f"pow({self.code}, {E(n).code})", self.kind)   # x ** n works

    # --- vector components
    @property
    def x(self): return Expr(f"{self.code}.x")
    @property
    def y(self): return Expr(f"{self.code}.y")
    @property
    def z(self): return Expr(f"{self.code}.z")


def E(x):
    """Turn numbers, tuples or Expr into an Expr."""
    if isinstance(x, Expr):
        return x
    if isinstance(x, bool):
        raise TypeError("expected a number, not True/False")
    if isinstance(x, (int, float)):
        return Expr(_num(x))
    if isinstance(x, (tuple, list)) and 2 <= len(x) <= 3:
        parts = [E(c) for c in x]
        if any(p.kind != "float" for p in parts):
            raise TypeError("vector components must be numbers")
        return Expr(f"vec{len(x)}({', '.join(p.code for p in parts)})", f"vec{len(x)}")
    raise TypeError(f"cannot convert {x!r} to GLSL")


def _bin(op, a, b):
    a, b = E(a), E(b)
    kind = a.kind if a.kind != "float" else b.kind
    # a negative number on the right goes in parentheses: "x--0.3" is not
    # a subtraction in GLSL
    right = f"({b.code})" if b.code.startswith("-") else b.code
    return Expr(f"({a.code}{op}{right})", kind)


def _fn(name, *args, kind=None):
    args = [E(a) for a in args]
    if kind is None:
        kind = next((a.kind for a in args if a.kind != "float"), "float")
    return Expr(f"{name}({', '.join(a.code for a in args)})", kind)


def vec3(x):
    """Make sure something is a vec3 (a single number is repeated in x, y, z)."""
    e = E(x)
    return e if e.kind == "vec3" else Expr(f"vec3({e.code})", "vec3")


# ---------------------------------------------------------------- variables
T = Expr("iTime")            # time in seconds
P = Expr("uvw", "vec3")      # position where paint() was applied (for drawing materials)

# ---------------------------------------------------------------- functions
# Same names as GLSL. For absolute value and powers use Python's abs(x) and x**n.
# sin, cos and radians of a plain number give a plain number, worked out in
# Python; of a formula, a formula.
def _plain(x):          return isinstance(x, (int, float)) and not isinstance(x, bool)
def sin(x):             return math.sin(x) if _plain(x) else _fn("sin", x)
def cos(x):             return math.cos(x) if _plain(x) else _fn("cos", x)
def radians(x):
    """Degrees to radians, for sin() and cos()."""
    return math.radians(x) if _plain(x) else _fn("radians", x)
def minimum(a, b):      return _fn("min", a, b)
def maximum(a, b):      return _fn("max", a, b)
def clamp(x, lo, hi):   return _fn("clamp", x, lo, hi)
def fract(x):           return _fn("fract", x)
def floor(x):           return _fn("floor", x)
def length(v):          return _fn("length", v, kind="float")
def vec(x, y, z):       return _fn("vec3", x, y, z, kind="vec3")

def mix(a, b, k):
    """Blend between a and b: k=0 gives a, k=1 gives b."""
    return _fn("mix", a, b, k)

def smoothstep(a, b, x):
    """Smooth transition: 0 when x<a, 1 when x>b (reversed if a>b)."""
    return _fn("smoothstep", a, b, x, kind="float")

def step(edge, x):
    """Hard transition: 0 when x<edge, 1 otherwise."""
    return _fn("step", edge, x, kind="float")

def noise(p):
    """Smooth noise between 0 and 1 from a 3D position."""
    return _fn("noise3", vec3(p), kind="float")

def noise_at(x, y, z):
    """The same noise as noise(), computed in Python for one fixed point: it
    returns a plain number. Useful to place things on a surface that was
    shaped with noise (for example, to know how high a hilly ground is)."""
    import math

    def uhash(v):
        v &= 0xFFFFFFFF
        v ^= v >> 16
        v = (v * 0x7feb352d) & 0xFFFFFFFF
        v ^= v >> 15
        v = (v * 0x846ca68b) & 0xFFFFFFFF
        v ^= v >> 16
        return v

    def corner(i, j, k):
        return uhash(i + uhash(j + uhash(k))) / 4294967295.0

    def lerp(a, b, k):
        return a + (b - a) * k

    i, j, k = math.floor(x), math.floor(y), math.floor(z)
    fx, fy, fz = (c - math.floor(c) for c in (x, y, z))
    fx, fy, fz = (f * f * (3.0 - 2.0 * f) for f in (fx, fy, fz))
    return lerp(lerp(lerp(corner(i, j, k),         corner(i + 1, j, k),         fx),
                     lerp(corner(i, j + 1, k),     corner(i + 1, j + 1, k),     fx), fy),
                lerp(lerp(corner(i, j, k + 1),     corner(i + 1, j, k + 1),     fx),
                     lerp(corner(i, j + 1, k + 1), corner(i + 1, j + 1, k + 1), fx), fy), fz)


def fbm(p):
    """Several layers of noise added together (more fine detail), between 0 and 1."""
    return _fn("fbm3", vec3(p), kind="float")

def checker(p, size=1.0):
    """Checkerboard on the xz plane: returns 0 or 1."""
    p, s = E(p), E(size)
    return Expr(f"mod(floor({p.code}.x/{s.code})+floor({p.code}.z/{s.code}),2.0)")

def stripes(x, width=0.2):
    """Stripes along one coordinate: returns 0 or 1."""
    x, w = E(x), E(width)
    return Expr(f"step(0.5,fract({x.code}/(2.0*{w.code})))")
