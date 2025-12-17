if __name__ == "__main__":
    import os
    import pytest

    # Skip CPython finalizers — cppyy holds C++ objects whose destructors run
    # during interpreter shutdown's GC pass and double-free, aborting an
    # otherwise-passing test run. _exit() preserves the pytest exit code while
    # bypassing the at-exit destructors.
    os._exit(pytest.main())
