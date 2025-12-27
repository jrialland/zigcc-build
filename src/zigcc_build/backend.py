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

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    config = _get_project_config()
    project_config = config.get("project", {})
    tool_config = config.get("tool", {}).get("zigcc-build", {})
    
    name = project_config.get("name", "unknown")
    version = project_config.get("version", "0.0.0")
    
    # Normalize name for wheel filename (replace - with _)
    safe_name = name.replace("-", "_")
    
    # Determine platform tag
    # For simplicity, we'll assume we are building a platform-specific wheel
    # since we are compiling native code.
    import platform
    
    # This is a simplified tag generation. Real backends use `packaging.tags`
    if sys.implementation.name == "cpython":
        impl = "cp"
    else:
        impl = sys.implementation.name
        
    pyver = f"{sys.version_info.major}{sys.version_info.minor}"
    abi = f"cp{pyver}" # Simplified
    
    # Detect OS and Arch for the tag
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    if system == "windows":
        plat = "win_amd64" if machine == "amd64" or machine == "x86_64" else "win32"
        ext_suffix = ".pyd"
    elif system == "linux":
        plat = f"linux_{machine}"
        ext_suffix = ".so"
    elif system == "darwin":
        plat = f"macosx_10_9_{machine}" # Simplified
        ext_suffix = ".so"
    else:
        plat = "any"
        ext_suffix = ".so"

    wheel_filename = f"{safe_name}-{version}-{impl}{pyver}-{abi}-{plat}.whl"
    wheel_path = os.path.join(wheel_directory, wheel_filename)
    
    print(f"Building wheel: {wheel_path}")
    
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
        
        # Prepare build config object
        build_config: ZigCcConfig = {
            "sources": tool_config.get("sources", []),
            "include_dirs": tool_config.get("include-dirs", []),
            "defines": tool_config.get("defines", []),
            "library_dirs": tool_config.get("library-dirs", []),
            "libraries": tool_config.get("libraries", []),
            "module_name": tool_config.get("module-name", safe_name)
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

        sources = build_config["sources"]
        include_dirs = build_config["include_dirs"]
        defines = build_config["defines"]
        library_dirs = build_config["library_dirs"]
        libraries = build_config["libraries"]
        ext_name = build_config["module_name"]
        
        if sources:
            # Compile using zig cc
            # We want to produce a single shared library (extension module)
            # The name of the extension usually matches the package name or is defined in config
            output_filename = f"{ext_name}{ext_suffix}"
            
            # Build command
            # python -m ziglang cc -shared -o output.pyd source.c -I...
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
                # This is tricky in a portable way, but sysconfig helps
                py_lib_dir = sysconfig.get_config_var("LIBDIR") or sysconfig.get_path("stdlib")
                # Often in libs folder on windows
                base = sys.base_prefix
                libs_dir = os.path.join(base, "libs")
                if os.path.exists(libs_dir):
                     cmd.extend([f"-L{libs_dir}", f"-lpython{pyver}"])
            
            print(f"Running: {' '.join(cmd)}")
            subprocess.check_call(cmd)
            
            # Add the compiled extension to the wheel
            write_file_to_zip(zf, output_filename, arcname=output_filename)
            
            # Cleanup artifact
            if os.path.exists(output_filename):
                os.remove(output_filename)

        # 2. Add pure python sources if any (simple copy of src/ folder usually)
        # For this example, we'll just look for a package folder with the project name
        # or just rely on the compiled extension.
        
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
