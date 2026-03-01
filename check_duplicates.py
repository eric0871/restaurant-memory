#!/usr/bin/env python3
"""
Image deduplication script for restaurant photos.
Uses perceptual hashing to detect similar images.
"""

import os
import sys
import hashlib
from pathlib import Path
from PIL import Image


def get_file_hash(filepath):
    """Get MD5 hash of file content (exact duplicates)"""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def get_image_hash(filepath):
    """Get perceptual hash of image (similar images)"""
    try:
        with Image.open(filepath) as img:
            # Convert to small grayscale for comparison
            img = img.convert('L').resize((8, 8), Image.Resampling.LANCZOS)
            pixels = list(img.getdata())
            avg = sum(pixels) / len(pixels)
            # Create binary hash
            bits = ''.join('1' if p > avg else '0' for p in pixels)
            return hex(int(bits, 2))[2:].zfill(16)
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return None


def hamming_distance(hash1, hash2):
    """Calculate Hamming distance between two hashes"""
    if not hash1 or not hash2:
        return 100
    try:
        x = int(hash1, 16) ^ int(hash2, 16)
        return bin(x).count('1')
    except:
        return 100


def find_duplicates(image_dir, threshold=5):
    """
    Find duplicate and similar images.
    threshold: max Hamming distance to consider images similar (default 5)
    """
    image_dir = Path(image_dir)
    if not image_dir.exists():
        print(f"Directory not found: {image_dir}")
        return

    # Get all image files
    images = []
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
        images.extend(image_dir.glob(ext))

    print(f"Scanning {len(images)} images in {image_dir}...")

    # Group by restaurant prefix
    restaurant_images = {}
    for img_path in images:
        # Extract restaurant name (e.g., "sushi-yoshizumi-1.jpg" -> "sushi-yoshizumi")
        name = img_path.stem.rsplit('-', 1)[0] if '-' in img_path.stem else img_path.stem
        if name not in restaurant_images:
            restaurant_images[name] = []
        restaurant_images[name].append(img_path)

    duplicates = []
    similar = []

    for restaurant, files in restaurant_images.items():
        if len(files) < 2:
            continue

        # Calculate hashes for all images
        hashes = {}
        for f in files:
            file_hash = get_file_hash(f)
            img_hash = get_image_hash(f)
            if img_hash:
                hashes[f] = {'file_hash': file_hash, 'img_hash': img_hash}

        # Check for exact duplicates
        file_hash_groups = {}
        for f, h in hashes.items():
            fh = h['file_hash']
            if fh not in file_hash_groups:
                file_hash_groups[fh] = []
            file_hash_groups[fh].append(f)

        for fh, group in file_hash_groups.items():
            if len(group) > 1:
                duplicates.append((restaurant, group))

        # Check for similar images (perceptual hash)
        checked = set()
        for f1, h1 in hashes.items():
            for f2, h2 in hashes.items():
                if f1 >= f2 or (f1, f2) in checked:
                    continue
                checked.add((f1, f2))
                checked.add((f2, f1))

                dist = hamming_distance(h1['img_hash'], h2['img_hash'])
                if dist <= threshold:
                    similar.append((restaurant, f1, f2, dist))

    # Report results
    print("\n" + "="*60)

    if duplicates:
        print(f"\n🚨 EXACT DUPLICATES FOUND ({len(duplicates)} groups):")
        for restaurant, files in duplicates:
            print(f"\n  {restaurant}:")
            for f in files:
                size = f.stat().st_size / 1024
                print(f"    - {f.name} ({size:.1f}KB)")
    else:
        print("\n✅ No exact duplicates found")

    if similar:
        print(f"\n⚠️  SIMILAR IMAGES FOUND ({len(similar)} pairs):")
        for restaurant, f1, f2, dist in similar:
            size1 = f1.stat().st_size / 1024
            size2 = f2.stat().st_size / 1024
            print(f"\n  {restaurant} (similarity: {dist}/64):")
            print(f"    - {f1.name} ({size1:.1f}KB)")
            print(f"    - {f2.name} ({size2:.1f}KB)")
    else:
        print("\n✅ No similar images found")

    return duplicates, similar


def suggest_removals(duplicates, similar, keep_best=True):
    """Suggest which files to remove"""
    to_remove = []

    # For duplicates, keep the largest file (assumed best quality)
    for restaurant, files in duplicates:
        files_sorted = sorted(files, key=lambda f: f.stat().st_size, reverse=True)
        to_remove.extend(files_sorted[1:])  # Remove all but largest

    # For similar images, remove the smaller one
    for restaurant, f1, f2, dist in similar:
        if f1.stat().st_size < f2.stat().st_size:
            to_remove.append(f1)
        else:
            to_remove.append(f2)

    return to_remove


if __name__ == "__main__":
    if len(sys.argv) > 1:
        image_dir = sys.argv[1]
    else:
        image_dir = os.path.expanduser("~/restaurant-memory-deploy/images")

    duplicates, similar = find_duplicates(image_dir)

    if duplicates or similar:
        print("\n" + "="*60)
        to_remove = suggest_removals(duplicates, similar)
        if to_remove:
            print(f"\n🗑️  SUGGESTED REMOVALS ({len(to_remove)} files):")
            for f in to_remove:
                size = f.stat().st_size / 1024
                print(f"    rm {f}")
            print("\nTo auto-remove, run: python3 check_duplicates.py --remove")

        # Check for --remove flag
        if "--remove" in sys.argv:
            print("\n🗑️  Removing suggested files...")
            for f in to_remove:
                f.unlink()
                print(f"  Removed: {f.name}")
            print("✅ Done!")
