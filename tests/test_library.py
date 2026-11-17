import math

import claymarch
from claymarch.expr import Expr


# what a size that may reach zero leaves in the generated code
GUARD = "> 0.0001 ? "


def scene_text(scene, out):
    scene().export(out)
    return (out / "scene.glsl").read_text()


def test_sin_cos_and_radians_of_a_number_give_a_number():
    assert claymarch.radians(180) == math.pi
    assert claymarch.sin(0.5) == math.sin(0.5)
    assert claymarch.cos(0.5) == math.cos(0.5)


def test_sin_cos_and_radians_of_a_formula_give_a_formula():
    for function in (claymarch.sin, claymarch.cos, claymarch.radians):
        assert isinstance(function(claymarch.T * 2), Expr)


def test_a_fixed_size_of_zero_never_divides_by_zero(tmp_path):
    class Gone(claymarch.Scene):
        ball = claymarch.Sphere(0.3, size=0.0)

    assert "/0.0;" not in scene_text(Gone, tmp_path)


def test_a_size_that_changes_is_guarded_against_zero(tmp_path):
    class Beat(claymarch.Scene):
        ball = claymarch.Sphere(0.3, size=claymarch.sin(claymarch.T))

    assert GUARD in scene_text(Beat, tmp_path)


def test_a_fixed_size_keeps_the_plain_code(tmp_path):
    class Big(claymarch.Scene):
        ball = claymarch.Sphere(0.3, size=2.0)

    assert GUARD not in scene_text(Big, tmp_path)


def test_pivot_changes_nothing_without_size_or_rotation(tmp_path):
    class Plain(claymarch.Scene):
        box = claymarch.Box(1, 1, 1, position=(0, 1, 0))

    class Pivoted(claymarch.Scene):
        box = claymarch.Box(1, 1, 1, position=(0, 1, 0), pivot=(0, 0.5, 0))

    assert scene_text(Plain, tmp_path / "a") == scene_text(
        Pivoted, tmp_path / "b"
    )
