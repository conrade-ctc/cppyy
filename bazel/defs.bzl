"""Shared copts, linkopts, and runtime env for the cppyy stack."""

load("@llvm//:defs.bzl", "CLANG_LIB_NAMES", "LLVM_GOLD_PLUGIN", "LLVM_INCLUDE_DIRS", "LLVM_LIB_NAMES", "LLVM_SYSTEM_LIBS", "LLVM_VERSION")

# bzlmod resolves Label() in THIS module's mapping, so the consumer repos
# (deps of the consumers, not of cppyy_bazel) can't be resolved here; their
# single-version deps canonicalize deterministically to "name+", so map the
# apparent names to those literals and fall back to Label() for @llvm/anything else.
_CONSUMER_CANON = {
    "cppinterop": "cppinterop+",
    "cppyy_backend": "cppyy_backend+",
    "cpycppyy": "cpycppyy+",
    "cppyy": "cppyy+",
}

def repo_name(repo):
    return _CONSUMER_CANON.get(repo.lstrip("@"), None) or Label(repo).repo_name

def repo_loc(repo):
    return "external/" + repo_name(repo)

def repo_rloc(repo):
    return "../" + repo_name(repo)

# Per-target compile flags. The ABI-critical flags (LLVM_DEFINES, visibility,
# -fno-semantic-interposition, -fno-stack-protector, etc.) are applied globally
# by our centralized clang toolchain (@llvm//:cc_toolchain); only per-target
# codegen choices live here. -fno-exceptions/-fno-rtti are per-target (some
# consumers re-enable them). -fPIC is kept here (not relied on from the
# toolchain) so these objects link into shared libraries regardless of which
# toolchain the consumer uses -- e.g. nebula's own toolchain defaults to no-PIC
# for cc_library and would otherwise fail the .so link. -O3 matches Release.
# -DNDEBUG is mandatory, not a -c opt nicety: the stack ships assert(0) stubs on
# live runtime paths (e.g. Interpreter::toString) plus JitCall validation asserts
# that fire during normal cppyy use. With asserts enabled (a consumer building
# -c dbg) those abort the process. The CMake/overlay build always compiles the
# stack with NDEBUG; we match that unconditionally regardless of consumer mode.
BASE_COPTS = [
    "-fPIC",
    "-fno-exceptions",
    "-fno-rtti",
    "-ffunction-sections",
    "-fdata-sections",
    "-fno-common",
    "-O3",
    "-DNDEBUG",
]

CPPINTEROP_COPTS = BASE_COPTS + [
    "-DCPPINTEROP_USE_REPL",
    "-DLLVM_BINARY_DIR='\"" + repo_loc("@llvm") + "\"'",
    "-DCPPINTEROP_VERSION='\"0.1.0-bazel\"'",
]

def _llvm_L_rpath():
    return [
        "-L" + repo_loc("@llvm") + "/lib",
        "-Wl,-rpath," + repo_rloc("@llvm") + "/lib",
    ]

# LTO codegen parallelism for the bitcode-archive link. Fixed (not nproc) for
# reproducibility; 16 is plenty for the cppinterop link's module count.
_LTO_JOBS = 16

# When the LLVM archives carry IR bitcode (an LTO-built tree, e.g. nebula's),
# the linker needs the LLVM plugin to read them; LLVM_GOLD_PLUGIN is the repo's
# LLVMgold.so path, or empty for a non-LTO tree (then this is a no-op).
# plugin-opt=O0 + jobs=<n> keep the implicit LTO codegen fast and parallel --
# without them the link does serial optimizing codegen of all of LLVM (minutes).
# O0 is fine: this is a JIT support library, runtime perf comes from the JIT.
def _llvm_plugin():
    if LLVM_GOLD_PLUGIN:
        return [
            "-Wl,--plugin=" + repo_loc("@llvm") + "/" + LLVM_GOLD_PLUGIN,
            "-Wl,-plugin-opt=O0",
            "-Wl,-plugin-opt=jobs=" + str(_LTO_JOBS),
        ]
    return []

