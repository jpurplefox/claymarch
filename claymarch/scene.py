"""The scene: shapes plus camera, light, ground and background; generates the GLSL."""
import hashlib
import math
import time
from pathlib import Path

from .expr import E, Expr, P, checker, mix, vec3
from .shapes import Context, Fuzz, Material, Shape, _const, _Fuzz, _num, _some, as_material, collect_shapes, union

TEMPLATE = Path(__file__).parent / "template"


class Camera:
    """Camera looking at a point. In the viewer you orbit by dragging the mouse.

    target:   point it looks at.
    distance: how far away it is.
    yaw:      angle around the target, in degrees (0 = from the front).
    pitch:    angle upward, in degrees.
    lens:     bigger = more zoom and less perspective.
    """
    def __init__(self, target=(0.0, 0.5, 0.0), distance=4.0, yaw=25.0, pitch=15.0, lens=2.0):
        self.target, self.distance = target, distance
        self.yaw, self.pitch, self.lens = yaw, pitch, lens


class Light:
    """Key light (like a sun): it comes FROM that direction.

    sun:  more than 0 draws the sun in the sky, where the light comes from:
          the number is its size (1 is a natural one). Clouds cover it, and
          whatever mirrors the sky mirrors it too.
    halo: how strong the glow around that sun is.
    """
    def __init__(self, direction=(0.5, 0.7, 0.5), color=(1.0, 0.95, 0.85), intensity=1.0, sun=0.0, halo=1.0):
        self.direction, self.color, self.intensity = direction, color, intensity
        self.sun, self.halo = sun, halo

    def glsl(self):
        """The lines that add the sun to the sky color `col`, looking along rd."""
        if not self.sun:
            return ""
        size = float(self.sun)
        radius = 0.035 * size
        return "\n".join([
            "    {",
            "        float sd = clamp( dot(rd,LIGHT_DIR), 0.0, 1.0 );",
            f"        float disc = smoothstep( {E(math.cos(radius * 1.25)).code}, {E(math.cos(radius)).code}, sd );",
            f"        float around = 0.5*pow( sd, {E(200.0 / (size * size)).code} ) + 0.18*pow( sd, 12.0 );",
            f"        col += (1.0-veil)*LIGHT_COL*{E(self.halo).code}*around;",
            "        orb = (1.0-veil)*LIGHT_COL*6.0*disc;",
            "    }",
        ])


class Halo:
    """A glow hanging in the air around a point, as around a lamp in mist.
    It does not light anything: it is only seen. What is in front of the
    point hides it.

    position: where it is, in the scene.
    color:    of the glow.
    size:     how far it spreads.
    strength: how bright it is; it can change with time.
    """
    def __init__(self, position, color=(1.0, 0.9, 0.6), size=0.5, strength=1.0):
        self.position, self.color, self.size, self.strength = position, color, size, strength

    def glsl(self):
        size = E(self.size).code
        # a tight bright core plus a faint wide veil; it only shows on rays
        # that get as far as the point, so what is in front of it hides it
        # (a margin here would show as a round patch on whatever is near)
        return (f"    {{ vec3 c = {vec3(self.position).code}-ro; float s = dot(c,rd);\n"
                f"      float d2 = (dot(c,c)-s*s)/({size}*{size});\n"
                f"      if( s>0.0 && s<t ) g += {vec3(self.color).code}*({E(self.strength).code})"
                f"*( exp(-8.0*d2) + 0.35/((1.0+d2)*(1.0+d2)) ); }}")


class Ground:
    """The floor. By default, a flat light gray checkerboard at y=0.

    height: a number (flat floor at that height), or a function of the
            position p that returns the height there, for hills:

                Ground(height=lambda p: 0.5 * noise(p * 0.2))

            Use p.x and p.z; keep slopes gentle (it is not an exact distance).
    top:    speed-up for a ground with hills: a height the hills never go
            above. Higher than that the hills are not computed at all. If
            it is too low, the hilltops show cut flat.
    fuzz:   a Fuzz, or a list of them, over the whole ground: grass (see
            Fuzz). grows(out, point) can leave some of it bare.
    """
    def __init__(self, height=0.0, material=None, top=None, fuzz=None):
        self.height, self.top, self.fuzz = height, top, fuzz
        self.material = as_material(material) if material is not None else Material(
            color=mix((0.80, 0.82, 0.84), (0.70, 0.72, 0.75), checker(P, 0.5)), specular=0.05)


