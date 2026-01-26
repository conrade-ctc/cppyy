import sys
import pytest

class Test_0:
    def test_fail(self):
        import cppyy

        ty = "int8_t"
        cppyy.cppdef(f"""
        struct fails {{
          {ty} b{{0x64}};
          const {ty} &ref() {{ return b; }}
        }};
        """)

        x = cppyy.gbl.fails()
        t = type(x.b)
        if t in [chr, str]:
            assert x.ref() == 'd'
        else:
            assert x.ref() == 0x64
        x.__destruct__()

    def test_passes(self):
        import cppyy

        cppyy.cppdef("""
        using Y = std::byte;
        struct passes {
          Y b{0x64};
          const Y &ref() { return b; }
        };
        """)

        x = cppyy.gbl.passes()
        #assert x.ref() == 100 # can't use this... bizarro
        assert x.ref() == 'd'
        x.__destruct__()
