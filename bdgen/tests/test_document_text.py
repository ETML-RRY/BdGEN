from __future__ import annotations

import io
import zipfile

import pytest

from bdgen import document_text


def _make_docx(paragraphs: list[str]) -> bytes:
    """Build a minimal valid .docx (ZIP + WordprocessingML) in memory."""
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def test_extract_plain_text() -> None:
    assert document_text.extract_text("notes.txt", "Bonjour à tous".encode("utf-8")) == "Bonjour à tous"


def test_extract_markdown() -> None:
    out = document_text.extract_text("cours.md", b"# Titre\n\nUn paragraphe.")
    assert "Titre" in out and "paragraphe" in out


def test_extract_docx() -> None:
    blob = _make_docx(["Chapitre 1", "La cellule est l'unite du vivant."])
    out = document_text.extract_text("cours.docx", blob)
    assert "Chapitre 1" in out
    assert "unite du vivant" in out


def test_extract_corrupt_docx_raises() -> None:
    with pytest.raises(ValueError):
        document_text.extract_text("bad.docx", b"not a zip")


def test_unsupported_format_raises() -> None:
    with pytest.raises(ValueError):
        document_text.extract_text("legacy.doc", b"anything")


def test_combine_documents_labels_and_skips_empty() -> None:
    combined = document_text.combine_documents(
        [
            ("a.txt", b"Premier document."),
            ("vide.txt", b"   "),
            ("b.txt", b"Second document."),
        ]
    )
    assert "===== Document : a.txt =====" in combined
    assert "===== Document : b.txt =====" in combined
    assert "vide.txt" not in combined  # empty file skipped


def test_combine_documents_too_many() -> None:
    files = [(f"f{i}.txt", b"x") for i in range(document_text.MAX_FILES + 1)]
    with pytest.raises(ValueError):
        document_text.combine_documents(files)


def test_combine_documents_oversized() -> None:
    big = b"x" * (document_text.MAX_FILE_BYTES + 1)
    with pytest.raises(ValueError):
        document_text.combine_documents([("huge.txt", big)])


def test_combine_documents_truncates() -> None:
    big_text = ("a" * (document_text.MAX_TOTAL_CHARS + 5000)).encode("utf-8")
    combined = document_text.combine_documents([("long.txt", big_text)])
    assert len(combined) <= document_text.MAX_TOTAL_CHARS + 50
    assert combined.endswith("[... documents tronqués ...]")


def test_combine_documents_empty() -> None:
    assert document_text.combine_documents([]) == ""
