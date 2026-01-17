#!/usr/bin/env python3
"""
Comprehensive test to verify all PEP 621 metadata fields are properly handled.
"""

import subprocess
import sys
import tempfile
import shutil
from pathlib import Path


def create_test_project(project_dir):
    """Create a test project with all PEP 621 metadata fields."""
    
    # Create project structure
    (project_dir / "src").mkdir()
    (project_dir / "src" / "test_pkg").mkdir()
    
    # Create a simple Python package
    (project_dir / "src" / "test_pkg" / "__init__.py").write_text(
        'def hello():\n    return "Hello from test package"\n'
    )
    
    # Create README
    (project_dir / "README.md").write_text("""# Test Package

This is a comprehensive test of PEP 621 metadata handling.

## Features

- Full metadata support
- All PEP 621 fields
""")
    
    # Create LICENSE file
    (project_dir / "LICENSE").write_text("MIT License\n\nCopyright (c) 2026 Test")
    
    # Create comprehensive pyproject.toml
    (project_dir / "pyproject.toml").write_text("""[build-system]
requires = ["zigcc-build"]
build-backend = "zigcc_build"

[project]
name = "test-metadata-package"
version = "0.1.0"
description = "Test package for PEP 621 metadata"
readme = "README.md"
requires-python = ">=3.12"
license = {file = "LICENSE"}
authors = [
    {name = "Primary Author", email = "primary@example.com"},
    {name = "Secondary Author", email = "secondary@example.com"}
]
maintainers = [
    {name = "Maintainer One", email = "maint1@example.com"}
]
keywords = ["test", "metadata", "pep621", "validation"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Testing",
]
dependencies = [
    "requests>=2.28.0",
    "packaging>=21.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "black>=22.0",
]
docs = [
    "sphinx>=4.0",
]

[project.urls]
Homepage = "https://example.com/test-package"
Documentation = "https://docs.example.com/test-package"
Repository = "https://github.com/example/test-package"
Issues = "https://github.com/example/test-package/issues"
Changelog = "https://github.com/example/test-package/blob/main/CHANGELOG.md"

[tool.zigcc-build]
packages = ["test_pkg"]
""")


def test_metadata_fields(metadata_text):
    """Test that all expected metadata fields are present."""
    
    expected_fields = {
        'Metadata-Version: 2.1': 'Core metadata version',
        'Name: test-metadata-package': 'Package name',
        'Version: 0.1.0': 'Version',
        'Summary: Test package for PEP 621 metadata': 'Description',
        'Home-page: https://example.com/test-package': 'Homepage',
        'Author: Primary Author, Secondary Author': 'Authors',
        'Author-Email: primary@example.com, secondary@example.com': 'Author emails',
        'Maintainer: Maintainer One': 'Maintainer',
        'Maintainer-Email: maint1@example.com': 'Maintainer email',
        'License: MIT License': 'License',
        'Project-URL: Documentation, https://docs.example.com/test-package': 'Project URLs',
        'Keywords: test,metadata,pep621,validation': 'Keywords',
        'Classifier: Development Status :: 3 - Alpha': 'Classifiers',
        'Requires-Python: >=3.12': 'Python requirement',
        'Requires-Dist: requests>=2.28.0': 'Dependencies',
        'Provides-Extra: dev': 'Optional dependencies',
        'Requires-Dist: pytest>=7.0; extra == \'dev\'': 'Extra dependencies',
        'Description-Content-Type: text/markdown': 'Content type',
    }
    
    print("\nMetadata Field Validation:")
    print("=" * 80)
    
    all_present = True
    for field, description in expected_fields.items():
        if field in metadata_text:
            print(f"✓ {description}: FOUND")
        else:
            print(f"✗ {description}: MISSING - Expected: {field}")
            all_present = False
    
    # Check for README content in long description
    if '# Test Package' in metadata_text:
        print("✓ Long description (README): FOUND")
    else:
        print("✗ Long description (README): MISSING")
        all_present = False
    
    print("=" * 80)
    
    return all_present


def main():
    print("Creating comprehensive metadata test project...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir()
        
        # Create test project
        create_test_project(project_dir)
        
        # Build the project
        print("\nBuilding project...")
        result = subprocess.run(
            [sys.executable, "-m", "build", "--no-isolation", "--wheel"],
            cwd=project_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Build failed: {result.stderr}")
            return 1
        
        print("Build successful!")
        
        # Extract and check metadata
        dist_dir = project_dir / "dist"
        wheels = list(dist_dir.glob("*.whl"))
        
        if not wheels:
            print("No wheel found!")
            return 1
        
        wheel_path = wheels[0]
        print(f"\nExamining wheel: {wheel_path.name}")
        
        # Extract metadata
        import zipfile
        with zipfile.ZipFile(wheel_path, 'r') as zf:
            for name in zf.namelist():
                if name.endswith('.dist-info/METADATA'):
                    metadata_text = zf.read(name).decode('utf-8')
                    
                    print("\n" + "=" * 80)
                    print("METADATA FILE CONTENT (sample):")
                    print("=" * 80)
                    print(metadata_text[:1000])
                    if len(metadata_text) > 1000:
                        print(f"\n... ({len(metadata_text) - 1000} more characters)")
                    print("=" * 80)
                    
                    # Validate metadata
                    if test_metadata_fields(metadata_text):
                        print("\n✓ All metadata fields present and correct!")
                        return 0
                    else:
                        print("\n✗ Some metadata fields are missing or incorrect")
                        return 1
        
        print("Could not find METADATA in wheel!")
        return 1


if __name__ == '__main__':
    sys.exit(main())
