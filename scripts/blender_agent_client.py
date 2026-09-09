"""Headless Blender side of the end-to-end test.

Connects the real add-on to a harness server (127.0.0.1:9876 by default) and
pumps the bridge on Blender's main thread so tool calls from the agent are
executed against live bpy. Exits 0 once the agent run finishes.

Run by scripts/integration_e2e.py; not meant to be started by hand.
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("BLENDER_HARNESS_DATA_DIR",
                      os.path.join(os.path.dirname(__file__), "..", "data", "blender_client_data"))

import bpy  # noqa: E402


def main() -> int:
    port = int(os.environ.get("HARNESS_PORT", "9876"))
    from blender_addon.transport.bridge import bridge

    br = bridge()
    br.configure("127.0.0.1", port)
    br.start()
    br.ensure_pump()

    deadline = time.time() + 150
    print("BLENDER_CLIENT_START", flush=True)
    saw_connected = False
    while time.time() < deadline:
        br._pump()  # main-thread tool execution
        if br.is_connected() and not saw_connected:
            saw_connected = True
            print("BLENDER_CLIENT_CONNECTED", flush=True)
        for line in br.log_tail[-20:]:
            if "run finished" in line or ("run" in line and "finished" in line):
                print("BLENDER_CLIENT_RUN_FINISHED", flush=True)
                # drain any remaining queued work
                for _ in range(40):
                    br._pump()
                    time.sleep(0.03)
                br.stop()
                return 0
        time.sleep(0.04)
    br.stop()
    print("BLENDER_CLIENT_TIMEOUT", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
