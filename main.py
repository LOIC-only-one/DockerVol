import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import volumes  # noqa: E402
from runtime import app  # noqa: E402

if __name__ == "__main__":
    volumes.check_user_permissions()
    # No authentication on the UI: listen on localhost only unless explicitly overridden.
    app.run(host=os.environ.get("DOCKERVOL_HOST", "127.0.0.1"),
            port=int(os.environ.get("DOCKERVOL_PORT", "5000")))
