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
import inspect

from .expr import T, Expr
from .shapes import Material, Shape, _Bound, as_material, assemble, collect_parts, place, role_of


def _is(value, number):
    return isinstance(value, (int, float)) and value == number


class Model(Shape):
    _is_model = True

    # --- properties (each can be overridden by a value or by a method of t)
    parts = None                    # explicit list of shapes; default: all Shape attributes
    smooth = 0.0                    # transition radius used to join the parts
    material = None                 # Material (instance or class) for parts that have none
    size = 1.0                      # uniform scale
    rotation = (0.0, 0.0, 0.0)      # degrees around x, y, z
    position = (0.0, 0.0, 0.0)
    bend = (0.0, 0.0)               # degrees per unit of height around x and around z, applied after position
    symmetry = None                 # "x", "y" or "z": the model is copied to the other side (see Shape.mirror)
    # what the model does when it is a part of another model (default: it is added)
    carve = None                    # a number or True: it is cut out of the parts before it
    join = None                     # a number: it is added, blended with the parts before it
    bounds = None                   # speed-up: radius, or (center, radius), of a sphere that contains the model

    def __init__(self, **overrides):
        """Critter(position=(1, 0, 0)) changes a property for this one instance."""
        for name, value in overrides.items():
            if not hasattr(type(self), name):
                raise TypeError(f"{type(self).__name__} has no property '{name}'")
            setattr(self, name, value)

    def _value(self, name):
        v = getattr(self, name)
        if callable(v) and not isinstance(v, (Shape, Expr, Material, type)):
            v = v(T) if inspect.signature(v).parameters else v()
        return v

    def build(self):
        """The whole model as one Shape: parts joined, painted, then placed."""
        if isinstance(self.parts, (list, tuple)) or self.parts is None:
            parts = collect_parts(self)
        else:
            parts = list(self._value("parts"))
        if not parts:
            raise ValueError(f"{type(self).__name__} has no parts: add Shape attributes or a `parts` list")
        shape = assemble(parts, self._value("smooth"), type(self).__name__)

        material = self._value("material")
        if material is not None:
            shape = shape.paint(as_material(material))

        # optional bounding sphere, in the model's own space (before size,
        # rotation and position, so it travels with the model)
        bounds = self._value("bounds")
        if bounds is not None:
            center, radius = bounds if isinstance(bounds, (tuple, list)) else ((0.0, 0.0, 0.0), bounds)
            shape = _Bound(shape, center, radius)

        # painted first, then placed: textures stay glued to the model.
        # Transforms left at their neutral value add no code to the shader.
        return place(shape, size=self._value("size"), rotation=self._value("rotation"),
                     position=self._value("position"), bend=self._value("bend"),
                     symmetry=self._value("symmetry"))

    @property
    def _role(self):
        return role_of(self._value("carve"), self._value("join"), type(self).__name__)

    def emit(self, ctx, p, mat):
        return self.build().emit(ctx, p, mat)
