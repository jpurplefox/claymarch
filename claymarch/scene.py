"""The scene: shapes plus camera, light, ground and background; generates the GLSL."""
import time
from pathlib import Path

from .expr import E, Expr, P, checker, mix, vec3
from .shapes import Context, Material, Shape, as_material, collect_shapes, union

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
    """Key light (like a sun): it comes FROM that direction."""
    def __init__(self, direction=(0.5, 0.7, 0.5), color=(1.0, 0.95, 0.85), intensity=1.0):
        self.direction, self.color, self.intensity = direction, color, intensity


class Ground:
    """The floor. By default, a flat light gray checkerboard at y=0.

    height: a number (flat floor at that height), or a function of the
            position p that returns the height there, for hills:

                Ground(height=lambda p: 0.5 * noise(p * 0.2))

            Use p.x and p.z; keep slopes gentle (it is not an exact distance).
    top:    speed-up for a ground with hills: a height the hills never go
            above. Higher than that the hills are not computed at all. If
            it is too low, the hilltops show cut flat.
    """
    def __init__(self, height=0.0, material=None, top=None):
        self.height, self.top = height, top
        self.material = as_material(material) if material is not None else Material(
            color=mix((0.80, 0.82, 0.84), (0.70, 0.72, 0.75), checker(P, 0.5)), specular=0.05)


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
            height = ground.height
            if callable(height) and not isinstance(height, Expr):
                # hills: p.y minus the height is only roughly a distance, so
                # the ray advances with shorter steps to avoid skipping slopes
                hills = f"(p0.y-{E(height(Expr('p0', 'vec3'))).code})*0.7"
                if ground.top is None:
                    ctx.line(f"float dground = {hills}; float mground = {gid}.0;")
                else:
                    # well above the tallest hill the height to `top` is a safe
                    # distance and the hills are skipped. Material -1 marks it
                    # as "not a surface" (see _Bound), so it casts no shadow
                    # Measured along the ray when there is one (gRd): a ray
                    # going up never reaches the ground, and a nearly level
                    # one is not slowed down by passing just above the hills.
                    ctx.line(f"float hground = p0.y-{E(ground.top).code}; float mground = -1.0;")
                    ctx.line("float dground = dot(gRd,gRd)<0.5 ? hground : gRd.y>=0.0 ? 1e4 : hground/(-gRd.y);")
                    ctx.line(f"if( hground<0.1 ) {{ dground = {hills}; mground = {gid}.0; }}")
            else:
                ctx.line(f"float dground = p0.y-{E(height).code}; float mground = {gid}.0;")
            ctx.line(f"bool isground = dground<{d};")
            d, m, u = f"(isground?dground:{d})", f"(isground?mground:{m})", f"(isground?p0:{u})"

        map_body = "\n".join(ctx.lines)

        material_body = "\n".join(
            f"    {'if' if i == 0 else 'else if'}( mat<{i}.5 ) "
            f"{{ col = {vec3(mat.value('color')).code}; ks = {E(mat.value('specular')).code}; "
            f"se = {E(mat.value('shininess')).code}; emi = {E(mat.value('glow')).code}; "
            f"opa = {E(mat.value('opacity')).code}; }}"
            for i, mat in enumerate(ctx.materials))

        bumps = "\n".join(
            f"    if( abs(mat-{i}.0)<0.5 ) return {E(mat.value('bump')).code};"
            for i, mat in enumerate(ctx.materials) if mat.bump is not None)

        c, l = self.camera or Camera(), self.light or Light()
        constants = "\n".join([
            f"const vec3  CAM_TA    = {vec3(c.target).code};",
            f"const float CAM_DIST  = {E(c.distance).code};",
            f"const float CAM_YAW   = radians({E(c.yaw).code});",
            f"const float CAM_PITCH = radians({E(c.pitch).code});",
            f"const float CAM_FL    = {E(c.lens).code};",
            f"const vec3  LIGHT_DIR = normalize({vec3(l.direction).code});",
            f"const vec3  LIGHT_COL = {vec3(l.color).code}*{E(l.intensity).code};",
            f"const vec3  BG_TOP    = {vec3(self.background[0]).code};",
            f"const vec3  BG_BOTTOM = {vec3(self.background[1]).code};",
            f"const vec3  AMBIENT   = {vec3(self.ambient).code};",
            f"#define AA {max(1, int(self.quality))}",
        ])

        base = (TEMPLATE / "base.glsl").read_text(encoding="utf-8")
        return (base + "\n" + _RENDER
                .replace("//@CONSTANTS", constants)
                .replace("//@MATERIAL_BODY", material_body)
                .replace("//@BUMPS", bumps)
                .replace("//@MAP_BODY", map_body)
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

// Which way the ray being advanced is going (zero when there is no ray, as when
// normals are computed). Repetitions use it to know how far the cell wall is.
vec3 gRd = vec3(0.0);
// True while a ray looks for what is behind a see-through surface: the
// see-through things are then left out of the scene.
bool gSolid = false;

// Distance function of the whole scene. Besides the distance it returns
// which material was hit and the coordinates used to draw it.
float map( in vec3 p0, out float mat, out vec3 uvw )
{
//@MAP_BODY
    mat = @OUT_M; uvw = @OUT_U;
    return @OUT_D;
}
float map( in vec3 p ) { float m; vec3 u; return map(p,m,u); }

void material( in float mat, in vec3 uvw, out vec3 col, out float ks, out float se, out float emi, out float opa )
{
    col = vec3(0.8); ks = 0.2; se = 32.0; emi = 0.0; opa = 1.0;
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
vec3 calcNormal( in vec3 pos )
{
    vec2 e = vec2(1.0,-1.0)*0.0015;
    return normalize( e.xyy*mapD(pos+e.xyy) + e.yyx*mapD(pos+e.yyx) +
                      e.yxy*mapD(pos+e.yxy) + e.xxx*mapD(pos+e.xxx) );
}

float softShadow( in vec3 ro, in vec3 rd )
{
    float res = 1.0, t = 0.02, m; vec3 u;
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
    return clamp(res,0.0,1.0);
}

float calcAO( in vec3 pos, in vec3 nor )
{
    float occ = 0.0, sca = 1.0, m; vec3 u;
    for( int i=0; i<5; i++ )
    {
        float h = 0.01 + 0.15*float(i)/4.0;
        float d = map(pos+nor*h,m,u);
        if( m>-0.5 ) occ += (h-d)*sca;      // a bounding sphere does not occlude
        sca *= 0.9;
    }
    return clamp(1.0-2.0*occ,0.0,1.0);
}

void camera( in vec2 fragCoord, out vec3 ro, out vec3 rd )
{
    vec2 p = (2.0*fragCoord-iResolution.xy)/iResolution.y;
    float yaw = CAM_YAW + uOrbit.x;
    float pit = clamp( CAM_PITCH + uOrbit.y, -1.5, 1.5 );
    ro = CAM_TA + CAM_DIST*uOrbit.z*vec3( sin(yaw)*cos(pit), sin(pit), cos(yaw)*cos(pit) );
    vec3 ww = normalize(CAM_TA-ro);
    vec3 uu = normalize(cross(ww,vec3(0.0,1.0,0.0)));
    vec3 vv = cross(uu,ww);
    rd = normalize( p.x*uu + p.y*vv + CAM_FL*ww );
}

// Advance a ray from distance t until it touches something. seen says
// whether there is a surface to shade there.
float march( in vec3 ro, in vec3 rd, in float t, out float mat, out vec3 uvw, out bool seen )
{
    bool hit = false; mat = 0.0; uvw = vec3(0.0);
    gRd = rd;
    for( int i=0; i<160; i++ )
    {
        float h = map( ro+t*rd, mat, uvw );
        if( h<0.0005*t+0.0002 ) { hit = true; break; }
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

// The color of a surface under the light. The highlight comes apart (spe),
// because on a see-through surface it stays whole while the rest fades.
vec3 shade( in vec3 pos, in vec3 rd, in float mat, in vec3 uvw,
            out vec3 nor, out vec3 alb, out vec3 spe, out float opa )
{
    nor = calcNormal(pos);

    float ks, se, emi;
    material( mat, uvw, alb, ks, se, emi, opa );
    alb = pow( max(alb,0.0), vec3(2.2) );      // colors are written as seen on screen

    float occ = calcAO(pos,nor);
    // a surface facing away from the light is dark anyway: no shadow ray needed
    float ndl = clamp(dot(nor,LIGHT_DIR),0.0,1.0);
    float sha = ndl>0.0 ? softShadow( pos+nor*0.005, LIGHT_DIR ) : 0.0;
    float dif = ndl*sha;
    float fre = pow( clamp(1.0+dot(nor,rd),0.0,1.0), 3.0 );

    vec3 lin = vec3(0.0);
    lin += 0.90*LIGHT_COL*dif;                                             // key light
    lin += 0.30*AMBIENT*(0.6+0.4*nor.y)*occ;                             // sky / fill
    lin += 0.12*vec3(1.00,0.85,0.70)*clamp(0.5-0.5*nor.y,0.0,1.0)*occ;   // bounce from the ground

    vec3 col = alb*lin;
    vec3 hal = normalize(LIGHT_DIR-rd);
    spe = ks*pow(clamp(dot(nor,hal),0.0,1.0),se)*dif*LIGHT_COL;            // highlight
    col += 0.08*fre*occ;                                                 // rim
    col += alb*emi*2.0;
    return col;
}

vec3 skyColor( in vec3 rd )
{
    vec3 sky = mix( BG_BOTTOM, BG_TOP, clamp(0.5+1.5*rd.y,0.0,1.0) );
    return pow(sky,vec3(2.2));
}

// far things fade into the background (so the ground has no hard edge)
vec3 fade( in vec3 col, in vec3 sky, in float t ) { return mix( col, sky, 1.0-exp(-0.0008*t*t) ); }

vec3 render( in vec3 ro, in vec3 rd )
{
    vec3 sky = skyColor(rd);

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
    t = march( ro, rd, t, mat, uvw, seen );
    if( !seen ) return sky;

    vec3 pos = ro + t*rd;
    vec3 nor, alb, spe; float opa;
    vec3 col = shade( pos, rd, mat, uvw, nor, alb, spe, opa );
    if( opa>0.999 ) return fade( col+spe, sky, t );

    // See-through: the ray goes on, a little bent, through a scene without
    // the see-through things, and what it finds is tinted with the color.
    vec3 rd2 = refract( rd, nor, 0.88 );
    rd2 = dot(rd2,rd2)<0.5 ? rd : normalize(rd2);
    vec3 sky2 = skyColor(rd2);
    vec3 behind = sky2;
    gSolid = true;
    float matB; vec3 uvwB; bool seen2;
    float t2 = march( pos, rd2, 0.02, matB, uvwB, seen2 );
    if( seen2 )
    {
        vec3 nor2, alb2, spe2; float opa2;
        behind = shade( pos+t2*rd2, rd2, matB, uvwB, nor2, alb2, spe2, opa2 ) + spe2;
        behind = fade( behind, sky2, t+t2 );
    }
    gSolid = false;
    float fre = pow( clamp(1.0+dot(nor,rd),0.0,1.0), 3.0 );
    col = mix( behind*mix(vec3(1.0),alb,0.6), col, opa );
    col += spe + 0.5*(1.0-opa)*fre*sky;        // the highlight and the sky on its edges
    return fade( col, sky, t );
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
