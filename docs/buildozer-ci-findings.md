# Buildozer CI findings

## Sources

1. Buildozer installation documentation: https://buildozer.readthedocs.io/en/latest/installation/
2. python-for-android recipes documentation: https://python-for-android.readthedocs.io/en/latest/recipes.html
3. Buildozer specifications documentation: https://buildozer.readthedocs.io/en/latest/specifications/

## Findings

- Buildozer documentation for Ubuntu 24.04 recommends Java 17, system packages including autoconf/libtool/pkg-config/libffi-dev/libssl-dev/automake/autopoint/gettext, and a virtual environment.
- The documented p4a master path is appropriate for Python versions through 3.12; the develop path is associated with Python 3.14 and requires additional configuration.
- python-for-android requires a recipe for Python packages containing compiled components; pure-Python modules are installed through pip, while compiled modules need an Android-compatible recipe or source build.
- Buildozer source.dir must contain main.py; source.include_exts and source.exclude_dirs control files copied into the Android project.
- CloakChat's Android build log showed cryptography being compiled for Android and a transient HTTP 502 while downloading freetype. The CI workflow therefore pins Cython, selects p4a master, accepts SDK licenses non-interactively, caches Buildozer toolchains, and retries the Buildozer command.
