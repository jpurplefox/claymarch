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


class OpenFence(Fence):
    def setup(self):
        self.gate.leaf.rotation = (0, 70, 0)


def test_setup_changes_a_piece_deep_inside(tmp_path):
    class OpenGate(claymarch.Model):
        post = claymarch.Box(0.1, 2, 0.1, material=moss)
        leaf = Hinge(position=(0, 0.5, 0), rotation=(0, 70, 0))

    class Written(claymarch.Model):
        gate = OpenGate(position=(2, 0, 0))

    class Changed(claymarch.Scene):
        fence = OpenFence

    class Rewritten(claymarch.Scene):
        fence = Written

    assert scene_text(Changed, tmp_path / "a") == scene_text(
        Rewritten, tmp_path / "b"
    )


def test_setup_changes_only_that_model(tmp_path):
    class Plain(claymarch.Scene):
        fence = Fence

    before = scene_text(Plain, tmp_path / "a")
    OpenFence()

    class Both(claymarch.Scene):
        fence = Fence
        open = OpenFence(position=(5, 0, 0))

    assert scene_text(Plain, tmp_path / "b") == before
    assert Gate.leaf.rotation == (0.0, 0.0, 0.0)
    # the hinge keeps the position its gate gave it
    assert "vec3(0.0, 0.5, 0.0)" in scene_text(Both, tmp_path / "c")


def test_setup_can_receive_t(tmp_path):
    class Swinging(Fence):
        def setup(self, t):
            self.gate.leaf.rotation = swing(t)

    class Method(claymarch.Scene):
        fence = Swinging

    class Written(claymarch.Scene):
        fence = Fence(
            gate=Gate(
                leaf=Hinge(position=(0, 0.5, 0), rotation=swing),
                position=(2, 0, 0),
            )
        )

    assert scene_text(Method, tmp_path / "a") == scene_text(
        Written, tmp_path / "b"
    )


def test_the_outer_setup_has_the_last_word(tmp_path):
    class Half(Gate):
        def setup(self):
            self.leaf.rotation = (0, 10, 0)

    class Inner(claymarch.Model):
        gate = Half

        def setup(self):
            self.gate.leaf.rotation = (0, 70, 0)

    class Outer(claymarch.Model):
        gate = Gate

        def setup(self):
            self.gate.leaf.rotation = (0, 70, 0)

    class A(claymarch.Scene):
        thing = Inner

    class B(claymarch.Scene):
        thing = Outer

    assert scene_text(A, tmp_path / "a") == scene_text(B, tmp_path / "b")


def test_setup_adds_and_takes_away_parts(tmp_path):
    class Changed(Gate):
        def setup(self):
            self.leaf = None
            self.top = claymarch.Sphere(0.3, position=(0, 1, 0))

    class Written(claymarch.Model):
        post = claymarch.Box(0.1, 2, 0.1, material=moss)
        top = claymarch.Sphere(0.3, position=(0, 1, 0))

    class A(claymarch.Scene):
        gate = Changed

    class B(claymarch.Scene):
        gate = Written

    assert scene_text(A, tmp_path / "a") == scene_text(B, tmp_path / "b")


def test_setup_changes_a_shape_of_a_piece(tmp_path):
    class Rusty(Fence):
        def setup(self):
            self.gate.post.material = rust
            self.gate.post.position = (0, 1, 0)

    class RustyGate(claymarch.Model):
        post = claymarch.Box(0.1, 2, 0.1, material=rust, position=(0, 1, 0))
        leaf = Hinge(position=(0, 0.5, 0))

    class Written(claymarch.Model):
        gate = RustyGate(position=(2, 0, 0))

    class Plain(claymarch.Scene):
        fence = Fence

    before = scene_text(Plain, tmp_path / "a")

    class A(claymarch.Scene):
        fence = Rusty

    class B(claymarch.Scene):
        fence = Written

    assert scene_text(A, tmp_path / "b") == scene_text(B, tmp_path / "c")
    assert scene_text(Plain, tmp_path / "d") == before


