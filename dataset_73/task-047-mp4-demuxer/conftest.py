# benchmark/mp4-demuxer -- ISOBMFF/MP4 box demuxer: walk the box hierarchy (containers recurse), handle 8-byte / 64-bit / size-0-to-EOF headers, decode ftyp/mvhd/tkhd…
import os
import sys
from pathlib import Path

engine_dir = os.environ.get("ENGINE_DIR")
if engine_dir:
    p = Path(engine_dir).resolve()
    if p.name == "engine":
        pkg_parent = str(p.parent)
    elif (p / "engine").is_dir():
        pkg_parent = str(p)
    else:
        pkg_parent = str(p.parent)

    if pkg_parent in sys.path:
        sys.path.remove(pkg_parent)
    sys.path.insert(0, pkg_parent)

    # Purge cached engine modules
    for mod in list(sys.modules.keys()):
        if mod == "engine" or mod.startswith("engine."):
            del sys.modules[mod]
else:
    here = Path(__file__).resolve().parent
    if Path("/app").is_dir():
        if "/app" not in sys.path:
            sys.path.insert(0, "/app")
    env_dir = str(here.parent / "environment")
    if env_dir not in sys.path:
        sys.path.insert(0, env_dir)
