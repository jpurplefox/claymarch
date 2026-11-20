// ===================================================================
// Fixed library: copied as is at the start of every scene.
// ===================================================================

// "smooth" union and subtraction: blend two shapes with a transition radius k
float smin( float a, float b, float k )
{
    float h = clamp( 0.5 + 0.5*(b-a)/k, 0.0, 1.0 );
    return mix( b, a, h ) - k*h*(1.0-h);
}
float smax( float a, float b, float k ) { return -smin(-a,-b,k); }

mat2 rot2( float a ) { float c = cos(a), s = sin(a); return mat2(c,-s,s,c); }
// A direction in a piece's own axes, from the axes it was turned from by
// rotation= (degrees around x, y, z), and back (see _Frame)
vec3 turnIn( vec3 v, vec3 a )
{
    a = radians(a); v.xy = rot2(a.z)*v.xy; v.xz = rot2(a.y)*v.xz; v.yz = rot2(a.x)*v.yz; return v;
}
vec3 turnOut( vec3 v, vec3 a )
{
    a = radians(a); v.yz = rot2(-a.x)*v.yz; v.xz = rot2(-a.y)*v.xz; v.xy = rot2(-a.z)*v.xy; return v;
}

// ---- distance function of each primitive
float sdEllipsoid( vec3 p, vec3 r )
{
    float k0 = length(p/r);
    if( k0<1e-4 ) return -min(r.x,min(r.y,r.z));
    // inside: a quick estimate (exact at the surface) is enough
    if( k0<1.0 ) return k0*(k0-1.0)/length(p/(r*r));
    // outside: the real distance. The quick estimate falls far too short
    // next to thin ellipsoids, which then seem close when they are not
    // (slow rays, dark bands in the ambient occlusion). The nearest point
    // is r*r*q/(r*r+l) for the l that puts it on the surface: a few Newton
    // steps, started on the side from which they cannot overshoot.
    vec3 q = abs(p), r2 = r*r;
    vec3 s = r*q - r2;
    float l = max( s.x, max(s.y,s.z) );
    for( int i=0; i<5; i++ )
    {
        vec3 w = max( r2+l, 1e-6 );
        vec3 g = r*q/w;
        l += 0.5*(dot(g,g)-1.0)/dot(g*g,1.0/w);
    }
    return length( q - r2*q/(r2+l) );
}
float sdBox( vec3 p, vec3 b )
{
    vec3 d = abs(p)-b;
    return min(max(d.x,max(d.y,d.z)),0.0) + length(max(d,0.0));
}
float sdCapsule2( vec3 p, vec3 a, vec3 b, float ra, float rb )
{
    vec3 pa = p-a, ba = b-a;
    float h = clamp( dot(pa,ba)/dot(ba,ba), 0.0, 1.0 );
    return length(pa-ba*h) - mix(ra,rb,h);
}
// A layer of a flat drawing: distance to the segment from a to a+ba, measured
// ignoring the direction f (so it is a shape that goes on forever along f).
// With ba = 0 it is a point: a disc.
float sdFlat( vec3 p, vec3 a, vec3 ba, vec3 f )
{
    vec3 q = p-a; q -= f*dot(q,f);
    float h = clamp( dot(q,ba)/max(dot(ba,ba),1e-12), 0.0, 1.0 );
    return length( q-ba*h );
}
// Tube along a quadratic Bezier (a parabola arc) from a to b, pulled toward c.
// Nearest point: coarse search over 8 samples, then 3 Newton steps.
float sdCurve( vec3 p, vec3 a, vec3 c, vec3 b, float ra, float rb )
{
    vec3 A = c-a, B = a-2.0*c+b;
    float t = 0.0, best = 1e9;
    for( int i=0; i<=8; i++ )
    {
        float s = float(i)/8.0;
        vec3 d = a + s*(2.0*A + s*B) - p;
        float dd = dot(d,d);
        if( dd<best ) { best = dd; t = s; }
    }
    for( int i=0; i<3; i++ )
    {
        vec3 d  = a + t*(2.0*A + t*B) - p;
        vec3 d1 = 2.0*(A + t*B);
        t = clamp( t - dot(d,d1)/(dot(d1,d1) + dot(d,2.0*B)), 0.0, 1.0 );
    }
    vec3 d = a + t*(2.0*A + t*B) - p;
    return length(d) - mix(ra,rb,t);
}
// A curved stroke of a flat drawing: distance to the arc from a to b pulled
// toward c, measured ignoring the direction f. a, c and b have nothing
// along f.
float sdFlatCurve( vec3 p, vec3 a, vec3 c, vec3 b, vec3 f )
{
    return sdCurve( p - f*dot(p,f), a, c, b, 0.0, 0.0 );
}
// Cone with its tip cut off (flat ends), vertical, centered. h = half height,
// r1 = bottom radius, r2 = top radius, rr = rounding of the edges.
float sdCutCone( vec3 p, float h, float r1, float r2, float rr )
{
    vec2 q  = vec2( length(p.xz), p.y );
    vec2 k1 = vec2( r2, h );
    vec2 k2 = vec2( r2-r1, 2.0*h );
    vec2 ca = vec2( q.x-min(q.x,(q.y<0.0)?r1:r2), abs(q.y)-h );
    vec2 cb = q - k1 + k2*clamp( dot(k1-q,k2)/dot(k2,k2), 0.0, 1.0 );
    float s = (cb.x<0.0 && ca.y<0.0) ? -1.0 : 1.0;
    return s*sqrt( min(dot(ca,ca),dot(cb,cb)) ) - rr;
}
float sdRoundCyl( vec3 p, float r, float h, float rr )
{
    vec2 w = vec2( length(p.xz)-r, abs(p.y)-h );
    return min(max(w.x,w.y),0.0) + length(max(w,0.0)) - rr;
}
float sdTorus( vec3 p, float R, float r )
{
    return length( vec2(length(p.xz)-R,p.y) ) - r;
}

