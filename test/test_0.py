import sys
import pytest

class Test_0:
    @pytest.mark.skip
    def test1(self):
        import cppyy

        cppyy.cppdef("""
        struct X {
          using Y = int16_t;

          Y x = 17;
          Y &xf();
          const Y &cxf();
        };

        X::Y &X::xf() { return x; }
        const X::Y &X::cxf() { return x; }
        """)

        X = cppyy.gbl.X
        x = X()
        assert isinstance(x, X)

        assert x.x == 17
        assert x.xf() == 17
        assert x.cxf() == 17

        x.__destruct__()

    def test2(self):
        import cppyy

        cppyy.cppdef("""
        struct X {
          using W = int16_t;
          using Y = int8_t;

          bool b = true;
          W w = 17;
          Y y = 18;

          W &wf();
          const W &cwf();

          Y &yf();
          const Y &cyf();
        };

        X::W &X::wf() { return w; }
        const X::W &X::cwf() { return w; }

        X::Y &X::yf() { return y; }
        const X::Y &X::cyf() { return y; }
        """)

        X = cppyy.gbl.X
        x = X()
        assert isinstance(x, X)

        ww = 17
        assert x.w == ww
        assert x.wf() == ww
        assert x.cwf() == ww

        yy = '\x12'
        assert x.y == yy
        assert x.yf() == yy
        assert x.cyf() == yy

        x.__destruct__()
