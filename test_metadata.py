#!/usr/bin/env python3
"""
Test script to verify that zigcc-build properly handles PEP 621 metadata.
Extracts and validates metadata from wheel and sdist distributions.
"""

import sys
import zipfile
import tarfile
import tempfile
import os
from pathlib import Path


def extract_wheel_metadata(wheel_path):
    """Extract METADATA from a wheel file."""
    with zipfile.ZipFile(wheel_path, 'r') as zf:
        for name in zf.namelist():
            if name.endswith('.dist-info/METADATA'):
                return zf.read(name).decode('utf-8')
    return None


def extract_sdist_pkginfo(sdist_path):
    """Extract PKG-INFO from a source distribution."""
    with tarfile.open(sdist_path, 'r:gz') as tf:
        for member in tf.getmembers():
            if member.name.endswith('/PKG-INFO'):
                f = tf.extractfile(member)
                if f:
                    return f.read().decode('utf-8')
    return None


def validate_metadata(metadata_text, distribution_type):
    """Validate that metadata contains expected PEP 621 fields."""
    required_fields = [
        'Metadata-Version: 2.1',
        'Name:',
        'Version:',
    ]
    
    recommended_fields = [
        'Summary:',
        'Author:',
        'License:',
        'Requires-Python:',
        'Classifier:',
        'Project-URL:',
        'Description-Content-Type:',
    ]
    
    print(f"\n{distribution_type} Metadata Validation:")
    print("=" * 60)
    
    # Check required fields
    all_required_present = True
    for field in required_fields:
        if field in metadata_text:
            print(f"✓ {field.split(':')[0]}: PRESENT")
        else:
            print(f"✗ {field.split(':')[0]}: MISSING")
            all_required_present = False
    
    # Check recommended fields
    print("\nRecommended fields:")
    for field in recommended_fields:
        if field in metadata_text:
            print(f"✓ {field.split(':')[0]}: PRESENT")
        else:
            print(f"  {field.split(':')[0]}: Not present")
    
    # Check for long description
    if '\n\n' in metadata_text:
        lines_after_headers = metadata_text.split('\n\n', 1)[1]
        if lines_after_headers.strip():
            print(f"✓ Long Description: PRESENT ({len(lines_after_headers)} chars)")
        else:
            print(f"  Long Description: Empty")
    else:
        print(f"  Long Description: Not present")
    
    print("\n" + "=" * 60)
    
    return all_required_present


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_metadata.py <dist_directory>")
        print("\nExample: python test_metadata.py demo-project/dist")
        sys.exit(1)
    
    dist_dir = Path(sys.argv[1])
    
    if not dist_dir.exists():
        print(f"Error: Directory {dist_dir} does not exist")
        sys.exit(1)
    
    # Find wheel and sdist
    wheels = list(dist_dir.glob('*.whl'))
    sdists = list(dist_dir.glob('*.tar.gz'))
    
    success = True
    
    # Test wheel
    if wheels:
        wheel_path = wheels[0]
        print(f"\nTesting wheel: {wheel_path.name}")
        metadata = extract_wheel_metadata(wheel_path)
        
        if metadata:
            print("\n--- METADATA Content (first 500 chars) ---")
            print(metadata[:500])
            print("..." if len(metadata) > 500 else "")
            
            if not validate_metadata(metadata, "Wheel"):
                success = False
        else:
            print("ERROR: Could not extract METADATA from wheel")
            success = False
    else:
        print("\nWarning: No wheel files found in", dist_dir)
    
    # Test sdist
    if sdists:
        sdist_path = sdists[0]
        print(f"\nTesting sdist: {sdist_path.name}")
        pkg_info = extract_sdist_pkginfo(sdist_path)
        
        if pkg_info:
            print("\n--- PKG-INFO Content (first 500 chars) ---")
            print(pkg_info[:500])
            print("..." if len(pkg_info) > 500 else "")
            
            if not validate_metadata(pkg_info, "Sdist"):
                success = False
        else:
            print("ERROR: Could not extract PKG-INFO from sdist")
            success = False
    else:
        print("\nWarning: No sdist files found in", dist_dir)
    
    if success:
        print("\n✓ All metadata validation checks passed!")
        return 0
    else:
        print("\n✗ Some metadata validation checks failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