def test_the_measures_of_a_shape_are_not_changed_but_replaced():
    class Wrong(Gate):
        def setup(self):
            self.post.height = 3

    with pytest.raises(AttributeError, match="new one in its place"):
        Wrong()


def test_setup_has_the_last_word_over_the_instance(tmp_path):
    class Raised(Gate):
        def setup(self):
            self.position = (0, 1, 0)

    class A(claymarch.Scene):
        gate = Raised(position=(5, 0, 0))

    class B(claymarch.Scene):
        gate = Gate(position=(0, 1, 0))

    assert scene_text(A, tmp_path / "a") == scene_text(B, tmp_path / "b")


def test_a_misspelled_property_in_setup_is_an_error():
    class Wrong(Gate):
        def setup(self):
            self.leaf.rotatoin = (0, 30, 0)

    with pytest.raises(AttributeError, match="rotatoin"):
        Wrong()


def test_clip_leaves_what_is_inside_the_part(tmp_path):
    class Declared(claymarch.Scene):
        class dome(claymarch.Model):
            ball = claymarch.Sphere(0.5)
            half = claymarch.Box(2, 1, 2, position=(0, 0.5, 0), clip=0.02)

    class Chained(claymarch.Scene):
        class dome(claymarch.Model):
            parts = [
                claymarch.Sphere(0.5).intersect(
                    claymarch.Box(2, 1, 2, position=(0, 0.5, 0)), smooth=0.02
                )
            ]

    assert scene_text(Declared, tmp_path / "a") == scene_text(
        Chained, tmp_path / "b"
    )


def test_a_model_can_clip(tmp_path):
    class Half(claymarch.Model):
        box = claymarch.Box(2, 1, 2, position=(0, 0.5, 0))

    class Clipped(claymarch.Scene):
        class dome(claymarch.Model):
            ball = claymarch.Sphere(0.5)
            half = Half(clip=True)

    class Whole(claymarch.Scene):
        class dome(claymarch.Model):
            ball = claymarch.Sphere(0.5)
            half = Half()

    assert scene_text(Clipped, tmp_path / "a") != scene_text(
        Whole, tmp_path / "b"
    )


def test_clip_says_what_is_wrong(tmp_path):
    with pytest.raises(TypeError, match="one role"):
        claymarch.Sphere(0.5, clip=True, carve=True)

    class Nothing(claymarch.Scene):
        class dome(claymarch.Model):
            half = claymarch.Box(1, 1, 1, clip=True)

    with pytest.raises(ValueError, match="nothing before it to clip"):
        Nothing().export(tmp_path)


HALF_RING = [(0, 1, 0), (1, 0, 0), (0, -1, 0)]


def test_a_mirrored_path_meets_its_copy_in_a_curve(tmp_path):
    class Declared(claymarch.Scene):
        ring = claymarch.Path(HALF_RING, 0.1, symmetry="x")

    class ByHand(claymarch.Scene):
        ring = claymarch.Path(
            [(-0.5, 0.5, 0), *HALF_RING, (-0.5, -0.5, 0)], 0.1
        ).mirror("x")

    assert scene_text(Declared, tmp_path / "a") == scene_text(
        ByHand, tmp_path / "b"
    )


def test_a_mirrored_path_away_from_the_plane_is_left_alone(tmp_path):
    points = [(0.2, 1, 0), (1, 0, 0), (0.2, -1, 0)]

    class Declared(claymarch.Scene):
        horns = claymarch.Path(points, 0.1, symmetry="x")

    class ByHand(claymarch.Scene):
        horns = claymarch.Path(points, 0.1).mirror("x")

    assert scene_text(Declared, tmp_path / "a") == scene_text(
        ByHand, tmp_path / "b"
    )


