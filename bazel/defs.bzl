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

# repo_loc / repo_rloc build paths to a dependency repo for use at build time
# (execroot-relative, e.g. -I) and at test runtime (runfiles-relative). They
# assume the referenced repo is EXTERNAL to the target consuming the path.
#
# That assumption breaks when a repo references ITSELF -- e.g. CppInterOp's own
# unit tests pointing at @cppinterop. As an external dep (nebula) the repo's
# canonical name is "<name>+" and the path is "external/<name>+" / "../<name>+".
# But when that same repo is the MAIN repo (its own standalone build) its files
# live at the execroot/runfiles root, NOT under external/<name>+ (which does not
# exist there). Detect the self-reference and emit the main-repo form (".").
#
# native.repository_name() reports only the CURRENT repo, and as "@" (-> "") when
# it is the main repo -- it never reveals another repo's canonical name. So we
# can't compare canonicals directly. Instead the caller, which knows it is in a
# standalone main-repo build, passes `is_self = True` for the one reference that
# points at its own module. When building as an external dep, is_self stays False
# and the normal "<name>+" path is used.
def repo_loc(repo, is_self = False):
    # Main repo's files are at the execroot root (".").
    return "." if is_self else "external/" + repo_name(repo)

def repo_rloc(repo, is_self = False):
    # Main repo's files are at the runfiles root, which is the test's cwd (".").
    return "." if is_self else "../" + repo_name(repo)

# ${ORIGIN} is expanded by cppyy-backend at startup to the directory of
# libcppyy-backend.so itself (ELF-$ORIGIN semantics -- no build-system content
# in the runtime code). Under Bazel that directory is always
# <runfiles root>/<repo>/python/cppyy_backend/lib (fixed by the solib's
# shared_lib_name), so four ups reach the runfiles root where sibling repos
# live. Consumers join this with repo_name() to write cwd-independent
# interpreter args:  ORIGIN_RUNFILES_ROOT + "/" + repo_name("@gcc") + "/..."
# See ORIGIN.md for the full contract.
ORIGIN_RUNFILES_ROOT = "${ORIGIN}/../../../.."

# True when building this module standalone (it is the main repo, repository_name()
# == "@"); used by a module's own BUILD/macros to mark a self-reference for
# repo_loc/repo_rloc. False when the module is an external dependency.
def is_main_repo(current_repo):
    return current_repo.lstrip("@") == ""

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

# LTO codegen optimization level for the bitcode-archive link is NOT a perf
# nicety -- it governs the STACK FRAME SIZE of clang's own code inside
# libclangCppInterOp.so. At O0 every local is spilled and nothing inlines, so
# clang's deeply-recursive constexpr evaluator (EvaluateStmt -> HandleFunctionCall
# -> Evaluate, exercised at JIT time by every cppdef) gets fat frames and blows
# the default 8 MiB stack on heavily-templated code (e.g. Fastor models) that an
# optimized build evaluates fine. The level is a per-consumer build setting (see
# the :lto_opt_level string_flag in CppInterOp/BUILD.bazel) rather than baked in
# here, because it is a link-time/runtime-robustness tradeoff: O0 keeps the
# standalone/upstream link fast (seconds), while a consumer that JIT-compiles
# heavy templates against an LTO @llvm tree (e.g. nebula) raises it via
#   --@cppinterop//:lto_opt_level=2
# to get the tight frames of a normal optimized build.
LTO_OPT_LEVELS = ["0", "1", "2", "3"]

# Upstream default: fast link. Insufficient for heavy JIT use; see above.
DEFAULT_LTO_OPT_LEVEL = "0"

def llvm_lto_opt_linkopts(level):
    """The -plugin-opt=O<level> flag for the LTO link, or [] for a non-LTO @llvm.

    Selected per build via the :lto_opt_level flag; emitted only when @llvm
    carries IR bitcode (LLVM_GOLD_PLUGIN set), where the level actually drives
    codegen. On a non-LTO tree the static link ignores it, so emit nothing.
    """
    if LLVM_GOLD_PLUGIN:
        return ["-Wl,-plugin-opt=O" + level]
    return []

