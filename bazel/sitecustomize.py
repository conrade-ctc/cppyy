"""Fix the hermetic interpreter's stale sysconfig include path.

rules_python's standalone Python bakes a build-time INCLUDEPY ("/install/...")
into sysconfig, so sysconfig.get_config_var("INCLUDEPY") points at a path that
doesn't exist at runtime. Some cppyy tests pass that value to
cppyy.add_include_path(), which errors on the missing dir. Repoint it (and the
related distutils var) at the real headers under sys.base_prefix. Python imports
sitecustomize automatically at startup when it's on sys.path.
"""

import os
import sys
import sysconfig

_real = os.path.join(
    sys.base_prefix, "include", "python" + sysconfig.get_python_version(),
)
if os.path.isdir(_real):
    sysconfig.get_config_vars()  # force the cache to populate
    sysconfig._CONFIG_VARS["INCLUDEPY"] = _real