def test_sheen_reaches_the_shader(tmp_path):
    velvet = claymarch.Material(color=(0.5, 0.2, 0.2), sheen=0.9)

    class Cushion(claymarch.Scene):
        ball = claymarch.Sphere(0.5, material=velvet)

    assert "shn = 0.9;" in scene_text(Cushion, tmp_path)


def test_fuzz_declared_is_fuzz_chained(tmp_path):
    fuzz = claymarch.Fuzz(length=0.04, spacing=0.02, flow=(0, 0, -1))

    class Declared(claymarch.Scene):
        ball = claymarch.Sphere(0.5, fuzz=fuzz)

    class Chained(claymarch.Scene):
        ball = claymarch.Sphere(0.5).fuzz(fuzz)

    assert scene_text(Declared, tmp_path / "a") == scene_text(
        Chained, tmp_path / "b"
    )


def test_denser_fuzz_stops_more_light(tmp_path):
    class Thin(claymarch.Scene):
        ball = claymarch.Sphere(0.5, fuzz=claymarch.Fuzz())

    class Dense(claymarch.Scene):
        ball = claymarch.Sphere(0.5, fuzz=claymarch.Fuzz(density=3))

    assert "3.0*smoothstep(0.45" not in scene_text(Thin, tmp_path / "a")
    assert "3.0*smoothstep(0.45" in scene_text(Dense, tmp_path / "b")


def test_fuzz_makes_room_in_the_bounding_sphere():
    furry = claymarch.Sphere(0.5).fuzz(claymarch.Fuzz(length=0.04, lift=90))
    [(center, radius)] = furry.spheres()
    assert radius == pytest.approx(0.54)


def test_lying_fuzz_is_as_deep_as_it_rises():
    furry = claymarch.Sphere(0.5).fuzz(claymarch.Fuzz(length=0.04, lift=30))
    [(center, radius)] = furry.spheres()
    assert radius == pytest.approx(0.52)


def test_a_model_can_have_fuzz(tmp_path):
    class Furry(claymarch.Model):
        ball = claymarch.Sphere(0.5)
        fuzz = claymarch.Fuzz()

    class Bare(claymarch.Model):
        ball = claymarch.Sphere(0.5)

    class A(claymarch.Scene):
        thing = Furry

    class B(claymarch.Scene):
        thing = Bare

    assert scene_text(A, tmp_path / "a") != scene_text(B, tmp_path / "b")


def test_fuzz_is_written_like_hair(tmp_path):
    def front(out, point):
        return claymarch.smoothstep(0.2, 0.4, out.z)

    class Windblown(claymarch.Fuzz):
        flow = (0, -1, 0)
        lift = 40
        wind = (0.5, 0, 0)
        material = claymarch.Material(color=(0.9, 0.9, 0.8))

    class Furry(claymarch.Scene):
        ball = claymarch.Sphere(0.5, fuzz=Windblown(grows=front))

    code = scene_text(Furry, tmp_path)
    assert "strand(vec3(0.0, -1.0, 0.0),(vec3(0.5, 0.0, 0.0)*" in code
    assert "smoothstep(0.2, 0.4, " in code
    with pytest.raises(TypeError, match="lean"):
        claymarch.Fuzz(lean=(0, 0, -0.03))


def test_fuzz_grows_shorter_where_it_thins_out(tmp_path):
    def patches(out, point):
        return claymarch.smoothstep(0.4, 0.6, claymarch.noise(point))

    class Lawn(claymarch.Scene):
        ball = claymarch.Sphere(0.5, fuzz=claymarch.Fuzz(grows=patches))

    code = scene_text(Lawn, tmp_path).split("float map(")[1]
    # how tall the strands are is scaled by how much grows there
    assert "(0.3+0.7*s" in code and ")*g" in code


