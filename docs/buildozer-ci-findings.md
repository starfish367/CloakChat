# Buildozer CI findings

## Sources

1. Buildozer installation documentation: https://buildozer.readthedocs.io/en/latest/installation/
2. python-for-android recipes documentation: https://python-for-android.readthedocs.io/en/latest/recipes.html
3. Buildozer specifications documentation: https://buildozer.readthedocs.io/en/latest/specifications/
4. python-for-android changelog: https://github.com/kivy/python-for-android/blob/develop/CHANGELOG.md

## Findings

- Buildozer documentation for Ubuntu 24.04 recommends Java 17, system packages including autoconf/libtool/pkg-config/libffi-dev/libssl-dev/automake/autopoint/gettext, and a virtual environment.
- Buildozer requires `p4a.local_recipes` in the `[app]` section when a project overrides a python-for-android recipe. The setting is now placed correctly in `buildozer.spec`.
- python-for-android requires a recipe for Python packages containing compiled components; pure-Python modules are installed through pip, while compiled modules need an Android-compatible recipe or source build.
- Buildozer `source.dir` must contain `main.py`; `source.include_exts` and `source.exclude_dirs` control files copied into the Android project.
- The Android build initially failed when the FreeType archive was downloaded from Savannah with HTTP 502. CloakChat now uses a local FreeType recipe and a direct SourceForge mirror whose URL has a stable archive basename.
- The subsequent Android run confirmed that the local recipe was loaded, then failed while compiling `cryptography-cffi` for `armeabi-v7a`: p4a master selected Python 3.14.2 and the C compiler reported `LONG_BIT definition appears wrong for platform`. The CI therefore pins p4a to the stable `v2024.01.21` tag, whose Python recipe is 3.11.5 and whose cryptography recipe is an Android-oriented recipe rather than the current Python 3.14 Rust build.
- The workflow pins Cython, accepts SDK licenses non-interactively, caches Buildozer toolchains, retries the Buildozer command, prevents stale runs with concurrency cancellation, and applies finite job timeouts. A successful APK claim still requires the Android artifact upload step to pass.
