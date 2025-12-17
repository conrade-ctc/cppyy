import sys
import pytest
import cppyy

def load_symengine_reqs():
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
    def setup_class(cls):
        if False: load_symengine_reqs()

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

    def test3(self):
        ctors = []
        nx = 1500
        for i in range(nx):
            si = str(i)
            ns = "ns_" + si
            gr = "Graph"
            cppyy.cppdef("namespace " + ns + """{
            struct """ + gr + """ {
            int m_a;
            int m_b;
            int m_c;
            int m_d;
            int m_e;
            int m_m[10000];
            void init() {
              m_a = """ + si + """;
              m_b = 2*""" + si + """;
              m_c = 3*""" + si + """;
              m_d = 4*""" + si + """;
              m_e = 5*""" + si + """;
            }

            """ + gr + """() {
              init();
            }
            void a(int aa) { m_a = aa; }
            void b(int aa) { m_b = aa; }
            void c(int aa) { m_c = aa; }
            void d(int aa) { m_d = aa; }
            void e(int aa) { m_e = aa; }
            };
            }""")

            nsf = "cppyy.gbl." + ns
            cppyy.gbl
            exec(nsf)
            assert ns in sys.modules["cppyy.gbl"].__dict__
            exec(nsf + "." + gr)
            assert gr in sys.modules["cppyy.gbl"].__dict__[ns].__dict__
            ctors.append(sys.modules["cppyy.gbl"].__dict__[ns].__dict__[gr])

        inst = []
        for i in range(nx):
            inst.append(ctors[i]())

        for i in range(nx):
            assert inst[i].m_a == i
            assert inst[i].m_b == 2*i
            assert inst[i].m_c == 3*i
            assert inst[i].m_d == 4*i
            assert inst[i].m_e == 5*i

        for i in range(nx):
            inst[i].a(2*i)
            inst[i].b(3*i)
            inst[i].c(4*i)
            inst[i].d(5*i)
            inst[i].e(6*i)

        for i in range(nx):
            assert inst[i].m_a == 2*i
            assert inst[i].m_b == 3*i
            assert inst[i].m_c == 4*i
            assert inst[i].m_d == 5*i
            assert inst[i].m_e == 6*i


class NothingForNow:
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

    def testEnumTemplates(self):
        with open("test_enum_templates.h", "w") as hdata:
            print("""
namespace EXNS {
template <typename E>
inline bool is_an_enum()
{
    return std::is_enum_v<E>;
}

template <typename E>
inline std::string underlying_enum_type_name()
{
    using T = std::underlying_type_t<E>;
    return std::string(std::is_signed_v<T> ? "" : "u") + "int" + std::to_string(8 * sizeof(T)) + "_t";
}

// get the standardized names of the underlying type of an enum
template <typename E>
requires std::is_enum_v<E>
inline std::string underlying_type_name()
{
    using T = std::underlying_type_t<E>;
    return std::string(std::is_signed_v<T> ? "" : "u") + "int" + std::to_string(8 * sizeof(T)) + "_t";
}
}
        """, file = hdata)
        cppyy.include("test_enum_templates.h")

        cppyy.cppdef("""
namespace NS0 {
enum class EX : uint32_t
{
    A = 0b1,
    B = 0b100,
    C = 0b101
};
}
        """)

        EX = cppyy.gbl.NS0.EX
        self.assertEqual(EX.A, 1)
        self.assertTrue(cppyy.gbl.EXNS.is_an_enum[EX]())
        self.assertEqual(cppyy.gbl.EXNS.underlying_enum_type_name[EX](), "uint32_t")
        self.assertEqual(cppyy.gbl.EXNS.underlying_type_name[EX](), "uint32_t")