class _Floor(Shape):
    """The ground as a shape, so it can take fuzz (see Ground). reach is how
    far above the hills that fuzz goes: the hills are worked out that much
    further up."""
    reach = 0.0

    def __init__(self, ground, gid):
        self.ground, self.gid = ground, gid

    def emit(self, ctx, p, mat, names=None):
        d, h, m = names or (ctx.var("dground"), ctx.var("hground"), ctx.var("mground"))
        ground, gid = self.ground, self.gid
        height = ground.height
        if callable(height) and not isinstance(height, Expr):
            # hills: p.y minus the height is only roughly a distance, so
            # the ray advances with shorter steps to avoid skipping slopes
            hills = f"({p}.y-{E(height(Expr(p, 'vec3'))).code})*0.7"
            if ground.top is None:
                ctx.line(f"float {d} = {hills}; float {m} = {gid}.0;")
            else:
                # well above the tallest hill the height to `top` is a safe
                # distance and the hills are skipped. Material -1 marks it
                # as "not a surface" (see _Bound), so it casts no shadow
                # Measured along the ray when there is one (gRd): a ray
                # going up never reaches the ground, and a nearly level
                # one is not slowed down by passing just above the hills.
                ctx.line(f"float {h} = {p}.y-({E(ground.top).code}); float {m} = -1.0;")
                ctx.line(f"float {d} = dot(gRd,gRd)<0.5 ? {h} : gRd.y>=0.0 ? 1e4 : {h}/(-gRd.y);")
                ctx.line(f"if( {h}<{_num(0.1 + self.reach)} ) {{ {d} = {hills}; {m} = {gid}.0; }}")
        else:
            ctx.line(f"float {d} = {p}.y-({E(height).code}); float {m} = {gid}.0;")
        return d, m, p

    def spheres(self):
        return None


class Clouds:
    """Clouds painted on the sky. They are part of the background: nothing
    can go through them, and they show in whatever mirrors the sky.

    cover:  how much of the sky they take, from 0 (none) to 1 (overcast).
    size:   how big each cloud is (larger = bigger, fewer).
    speed:  how fast the wind carries them, and direction is where to, as
            (x, z).
    color:  the side the light hits; shade is the other side.
    """
    def __init__(self, cover=0.45, size=1.0, speed=0.03, direction=(1.0, 0.3),
                 color=(1.0, 1.0, 1.0), shade=(0.62, 0.68, 0.80)):
        if len(direction) != 2:
            raise TypeError("Clouds: direction is where the wind goes, (x, z)")
        self.cover, self.size, self.speed, self.direction = cover, size, speed, direction
        self.color, self.shade = color, shade

    def glsl(self):
        """The lines that paint the clouds over `sky`, looking along rd."""
        wind = E((self.direction[0], self.direction[1]))
        return "\n".join([
            "    if( rd.y>0.01 )",
            "    {",
            "        // the clouds are flat, far above: where the ray would meet them",
            f"        vec2 uv = rd.xz/(rd.y+0.2)/{E(self.size).code} + normalize({wind.code})*{E(self.speed).code}*iTime;",
            "        float n = fbm3( vec3(uv.x, 0.02*iTime, uv.y) );",
            f"        float edge = mix( 0.75, 0.30, clamp({E(self.cover).code},0.0,1.0) );",
            "        float den = smoothstep( edge, edge+0.18, n )*smoothstep( 0.02, 0.25, rd.y );",
            "        // thinner toward the light means that side is lit",
            "        vec2 sun = LIGHT_DIR.xz/(length(LIGHT_DIR.xz)+0.001);",
            "        float lit = clamp( 0.55+3.0*(n-fbm3( vec3(uv.x+0.25*sun.x, 0.02*iTime, uv.y+0.25*sun.y) )), 0.0, 1.0 );",
            f"        sky = mix( sky, mix({vec3(self.shade).code}, {vec3(self.color).code}, lit), den );",
            "        veil = den;",
            "    }",
        ])


