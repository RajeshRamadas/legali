"""Exercise the real parser with hostile uploaded DOCX archives, without external tools/providers."""
import io
import zipfile

import pytest

from app import document_reader

NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx(xml):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", xml)
    return output.getvalue()


def test_normal_docx_still_extracts_unicode_and_escaped_text():
    data = docx(f'<w:document xmlns:w="{NAMESPACE}"><w:body><w:p><w:r><w:t>Title &amp; deed · ನಮಸ್ಕಾರ</w:t></w:r></w:p></w:body></w:document>')
    result = document_reader.extract(data, "title.docx")
    assert result["pages"] == [{"page": 1, "text": "Title & deed · ನಮಸ್ಕಾರ", "method": "docx_text"}]


@pytest.mark.parametrize("declaration", [
    '<!DOCTYPE w:document [<!ENTITY secret "PRIVATE_XML_ENTITY">]>',
    '<!DOCTYPE w:document SYSTEM "https://invalid.example/private.dtd">',
    '<!DOCTYPE w:document [<!ENTITY secret SYSTEM "file:///etc/passwd">]>',
    '<!DOCTYPE w:document [<!ENTITY % remote SYSTEM "https://invalid.example/entity.dtd">%remote;]>',
])
def test_docx_dtd_and_entity_payloads_fail_closed_without_returning_text(declaration):
    data = docx(f'{declaration}<w:document xmlns:w="{NAMESPACE}"><w:body><w:p><w:r><w:t>&secret;</w:t></w:r></w:p></w:body></w:document>')
    result = document_reader.extract(data, "hostile.docx")
    assert result["pages"] == []
    assert any("failed" in warning for warning in result["warnings"])
    assert "PRIVATE_XML_ENTITY" not in str(result)
    assert "passwd" not in str(result) and "invalid.example" not in str(result)


def test_compressed_oversized_xml_is_rejected_before_parsing(monkeypatch):
    data = docx(b"x" * 2_000_001)
    assert len(data) < 10_000
    def unexpected(*args, **kwargs):
        raise AssertionError("Oversized XML reached the parser")
    monkeypatch.setattr(document_reader.ElementTree, "fromstring", unexpected)
    result = document_reader.extract(data, "compressed.docx")
    assert not result["pages"] and any("failed" in warning for warning in result["warnings"])


@pytest.mark.parametrize("library_limit", [False, True])
def test_oversized_images_fail_before_ocr_or_vision_conversion(monkeypatch, tmp_path, library_limit):
    from PIL import Image
    output = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="PNG")
    if library_limit:
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    else:
        monkeypatch.setattr(document_reader, "MAX_IMAGE_PIXELS", 100)
    def unexpected(*args, **kwargs):
        raise AssertionError("Oversized image reached native OCR")
    monkeypatch.setattr(document_reader, "command", unexpected)
    result = document_reader.extract(output.getvalue(), "oversized.png")
    assert not result["pages"] and any("failed" in warning for warning in result["warnings"])
    path = tmp_path / "oversized.png"
    path.write_bytes(output.getvalue())
    assert document_reader.model_image(path) is None
