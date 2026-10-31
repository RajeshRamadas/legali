"""Bounded local text extraction. Uploaded files are data, never commands."""
import io
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from . import config

MAX_PAGES = 15
MAX_CHARS = 45000
# Long edge for page images sent to vision models; larger images are downscaled by the provider anyway.
IMAGE_EDGE = 1568


def model_image(path) -> bytes | None:
    """A JPEG copy of a scanned page for the extraction model. OCR text stays the quote anchor."""
    try:
        from PIL import Image
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((IMAGE_EDGE, IMAGE_EDGE))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85)
            return out.getvalue()
    except (OSError, ValueError, ImportError):
        return None


def command(args, timeout=45):
    return subprocess.run(args, check=True, capture_output=True, timeout=timeout).stdout.decode("utf-8", errors="replace")


def extract(data: bytes, filename: str, images: dict | None = None, max_pages: int = MAX_PAGES) -> dict:
    """Return page text and warnings. When `images` is a dict, JPEG copies of OCR'd pages are added to it
    by page number; they are kept out of the returned result so they never enter the saved run."""
    suffix = Path(filename).suffix.lower()
    pages, warnings = [], []
    count = None
    try:
        with tempfile.TemporaryDirectory(prefix="homexo-read-") as folder:
            path = Path(folder) / ("input" + suffix)
            path.write_bytes(data)
            if suffix == ".pdf":
                info = command(["pdfinfo", str(path)])
                count = next(int(line.split(":", 1)[1]) for line in info.splitlines() if line.startswith("Pages:"))
                if count > max_pages:
                    warnings.append(f"Only the first {max_pages} of {count} pages were examined; split the remaining pages into additional files.")
                text = command(["pdftotext", "-f", "1", "-l", str(max_pages), "-layout", str(path), "-"])
                native = text.split("\f")
                for number in range(1, min(count, max_pages) + 1):
                    content = native[number - 1].strip() if number <= len(native) else ""
                    method = "embedded_text"
                    if len(content) < 50:
                        prefix = str(Path(folder) / "scan")
                        command(["pdftoppm", "-f", str(number), "-l", str(number), "-scale-to", "1800", "-singlefile", "-png", str(path), prefix])
                        content = command(["tesseract", prefix + ".png", "stdout", "-l", config.VERIFICATION_OCR_LANGUAGES])
                        method = "ocr"
                        if images is not None and (image := model_image(prefix + ".png")):
                            images[number] = image
                    if len(content.strip()) > 10000:
                        warnings.append(f"Page {number} exceeds the text limit and was partially examined.")
                    pages.append({"page": number, "text": content.strip()[:10000], "method": method})
            elif suffix in (".png", ".jpg", ".jpeg", ".webp"):
                text = command(["tesseract", str(path), "stdout", "-l", config.VERIFICATION_OCR_LANGUAGES])
                if images is not None and (image := model_image(path)):
                    images[1] = image
                if len(text.strip()) > 10000:
                    warnings.append("Image text limit reached; the image was partially examined.")
                pages = [{"page": 1, "text": text.strip()[:10000], "method": "ocr"}]
            elif suffix == ".docx":
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    info = archive.getinfo("word/document.xml")
                    if info.file_size > 2_000_000:
                        raise ValueError("Document XML exceeds extraction limit")
                    root = ElementTree.fromstring(archive.read(info))
                text = "\n".join("".join(p.itertext()) for p in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"))
                if len(text) > MAX_CHARS:
                    warnings.append("DOCX text limit reached; the file was partially examined.")
                pages = [{"page": 1, "text": text[:MAX_CHARS], "method": "docx_text"}]
                warnings.append("DOCX references use logical part 1, not printed page numbers; signatures and layout were not inspected.")
            else:
                warnings.append("This format cannot be read by the agent. Supply a PDF, DOCX, PNG, JPEG or WEBP copy.")
    except (OSError, subprocess.SubprocessError, ValueError, StopIteration, zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        warnings.append("Text extraction failed or timed out. Supply a legible, unencrypted copy and check OCR tools/language packs.")
    remaining = MAX_CHARS
    for page in pages:
        if len(page["text"]) > remaining:
            warnings.append("Extraction text limit reached; the file was only partially examined.")
        page["text"] = page["text"][:remaining]
        remaining -= len(page["text"])
    if not any(p["text"].strip() for p in pages):
        warnings.append("No readable text was extracted. This document has not been analysed.")
    result = {"pages": pages, "warnings": list(dict.fromkeys(warnings))}
    if count is not None:
        result["page_count"] = count
    return result