class Scene:
    """Everything needed to draw. Two equivalent ways to use it:

        scene = Scene(shape1, shape2, camera=Camera(...))

        class MyScene(Scene):
            critter = Critter()              # every Shape attribute is drawn
            camera  = Camera(...)

    ground=None removes the ground. quality=2 smooths edges (4 times slower).
    A scene with no shapes yet is valid: it shows the ground and the sky.
    """
    models = None                   # explicit list of shapes; default: all Shape attributes
    camera = None
    light = None
    ground = "auto"
    background = ((0.45, 0.62, 0.90), (0.88, 0.90, 0.95))     # (top, bottom)
    ambient = (0.60, 0.75, 1.00)    # fill light: the color of what is in shadow (sky blue outdoors)
    haze = 1.0                      # how fast far things fade into the background (0 = never)
    clouds = None                   # Clouds(...) paints clouds on the sky
    bounce = (1.00, 0.85, 0.70)     # light that comes back up from the ground, onto what faces down
    fill = None                     # a second Light, softer: it casts no shadows
    halos = ()                      # Halo(...)s: glows in the air around points
    quality = 1

    def __init__(self, *shapes, **options):
        for name, value in options.items():
            if not hasattr(Scene, name):
                raise TypeError(f"Scene has no option '{name}'")
            setattr(self, name, value)
        if shapes:
            self.models = list(shapes)

    def shape(self):
        """Everything in the scene as one shape, or None if it is still empty
        (an empty scene is fine: it shows the ground and the sky)."""
        models = collect_shapes(self, "models")
        if not all(isinstance(m, Shape) for m in models):
            raise TypeError(f"{type(self).__name__}: everything in a scene must be a shape or a model")
        return union(*models) if models else None

    # ------------------------------------------------------------------ GLSL
    def glsl(self):
        ctx = Context(Material())
        shape = self.shape()
        if shape is None:
            d, m, u = "1e4", "0.0", "p0"         # nothing yet: far away from everything
        else:
            d, m, u = shape.emit(ctx, "p0", None)

        ground = Ground() if self.ground == "auto" else self.ground
        if ground is not None:
            gid = ctx.material_id(ground.material)
            grass = _some(ground.fuzz, Fuzz, "Fuzz(length=0.1, lift=70)")
            if grass:
                floor = _Fuzz(_Floor(ground, gid), grass)
                floor.child.reach = floor.top
                dg, mg, _ = floor.emit(ctx, "p0", None)
            else:
                dg, mg, _ = _Floor(ground, gid).emit(ctx, "p0", None, names=("dground", "hground", "mground"))
            ctx.line(f"bool isground = {dg}<{d};")
            d, m, u = f"(isground?{dg}:{d})", f"(isground?{mg}:{m})", f"(isground?p0:{u})"

        map_body = "\n".join(ctx.lines)

        material_body = "\n".join(
            f"    {'if' if i == 0 else 'else if'}( mat<{i}.5 ) "
            f"{{ col = {vec3(mat.value('color')).code}; ks = {E(mat.value('specular')).code}; "
            f"se = {E(mat.value('shininess')).code}; emi = {E(mat.value('glow')).code}; "
            f"opa = {E(mat.value('opacity')).code}; rfl = {E(mat.value('reflection')).code}; "
            f"shn = {E(mat.value('sheen')).code}; }}"
            for i, mat in enumerate(ctx.materials))

        bumps = "\n".join(
            f"    if( abs(mat-{i}.0)<0.5 ) return {E(mat.value('bump')).code};"
            for i, mat in enumerate(ctx.materials) if mat.bump is not None)

        # the hair: how far out from the skin it reaches, and how dense it is
        lengths = [_const(length) or 0.05 for length, size in ctx.hairs]
        sizes = [_const(size) or 0.01 for length, size in ctx.hairs]
        hair = [
            f"const bool  HAIRY      = {'true' if ctx.hairs else 'false'};",
            f"const float HAIR_REACH = {E(max(lengths, default=0.05) * 1.02).code};",
            f"const float HAIR_THICK = {E(1.2 / min(sizes, default=0.01)).code};",
        ]
        c, sun = self.camera or Camera(), self.light or Light()
        f = self.fill or Light()
        constants = "\n".join([
            f"const vec3  CAM_TA    = {vec3(c.target).code};",
            f"const float CAM_DIST  = {E(c.distance).code};",
            f"const float CAM_YAW   = radians({E(c.yaw).code});",
            f"const float CAM_PITCH = radians({E(c.pitch).code});",
            f"const float CAM_FL    = {E(c.lens).code};",
            f"const vec3  LIGHT_DIR = normalize({vec3(sun.direction).code});",
            f"const vec3  LIGHT_COL = {vec3(sun.color).code}*{E(sun.intensity).code};",
            f"const vec3  BG_TOP    = {vec3(self.background[0]).code};",
            f"const vec3  BG_BOTTOM = {vec3(self.background[1]).code};",
            f"const vec3  AMBIENT   = {vec3(self.ambient).code};",
            f"const float HAZE      = 0.0008*{E(self.haze).code};",
            f"const vec3  BOUNCE    = {vec3(self.bounce).code};",
            f"const vec3  FILL_DIR  = normalize({vec3(f.direction).code});",
            f"const vec3  FILL_COL  = {vec3(f.color).code}*{E(f.intensity if self.fill is not None else 0.0).code};",
            f"#define AA {max(1, int(self.quality))}",
            *hair,
        ])

        base = (TEMPLATE / "base.glsl").read_text(encoding="utf-8")
        return (base + "\n" + _RENDER
                .replace("//@CONSTANTS", constants)
                .replace("//@CLOUDS", self.clouds.glsl() if self.clouds is not None else "")
                .replace("//@SUN", sun.glsl())
                .replace("//@HALOS", "\n".join(h.glsl() for h in self.halos))
                .replace("//@MATERIAL_BODY", material_body)
                .replace("//@BUMPS", bumps)
                .replace("//@MAP_BODY", map_body)
                .replace("//@FUZZ_KEPT", "".join(f"vec3 gFuzzOut{i}, gFuzzAt{i};\n"
                                                 for i in range(ctx.fuzzes)))
                .replace("//@FUZZ_RESET", "".join(f"            gFuzzAt{i} = vec3(1e9);\n"
                                                  for i in range(ctx.fuzzes)))
                .replace("@OUT_D", d).replace("@OUT_M", m).replace("@OUT_U", u))

    # ---------------------------------------------------------------- export
    def export(self, folder):
        """Write a folder ready to be opened through a web server."""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        code = self.glsl()
        for name in ("index.html", "main.js"):
            (folder / name).write_text((TEMPLATE / name).read_text(encoding="utf-8"), encoding="utf-8")
        (folder / "scene.glsl").write_text(code, encoding="utf-8")
        # what the page itself is made of: when it changes, an open page is
        # out of date (it may lack something the new shader needs) and
        # reloads itself
        page = "".join((TEMPLATE / name).read_text(encoding="utf-8") for name in ("index.html", "main.js"))
        (folder / "viewer.txt").write_text(hashlib.sha1(page.encode("utf-8")).hexdigest(), encoding="utf-8")
        # the viewer watches this file to know when to reload
        (folder / "version.txt").write_text(str(time.time_ns()), encoding="utf-8")
        return folder


