"""A PEP 517 build backend using zig cc."""

import os
import sys
import subprocess
import tarfile
import zipfile
import sysconfig
import importlib.util
import hashlib
import base64
import platform
from typing import List, TypedDict
from packaging import tags

__version__ = "0.2.4"


class ZigCcConfig(TypedDict):
    """
    Configuration object for zigcc-build.

    Attributes:
        sources: List of source files to compile (e.g. ["src/main.c"]).
        include_dirs: List of include directories (e.g. ["include"]).
        defines: List of compiler macros (e.g. ["DEBUG", "VERSION=1"]).
    cflags: List of compiler flags (e.g. ["-O3", "-Wall"]).
    library_dirs: List of library directories (e.g. ["libs"]).
    libraries: List of libraries to link against (e.g. ["m", "user32"]).
    module_name: The name of the extension module to generate.
    """

    sources: List[str]
    include_dirs: List[str]
    defines: List[str]
    cflags: List[str]
    library_dirs: List[str]
    libraries: List[str]
    module_name: str
    packages: List[str]  # List of python packages to include (e.g. ["mypackage"])


# Compatibility for toml parsing
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        # Fallback or error if tomli is missing on < 3.11
        raise ImportError("tomli is required for python < 3.11")


def _get_project_config():
    with open("pyproject.toml", "rb") as f:
        return tomllib.load(f)


def get_requires_for_build_wheel(config_settings=None):
    return []


def get_requires_for_build_sdist(config_settings=None):
    return []


def get_requires_for_build_editable(config_settings=None):
    """PEP 660: Return build requirements for editable installs."""
    return []


def _get_platform_info():
    """Get platform-specific information for wheel building."""
    # Use packaging.tags for proper platform tag generation
    # This handles CPython, PyPy, manylinux, macOS universal2, etc.
    tag = next(tags.sys_tags())

    # Extract components from the tag
    impl = tag.interpreter
    abi = tag.abi
    plat = tag.platform

    # Extract Python version from interpreter tag (e.g., "cp311" -> "311")
    if impl.startswith("cp"):
        pyver = impl[2:]  # Strip "cp" prefix
    elif impl.startswith("pp"):
        pyver = impl[2:]  # PyPy: "pp39" -> "39"
    else:
        pyver = f"{sys.version_info.major}{sys.version_info.minor}"

    # Detect OS and extension suffix
    system = platform.system().lower()
    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")

    if not ext_suffix:
        # Fallback if EXT_SUFFIX is not available
        if system == "windows":
            ext_suffix = ".pyd"
        else:
            ext_suffix = ".so"

    return {
        "impl": impl,
        "pyver": pyver,
        "abi": abi,
        "plat": plat,
        "ext_suffix": ext_suffix,
        "system": system,
    }


def _prepare_build_config(tool_config, safe_name):
    """Prepare and configure the build configuration."""
    build_config: ZigCcConfig = {
        "sources": tool_config.get("sources", []),
        "include_dirs": tool_config.get("include-dirs", []),
        "defines": tool_config.get("defines", []),
        "cflags": tool_config.get("cflags", []),
        "library_dirs": tool_config.get("library-dirs", []),
        "libraries": tool_config.get("libraries", []),
        "module_name": tool_config.get("module-name", safe_name),
        "packages": tool_config.get("packages", []),
    }

    # Run configurer script if present
    configurer_script = tool_config.get("configurer-script")
    if configurer_script:
        print(f"Running configurer script: {configurer_script}")
        spec = importlib.util.spec_from_file_location(
            "zigcc_configurer", configurer_script
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules["zigcc_configurer"] = module
            spec.loader.exec_module(module)

            if hasattr(module, "configure"):
                module.configure(build_config)
            else:
                print(
                    f"Warning: {configurer_script} does not have a 'configure' function."
                )
        else:
            print(f"Error: Could not load {configurer_script}")

    return build_config


def _compile_extension(build_config, platform_info):
    """Compile extension module and return the output filename."""
    sources = build_config["sources"]
    if not sources:
        return None

    include_dirs = build_config["include_dirs"]
    defines = build_config["defines"]
    cflags = build_config["cflags"]
    library_dirs = build_config["library_dirs"]
    libraries = build_config["libraries"]
    ext_name = build_config["module_name"]
    ext_suffix = platform_info["ext_suffix"]
    system = platform_info["system"]
    pyver = platform_info["pyver"]

    # Compile using zig cc
    output_filename = f"{ext_name}{ext_suffix}"

    # Build command
    cmd = [sys.executable, "-m", "ziglang", "cc", "-shared", "-o", output_filename]

    # Add python include path
    py_include = sysconfig.get_path("include")
    cmd.extend(["-I", py_include])

    # Add user include dirs
    for inc in include_dirs:
        cmd.extend(["-I", inc])

    # Add user library dirs
    for lib_dir in library_dirs:
        cmd.extend([f"-L{lib_dir}"])

    # Add macros/defines
    for define in defines:
        cmd.extend([f"-D{define}"])

    # Add cflags
    cmd.extend(cflags)

    # Add sources
    cmd.extend(sources)

    # Add user libraries
    for lib in libraries:
        cmd.extend([f"-l{lib}"])

    # On Windows, we might need to link against python lib
    if system == "windows":
        # Find python library
        py_lib_dir = sysconfig.get_config_var("LIBDIR") or sysconfig.get_path("stdlib")
        base = sys.base_prefix
        libs_dir = os.path.join(base, "libs")
        if os.path.exists(libs_dir):
            cmd.extend([f"-L{libs_dir}", f"-lpython{pyver}"])
    
    # On macOS, use undefined dynamic lookup for Python symbols
    # They will be resolved at runtime when the module is imported
    elif system == "darwin":
        cmd.extend(["-undefined", "dynamic_lookup"])

    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd)

    return output_filename


