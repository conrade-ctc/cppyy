import sys
import pytest
import cppyy

cppyy.add_library_path("external/symengine/lib")
cppyy.load_library("libsymengine.so")

cppyy.add_include_path("external/gmp/include")
cppyy.add_include_path("external/symengine/include")
cppyy.include("symengine/basic.h")
cppyy.include("symengine/real_double.h")
cppyy.include("symengine/integer.h")
cppyy.include("symengine/add.h")
cppyy.include("symengine/mul.h")
cppyy.include("symengine/pow.h")
cppyy.include("symengine/functions.h")
cppyy.include("symengine/logic.h")
cppyy.include("symengine/subs.h")

cppyy.cppdef("""
template <typename T>
SymEngine::RCP<const SymEngine::Basic> symengine_to_basic(SymEngine::RCP<const T>& expr)
{
    return SymEngine::rcp_static_cast<const SymEngine::Basic>(expr);
}

inline SymEngine::RCP<const SymEngine::Basic> symengine_int(int64_t i)
{
    SymEngine::RCP<const SymEngine::Integer> inter = SymEngine::integer(i);
    return symengine_to_basic(inter);
}
""")

from cppyy.gbl import SymEngine, std, symengine_to_basic, symengine_int

class Test_0:
    @pytest.mark.skip
    def test1(self):
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

    def assertTrue(self, xx):
        assert xx

    def assertFalse(self, xx):
        assert not xx

    def assertEqual(self, xx, yy):
        assert xx == yy

    def testVecElemRefCounts(self):
        # vec is std::vector<SymEngine::RCP<const SymEngine::Basic>>
        vec = SymEngine.vec_basic()
        vec.push_back(symengine_to_basic(symengine_int(42)))

        self.assertTrue(vec.__python_owns__)
        vec_refcnt = sys.getrefcount(vec)
        self.assertTrue(vec_refcnt > 0)

        # taking a python reference of an element does NOT increase ref-count on vec
        elem = vec[0]
        self.assertFalse(vec._getitem__unchecked.__set_lifeline__)
        self.assertEqual(sys.getrefcount(vec), vec_refcnt)
        self.assertEqual(elem.use_count(), 1)
        self.assertFalse(elem.__python_owns__)

        # taking a python reference of an element does NOT increase ref-count on vec
        elem = vec[0]
        self.assertFalse(vec._getitem__unchecked.__set_lifeline__)
        self.assertEqual(sys.getrefcount(vec), vec_refcnt)
        self.assertEqual(elem.use_count(), 1)
        self.assertFalse(elem.__python_owns__)

        # taking another python reference of the same element does NOT increase use_count of elem
        elem2 = vec[0]
        self.assertEqual(sys.getrefcount(vec), vec_refcnt)
        self.assertEqual(elem2.use_count(), 1)
        self.assertFalse(elem2.__python_owns__)

    def testVecElemExtraRef(self):
        def get_elem():
            vec = SymEngine.vec_basic()
            vec.push_back(symengine_to_basic(symengine_int(42)))

            elem = vec[0]
            self.assertEqual(elem.use_count(), 1)
            self.assertFalse(elem.__python_owns__)

            # Upon leaving the scope of get_elem, the extra reference to vec keeps elem alive.
            return vec, elem

        _vec, elem = get_elem()
        self.assertEqual(elem.use_count(), 1)
        self.assertFalse(elem.__python_owns__)
        self.assertEqual(elem.get().as_int(), 42)

    def testVecElemCopy(self):
        def copy(x):
            return type(x)(x)  # invokes copy constructor of SymEngine::RCP<const SymEngine::Basic>

        def get_elem():
            vec = SymEngine.vec_basic()
            vec.push_back(symengine_to_basic(symengine_int(42)))
            self.assertTrue(vec.size() > 0)

            elem = vec[0]
            self.assertEqual(elem.use_count(), 1)
            self.assertFalse(elem.__python_owns__)

            # making a true copy of elem increments use_count in SymEngine::RCP<const SymEngine::Basic>
            elem = copy(elem)
            self.assertEqual(elem.use_count(), 2)
            # and the copy is owned by python
            self.assertTrue(elem.__python_owns__)

            # Upon leaving the scope of get_elem, vec is destroyed, which decrements elem's use_count.
            # But use_count does not go to zero because python still holds a reference to a copy of the SymEngine::RCP<...>.
            return elem

        elem = get_elem()
        self.assertEqual(elem.use_count(), 1)
        self.assertTrue(elem.__python_owns__)
        self.assertEqual(elem.get().as_int(), 42)

    def testVecElemDanglingRef(self):
        """
        We can get a dangling reference to an element of a vector, in python.
        Use std::shared_ptr<...> here because SymEngine::RCP<...> doesn't have a weak_ptr interface.
        But the behavior would be the same for SymEngine::RCP<...>.

        Upon leaving the scope of get_elem, vec is destroyed, so are its elements, even if
        python still holds references to the elements.
        """

        def get_elem():
            vec = std.vector[std.shared_ptr[int]]()
            vec.push_back(std.make_shared[int](42))
            elem = vec[0]
            return elem, std.weak_ptr[int](elem)

        elem, elem_weak_ptr = get_elem()

        # python thinks elem is still alive, but accessing elem's content causes segfault
        self.assertTrue(sys.getrefcount(elem) > 0)

        # the object referenced by elem no longer exists, elem is dangling.
        self.assertTrue(elem_weak_ptr.expired())

    def testExprGet(self):
        expr = symengine_to_basic(symengine_int(42))
        refcnt = sys.getrefcount(expr)
        self.assertEqual(expr.use_count(), 1)

        # .get() creates a python back reference to expr
        n = expr.get()
        self.assertTrue(expr.get.__set_lifeline__)  # check after call to .get()

        self.assertEqual(sys.getrefcount(expr), refcnt + 1)
        # NOPE!
        #self.assertEqual(sys.getrefcount(expr), refcnt)
        self.assertEqual(expr.use_count(), 1)

        del n
        self.assertEqual(sys.getrefcount(expr), refcnt)
        self.assertEqual(expr.use_count(), 1)