def test_a_shape_can_have_several_fuzzes(tmp_path):
    cream = claymarch.Material(color=(0.9, 0.9, 0.8))

    class Two(claymarch.Scene):
        ball = claymarch.Sphere(
            0.5,
            fuzz=[claymarch.Fuzz(), claymarch.Fuzz(length=0.2, material=cream)],
        )

    code = scene_text(Two, tmp_path).split("float map(")[1]
    assert code.count("smoothstep(0.45,0.65,") == 2


def test_strands_without_a_material_look_like_the_skin(tmp_path):
    cream = claymarch.Material(color=(0.9, 0.9, 0.8))

    class Plain(claymarch.Scene):
        ball = claymarch.Sphere(0.5, fuzz=claymarch.Fuzz())

    class Painted(claymarch.Scene):
        ball = claymarch.Sphere(0.5, fuzz=claymarch.Fuzz(material=cream))

    plain = scene_text(Plain, tmp_path / "a").split("float map(")[1]
    painted = scene_text(Painted, tmp_path / "b").split("float map(")[1]
    assert "gHairUvw = vec3(" not in plain
    # each strand, a random number of its own
    assert "gHairUvw = vec3(cellRand(floor(" in painted


def test_a_flat_curve_draws_in_its_own_coordinates(tmp_path):
    class Lock(claymarch.Scene):
        lock = claymarch.Curve(
            (0, 0, 0), (0, 0.05, -0.5), (0, 0, -1), 0.1, 0.012,
            up=(0, 1, 0), flat=0.5, grooves=3,
        )

    code = scene_text(Lock, tmp_path)
    assert "*vec3(1.0,2.0,1.0)" in code.replace(" ", "")


def test_a_curve_cannot_lie_along_its_own_up():
    with pytest.raises(ValueError, match="up cannot point along"):
        claymarch.Curve((0, 0, 0), (0, 0.5, 0), (0, 1, 0), 0.1, up=(0, 1, 0))


def test_a_curve_is_flattened_only_against_a_skin():
    with pytest.raises(TypeError, match="need up"):
        claymarch.Curve((0, 0, 0), (0, 0.5, 0), (0, 1, 0), 0.1, flat=0.5)


def hairy(hair, shape=None):
    """A scene with one shape covered in hair."""
    class Furry(claymarch.Scene):
        ball = (shape or claymarch.Ellipsoid)(0.3, 0.2, 0.4, hair=hair)

    return Furry


def test_hair_looks_for_hairs_near_each_point(tmp_path):
    code = scene_text(hairy(claymarch.Hair(flow=(0, 0, -1))), tmp_path)
    assert "strand(vec3(0.0, 0.0, 1.0)" not in code
    assert "strand(vec3(0.0, 0.0, -1.0)" in code
    assert "? 8 : 0); i++ )" in code


def test_hair_grows_only_where_it_says(tmp_path):
    def grows(out):
        return claymarch.smoothstep(0.2, 0.4, out.y)

    furry = scene_text(hairy(claymarch.Hair(grows=grows)), tmp_path / "a")
    plain = scene_text(hairy(claymarch.Hair()), tmp_path / "b")
    assert "smoothstep(0.2, 0.4, " in furry
    assert "smoothstep(0.2, 0.4, " not in plain


def test_a_model_makes_room_for_the_hair_of_its_parts():
    class Ball(claymarch.Model):
        ball = claymarch.Sphere(0.3)
        other = claymarch.Sphere(0.1, position=(1, 0, 0))

    class Furry(Ball):
        ball = claymarch.Ellipsoid(
            0.3, 0.3, 0.3, hair=claymarch.Hair(length=0.1)
        )

    _, bare = Ball().extent()
    _, furry = Furry().extent()
    assert furry > bare


def test_hair_can_ask_where_on_the_skin(tmp_path):
    def grows(out, point):
        return claymarch.step(1.1, point.y)

    class Furry(claymarch.Scene):
        ball = claymarch.Ellipsoid(
            0.3, 0.2, 0.4, position=(0, 1, 0),
            hair=claymarch.Hair(grows=grows),
        )

    assert "+vec3(0.0, 1.0, 0.0)).y)" in scene_text(Furry, tmp_path)