def _discover_packages(build_config):
    """Discover Python packages to include in the wheel."""
    packages = build_config.get("packages", [])
    package_dir = "."

    # Auto-discovery if no packages specified
    if not packages:
        if os.path.exists("src") and os.path.isdir("src"):
            # Check if src contains packages
            found_packages = []
            for item in os.listdir("src"):
                item_path = os.path.join("src", item)
                if os.path.isdir(item_path) and os.path.exists(
                    os.path.join(item_path, "__init__.py")
                ):
                    found_packages.append(item)

            if found_packages:
                package_dir = "src"
                packages = found_packages

        if not packages:
            # Check current directory
            for item in os.listdir("."):
                if item in [
                    ".git",
                    ".venv",
                    "dist",
                    "build",
                    "__pycache__",
                    "zigcc_build.egg-info",
                    "demo-project",
                ]:
                    continue
                if os.path.isdir(item) and os.path.exists(
                    os.path.join(item, "__init__.py")
                ):
                    packages.append(item)

    return packages, package_dir


def _generate_metadata(project_config):
    """Generate PKG-INFO/METADATA content from PEP 621 project config."""
    lines = []
    
    # Required fields
    lines.append("Metadata-Version: 2.1")
    lines.append(f"Name: {project_config.get('name', 'unknown')}")
    lines.append(f"Version: {project_config.get('version', '0.0.0')}")
    
    # Summary/Description (single line)
    description = project_config.get("description", "")
    if description:
        lines.append(f"Summary: {description}")
    
    # Home-page (deprecated but still used)
    urls = project_config.get("urls", {})
    if "Homepage" in urls:
        lines.append(f"Home-page: {urls['Homepage']}")
    
    # Author and Author-Email
    authors = project_config.get("authors", [])
    if authors:
        author_names = [a.get("name", "") for a in authors if "name" in a]
        author_emails = [a.get("email", "") for a in authors if "email" in a]
        
        if author_names:
            lines.append(f"Author: {', '.join(author_names)}")
        if author_emails:
            lines.append(f"Author-Email: {', '.join(author_emails)}")
    
    # Maintainer and Maintainer-Email
    maintainers = project_config.get("maintainers", [])
    if maintainers:
        maintainer_names = [m.get("name", "") for m in maintainers if "name" in m]
        maintainer_emails = [m.get("email", "") for m in maintainers if "email" in m]
        
        if maintainer_names:
            lines.append(f"Maintainer: {', '.join(maintainer_names)}")
        if maintainer_emails:
            lines.append(f"Maintainer-Email: {', '.join(maintainer_emails)}")
    
    # License
    license_info = project_config.get("license", {})
    if isinstance(license_info, dict):
        if "text" in license_info:
            lines.append(f"License: {license_info['text']}")
        elif "file" in license_info:
            # Read license from file
            try:
                with open(license_info["file"], "r", encoding="utf-8") as f:
                    license_text = f.read().strip()
                    lines.append(f"License: {license_text}")
            except Exception:
                pass
    elif isinstance(license_info, str):
        lines.append(f"License: {license_info}")
    
    # Project-URL (for additional URLs)
    for name, url in urls.items():
        if name != "Homepage":  # Already added as Home-page
            lines.append(f"Project-URL: {name}, {url}")
    
    # Keywords
    keywords = project_config.get("keywords", [])
    if keywords:
        if isinstance(keywords, list):
            lines.append(f"Keywords: {','.join(keywords)}")
        else:
            lines.append(f"Keywords: {keywords}")
    
    # Classifiers
    classifiers = project_config.get("classifiers", [])
    for classifier in classifiers:
        lines.append(f"Classifier: {classifier}")
    
    # Requires-Python
    requires_python = project_config.get("requires-python")
    if requires_python:
        lines.append(f"Requires-Python: {requires_python}")
    
    # Dependencies (Requires-Dist)
    dependencies = project_config.get("dependencies", [])
    for dep in dependencies:
        lines.append(f"Requires-Dist: {dep}")
    
    # Optional dependencies
    optional_deps = project_config.get("optional-dependencies", {})
    for extra_name, extra_deps in optional_deps.items():
        lines.append(f"Provides-Extra: {extra_name}")
        for dep in extra_deps:
            lines.append(f"Requires-Dist: {dep}; extra == '{extra_name}'")
    
    # Description-Content-Type and Description (long description from readme)
    readme = project_config.get("readme")
    if readme:
        readme_path = None
        content_type = "text/plain"
        
        if isinstance(readme, str):
            readme_path = readme
            # Infer content type from extension
            if readme.endswith(".md"):
                content_type = "text/markdown"
            elif readme.endswith(".rst"):
                content_type = "text/x-rst"
        elif isinstance(readme, dict):
            readme_path = readme.get("file")
            content_type = readme.get("content-type", content_type)
        
        if readme_path and os.path.exists(readme_path):
            lines.append(f"Description-Content-Type: {content_type}")
            lines.append("")  # Blank line before description body
            try:
                with open(readme_path, "r", encoding="utf-8") as f:
                    lines.append(f.read())
            except Exception:
                pass
    
    return "\n".join(lines) + "\n"


