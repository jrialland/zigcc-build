import os
import sys
import subprocess
import tarfile
import zipfile
import sysconfig
import importlib.util

import hashlib
import base64

from .config import ZigCcConfig

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
    import platform
    from packaging import tags
    
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
        "system": system
    }

def _prepare_build_config(tool_config, safe_name):
    """Prepare and configure the build configuration."""
    build_config: ZigCcConfig = {
        "sources": tool_config.get("sources", []),
        "include_dirs": tool_config.get("include-dirs", []),
        "defines": tool_config.get("defines", []),
        "library_dirs": tool_config.get("library-dirs", []),
        "libraries": tool_config.get("libraries", []),
        "module_name": tool_config.get("module-name", safe_name),
        "packages": tool_config.get("packages", [])
    }
    
    # Run configurer script if present
    configurer_script = tool_config.get("configurer-script")
    if configurer_script:
        print(f"Running configurer script: {configurer_script}")
        spec = importlib.util.spec_from_file_location("zigcc_configurer", configurer_script)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules["zigcc_configurer"] = module
            spec.loader.exec_module(module)
            
            if hasattr(module, "configure"):
                module.configure(build_config)
            else:
                print(f"Warning: {configurer_script} does not have a 'configure' function.")
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
                if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "__init__.py")):
                    found_packages.append(item)
            
            if found_packages:
                package_dir = "src"
                packages = found_packages
        
        if not packages:
            # Check current directory
            for item in os.listdir("."):
                if item in [".git", ".venv", "dist", "build", "__pycache__", "zigcc_build.egg-info", "demo-project"]:
                    continue
                if os.path.isdir(item) and os.path.exists(os.path.join(item, "__init__.py")):
                    packages.append(item)
    
    return packages, package_dir

def _build_wheel_impl(wheel_directory, config_settings=None, metadata_directory=None, editable=False):
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

    wheel_filename = f"{safe_name}-{version}-{impl}{pyver}-{abi}-{plat}.whl"
    wheel_path = os.path.join(wheel_directory, wheel_filename)
    
    print(f"Building {'editable ' if editable else ''}wheel: {wheel_path}")
    
    # Helper to write file and track for RECORD
    record_rows = []
    
    def write_file_to_zip(zf, path, arcname):
        zf.write(path, arcname=arcname)
        with open(path, "rb") as f:
            data = f.read()
        digest = hashlib.sha256(data).digest()
        hash_str = "sha256=" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        record_rows.append(f"{arcname},{hash_str},{len(data)}")

    def write_str_to_zip(zf, arcname, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        zf.writestr(arcname, data)
        digest = hashlib.sha256(data).digest()
        hash_str = "sha256=" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        record_rows.append(f"{arcname},{hash_str},{len(data)}")

    # Create the wheel zip
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Compile and add extension modules
        build_config = _prepare_build_config(tool_config, safe_name)
        
        output_filename = _compile_extension(build_config, platform_info)
        if output_filename:
            # Add the compiled extension to the wheel
            write_file_to_zip(zf, output_filename, arcname=output_filename)
            
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
        
        # METADATA
        metadata_content = f"""Metadata-Version: 2.1
Name: {name}
Version: {version}
Summary: {project_config.get('description', '')}
"""
        write_str_to_zip(zf, f"{dist_info_dir}/METADATA", metadata_content)
        
        # WHEEL
        wheel_content = f"""Wheel-Version: 1.0
Generator: zigcc-build-backend
Root-Is-Purelib: false
Tag: {impl}{pyver}-{abi}-{plat}
"""
        write_str_to_zip(zf, f"{dist_info_dir}/WHEEL", wheel_content)
        
        # RECORD
        record_rows.append(f"{dist_info_dir}/RECORD,,")
        record_content = "\n".join(record_rows) + "\n"
        zf.writestr(f"{dist_info_dir}/RECORD", record_content)
        
    return wheel_filename

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    """Build a regular wheel."""
    return _build_wheel_impl(wheel_directory, config_settings, metadata_directory, editable=False)

def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    """PEP 660: Build an editable wheel using .pth files."""
    return _build_wheel_impl(wheel_directory, config_settings, metadata_directory, editable=True)

def build_sdist(sdist_directory, config_settings=None):
    config = _get_project_config()
    project_config = config.get("project", {})
    name = project_config.get("name", "unknown")
    version = project_config.get("version", "0.0.0")
    
    sdist_filename = f"{name}-{version}.tar.gz"
    sdist_path = os.path.join(sdist_directory, sdist_filename)
    
    with tarfile.open(sdist_path, "w:gz") as tf:
        # Add all files in current directory recursively, excluding venv/git etc.
        # Simplified: just add everything in current dir
        for root, dirs, files in os.walk("."):
            if ".git" in dirs:
                dirs.remove(".git")
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            if "dist" in dirs:
                dirs.remove("dist")
                
            for file in files:
                file_path = os.path.join(root, file)
                arcname = f"{name}-{version}/{os.path.relpath(file_path, '.')}"
                tf.add(file_path, arcname=arcname)
                
    return sdist_filename