// Which way a hair lies on skin that looks toward n, combed toward flow.
// Where the flow goes straight into or out of the skin, it falls downward.
vec3 combed( vec3 flow, vec3 n )
{
    vec3 way = flow - n*dot(flow,n);
    vec3 down = vec3(0.0,-1.0,0.0) - n*(-n.y);
    way += down*(1.0-smoothstep(0.0,0.5,length(way)));
    return way/max(length(way),1e-4);
}

// Which way a strand goes from its root (of length 1): it rises lift
// (radians) off skin that looks toward n, combed toward flow. push (the
// wind) lays it over and turns it, but does not stand it up past its lift.
vec3 strand( vec3 flow, vec3 push, vec3 n, float lift )
{
    vec3 way = combed(flow,n)*cos(lift) + push - n*dot(push,n);
    float along = length(way);
    if( along<cos(lift) ) way = along>1e-4 ? way*cos(lift)/along : combed(flow,n)*cos(lift);
    return normalize( way + n*sin(lift) );
}

// ---- procedural noise
uint uhash( uint x )
{
    x ^= x >> 16; x *= 0x7feb352dU;
    x ^= x >> 15; x *= 0x846ca68bU;
    x ^= x >> 16;
    return x;
}
float hashI( ivec3 p ) { return float( uhash( uint(p.x) + uhash(uint(p.y) + uhash(uint(p.z))) ) )*(1.0/4294967295.0); }
// three random numbers (0..1) for a cell of a repetition: always the same for the same cell
vec3 cellRand( vec3 c, float seed )
{
    ivec3 i = ivec3(c) + ivec3(int(seed)*1013);
    return vec3( hashI(i), hashI(i+ivec3(57,113,31)), hashI(i+ivec3(-91,17,203)) );
}
float noise3( vec3 x )
{
    ivec3 i = ivec3(floor(x));
    vec3  f = fract(x); f = f*f*(3.0-2.0*f);
    return mix( mix( mix( hashI(i),              hashI(i+ivec3(1,0,0)), f.x ),
                     mix( hashI(i+ivec3(0,1,0)), hashI(i+ivec3(1,1,0)), f.x ), f.y ),
                mix( mix( hashI(i+ivec3(0,0,1)), hashI(i+ivec3(1,0,1)), f.x ),
                     mix( hashI(i+ivec3(0,1,1)), hashI(i+ivec3(1,1,1)), f.x ), f.y ), f.z );
}
// several octaves of noise added: each at twice the frequency and half the strength
float fbm3( vec3 x )
{
    float f = 0.0, a = 0.5;
    for( int i=0; i<4; i++ ) { f += a*noise3(x); x = x*2.02 + 5.3; a *= 0.5; }
    return f/0.9375;
}