def _build_wheel_impl(
    wheel_directory, config_settings=None, metadata_directory=None, editable=False
):
    """Common wheel building implementation for both regular and editable wheels."""
    config = _get_project_config()
    project_config = config.get("project", {})
    tool_config = config.get("tool", {}).get("zigcc-build", {})

    name = project_config.get("name", "unknown")
    version = project_config.get("version", "0.0.0")
    safe_name = name.replace("-", "_")

    platform_info = _get_platform_info()
    impl = platform_info["impl"]
    pyver = platform_info["pyver"]
    abi = platform_info["abi"]
    plat = platform_info["plat"]

    wheel_filename = f"{safe_name}-{version}-{impl}-{abi}-{plat}.whl"
    wheel_path = os.path.join(wheel_directory, wheel_filename)

    print(f"Building {'editable ' if editable else ''}wheel: {wheel_path}")

    # Helper to write file and track for RECORD
    record_rows = []

    def write_file_to_zip(zf, path, arcname):
        zf.write(path, arcname=arcname)
        with open(path, "rb") as f:
            data = f.read()
        digest = hashlib.sha256(data).digest()
        hash_str = "sha256=" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip(
            "="
        )
        record_rows.append(f"{arcname},{hash_str},{len(data)}")

    def write_str_to_zip(zf, arcname, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        zf.writestr(arcname, data)
        digest = hashlib.sha256(data).digest()
        hash_str = "sha256=" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip(
            "="
        )
        record_rows.append(f"{arcname},{hash_str},{len(data)}")

    # Create the wheel zip
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Compile and add extension modules
        build_config = _prepare_build_config(tool_config, safe_name)

        output_filename = _compile_extension(build_config, platform_info)
        if output_filename:
            # Calculate correct arcname for dotted module names
            module_name = build_config["module_name"]
            if "." in module_name:
                ext_suffix = platform_info["ext_suffix"]
                # Replace dots with slashes for the directory structure
                # And ensure we append the suffix correctly
                target_path = module_name.replace(".", "/") + ext_suffix
                arcname = target_path
            else:
                arcname = output_filename

            # Add the compiled extension to the wheel
            write_file_to_zip(zf, output_filename, arcname=arcname)

            # Cleanup artifact
            if os.path.exists(output_filename):
                os.remove(output_filename)

        # 2. Add pure python sources or editable .pth file
        packages, package_dir = _discover_packages(build_config)

        if editable:
            # PEP 660: Create a .pth file pointing to the source directory
            # This allows the package to be imported from its source location
            pth_name = f"__{safe_name}__path__.pth"
            source_path = os.path.abspath(package_dir)
            write_str_to_zip(zf, pth_name, source_path + "\n")
        else:
            # Regular wheel: copy all package files
            if packages:
                print(f"Including packages from {package_dir}: {packages}")
                for package in packages:
                    src_path = os.path.join(package_dir, package)
                    if not os.path.exists(src_path):
                        print(f"Warning: Package {package} not found in {package_dir}")
                        continue

                    for root, _, files in os.walk(src_path):
                        for file in files:
                            if file.endswith(".pyc") or file == "__pycache__":
                                continue
                            abs_file = os.path.join(root, file)
                            # Calculate arcname relative to package_dir
                            # e.g. src/mypkg/init.py -> mypkg/init.py
                            rel_path = os.path.relpath(abs_file, package_dir)
                            write_file_to_zip(zf, abs_file, arcname=rel_path)

        # 3. Write Metadata
        dist_info_dir = f"{safe_name}-{version}.dist-info"

        # METADATA - Generate full PEP 621 compliant metadata
        metadata_content = _generate_metadata(project_config)
        write_str_to_zip(zf, f"{dist_info_dir}/METADATA", metadata_content)

        # WHEEL
        wheel_content = f"""Wheel-Version: 1.0
Generator: zigcc-build-backend
Root-Is-Purelib: false
Tag: {impl}-{abi}-{plat}
"""
        write_str_to_zip(zf, f"{dist_info_dir}/WHEEL", wheel_content)

        # RECORD
        record_rows.append(f"{dist_info_dir}/RECORD,,")
        record_content = "\n".join(record_rows) + "\n"
        zf.writestr(f"{dist_info_dir}/RECORD", record_content)

    return wheel_filename


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    """Build a regular wheel."""
    return _build_wheel_impl(
        wheel_directory, config_settings, metadata_directory, editable=False
    )


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    """PEP 660: Build an editable wheel using .pth files."""
    return _build_wheel_impl(
        wheel_directory, config_settings, metadata_directory, editable=True
    )


def build_sdist(sdist_directory, config_settings=None):
    config = _get_project_config()
    project_config = config.get("project", {})
    name = project_config.get("name", "unknown")
    version = project_config.get("version", "0.0.0")
    safe_name = name.replace("-", "_")

    sdist_filename = f"{safe_name}-{version}.tar.gz"
    sdist_path = os.path.join(sdist_directory, sdist_filename)

    # Create PKG-INFO content
    pkg_info_content = _generate_metadata(project_config)

    with tarfile.open(sdist_path, "w:gz") as tf:
        # Add PKG-INFO file first
        import io
        pkg_info_bytes = pkg_info_content.encode("utf-8")
        pkg_info_tarinfo = tarfile.TarInfo(name=f"{safe_name}-{version}/PKG-INFO")
        pkg_info_tarinfo.size = len(pkg_info_bytes)
        pkg_info_tarinfo.mode = 0o644
        tf.addfile(pkg_info_tarinfo, io.BytesIO(pkg_info_bytes))
        
        # Add all files in current directory recursively, excluding venv/git etc.
        for root, dirs, files in os.walk("."):
            if ".git" in dirs:
                dirs.remove(".git")
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            if "dist" in dirs:
                dirs.remove("dist")
            if ".venv" in dirs:
                dirs.remove(".venv")
            if "build" in dirs:
                dirs.remove("build")

            for file in files:
                file_path = os.path.join(root, file)
                # Skip compiled files and cache
                if file.endswith((".pyc", ".pyo", ".pyd", ".so", ".pdb")):
                    continue
                arcname = f"{safe_name}-{version}/{os.path.relpath(file_path, '.')}"
                tf.add(file_path, arcname=arcname)

    return sdist_filename
