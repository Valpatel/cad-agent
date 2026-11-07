**Fixed**

- FEA installs select Intel PARDISO only on x86-64 Linux and Windows; macOS and other architectures keep the
  existing SciPy/pyamg fallback. The updater evaluates platform markers when retaining installed extras, using
  the standard `packaging` parser. Linux ARM still needs the documented external Gmsh setup; a metadata fix does
  not create a missing upstream wheel. Projects need no source changes; reinstall to use the corrected metadata.
