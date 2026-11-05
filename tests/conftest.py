import os
import tempfile

# Never touch the real config or presets.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="dotlab-test-config-")
