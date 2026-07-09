# Runtime path resolution: the ${ORIGIN} token

The stack self-locates its own resources (backend solib, bundled CppInterOp,
CPyCppyy headers) relative to its load path — see staging.bzl for how the
Bazel tree recreates the wheel layout that makes this work. The only paths a
consumer must supply are its *own* toolchain args (e.g. --gcc-toolchain) in
CPPINTEROP_EXTRA_INTERPRETER_ARGS.

No installer knows its final absolute prefix at build time, and relative paths
break as soon as the process runs from a different cwd (a notebook kernel, a
tool run from $HOME). Args may therefore reference `${ORIGIN}` — the directory
of libcppyy-backend.so itself, mirroring ELF rpath $ORIGIN semantics —
expanded by cppyy-backend at interpreter startup, independent of cwd.
Unresolvable tokens pass through verbatim so the interpreter reports them.

Bazel consumers: the solib dir sits four levels below the runfiles root, so
sibling repos resolve via ORIGIN_RUNFILES_ROOT (defs.bzl), e.g.
`"--gcc-toolchain=" + ORIGIN_RUNFILES_ROOT + "/" + repo_name("@gcc")`.
The expanded args carry literal `..` components; clang handles them fine.
