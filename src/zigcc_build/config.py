from typing import List, TypedDict

class ZigCcConfig(TypedDict):
    """
    Configuration object for zigcc-build.
    
    Attributes:
        sources: List of source files to compile (e.g. ["src/main.c"]).
        include_dirs: List of include directories (e.g. ["include"]).
        defines: List of compiler macros (e.g. ["DEBUG", "VERSION=1"]).
        library_dirs: List of library directories (e.g. ["libs"]).
        libraries: List of libraries to link against (e.g. ["m", "user32"]).
        module_name: The name of the extension module to generate.
    """
    sources: List[str]
    include_dirs: List[str]
    defines: List[str]
    library_dirs: List[str]
    libraries: List[str]
    module_name: str
    packages: List[str] # List of python packages to include (e.g. ["mypackage"])