# When the LLVM archives carry IR bitcode (an LTO-built tree, e.g. nebula's),
# the linker needs the LLVM plugin to read them; LLVM_GOLD_PLUGIN is the repo's
# LLVMgold.so path, or empty for a non-LTO tree (then this is a no-op).
# jobs=<n> keeps the implicit LTO codegen parallel (without it the link does
# serial codegen of all of LLVM -- minutes). The -plugin-opt=O<n> level is NOT
# here: it is appended at the link via select() on :lto_opt_level.
def _llvm_plugin():
    if LLVM_GOLD_PLUGIN:
        return [
            "-Wl,--plugin=" + repo_loc("@llvm") + "/" + LLVM_GOLD_PLUGIN,
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
        "-Wl,--gc-sections",
        "-Wl,--start-group",
    ] + ["-l" + n for n in CLANG_LIB_NAMES] + \
        ["-l" + n for n in LLVM_LIB_NAMES] + [
        "-Wl,--end-group",
        "-ldl",
    ]

# For standalone LLVM tools (cppinterop-tblgen): the static component libs.
# libclang-cpp.so omits TableGen and some cl:: internals, so a tool using
# llvm::TableGen / RecordKeeper must link the components statically.
# tblgen does not run the JIT, so it always uses the fast default LTO level (no
# need for the per-consumer :lto_opt_level the solib carries).
def llvm_tblgen_linkopts():
    return _llvm_L_rpath() + _llvm_plugin() + \
           llvm_lto_opt_linkopts(DEFAULT_LTO_OPT_LEVEL) + \
           ["-l" + n for n in LLVM_LIB_NAMES]

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

# Runtime env for the cppinterop unit tests. A function (not a constant) so the
# @cppinterop runfiles path self-corrects when cppinterop is its own main repo
# (standalone): the caller passes cppinterop_is_self = is_main_repo(
# native.repository_name()). @cppyy_backend and @llvm are always external to
# cppinterop, so their paths never need the fixup.
def cppinterop_base_env(cppinterop_is_self = False):
    return {
        "CLING_STANDARD_PCH": "none",
        "LLVM_LIB_PATH": _LLVM_RLOC + "/lib",
        "LD_LIBRARY_PATH": _LLVM_RLOC + "/lib:" +
                           repo_rloc("@cppinterop", cppinterop_is_self) + "/lib:" +
                           repo_rloc("@cppyy_backend") +
                           "/python/cppyy_backend/lib",
        "CPLUS_INCLUDE_PATH": _CPLUS_INCLUDE_PATH,
    }

# Make-variable carrier for the consumer-supplied JIT interpreter args. The JIT
# tests' in-process clang-repl needs C++ toolchain args (--gcc-toolchain /
# -stdlib++-isystem) at RUN time; standalone they're empty (clang-repl
# autodetects the host gcc/clang). A consumer with no host toolchain instead
# computes them from its own repo layout -- the paths must be runfiles-relative
# and so can only be formed in a .bzl that can resolve repo locations, NOT in
# static MODULE.bazel/.bazelrc text. This rule exposes the precomputed string as
# the CPPINTEROP_JIT_CXX_ARGS make-var; the test macros reference it via $(...)
# in the env, and a label_flag lets a consumer swap the empty default for its own
# instance (paired with the :jit_cxx_data files flag). See _jit_cxx_env in
# rules.bzl and the :jit_cxx_interp_args label_flag in the module BUILDs.
def _jit_cxx_interp_args_impl(ctx):
    return [platform_common.TemplateVariableInfo({
        "CPPINTEROP_JIT_CXX_ARGS": ctx.attr.args,
    })]

jit_cxx_interp_args = rule(
    implementation = _jit_cxx_interp_args_impl,
    attrs = {
        "args": attr.string(
            doc = "Space-joined interpreter args, exposed as the " +
                  "CPPINTEROP_JIT_CXX_ARGS make-var. Empty by default (host).",
        ),
    },
)
