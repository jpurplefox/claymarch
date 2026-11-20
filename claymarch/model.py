"""Model: a thing made of parts, described as a class.

    class Critter(Model):
        body  = Ellipsoid(0.5, 0.5, 0.5).move(y=0.5)     # every Shape attribute is a part
        eye   = Sphere(0.08).move(x=0.15, y=0.7, z=0.4).mirror("x")
        smooth   = 0.1                                   # how the parts are blended
        material = Material(color=(0.3, 0.7, 0.6))       # paint for parts with no paint of their own
        position = (0, 0, 0)                             # placement: fixed values...

        def size(self, t):                               # ...or a method of time, to animate
            return 1 - 0.06 * cos(t * 6)

The rule: every property is either a VALUE, or a METHOD that receives t (time)
and returns the value. Nothing else is needed to animate.

A Model is itself a Shape, so a model can be a part of another model, and can
be moved, mirrored or combined like any other shape.
"""
import copy
import inspect

from .expr import T, Expr
from .shapes import (Material, Shape, _Bound, _Declared, _Repaint, as_material, assemble,
                     collect_parts, is_part, with_hair, part_names as _part_names, place, role_of)


def _is(value, number):
    return isinstance(value, (int, float)) and value == number


_PLACEMENT = ("size", "rotation", "pivot", "position", "bend")


def _own(part):
    """A copy of a part, for a model to change without changing the class."""
    if isinstance(part, type) and getattr(part, "_is_model", False):
        return part()
    if isinstance(part, Model):
        return part._copied()
    if isinstance(part, _Declared):
        return copy.copy(part)
    return part


class Model(Shape):
    _is_model = True

    # --- properties (each can be overridden by a value or by a method of t)
    parts = None                    # explicit list of shapes; default: all Shape attributes
    smooth = 0.0                    # transition radius used to join the parts
    material = None                 # Material (instance or class) for parts that have none
    repaint = None                  # {a material: the one that replaces it}, anywhere inside the model
    ripple = None                   # Ripple(height, size, drift): a lumpy surface that moves
    fuzz = None                     # Fuzz(...), or a list: a soft layer of strands over the whole model
    hair = None                     # Hair(...), or a list: single hairs on each of its shapes
    size = 1.0                      # uniform scale
    rotation = (0.0, 0.0, 0.0)      # degrees around x, y, z
    pivot = (0.0, 0.0, 0.0)         # the point of the model that size and rotation act around
    position = (0.0, 0.0, 0.0)
    bend = (0.0, 0.0)               # degrees per unit of height around x and around z, applied after position
    symmetry = None                 # "x", "y" or "z": the model is copied to the other side (see Shape.mirror)
    # what the model does when it is a part of another model (default: it is added)
    carve = None                    # a number or True: it is cut out of the parts before it
    clip = None                     # a number or True: only what is inside it is left of the parts before it
    join = None                     # a number: it is added, blended with the parts before it
    # speed-up: a sphere that contains the model. None = worked out from the
    # parts when it can be; a radius or (center, radius) = this one; False = none
    bounds = None

    def __init__(self, **overrides):
        """Critter(position=(1, 0, 0)) changes a property for this one instance.

        Each instance has its own parts, copied from the class, so changing
        one (in setup) does not change it anywhere else."""
        for name in _part_names(type(self)):
            self.__dict__[name] = _own(getattr(type(self), name))
        for name, value in overrides.items():
            if not hasattr(type(self), name):
                raise TypeError(f"{type(self).__name__} has no property '{name}'")
            setattr(self, name, value)
        if inspect.signature(self.setup).parameters:
            self.setup(T)
        else:
            self.setup()

    def setup(self):
        """Change the pieces inside, once the model is made: plain Python on
        this instance and its pieces, which are its own.

            def setup(self):
                self.head.ears.fuzz = Fuzz(length=0.03, spacing=0.006)
                self.tail.tip = Sphere(0.1, position=(0, 0, -0.7))   # a new part
                self.legs = None                                     # no legs

        It may receive t, to animate what it changes:
            def setup(self, t):
                self.tail.rotation = (0, 20 * sin(t), 0)"""

    def __setattr__(self, name, value):
        known = name.startswith("_") or hasattr(type(self), name) or name in self.__dict__
        if not known and not is_part(value):
            raise AttributeError(
                f"{type(self).__name__} has no property '{name}' (a new part is a Shape, a Model or a drawing)")
        super().__setattr__(name, value)

    _hair_above = None              # the hair of the model this one is in

    def _hand_down_hair(self, hair):
        """The hair of the model this one is in, for when it has none."""
        self._hair_above = hair

    def _copied(self):
        """This instance, with copies of the models inside it."""
        twin = copy.copy(self)
        for name, value in vars(self).items():
            twin.__dict__[name] = _own(value)
        return twin

    def _value(self, name):
        v = getattr(self, name)
        if callable(v) and not isinstance(v, (Shape, Expr, Material, type)):
            v = v(T) if inspect.signature(v).parameters else v()
        return v

    def build(self, blended=False):
        """The whole model as one Shape: parts joined, painted, then placed.

        blended: the model is a part that melts into its neighbors (or cuts
        them), so it must not wrap itself in a bounding sphere: the sphere
        would show in the blend."""
        placement = {name: self._value(name) for name in (*_PLACEMENT, "symmetry", "ripple", "fuzz")}
        # the fuzz of a model is in the model's own coordinates, those its
        # parts are written in
        return place(self._put_together(blended), **placement, rest={})

    def _put_together(self, blended):
        """The parts joined and painted, in the model's own space."""
        hair = self._value("hair")
        if hair is None and self._value("carve") is None and self._value("clip") is None:
            hair = self._hair_above
        if isinstance(self.parts, (list, tuple)) or self.parts is None:
            parts = collect_parts(self, hair)
        else:
            parts = with_hair(list(self._value("parts")), hair)
        if not parts:
            raise ValueError(f"{type(self).__name__} has no parts: add Shape attributes or a `parts` list")
        shape = assemble(parts, self._value("smooth"), type(self).__name__)

        material = self._value("material")
        if material is not None:
            shape = shape.paint(as_material(material))
        repaint = self._value("repaint")
        if repaint:
            shape = _Repaint(shape, repaint)

        # optional bounding sphere, in the model's own space (before size,
        # rotation and position, so it travels with the model)
        bounds = self._value("bounds")
        if bounds is None:
            # nobody said: work it out, when the model is worth skipping,
            # it is known how much room it takes, and nothing blends with it
            found = None if blended or shape.weight() < 4 else shape.extent()
            if found is not None:
                center, radius = found
                shape = _Bound(shape, tuple(round(c, 4) for c in center), round(radius * 1.02 + 0.005, 4))
        elif bounds is not False:
            center, radius = bounds if isinstance(bounds, (tuple, list)) else ((0.0, 0.0, 0.0), bounds)
            shape = _Bound(shape, center, radius)

        # painted first, then placed (in build): textures stay glued to the
        # model. Transforms left at their neutral value add no code to the shader.
        return shape

    @property
    def _role(self):
        return role_of(self._value("carve"), self._value("clip"), self._value("join"), type(self).__name__)

    def emit(self, ctx, p, mat):
        return self.build().emit(ctx, p, mat)

    def spheres(self):
        return self.build(blended=True).spheres()

    def weight(self):
        return self.build(blended=True).weight()
