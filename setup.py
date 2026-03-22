"""Build configuration for Cython extensions."""

from Cython.Build import cythonize
from setuptools import setup

setup(
    ext_modules=cythonize(
        "src/jetsocket/_core.pyx",
        compiler_directives={
            "language_level": 3,
            "boundscheck": False,
            "wraparound": False,
        },
    ),
)