def test_a_turned_shape_grows_its_hair_in_the_models_coordinates(tmp_path):
    def top(out, point):
        return claymarch.step(0.0, out.y) * claymarch.step(1.0, point.y)

    class Furry(claymarch.Scene):
        ball = claymarch.Ellipsoid(
            0.3, 0.2, 0.4,
            rotation=(0, 0, 90), size=2, position=(0, 1, 0),
            hair=claymarch.Hair(flow=(0, -1, 0), grows=top),
        )

    code = scene_text(Furry, tmp_path).split("float map(")[1]
    assert "turnIn(vec3(0.0, -1.0, 0.0),vec3(0.0, 0.0, 90.0))" in code
    assert "step(0.0, turnOut(" in code
    assert "*2.0,vec3(0.0, 0.0, 90.0))+vec3(0.0, 1.0, 0.0))" in code


def test_a_moving_shape_takes_its_fur_along(tmp_path):
    def swing(t):
        return (0, 0, 30 * claymarch.sin(t))

    class Furry(claymarch.Scene):
        ball = claymarch.Ellipsoid(
            0.3, 0.2, 0.4, rotation=swing, hair=claymarch.Hair()
        )

    code = scene_text(Furry, tmp_path).split("float map(")[1]
    # the fur is combed as the shape was at the start, not as it is now
    assert "turnIn(" not in code


def test_a_models_fuzz_is_in_its_own_coordinates(tmp_path):
    def top(out, point):
        return claymarch.step(0.0, point.y)

    class Ball(claymarch.Model):
        ball = claymarch.Sphere(0.5)
        fuzz = claymarch.Fuzz(grows=top)
        rotation = (0, 0, 90)
        position = (0, 1, 0)

    class Furry(claymarch.Scene):
        ball = Ball

    code = scene_text(Furry, tmp_path).split("float map(")[1]
    assert "turnIn(" not in code and "turnOut(" not in code


def test_hair_grows_on_any_shape(tmp_path):
    class Furry(claymarch.Scene):
        neck = claymarch.Capsule(
            (0, 0, 0), (0, 1, 0), 0.2, hair=claymarch.Hair()
        )

    code = scene_text(Furry, tmp_path).split("float map(")[1]
    assert "? 8 : 0); i++ )" in code
    assert "sdEllipsoid" not in code


def test_a_shape_can_have_several_hairs(tmp_path):
    def top(out):
        return claymarch.step(0.0, out.y)

    def bottom(out):
        return claymarch.step(out.y, 0.0)

    one = scene_text(hairy(claymarch.Hair(grows=top)), tmp_path / "a")
    both = scene_text(
        hairy([claymarch.Hair(grows=top), claymarch.Hair(grows=bottom)]),
        tmp_path / "b",
    )
    assert one.count("? 8 : 0); i++ )") == 1
    assert both.count("? 8 : 0); i++ )") == 2


def test_a_model_puts_its_hair_on_each_of_its_shapes(tmp_path):
    class Arm(claymarch.Model):
        upper = claymarch.Ellipsoid(0.1, 0.3, 0.1)
        lower = claymarch.Capsule((0, -0.3, 0), (0, -0.7, 0), 0.08)

    class Body(claymarch.Model):
        trunk = claymarch.Ellipsoid(0.3, 0.4, 0.3)
        arm = Arm
        hole = claymarch.Sphere(0.1, position=(0, 0.4, 0), carve=0.01)
        eye = claymarch.Sphere(0.03, position=(0, 0.3, 0.3), hair=[])

        hair = claymarch.Hair()

    class Furry(claymarch.Scene):
        body = Body

    code = scene_text(Furry, tmp_path).split("float map(")[1]
    # the trunk, the upper arm and the lower one; not the hole nor the eye
    assert code.count("? 8 : 0); i++ )") == 3


