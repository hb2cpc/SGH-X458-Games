"""Trim Chaquopy's Python runtime down to what the games import.

Each command edits one Chaquopy task's output directory in place:

    slim_python.py runtime <misc assets> <merged Python sources>
    slim_python.py app <source assets>
    slim_python.py native <jniLibs> <Android SDK> <min SDK>
"""

import subprocess
import sys
import zipfile
from importlib.util import MAGIC_NUMBER
from inspect import CO_OPTIMIZED
from modulefinder import ModuleFinder
from pathlib import Path
from tempfile import TemporaryDirectory
from types import CodeType


# Only reachable through Chaquopy's on-import hooks, pkg_resources, or `if __name__ == "__main__"`
# blocks. The build fails if game code starts importing one of these.
REMOVED = {"doctest", "email", "multiprocessing", "pdb", "pkg_resources", "plistlib", "ssl", "unittest"}
# Imported by name at run time, or from Chaquopy's compiled module, where the scan can't see them.
REQUIRED = [
    "collections", "copy", "importlib", "io", "keyword", "os", "pickle", "platform", "re", "shutil",
    "site", "string", "struct", "sysconfig", "threading", "traceback", "types", "warnings", "weakref",
    "zipfile",
    *("encodings." + codec for codec in (
        "aliases", "ascii", "cp437", "latin_1", "raw_unicode_escape", "unicode_escape",
        "utf_16", "utf_16_be", "utf_16_le", "utf_32", "utf_8", "utf_8_sig")),
]
# hashlib uses these once OpenSSL is gone, and fails to import without them.
NATIVE_REQUIRED = {"_blake2", "_md5", "_sha1", "_sha3"}
# The games never open a network connection or a database, so these become empty libraries.
UNUSED_LIBRARIES = ("crypto_python", "ssl_python", "sqlite3_python")
NATIVE_REMOVED = {"_hashlib", "_sqlite3", "_ssl"}
TRIPLES = {"arm64-v8a": "aarch64-linux-android", "armeabi-v7a": "armv7a-linux-androideabi",
           "x86": "i686-linux-android", "x86_64": "x86_64-linux-android"}


class ImportScan(ModuleFinder):
    """Follow every import in our code, but only module-level imports inside the standard library."""

    def __init__(self, path, stdlib):
        super().__init__(path=[str(entry) for entry in path])
        self.stdlib = stdlib

    def find_module(self, name, path, parent=None):
        if (parent.__name__ if parent else name).split(".")[0] in REMOVED:
            raise ImportError(name)
        return super().find_module(name, path, parent)

    def scan_code(self, co, m):
        if m.__file__ and Path(m.__file__).is_relative_to(self.stdlib):
            # Function bodies are optional code paths; class bodies run on import.
            co = co.replace(co_consts=tuple(
                None if isinstance(const, CodeType) and const.co_flags & CO_OPTIMIZED else const
                for const in co.co_consts))
        super().scan_code(co, m)


