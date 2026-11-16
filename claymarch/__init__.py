"""claymarch: describe 3D scenes in Python and translate them to a GLSL shader.

    from claymarch import *

    class Ball(Model):
        body = Sphere(0.5).move(y=0.5)
        material = Material(color=(0.9, 0.3, 0.2))

        def position(self, t):               # any property can be a method of time
            return (0, 0.2 * abs(sin(t * 3)), 0)

    class MyScene(Scene):
        ball = Ball()

To see it, reloading automatically on save:

    python -m claymarch my_scene.py
"""
from .expr import (E, Expr, P, T, checker, clamp, cos, fbm, floor, fract, length, maximum,
                   minimum, mix, noise, noise_at, sin, smoothstep, step, stripes, vec)
from .shapes import (Box, Capsule, Cone, Curve, CutCone, Cylinder, Disc, Drawing, Ellipsoid, Line, Material,
                     Path, Shape, Sphere, Torus, union)
from .model import Model
from .scene import Camera, Ground, Light, Scene

__all__ = [
    # shapes
    "Sphere", "Ellipsoid", "Box", "Capsule", "Curve", "Path", "Cylinder", "Torus", "Cone", "CutCone", "Shape", "union",
    # classes to subclass
    "Model", "Scene", "Drawing",
    # scene pieces
    "Camera", "Light", "Ground", "Material", "Disc", "Line",
    # expressions (for absolute value and powers use Python's abs(x) and x**n)
    "T", "P", "E", "Expr", "vec",
    "sin", "cos", "minimum", "maximum", "clamp", "fract", "floor", "length",
    "mix", "smoothstep", "step", "noise", "noise_at", "fbm", "checker", "stripes",
]
