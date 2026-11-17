import math

import pytest

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


brass = claymarch.Material(color=(0.85, 0.65, 0.25))
rust = claymarch.Material(color=(0.45, 0.22, 0.12))
moss = claymarch.Material(color=(0.2, 0.5, 0.2))


class Knob(claymarch.Model):
    ball = claymarch.Sphere(0.1, material=brass)


class Door(claymarch.Model):
    panel = claymarch.Box(1, 2, 0.1, material=moss)
    knob = Knob(position=(0.4, 0, 0.1))


def test_repaint_swaps_a_material_deep_inside(tmp_path):
    class RustyKnob(claymarch.Model):
        ball = claymarch.Sphere(0.1, material=rust)

    class RustyDoor(claymarch.Model):
        panel = claymarch.Box(1, 2, 0.1, material=moss)
        knob = RustyKnob(position=(0.4, 0, 0.1))

    class Repainted(claymarch.Scene):
        door = Door(repaint={brass: rust})

    class Written(claymarch.Scene):
        door = RustyDoor

    assert scene_text(Repainted, tmp_path / "a") == scene_text(
        Written, tmp_path / "b"
    )


def test_repaint_leaves_the_other_materials_alone(tmp_path):
    class Plain(claymarch.Scene):
        door = Door

    class Repainted(claymarch.Scene):
        door = Door(repaint={rust: brass})

    assert scene_text(Plain, tmp_path / "a") == scene_text(
        Repainted, tmp_path / "b"
    )


def test_the_inner_repaint_goes_first(tmp_path):
    class Inner(claymarch.Model):
        knob = Knob(repaint={brass: rust})

    class Chained(claymarch.Scene):
        thing = Inner(repaint={rust: moss, brass: brass})

    class Direct(claymarch.Scene):
        thing = Knob(repaint={brass: moss})

    assert scene_text(Chained, tmp_path / "a") == scene_text(
        Direct, tmp_path / "b"
    )


def test_repaint_must_be_a_dictionary(tmp_path):
    class Wrong(claymarch.Scene):
        door = Door(repaint=rust)

    with pytest.raises(TypeError, match="dictionary"):
        scene_text(Wrong, tmp_path)


class Hinge(claymarch.Model):
    """A bar that turns around one of its ends."""
    bar = claymarch.Box(1, 0.1, 0.1, position=(0.5, 0, 0), material=brass)


class Gate(claymarch.Model):
    post = claymarch.Box(0.1, 2, 0.1, material=moss)
    leaf = Hinge(position=(0, 0.5, 0))


class Fence(claymarch.Model):
    gate = Gate(position=(2, 0, 0))


def swing(t):
    return (0, 40 * claymarch.sin(t), 0)


def test_pose_places_a_piece_deep_inside(tmp_path):
    class OpenGate(claymarch.Model):
        post = claymarch.Box(0.1, 2, 0.1, material=moss)
        leaf = Hinge(position=(0, 0.5, 0), rotation=swing)

    class OpenFence(claymarch.Model):
        gate = OpenGate(position=(2, 0, 0))

    class Posed(claymarch.Scene):
        fence = Fence(pose={Hinge: {"rotation": swing}})

    class Written(claymarch.Scene):
        fence = OpenFence

    assert scene_text(Posed, tmp_path / "a") == scene_text(
        Written, tmp_path / "b"
    )


def test_pose_can_be_a_method_of_time(tmp_path):
    class Swinging(Fence):
        def pose(self, t):
            return {Hinge: {"rotation": swing(t)}}

    class Method(claymarch.Scene):
        fence = Swinging

    class Value(claymarch.Scene):
        fence = Fence(pose={Hinge: {"rotation": swing}})

    assert scene_text(Method, tmp_path / "a") == scene_text(
        Value, tmp_path / "b"
    )


def test_pose_replaces_only_what_it_names(tmp_path):
    class Posed(claymarch.Scene):
        fence = Fence(pose={Hinge: {"rotation": (0, 30, 0)}})

    text = scene_text(Posed, tmp_path)
    # the hinge keeps the position its gate gave it
    assert "vec3(0.0, 0.5, 0.0)" in text


def test_the_outer_pose_has_the_last_word(tmp_path):
    class Inner(claymarch.Model):
        gate = Gate(pose={Hinge: {"rotation": (0, 10, 0)}})

    class Both(claymarch.Scene):
        thing = Inner(pose={Hinge: {"rotation": (0, 70, 0)}})

    class Outer(claymarch.Scene):
        thing = Gate(pose={Hinge: {"rotation": (0, 70, 0)}})

    assert scene_text(Both, tmp_path / "a") == scene_text(
        Outer, tmp_path / "b"
    )


def test_a_pose_is_not_for_the_model_that_has_it(tmp_path):
    class Plain(claymarch.Scene):
        gate = Gate

    class Posed(claymarch.Scene):
        gate = Gate(pose={Gate: {"position": (5, 0, 0)}})

    assert scene_text(Plain, tmp_path / "a") == scene_text(
        Posed, tmp_path / "b"
    )


def test_pose_says_what_is_wrong(tmp_path):
    class NotAClass(claymarch.Scene):
        gate = Gate(pose={"leaf": {"rotation": (0, 30, 0)}})

    class NotAPlacement(claymarch.Scene):
        gate = Gate(pose={Hinge: {"smooth": 0.1}})

    with pytest.raises(TypeError, match="by their class"):
        scene_text(NotAClass, tmp_path)
    with pytest.raises(TypeError, match="smooth"):
        scene_text(NotAPlacement, tmp_path)