def test_a_shape_keeps_its_own_hair_in_a_hairy_model(tmp_path):
    class Body(claymarch.Model):
        trunk = claymarch.Ellipsoid(0.3, 0.4, 0.3)
        ear = claymarch.Ellipsoid(
            0.1, 0.2, 0.05, hair=claymarch.Hair(flow=(0, 1, 0))
        )

        hair = claymarch.Hair(flow=(0, -1, 0))

    class Furry(claymarch.Scene):
        body = Body

    code = scene_text(Furry, tmp_path)
    assert code.count("strand(vec3(0.0, -1.0, 0.0)") == 3
    assert code.count("strand(vec3(0.0, 1.0, 0.0)") == 3


def test_hair_is_written_with_its_class():
    with pytest.raises(TypeError, match="Hair"):
        claymarch.Sphere(0.5, hair=(0, -1, 0))
    with pytest.raises(TypeError, match="lenght"):
        claymarch.Hair(lenght=0.1)


def test_fuzz_and_ripple_are_written_with_their_classes():
    with pytest.raises(TypeError, match="Fuzz"):
        claymarch.Sphere(0.5, fuzz=(0.04, 0.02))
    with pytest.raises(TypeError, match="Ripple"):
        claymarch.Sphere(0.5, ripple=(0.1, 0.3))


def test_ripple_drifts(tmp_path):
    class Stream(claymarch.Scene):
        water = claymarch.Sphere(
            0.5, ripple=claymarch.Ripple(height=0.1, drift=(0, 1, 0))
        )

    assert "-vec3(0.0, 1.0, 0.0)*iTime)" in scene_text(Stream, tmp_path)


def test_wind_moves_the_hair_with_time(tmp_path):
    calm = scene_text(hairy(claymarch.Hair()), tmp_path / "a")
    blown = scene_text(
        hairy(claymarch.Hair(wind=(0.5, 0, 0))), tmp_path / "b"
    )
    assert "*(0.2+1.6*noise3(" not in calm.split("float map(")[1]
    assert "vec3(0.5, 0.0, 0.0)*(0.2+1.6*noise3(" in blown


def test_wind_lays_over_strands_that_stand_straight_up(tmp_path):
    class Standing(claymarch.Scene):
        ball = claymarch.Sphere(
            0.5, fuzz=claymarch.Fuzz(lift=90, wind=(0.5, 0, 0))
        )

    code = scene_text(Standing, tmp_path).split("float map(")[1]
    assert "strand(vec3(0.0, 0.0, -1.0),(vec3(0.5, 0.0, 0.0)*" in code


def test_wind_blows_fuzz_in_gusts_through_the_scene(tmp_path):
    class Still(claymarch.Model):
        ball = claymarch.Sphere(0.5)
        fuzz = claymarch.Fuzz()

    class Windy(Still):
        fuzz = claymarch.Fuzz(wind=(0.5, 0, 0))

    class Calm(claymarch.Scene):
        thing = Still

    class Blown(claymarch.Scene):
        thing = Windy

    assert "iTime" not in scene_text(Calm, tmp_path / "a").split(
        "float map("
    )[1]
    blown = scene_text(Blown, tmp_path / "b")
    assert "vec3(0.5, 0.0, 0.0)*(0.2+1.6*noise3((p0-" in blown


def test_hair_turns_into_fuzz_when_pixels_are_wider_than_hairs(tmp_path):
    code = scene_text(hairy(claymarch.Hair()), tmp_path)
    body = code.split("float map(")[1]
    assert ",gFoot);" in body
    assert "gHairy==2" in body
    assert "const bool  HAIRY      = true;" in code


def test_the_combing_can_change_with_time(tmp_path):
    class Swaying(claymarch.Hair):
        def flow(self, t):
            return (claymarch.sin(t), 0, -1)

    code = scene_text(hairy(Swaying()), tmp_path)
    assert "strand(normalize(vec3(sin(iTime)" in code