# For libclangCppInterOp.so: link it self-contained from the static clang
# archives + LLVM components (no libclang-cpp.so dylib), mirroring CMake's
# add_llvm_library(... DISABLE_LLVM_LINK_LLVM_DYLIB). One static copy of every
# symbol -- including the X86/NVPTX target backends and the cl::opt globals --
# so nothing double-registers when the .so is later dlopen'd. --start-group
# resolves the ~100 archives' mutual references regardless of order. Applied at
# the cc_shared_library boundary only, so these flags don't leak to consumers
# that merely link the finished .so.
# NB: the LLVM --system-libs (zlib/zstd etc.) are NOT emitted here. They are
# provided as a cc_library dep via the :llvm_system_libs label_flag so a hermetic
# consumer can swap the host's bare -l flags for libs it ships (see CppInterOp's
# BUILD.bazel). LLVM_SYSTEM_LIBS is re-exported for that default target.
def llvm_linkopts():
    return _llvm_L_rpath() + _llvm_plugin() + [
        "-Wl,--start-group",
    ] + ["-l" + n for n in CLANG_LIB_NAMES] + \
        ["-l" + n for n in LLVM_LIB_NAMES] + [
        "-Wl,--end-group",
        "-ldl",
    ]

# For standalone LLVM tools (cppinterop-tblgen): the static component libs.
# libclang-cpp.so omits TableGen and some cl:: internals, so a tool using
# llvm::TableGen / RecordKeeper must link the components statically.
def llvm_tblgen_linkopts():
    return _llvm_L_rpath() + _llvm_plugin() + ["-l" + n for n in LLVM_LIB_NAMES]

# The LLVM --system-libs as bare -l flags (e.g. ["-lz", "-lzstd"]). Used as the
# linkopts of the DEFAULT :llvm_system_libs target, which resolves them from the
# host. A hermetic consumer (no host system libs, e.g. remote execution) swaps
# that target for a cc_library that ships the .so files directly.
def llvm_system_libs():
    return LLVM_SYSTEM_LIBS

_LLVM_RLOC = repo_rloc("@llvm")

# clang-repl auto-detects its resource dir from the host binary's location,
# which fails under the test sandbox (the binary isn't beside lib/clang/<v>).
# Point it at @llvm's runfiles so the JIT finds stddef.h etc. Major version
# from LLVM_VERSION ("22.1.8" -> "22").
_LLVM_MAJOR = LLVM_VERSION.split(".")[0]

# The in-process interpreter finds headers at JIT time via CPLUS_INCLUDE_PATH
# (the devsetup CMake flow relies on the same). Include the clang builtins dir
# (lib/clang/<v>/include -> stddef.h etc.) plus every LLVM/Clang header root
# (@llvm exposes each under its own runfiles dir, LLVM_INCLUDE_DIRS). We do NOT
# pass -resource-dir via the interpreter args: doing so crashes the backend's
# interpreter in early lexing; letting it auto-detect the resource dir while
# CPLUS_INCLUDE_PATH supplies the builtins works for both the C++ and py stacks.
_CPLUS_INCLUDE_PATH = ":".join(
    [_LLVM_RLOC + "/lib/clang/" + _LLVM_MAJOR + "/include"] +
    [_LLVM_RLOC + "/" + d for d in LLVM_INCLUDE_DIRS],
)

CPPINTEROP_BASE_ENV = {
    "CLING_STANDARD_PCH": "none",
    "LLVM_LIB_PATH": _LLVM_RLOC + "/lib",
    "LD_LIBRARY_PATH": _LLVM_RLOC + "/lib:" +
                       repo_rloc("@cppinterop") + "/lib:" +
                       repo_rloc("@cppyy_backend") + "/python/cppyy_backend/lib",
    "CPLUS_INCLUDE_PATH": _CPLUS_INCLUDE_PATH,
}
