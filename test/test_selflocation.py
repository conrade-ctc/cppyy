import os


class TestSELFLOCATION:
    def test01_jit_from_foreign_cwd(self):
        """Import and JIT with cwd '/' and no path env vars: the stack must
        locate the backend solib, CppInterOp, and the CPyCppyy API headers
        from its own installed location alone."""

        for var in ('CPPINTEROP_LIB_PATH', 'CPPINTEROP_INCLUDE_PATH',
                    'CPPYY_BACKEND_LIBRARY', 'CPPYY_API_PATH',
                    'RUNFILES_DIR', 'RUNFILES_MANIFEST_FILE'):
            os.environ.pop(var, None)
        os.chdir('/')

        import cppyy

        cppyy.cppdef("int self_location_add(int a, int b) { return a + b; }")
        assert cppyy.gbl.self_location_add(20, 22) == 42
