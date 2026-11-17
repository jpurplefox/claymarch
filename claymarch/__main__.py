"""Viewer with automatic reload.

    python -m claymarch examples/caterpie.py [--port 8770]

Runs the file, takes its scene (a variable named `scene`, or the last Scene
subclass defined in it), generates the shader and serves it to the browser.
Every time the file is saved it is generated again and the page updates itself.
"""
import argparse
import functools
import http.server
import runpy
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

from .scene import Scene


def find_scene(namespace, filename):
    scene = namespace.get("scene")
    if isinstance(scene, Scene):
        return scene
    classes = [v for v in namespace.values()
               if isinstance(v, type) and issubclass(v, Scene) and v is not Scene]
    if classes:
        return classes[-1]()
    raise RuntimeError(f"{filename} must define a Scene subclass, or a variable named `scene`")


def generate(source, out):
    find_scene(runpy.run_path(str(source)), source.name).export(out)


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        # the page sends the finished video here (see record() in main.js)
        job = getattr(self.server, "video_job", None)
        if job is None or not self.path.startswith("/video"):
            self.send_error(404)
            return
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        ext = "webm" if "ext=webm" in self.path else "mp4"
        target = job["target"].with_suffix("." + ext)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        job["saved"] = target
        body = str(target).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        job["done"].set()


def main():
    ap = argparse.ArgumentParser(prog="python -m claymarch", description="Scene viewer with automatic reload")
    ap.add_argument("file", help=".py file that defines the scene")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--out", default=None, help="folder to write to (default: build/<name>)")
    ap.add_argument("--once", action="store_true", help="generate the files and exit, without serving")
    ap.add_argument("--video", default=None, metavar="FILE",
                    help="export a video to FILE (.mp4) instead of opening the viewer; it is drawn in a browser tab")
    ap.add_argument("--size", default="1080x1920", help="video size, WIDTHxHEIGHT (default 1080x1920, vertical)")
    ap.add_argument("--seconds", type=float, default=8.0, help="video length (default 8)")
    ap.add_argument("--fps", type=int, default=30, help="video frames per second (default 30)")
    ap.add_argument("--zoom", type=float, default=1.0, help="video: camera distance factor (bigger = farther)")
    ap.add_argument("--sway", type=float, default=0.0, help="video: degrees the camera sways side to side")
    ap.add_argument("--yaw", type=float, default=0.0, help="video: degrees the camera is turned sideways from the scene's own")
    ap.add_argument("--pitch", type=float, default=0.0, help="video: degrees the camera is raised from the scene's own")
    ap.add_argument("--right", type=float, default=0.0,
                    help="video: slides the picture to the right inside the frame, as a fraction of its height")
    ap.add_argument("--up", type=float, default=0.0,
                    help="video: slides the picture up inside the frame, as a fraction of its height")
    ap.add_argument("--lens", type=float, default=1.0,
                    help="video: magnifies the picture without moving the camera (2 = twice as big)")
    ap.add_argument("--blend", type=float, default=0.0,
                    help="video: seconds at the end that dissolve into the beginning, so that it loops")
    ap.add_argument("--no-open", action="store_true", help="video: print the link instead of opening the browser")
    args = ap.parse_args()

    source = Path(args.file).resolve()
    if not source.exists():
        sys.exit(f"{source} does not exist")
    out = Path(args.out) if args.out else Path("build") / source.stem
    sys.path.insert(0, str(source.parent))

    out.mkdir(parents=True, exist_ok=True)

    if args.once:
        try:
            generate(source, out)
        except Exception:
            traceback.print_exc()
            sys.exit(1)
        return

    def attempt():
        # Each generation runs in a fresh Python process, so edits to the scene,
        # to files it imports, and to this library itself are always picked up.
        # An error does not kill the viewer: fix it and save again.
        result = subprocess.run([sys.executable, "-m", "claymarch", str(source), "--out", str(out), "--once"])
        stamp_text = time.strftime("%H:%M:%S")
        print(f"[{stamp_text}] " + ("scene generated" if result.returncode == 0 else f"error in {source.name}"), flush=True)

    attempt()

    handler = functools.partial(_Quiet, directory=str(out))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    if args.video:
        try:
            width, height = (int(n) for n in args.size.lower().split("x"))
        except ValueError:
            sys.exit("--size must look like 1080x1920")
        job = {"target": Path(args.video).resolve(), "done": threading.Event(), "saved": None}
        server.video_job = job
        url = (f"http://localhost:{args.port}/?record=1&w={width}&h={height}&seconds={args.seconds}"
               f"&fps={args.fps}&zoom={args.zoom}&sway={args.sway}&yaw={args.yaw}&pitch={args.pitch}"
               f"&blend={args.blend}&right={args.right}&up={args.up}&lens={args.lens}")
        print(f"drawing {round(args.seconds * args.fps)} frames at {width}x{height} in the browser:\n  {url}\n"
              "keep that tab visible until it says 'saved' (Ctrl+C to cancel)", flush=True)
        if not args.no_open:
            import webbrowser
            webbrowser.open(url)
        try:
            job["done"].wait()
        except KeyboardInterrupt:
            sys.exit("\ncancelled")
        print(f"video saved: {job['saved']}", flush=True)
        return
    print(f"open http://localhost:{args.port}   (Ctrl+C to quit)", flush=True)

    # watched: the scene file, the .py files next to it, and this library
    library = Path(__file__).parent

    def stamp():
        files = [*source.parent.glob("*.py"), *library.glob("*.py"), *(library / "template").glob("*")]
        return max((f.stat().st_mtime for f in files if f.is_file()), default=0.0)

    last = stamp()
    try:
        while True:
            time.sleep(0.4)
            now = stamp()
            if now != last:
                last = now
                attempt()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
