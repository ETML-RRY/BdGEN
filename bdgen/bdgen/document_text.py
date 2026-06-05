"""Extract plain text from user-uploaded reference documents.

Powers the "Création rapide" step: the user can attach one or more source
documents (course handout, lecture notes, a brief…) that the comic should be
based on. We pull their raw text out here and hand the concatenation to the
text LLM alongside the free-text prompt.

Formats:
- Plain text (``.txt``, ``.md``, ``.markdown``, ``.rst``, ``.csv``, ``.log``,
  ``.text``): decoded directly.
- Word (``.docx``): unzipped with the stdlib — a ``.docx`` is a ZIP whose
  ``word/document.xml`` holds the text — so no extra dependency is needed.
- PDF (``.pdf``): via ``pypdf`` when available; otherwise a clear error.

Old binary ``.doc`` is not supported (different, opaque format).
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

# Guardrails so a careless upload can't blow up memory or the LLM context.
MAX_FILES = 5
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB per file
MAX_TOTAL_CHARS = 60_000  # combined text budget fed to the LLM

_TEXT_EXTENSIONS = {".txt", ".text", ".md", ".markdown", ".rst", ".csv", ".log"}
_DOCX_EXT = ".docx"
_PDF_EXT = ".pdf"

SUPPORTED_EXTENSIONS = _TEXT_EXTENSIONS | {_DOCX_EXT, _PDF_EXT}

# WordprocessingML namespace.
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _extract_plain(blob: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return blob.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return blob.decode("utf-8", errors="replace")


def _extract_docx(blob: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            xml = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise ValueError("Document Word illisible ou corrompu.") from e

    root = ET.fromstring(xml)
    paragraphs: list[str] = []
    for para in root.iter(f"{_W}p"):
        runs: list[str] = []
        for node in para.iter():
            tag = node.tag
            if tag == f"{_W}t" and node.text:
                runs.append(node.text)
            elif tag == f"{_W}tab":
                runs.append("\t")
            elif tag in (f"{_W}br", f"{_W}cr"):
                runs.append("\n")
        line = "".join(runs).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _extract_pdf(blob: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover - depends on install
        raise ValueError(
            "La lecture des PDF n'est pas disponible sur cette installation."
        ) from e
    try:
        reader = PdfReader(io.BytesIO(blob))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as e:
        raise ValueError("PDF illisible ou protégé.") from e
    return "\n\n".join(p for p in pages if p)


def extract_text(filename: str, blob: bytes) -> str:
    """Extract plain text from a single uploaded document.

    Raises ``ValueError`` for unsupported or unreadable files.
    """
    ext = Path(filename or "").suffix.lower()
    if ext in _TEXT_EXTENSIONS:
        return _extract_plain(blob)
    if ext == _DOCX_EXT:
        return _extract_docx(blob)
    if ext == _PDF_EXT:
        return _extract_pdf(blob)
    accepted = ", ".join(sorted(SUPPORTED_EXTENSIONS))
    raise ValueError(
        f"Format non pris en charge : « {filename} ». Formats acceptés : {accepted}."
    )


def combine_documents(files: list[tuple[str, bytes]]) -> str:
    """Extract and concatenate several documents into one labelled block.

    Each document is prefixed with a ``===== Document : <name> =====`` header so
    the LLM can tell them apart. The result is capped at ``MAX_TOTAL_CHARS``.
    Empty / text-less documents are skipped. Raises ``ValueError`` on too many
    files, oversized files, or unreadable formats.
    """
    if not files:
        return ""
    if len(files) > MAX_FILES:
        raise ValueError(f"Trop de documents : maximum {MAX_FILES}.")

    chunks: list[str] = []
    for name, blob in files:
        if len(blob) > MAX_FILE_BYTES:
            mb = MAX_FILE_BYTES // (1024 * 1024)
            raise ValueError(f"Le document « {name} » dépasse la taille maximale de {mb} Mo.")
        text = extract_text(name, blob).strip()
        if not text:
            continue
        chunks.append(f"===== Document : {name} =====\n{text}")

    combined = "\n\n".join(chunks)
    if len(combined) > MAX_TOTAL_CHARS:
        combined = combined[:MAX_TOTAL_CHARS].rstrip() + "\n\n[... documents tronqués ...]"
    return combined