# =====================================================================
# Fixed part of the shader. The @... marks are replaced with generated code.
# =====================================================================
_RENDER = r"""
// ===================================================================
// Scene generated from Python
// ===================================================================
//@CONSTANTS

// The GPU has no real function calls: every call to map() is a whole copy
// of the scene in the compiled shader. A loop that starts at ZERO (0, but
// the compiler does not know it) is not unrolled, so what it calls is
// copied once.
#define ZERO min(iFrame,0)

// Which way the ray being advanced is going (zero when there is no ray, as when
// normals are computed). Repetitions use it to know how far the cell wall is.
vec3 gRd = vec3(0.0);
// True while a ray looks for what is behind a see-through surface: the
// see-through things are then left out of the scene.
bool gSolid = false;
// Hair (see _Fuzz). gHairy says what map() does with it: 0, the hair is a
// smooth shell around the skin; 1, there is only the skin; 2, the skin, and
// besides, how much hair there is at the point (gHair), whose it is
// (gHairMat, gHairUvw) and how far up its strand (gHairUp). gHairRoot is
// how far the point is from the skin of the nearest furry thing, and
// gHairStep how short the steps through the hair there have to be (where
// nothing grows, as long as the way to the nearest skin).
// How wide one pixel is, at distance 1 (gPixel) and where the ray is now
// (gFoot): detail finer than gFoot cannot be drawn, only flicker (see Hair).
float gPixel = 0.0, gFoot = 0.0;
int   gHairy = 0;
float gHair = 0.0, gHairRoot = 1e4, gHairMat = 0.0, gHairUp = 0.0, gHairStep = 1.0;
// the way out of the skin of each fuzzy thing, and where it was measured,
// kept while a ray walks through its hair (see _Fuzz)
//@FUZZ_KEPT
vec3  gHairUvw = vec3(0.0);

// Distance function of the whole scene. Besides the distance it returns
// which material was hit and the coordinates used to draw it.
float map( in vec3 p0, out float mat, out vec3 uvw )
{
    gHair = 0.0; gHairRoot = 1e4; gHairStep = 1e4;
//@MAP_BODY
    mat = @OUT_M; uvw = @OUT_U;
    return @OUT_D;
}
float map( in vec3 p ) { float m; vec3 u; return map(p,m,u); }

void material( in float mat, in vec3 uvw, out vec3 col, out float ks, out float se, out float emi,
               out float opa, out float rfl, out float shn )
{
    col = vec3(0.8); ks = 0.2; se = 32.0; emi = 0.0; opa = 1.0; rfl = 0.0; shn = 0.0;
//@MATERIAL_BODY
}

// Bump of each material: how much the surface is displaced at that point.
float bump( in float mat, in vec3 uvw )
{
//@BUMPS
    return 0.0;
}

// The same shape + the bump. Used ONLY to compute normals: fine detail changes
// how light hits without making the raymarching or the shadows more expensive.
float mapD( in vec3 p )
{
    float m; vec3 u;
    float d = map(p,m,u);
    return d + bump(m,u);
}

// ===================================================================
// Render: the same for every scene
// ===================================================================
// The four points around pos are measured in a loop the compiler cannot
// unroll (see ZERO): one copy of the scene instead of four, and the shader
// compiles in about half the time.
vec3 calcNormal( in vec3 pos )
{
    vec3 n = vec3(0.0);
    for( int i=ZERO; i<4; i++ )
    {
        vec3 k = 2.0*vec3(float(((i+3)>>1)&1),float((i>>1)&1),float(i&1))-1.0;
        n += k*mapD(pos+k*0.0015);
    }
    return normalize(n);
}

// Hair is soft: neither shadows nor ambient occlusion take its smooth
// shell for solid, only the skin under it. Otherwise ground seen through
// the hair would be lit and ground seen beside it shaded.
float softShadow( in vec3 ro, in vec3 rd )
{
    float res = 1.0, t = 0.02, m; vec3 u;
    int hairy = gHairy; gHairy = 1;
    gRd = rd;
    for( int i=0; i<48; i++ )
    {
        float h = map(ro+rd*t,m,u);
        // m<0: h is the distance to a bounding sphere, not to a real surface.
        // It is safe for advancing, but it must not count as a near miss
        if( m>-0.5 ) res = min( res, 10.0*h/t );
        t += clamp(h,0.02,0.4);
        if( res<0.005 || t>12.0 ) break;
    }
    gRd = vec3(0.0);
    gHairy = hairy;
    return clamp(res,0.0,1.0);
}

float calcAO( in vec3 pos, in vec3 nor )
{
    float occ = 0.0, sca = 1.0, m; vec3 u;
    int hairy = gHairy; gHairy = 1;
    for( int i=0; i<5; i++ )
    {
        float h = 0.01 + 0.15*float(i)/4.0;
        float d = map(pos+nor*h,m,u);
        if( m>-0.5 ) occ += (h-d)*sca;      // a bounding sphere does not occlude
        sca *= 0.9;
    }
    gHairy = hairy;
    return clamp(1.0-2.0*occ,0.0,1.0);
}

void camera( in vec2 fragCoord, out vec3 ro, out vec3 rd )
{
    // uShift slides the picture inside the frame without turning the camera;
    // uLens magnifies it without moving the camera (a longer lens)
    vec2 p = ((2.0*fragCoord-iResolution.xy)/iResolution.y - uShift)/uLens;
    float yaw = CAM_YAW + uOrbit.x;
    float pit = clamp( CAM_PITCH + uOrbit.y, -1.5, 1.5 );
    ro = CAM_TA + CAM_DIST*uOrbit.z*vec3( sin(yaw)*cos(pit), sin(pit), cos(yaw)*cos(pit) );
    vec3 ww = normalize(CAM_TA-ro);
    vec3 uu = normalize(cross(ww,vec3(0.0,1.0,0.0)));
    vec3 vv = cross(uu,ww);
    rd = normalize( p.x*uu + p.y*vv + CAM_FL*ww );
    gPixel = 2.0/(iResolution.y*uLens*CAM_FL*float(AA));
}

// Advance a ray from distance t until it touches something. seen says
// whether there is a surface to shade there.
float march( in vec3 ro, in vec3 rd, in float t, out float mat, out vec3 uvw, out bool seen )
{
    bool hit = false; mat = 0.0; uvw = vec3(0.0);
    gRd = rd;
    for( int i=0; i<160; i++ )
    {
        gFoot = t*gPixel;
        float h = map( ro+t*rd, mat, uvw );
        // mat<0 is never a surface, however close: a safe guess that keeps
        // a ray from stepping too far (between hairs, see Hair), not a hit
        if( h<0.0005*t+0.0002 && mat>-0.5 ) { hit = true; break; }
        t += h*0.9;
        if( t>80.0 ) break;
    }
    gRd = vec3(0.0);
    // out of steps while still near a surface (a ray grazing a hill): shade it
    // as a hit instead of letting the sky show through as a bright outline
    // (mat<0: what it was near is not a surface but a bounding sphere or the
    // wall of a repetition cell, so there is nothing to shade)
    seen = hit || !(t>80.0 || mat<-0.5);
    return t;
}

// The sky looking along rd, without the sun's disc, which comes out apart in
// orb: the haze takes the color of the sky, but the disc is not part of it
// (it would show through whatever is in front of the sun).
vec3 skyColor( in vec3 rd, out vec3 orb )
{
    orb = vec3(0.0);
    vec3 sky = mix( BG_BOTTOM, BG_TOP, clamp(0.5+1.5*rd.y,0.0,1.0) );
    float veil = 0.0;       // how much the clouds cover this part of the sky
//@CLOUDS
    vec3 col = pow(sky,vec3(2.2));
//@SUN
    return col;
}
vec3 skyColor( in vec3 rd ) { vec3 orb; vec3 col = skyColor( rd, orb ); return col+orb; }

// Glows in the air (Halo) that a ray going as far as t passes near.
vec3 glowAir( in vec3 ro, in vec3 rd, in float t )
{
    vec3 g = vec3(0.0);
//@HALOS
    return g;
}

// How much of the key light reaches pos (1 all of it, 0 none), on a surface
// facing nor. A surface facing away from the light is dark anyway, so it
// gets no shadow ray, unless lit says it is hair, which the light reaches
// from all around.
float shadowAt( in vec3 pos, in vec3 nor, in bool lit )
{
    return (lit || dot(nor,LIGHT_DIR)>0.0) ? softShadow( pos+nor*0.005, LIGHT_DIR ) : 0.0;
}

// The color of a surface under the light, given which way it faces (nor)
// and its shadow (sha). The highlight comes apart (spe), because on a
// see-through surface it stays whole while the rest fades.
vec3 shade( in vec3 pos, in vec3 rd, in float mat, in vec3 uvw, in vec3 nor, in float sha,
            out vec3 alb, out vec3 spe, out float opa )
{
    float ks, se, emi, rfl, shn;
    material( mat, uvw, alb, ks, se, emi, opa, rfl, shn );
    alb = pow( max(alb,0.0), vec3(2.2) );      // colors are written as seen on screen

    float occ = calcAO(pos,nor);
    float ndl = clamp(dot(nor,LIGHT_DIR),0.0,1.0);
    float dif = ndl*sha;
    float fre = pow( clamp(1.0+dot(nor,rd),0.0,1.0), 3.0 );

    vec3 lin = vec3(0.0);
    lin += 0.90*LIGHT_COL*dif;                                             // key light
    lin += 0.30*AMBIENT*(0.6+0.4*nor.y)*occ;                             // sky / fill
    lin += 0.12*BOUNCE*clamp(0.5-0.5*nor.y,0.0,1.0)*occ;                 // bounce from the ground
    float fil = clamp(dot(nor,FILL_DIR),0.0,1.0)*occ;
    lin += 0.90*FILL_COL*fil;                                              // second light, no shadows

    vec3 col = alb*lin;
    vec3 hal = normalize(LIGHT_DIR-rd);
    spe = ks*pow(clamp(dot(nor,hal),0.0,1.0),se)*dif*LIGHT_COL;            // highlight
    spe += ks*pow(clamp(dot(nor,normalize(FILL_DIR-rd)),0.0,1.0),se)*fil*FILL_COL;
    col += 0.08*fre*occ;                                                 // rim
    col += alb*emi*2.0;
    // sheen: light caught by the hairs where the surface turns away from the
    // eye, brightest on the lit side, never quite gone on the other
    if( shn>0.0 )
    {
        float grazing = pow( clamp(1.0+dot(nor,rd),0.0,1.0), 2.0 );
        float wrap = clamp( 0.5+0.5*dot(nor,LIGHT_DIR), 0.0, 1.0 );
        vec3 caught = LIGHT_COL*wrap*(0.3+0.7*sha) + 0.4*AMBIENT*occ;
        col += shn*grazing*(0.5*alb+0.15)*caught;
    }
    // the sky mirrored on it: faint from the front, strong at a grazing angle
    if( rfl>0.0 )
    {
        float edge = pow( clamp(1.0+dot(nor,rd),0.0,1.0), 5.0 );
        col = mix( col, skyColor(reflect(rd,nor)), rfl*(0.04+0.96*edge) );
    }
    return col;
}

// far things fade into the background (so the ground has no hard edge)
vec3 fade( in vec3 col, in vec3 sky, in float t ) { return mix( col, sky, 1.0-exp(-HAZE*t*t) ); }

vec3 render( in vec3 ro, in vec3 rd )
{
    vec3 orb;
    vec3 sky = skyColor( rd, orb );
    gHairy = 0;

    float t = 0.05, mat; vec3 uvw; bool seen;
    // The camera may be INSIDE something (a tree trunk, a hill) after orbiting
    // or zooming out. From inside everything is black, so first walk forward
    // until the ray is out in the open: the thing is seen as if cut open.
    gRd = rd;
    for( int i=0; i<24; i++ )
    {
        float h = map( ro+t*rd );
        if( h>0.01 ) break;
        t += max(-h,0.0) + 0.05;
    }
    gRd = vec3(0.0);

    // The ray goes on until it touches something. If that is the outside of
    // the hair of something furry, from there it walks in short steps,
    // gathering the strands it passes, until it reaches the skin, leaves the
    // hair, or the hair hides everything. What is behind is seen through what
    // the strands let pass (hairT), and may be the hair of something else:
    // up to three, one after the other.
    // Every pass works out which way the surface faces and its shadow, in
    // one place, whether for the hair or for the surface that is shaded at
    // the end; and march is called from one place only. In a loop that is
    // not unrolled, each is one copy of the scene (see ZERO).
    vec3 hairCol = vec3(0.0); float hairT = 1.0;
    vec3 pos = ro, nor = vec3(0.0,1.0,0.0); float sha = 1.0;
    bool skin = false;          // the walk through the hair reached the skin
    for( int pass=ZERO; pass<4; pass++ )
    {
        if( !skin ) t = march( ro, rd, t, mat, uvw, seen );
        if( !seen ) break;
        pos = ro + t*rd;
        // only where the hair really is: what the ray hit (the ground, say)
        // may be near something furry and still out of reach of its hair.
        // The ray stops a little short of the hair's outside (as close as
        // march asks for), so the reach is that much longer. gHairRoot is
        // still the one march found where it stopped.
        float reach = HAIR_REACH + 0.0005*t + 0.0002;
        bool furry = HAIRY && !skin && pass<3 && gHairRoot<reach && gHairRoot>0.002;
        gHairy = furry ? 0 : 1;
        nor = calcNormal( pos );
        sha = shadowAt( pos, nor, furry );
        if( !furry ) break;

        // the light on the hair is worked out once, where the ray goes in
        float wrap = clamp( 0.5+0.5*dot(nor,LIGHT_DIR), 0.0, 1.0 );
        // hair glows when the light is behind it
        float back = pow( clamp(dot(rd,LIGHT_DIR),0.0,1.0), 4.0 );
        vec3 lit = LIGHT_COL*(wrap*(0.3+0.7*sha) + 0.8*back*sha) + 0.35*AMBIENT;
        gHairy = 2; gRd = rd; seen = false;
//@FUZZ_RESET
        for( int i=0; i<128; i++ )
        {
            float h = map( ro+t*rd, mat, uvw );
            // mat<0 is a safe guess, not a surface (see march)
            if( h<0.0005*t+0.0002 && mat>-0.5 ) { seen = true; break; }
            if( gHairRoot>reach ) break;
            // steps no finer than a pixel there: detail smaller than that
            // cannot be drawn, so far away the walk takes longer strides
            float foot = t*gPixel;
            float stp = clamp( h, max(0.0015,foot), max(gHairStep,2.0*foot) );
            if( gHair>0.0 )
            {
                vec3 alb; float ks, se, emi, opa, rfl, shn;
                material( gHairMat, gHairUvw, alb, ks, se, emi, opa, rfl, shn );
                alb = pow( max(alb,0.0), vec3(2.2) );
                // darker down at the roots, where less light gets in
                vec3 strand = alb*lit*(0.3+0.7*gHairUp);
                // far away it fades into the haze, as surfaces do
                strand = fade( strand, sky, t );
                float a = 1.0-exp( -gHair*HAIR_THICK*stp );
                hairCol += hairT*a*strand;
                hairT *= 1.0-a;
                if( hairT<0.02 ) break;
            }
            t += stp;
        }
        gRd = vec3(0.0);
        gHairy = 1;
        // the hair hides everything: what little it lets pass, as sky
        if( hairT<0.02 ) return hairCol + hairT*(sky + orb);
        // reached the skin: the next pass lights it, without marching
        skin = seen;
        seen = true;
        // left the hair without touching anything: go on to what is
        // behind, hair included while there are passes left
        if( !skin ) gHairy = pass<2 ? 0 : 1;
    }
    if( !seen ) return hairCol + hairT*(sky + orb + glowAir(ro,rd,1e4));

    vec3 alb, spe; float opa;
    vec3 col = shade( pos, rd, mat, uvw, nor, sha, alb, spe, opa );
    if( opa>0.999 ) return hairCol + hairT*(fade( col+spe, sky, t ) + glowAir(ro,rd,t));

    // See-through: the ray goes on, a little bent, through a scene without
    // the see-through things, and what it finds is tinted with the color.
    vec3 rd2 = refract( rd, nor, 0.88 );
    rd2 = dot(rd2,rd2)<0.5 ? rd : normalize(rd2);
    vec3 orb2;
    vec3 sky2 = skyColor( rd2, orb2 );
    vec3 behind = sky2 + orb2;
    gSolid = true;
    float matB; vec3 uvwB; bool seen2;
    float t2 = march( pos, rd2, 0.02, matB, uvwB, seen2 );
    if( seen2 )
    {
        vec3 pos2 = pos+t2*rd2, nor2 = calcNormal( pos2 ), alb2, spe2; float opa2;
        behind = shade( pos2, rd2, matB, uvwB, nor2, shadowAt( pos2, nor2, false ),
                        alb2, spe2, opa2 ) + spe2;
        behind = fade( behind, sky2, t+t2 );
    }
    gSolid = false;
    float fre = pow( clamp(1.0+dot(nor,rd),0.0,1.0), 3.0 );
    col = mix( behind*mix(vec3(1.0),alb,0.6), col, opa );
    col += spe + 0.5*(1.0-opa)*fre*sky;        // the highlight and the sky on its edges
    return hairCol + hairT*(fade( col, sky, t ) + glowAir(ro,rd,t));
}

void mainImage( out vec4 fragColor, in vec2 fragCoord )
{
    vec3 tot = vec3(0.0);
    for( int m=0; m<AA; m++ )
    for( int n=0; n<AA; n++ )
    {
        vec2 o = (vec2(float(m),float(n))+0.5)/float(AA) - 0.5;
        vec3 ro, rd;
        camera( fragCoord+o, ro, rd );
        tot += render(ro,rd);
    }
    vec3 col = tot/float(AA*AA);
    col = pow( clamp(col,0.0,1.0), vec3(0.4545) );
    fragColor = vec4(col,1.0);
}
"""
