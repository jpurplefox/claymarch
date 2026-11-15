// Viewer: draws scene.glsl full screen and reloads it by itself whenever
// version.txt changes (Python rewrites it every time the scene is regenerated).

const canvas = document.getElementById('c');
const hud = document.getElementById('hud');
const errEl = document.getElementById('err');
const gl = canvas.getContext('webgl2', { antialias: false, alpha: false, powerPreference: 'high-performance' });

function showError(msg) { errEl.textContent = msg; errEl.style.display = msg ? 'block' : 'none'; }
if (!gl) showError('This browser does not support WebGL2.');

const VERT = `#version 300 es
void main() {
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

// "#line 1" makes compile errors match the lines of scene.glsl
const HEADER = `#version 300 es
precision highp float;
precision highp int;
uniform vec3 iResolution;
uniform float iTime;
uniform int iFrame;
uniform vec3 uOrbit;
out vec4 viewerColor;
#line 1
`;
const FOOTER = `
void main() {
  vec4 c = vec4(0.0, 0.0, 0.0, 1.0);
  mainImage(c, gl_FragCoord.xy);
  viewerColor = vec4(c.rgb, 1.0);
}`;

function compile(type, src) {
  const sh = gl.createShader(type);
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(sh);
    gl.deleteShader(sh);
    throw new Error(log);
  }
  return sh;
}

function build(fragBody) {
  const prog = gl.createProgram();
  gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
  gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, HEADER + fragBody + FOOTER));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
  const u = {};
  for (const n of ['iResolution', 'iTime', 'iFrame', 'uOrbit']) u[n] = gl.getUniformLocation(prog, n);
  return { prog, u };
}

// ---------- state ----------
let current = null, version = '';
let time = 0, frame = 0, paused = false, last = performance.now();
let yaw = 0, pitch = 0, zoom = 1, scale = 0.75;
let fpsAcc = 0, fpsN = 0;

async function reloadIfChanged() {
  try {
    const v = await (await fetch('version.txt', { cache: 'no-store' })).text();
    if (v === version) return;
    const src = await (await fetch('scene.glsl', { cache: 'no-store' })).text();
    version = v;
    try {
      const next = build(src);
      if (current) gl.deleteProgram(current.prog);
      current = next;
      showError('');
    } catch (e) {
      // if the new scene does not compile, the previous one keeps showing
      showError('Error in scene.glsl (the numbers are lines of that file):\n\n' + e.message);
    }
  } catch (e) { /* the server may be restarting */ }
}

function resize() {
  const w = Math.max(2, Math.round(canvas.clientWidth * scale));
  const h = Math.max(2, Math.round(canvas.clientHeight * scale));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
}

function tick(now) {
  requestAnimationFrame(tick);
  const dt = Math.min((now - last) / 1000, 0.25);
  last = now;
  if (!current) return;
  if (!paused) time += dt;
  resize();
  gl.viewport(0, 0, canvas.width, canvas.height);
  gl.useProgram(current.prog);
  gl.uniform3f(current.u.iResolution, canvas.width, canvas.height, 1);
  gl.uniform1f(current.u.iTime, time);
  gl.uniform1i(current.u.iFrame, frame++);
  gl.uniform3f(current.u.uOrbit, yaw, pitch, zoom);
  gl.drawArrays(gl.TRIANGLES, 0, 3);

  fpsAcc += dt; fpsN++;
  if (fpsAcc >= 0.5) {
    hud.textContent = `${(fpsN / fpsAcc).toFixed(0)} fps · ${canvas.width}×${canvas.height} · t=${time.toFixed(1)}s${paused ? ' · paused' : ''}`;
    fpsAcc = 0; fpsN = 0;
  }
}

// ---------- controls ----------
let drag = null;
canvas.addEventListener('pointerdown', (e) => { drag = [e.clientX, e.clientY]; canvas.setPointerCapture(e.pointerId); });
canvas.addEventListener('pointerup', () => { drag = null; });
canvas.addEventListener('pointermove', (e) => {
  if (!drag) return;
  yaw -= (e.clientX - drag[0]) * 0.008;
  pitch += (e.clientY - drag[1]) * 0.008;
  drag = [e.clientX, e.clientY];
});
canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  zoom = Math.min(8, Math.max(0.15, zoom * Math.exp(e.deltaY * 0.0015)));
}, { passive: false });
window.addEventListener('keydown', (e) => {
  if (e.key === ' ') { paused = !paused; e.preventDefault(); }
  if (e.key === 'r' || e.key === 'R') { time = 0; yaw = 0; pitch = 0; zoom = 1; }
  if (e.key === '1') scale = 0.5;
  if (e.key === '2') scale = 0.75;
  if (e.key === '3') scale = 1.0;
});

// ---------- video export ----------
// Opened as ?record=1&w=1080&h=1920&seconds=8&fps=30 (python -m sculpt ... --video
// does it). Two passes: first every frame is drawn at its exact time, however
// long each one takes; then the saved frames are played back at real speed
// into a recorder, and the finished file is sent to the Python server.
const params = new URLSearchParams(location.search);
const sleepUntil = (when) => new Promise((ok) => setTimeout(ok, Math.max(0, when - performance.now())));

async function record() {
  const num = (name, fallback) => (params.has(name) ? Number(params.get(name)) : fallback);
  const W = num('w', 1080), H = num('h', 1920), seconds = num('seconds', 8), fps = num('fps', 30);
  const sway = num('sway', 0) * Math.PI / 180, total = Math.round(seconds * fps);
  zoom = num('zoom', 1);
  document.getElementById('help').style.display = 'none';
  canvas.style.width = 'auto'; canvas.style.height = '100vh'; canvas.style.margin = '0 auto';
  canvas.width = W; canvas.height = H;

  // pass 1: draw
  const frames = [];
  for (let i = 0; i < total; i++) {
    const t = i / fps;
    gl.viewport(0, 0, W, H);
    gl.useProgram(current.prog);
    gl.uniform3f(current.u.iResolution, W, H, 1);
    gl.uniform1f(current.u.iTime, t);
    gl.uniform1i(current.u.iFrame, i);
    gl.uniform3f(current.u.uOrbit, sway * Math.sin(2 * Math.PI * t / seconds), 0, zoom);   // a slow sway that loops
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    frames.push(await new Promise((ok) => canvas.toBlob(ok, 'image/jpeg', 0.97)));
    hud.textContent = `video: drawing frame ${i + 1} of ${total}`;
  }

  // pass 2: play back into the recorder
  const out = document.createElement('canvas');
  out.width = W; out.height = H;
  out.style.cssText = 'width:auto;height:100vh;display:block;margin:0 auto';
  canvas.replaceWith(out);
  const ctx = out.getContext('2d');
  const mime = ['video/mp4;codecs=avc1.640028', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm']
    .find((m) => MediaRecorder.isTypeSupported(m));
  const stream = out.captureStream(0), track = stream.getVideoTracks()[0];
  const recorder = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 16e6 });
  const chunks = [];
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  const stopped = new Promise((ok) => { recorder.onstop = ok; });
  recorder.start();
  const t0 = performance.now() + 200;
  for (let i = 0; i < total; i++) {
    const image = await createImageBitmap(frames[i]);
    await sleepUntil(t0 + i * 1000 / fps);
    ctx.drawImage(image, 0, 0);
    track.requestFrame();
    image.close();
    hud.textContent = `video: recording ${i + 1} of ${total}`;
  }
  await sleepUntil(t0 + total * 1000 / fps);
  recorder.stop();
  await stopped;

  const ext = mime.includes('mp4') ? 'mp4' : 'webm';
  const reply = await fetch('video?ext=' + ext, { method: 'POST', body: new Blob(chunks, { type: mime }) });
  hud.textContent = reply.ok ? 'video: saved — ' + (await reply.text()) : 'video: the server could not save the file';
}

if (gl) {
  gl.bindVertexArray(gl.createVertexArray());
  await reloadIfChanged();
  if (params.has('record') && current) {
    record().catch((e) => showError('Video export failed:\n\n' + e.message));
  } else {
    setInterval(reloadIfChanged, 700);
    requestAnimationFrame(tick);
  }
}
