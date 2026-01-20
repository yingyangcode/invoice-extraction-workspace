#!/usr/bin/env python3
"""
Skill: Extract images from PDF

Converts a PDF file to a series of PNG images, one per page.
Saves images to the specified output directory.

Usage:
    python extract-pdf-images.py <pdf_path> <output_dir> [--dpi=300]

Output:
    Creates PNG files: page_001.png, page_002.png, etc.
    Returns JSON with image paths and metadata
"""

import sys
import json
import os
from pathlib import Path
from pdf2image import convert_from_path


def extract_pdf_images(pdf_path: str, output_dir: str, dpi: int = 300):
    """
    Extract images from PDF file

    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save images
        dpi: Resolution for image extraction (default 300)

    Returns:
        dict: Metadata about extracted images
    """
    # Validate input
    if not os.path.exists(pdf_path):
        return {
            "success": False,
            "error": f"PDF file not found: {pdf_path}"
        }

    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    try:
        # Convert PDF to images
        images = convert_from_path(pdf_path, dpi=dpi)

        # Save each page as PNG
        image_paths = []
        for i, image in enumerate(images, start=1):
            output_path = os.path.join(output_dir, f"page_{i:03d}.png")
            image.save(output_path, "PNG")

            image_paths.append({
                "page": i,
                "path": output_path,
                "width": image.width,
                "height": image.height,
            })

        return {
            "success": True,
            "pdf_path": pdf_path,
            "output_dir": output_dir,
            "total_pages": len(images),
            "dpi": dpi,
            "images": image_paths,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({
            "success": False,
            "error": "Usage: extract-pdf-images.py <pdf_path> <output_dir> [--dpi=300]"
        }))
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_dir = sys.argv[2]

    # Parse optional DPI argument
    dpi = 300
    for arg in sys.argv[3:]:
        if arg.startswith("--dpi="):
            dpi = int(arg.split("=")[1])

    result = extract_pdf_images(pdf_path, output_dir, dpi)
    print(json.dumps(result, indent=2))

    sys.exit(0 if result["success"] else 1)
