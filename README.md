# zigcc-build-backend

![Test Backend](https://github.com/jrialland/zigcc-build/actions/workflows/test.yml/badge.svg)

A PEP 517 build backend that uses `zig cc` (via the `ziglang` Python package) to compile C/C++ extensions for Python.

This backend allows you to easily compile native Python extensions without needing a pre-installed C compiler on the system, as it leverages the portable Zig compiler toolchain distributed via PyPI.

## How it works

When you build your project (e.g., using `pip` or `build`), this backend:
1.  Reads your `pyproject.toml` configuration.
2.  Identifies the source files specified in `[tool.zigcc-build]`.
3.  Invokes `zig cc` (provided by the `ziglang` package) to compile these sources into a native extension module (`.pyd` on Windows, `.so` on Linux/macOS).
4.  Packages the result into a standard Python Wheel.

## Usage

### 1. Configure `[build-system]`

In your `pyproject.toml`, specify `zigcc-build` as the build backend.

**Option A: Using from PyPI (if published)**
```toml
[build-system]
requires = ["zigcc-build"]
build-backend = "zigcc_build"
```

**Option B: Using directly from GitHub**
```toml
[build-system]
requires = ["zigcc-build @ git+https://github.com/jrialland/zigcc-build.git"]
build-backend = "zigcc_build"
```

### 2. Configure `[tool.zigcc-build]`

Define your extension module settings in the `[tool.zigcc-build]` table.

```toml
[tool.zigcc-build]
# The name of the compiled extension module (optional).
# Defaults to the project name (with dashes replaced by underscores).
module-name = "my_extension"

# List of source files to compile (C or C++).
sources = ["src/main.c", "src/utils.c"]

# List of additional include directories (optional).
include-dirs = ["include"]

# List of compiler macros/defines (optional).
# Translates to -Dname or -Dname=value
defines = ["MY_MACRO=1", "DEBUG"]

# List of library directories (optional).
# Translates to -Lpath
library-dirs = ["libs"]

# List of libraries to link against (optional).
# Translates to -lname
libraries = ["m", "user32"]

# Optional python script to configure the build dynamically
configurer-script = "configure.py"

# List of python packages to include (optional).
# If omitted, the backend will try to auto-discover packages in 'src/' or the root directory.
packages = ["mypackage"]
```

### Including Pure Python Code

The backend automatically detects and includes pure Python packages.
- If a `src` directory exists, it looks for packages inside `src`.
- Otherwise, it looks for packages in the project root.

You can also explicitly specify packages to include using the `packages` option in `[tool.zigcc-build]`.

### Dynamic Configuration

If you specify a `configurer-script`, the backend will load this Python script and call a `configure(config)` function. This allows you to modify the build configuration dynamically (e.g., based on the platform or environment).

**Example `configure.py`:**

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zigcc_build.config import ZigCcConfig

def configure(config: "ZigCcConfig"):
    # config is a dictionary with keys: 'sources', 'include_dirs', 'defines', 'module_name'
    print("Running custom configuration...")
    
    # Add a define dynamically
    config["defines"].append("DYNAMIC_MACRO=1")
    
    # Add sources based on platform
    import sys
    if sys.platform == "win32":
        config["sources"].append("src/windows_utils.c")
```

### Configuration Schema

The configuration object passed to `configure()` follows this `TypedDict` schema:

```python
class ZigCcConfig(TypedDict):
    sources: List[str]      # List of source files to compile
    include_dirs: List[str] # List of include directories
    defines: List[str]      # List of compiler macros
    library_dirs: List[str] # List of library directories
    libraries: List[str]    # List of libraries to link against
    module_name: str        # The name of the extension module
    packages: List[str]     # List of python packages to include
```

### 3. Build

You can build your project using standard Python tooling:

```bash
# Install the package in editable mode
pip install -e .

# Build a wheel and sdist
python -m build
```

## PEP 621 Metadata Support

The `zigcc-build` backend fully supports PEP 621 metadata fields defined in your `pyproject.toml`. All metadata is automatically included in the generated wheel's `METADATA` file and the source distribution's `PKG-INFO` file.

### Supported Metadata Fields

- **name** - Package name
- **version** - Package version
- **description** - Short one-line summary
- **readme** - Long description from README file (supports `.md`, `.rst`, `.txt`)
- **requires-python** - Python version requirements
- **license** - License information (text or file)
- **authors** - List of authors with name and email
- **maintainers** - List of maintainers with name and email
- **keywords** - List of keywords for PyPI
- **classifiers** - List of PyPI classifiers
- **urls** - Project URLs (Homepage, Repository, Issues, etc.)
- **dependencies** - Runtime dependencies
- **optional-dependencies** - Optional dependency groups

### Example with Full Metadata

```toml
[build-system]
requires = ["zigcc-build"]
build-backend = "zigcc_build"

[project]
name = "my-package"
version = "1.0.0"
description = "A package with C extensions"
readme = "README.md"
requires-python = ">=3.12"
license = {text = "MIT"}
authors = [
    {name = "Your Name", email = "you@example.com"}
]
keywords = ["c-extension", "zig", "compiler"]
classifiers = [
    "Development Status :: 4 - Beta",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.12",
]
dependencies = [
    "numpy>=1.20",
]

[project.urls]
Homepage = "https://github.com/user/my-package"
Repository = "https://github.com/user/my-package"
Issues = "https://github.com/user/my-package/issues"

[tool.zigcc-build]
module-name = "my_extension"
sources = ["src/extension.c"]
```

The backend will automatically generate complete `METADATA` and `PKG-INFO` files with all this information, ensuring your packages are fully compliant with PyPI requirements.

## Example `pyproject.toml`

Here is a complete example for a project named `demo-package`:

```toml
[build-system]
requires = ["zigcc-build"]
build-backend = "zigcc_build"

[project]
name = "demo-package"
version = "1.0.0"
description = "A demo package built with zigcc"
readme = "README.md"
requires-python = ">=3.7"

[tool.zigcc-build]
module-name = "demo"
sources = ["src/hello.c"]
```

## Requirements

- Python >= 3.7
- The `ziglang` package (automatically handled by the build system requirements).

## Tutorial: Building the Demo Project

This repository includes a `demo-project` to illustrate how to use `zigcc-build`.

### 1. Install the backend locally

Since `zigcc-build` is not yet on PyPI, you need to install it in your environment first.

```bash
# From the root of the repository
pip install -e .
```

### 2. Build the demo project

Navigate to the `demo-project` directory and build it. We use `--no-build-isolation` because the backend is installed locally, not from PyPI.

```bash
cd demo-project
python -m build --no-isolation
```

### 3. Install and Test

Install the generated wheel and run the tests.

```bash
# Install the generated wheel (replace * with the actual version/platform)
pip install dist/demo_package-*.whl --force-reinstall

# Run the tests
python -m pytest tests
```

### 4. Recompiling

To recompile after changing the C source code, simply run the build command again:

```bash
python -m build --no-isolation
```