def module_names(root, suffix):
    for path in sorted(root.rglob("*" + suffix)):
        parts = list(path.relative_to(root).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        if parts:
            yield ".".join(parts)


def rewrite(archive, keep):
    """Rebuild a Chaquopy asset zip with only the entries `keep` accepts."""
    with zipfile.ZipFile(archive) as source:
        entries = [(info.filename, source.read(info)) for info in source.infolist()
                   if not info.is_dir() and keep(info.filename)]
    before = archive.stat().st_size
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        folders = set()
        for name, data in entries:
            for parent in reversed(Path(name).parents[:-1]):
                if parent not in folders:
                    folders.add(parent)
                    target.writestr(zipfile.ZipInfo(parent.as_posix() + "/"), b"")
            target.writestr(zipfile.ZipInfo(name), data, zipfile.ZIP_DEFLATED, 9)
    print(f"{archive.name}: {before:,} -> {archive.stat().st_size:,} bytes")


def slim_runtime(assets, sources):
    chaquopy = assets / "chaquopy"
    (chaquopy / "cacert.pem").write_bytes(b"")  # Chaquopy insists on the file; nothing reads it.
    with TemporaryDirectory() as scratch:
        stdlib, bootstrap = Path(scratch, "stdlib"), Path(scratch, "bootstrap")
        zipfile.ZipFile(chaquopy / "stdlib-common.imy").extractall(stdlib)
        zipfile.ZipFile(chaquopy / "bootstrap.imy").extractall(bootstrap)
        if (stdlib / "os.pyc").read_bytes()[:4] != MAGIC_NUMBER:
            print("warning: the build Python doesn't match the app's Python, so the standard library "
                  "was left untrimmed", file=sys.stderr)
            return
        scan = ImportScan([sources, bootstrap, stdlib], stdlib)
        chaquopy_modules = (f"java.{name}" for name in module_names(bootstrap / "java", ".pyc")
                            if "_vendor" not in name)
        for name in (*module_names(sources, ".py"), *REQUIRED, "java", *chaquopy_modules):
            scan.import_hook(name)

        for missing, importers in scan.badmodules.items():
            ours = [name for name in importers
                    if name in scan.modules and Path(scan.modules[name].__file__).is_relative_to(sources)]
            if missing.split(".")[0] in REMOVED and ours:
                raise SystemExit(f"{', '.join(ours)} imports {missing}, which slim_python.py removes. "
                                 "Take it out of REMOVED.")

        used = {Path(module.__file__).resolve() for module in scan.modules.values() if module.__file__}
        used.update(stdlib.resolve().glob("_sysconfigdata*.pyc"))
        # Extension modules show up as missing, or as built in when the build Python has them too.
        native = {name for name, module in scan.modules.items() if not module.__file__}
        native = (native | set(scan.badmodules) | NATIVE_REQUIRED) - NATIVE_REMOVED

        rewrite(chaquopy / "stdlib-common.imy", lambda name: (stdlib / name).resolve() in used)
        rewrite(chaquopy / "bootstrap.imy", lambda name: (bootstrap / name).resolve() in used)
        for archive in chaquopy.glob("stdlib-*.imy"):
            if archive.name != "stdlib-common.imy":
                rewrite(archive, lambda name: name.split(".")[0] in native)


def slim_app(assets):
    archive = assets / "chaquopy" / "app.imy"
    with zipfile.ZipFile(archive) as source:
        names = set(source.namelist())
    # Chaquopy keeps the source of extracted packages next to the bytecode it runs.
    rewrite(archive, lambda name: not (name.endswith(".py") and name + "c" in names))


def stub_libraries(libraries, sdk, min_sdk):
    compilers = sorted((path for path in sdk.glob("ndk/*/toolchains/llvm/prebuilt/*/bin/clang*")
                        if path.stem == "clang"),
                       key=lambda path: [int(part) for part in path.parts[-7].split(".") if part.isdigit()])
    if not compilers:
        print("warning: no Android NDK is installed, so the unused OpenSSL and SQLite libraries "
              "stay in the APK", file=sys.stderr)
        return
    with TemporaryDirectory() as scratch:
        empty = Path(scratch, "empty.c")
        empty.write_text("")
        for folder in libraries.iterdir():
            for library in UNUSED_LIBRARIES:
                target = folder / f"lib{library}.so"
                if target.exists():
                    subprocess.run([compilers[-1], f"--target={TRIPLES[folder.name]}{min_sdk}", "-shared",
                                    "-nostdlib", f"-Wl,-soname,{target.name}", "-Wl,-z,max-page-size=16384",
                                    "-o", target, empty], check=True)


if __name__ == "__main__":
    command, *paths = sys.argv[1:]
    if command == "runtime":
        slim_runtime(Path(paths[0]), Path(paths[1]))
    elif command == "app":
        slim_app(Path(paths[0]))
    elif command == "native":
        stub_libraries(Path(paths[0]), Path(paths[1]), paths[2])
    else:
        raise SystemExit(__doc__)
