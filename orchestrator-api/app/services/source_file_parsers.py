from __future__ import annotations

from pathlib import Path

from app.schemas.dataset_rebuild import ParsedChunk, SUPPORTED_RAG_EXTENSIONS


MAX_RAG_EXTRACTED_CHARS = 60_000
MAX_PDF_PAGES = 100
MAX_DOCX_PARAGRAPHS = 2000


class SourceParseError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parse_rag_document(path: Path, *, safe_path: str) -> list[ParsedChunk]:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_RAG_EXTENSIONS:
        raise SourceParseError("unsupported_document_type")
    if suffix in {".md", ".txt"}:
        text = path.read_text(encoding="utf-8-sig")[:MAX_RAG_EXTRACTED_CHARS]
    elif suffix == ".pdf":
        text = _read_pdf_text(path)
    else:
        text = _read_docx_text(path)
    if not text.strip():
        code = "pdf_no_extractable_text" if suffix == ".pdf" else "docx_no_extractable_text" if suffix == ".docx" else "document_no_extractable_text"
        raise SourceParseError(code)
    return _chunk_text(text, safe_path=safe_path, extension=suffix)


def _read_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = reader.pages[:MAX_PDF_PAGES]
        return "\n".join(page.extract_text() or "" for page in pages)[:MAX_RAG_EXTRACTED_CHARS]
    except Exception as exc:
        raise SourceParseError("pdf_parse_failed") from exc


def _read_docx_text(path: Path) -> str:
    try:
        from docx import Document

        document = Document(str(path))
        paragraphs = [paragraph.text for paragraph in document.paragraphs[:MAX_DOCX_PARAGRAPHS]]
        return "\n".join(paragraphs)[:MAX_RAG_EXTRACTED_CHARS]
    except Exception as exc:
        raise SourceParseError("docx_parse_failed") from exc


def _chunk_text(text: str, *, safe_path: str, extension: str) -> list[ParsedChunk]:
    normalized = " ".join(text.split())
    chunks: list[ParsedChunk] = []
    size = 1200
    for index, start in enumerate(range(0, len(normalized), size)):
        chunk_text = normalized[start : start + size]
        if chunk_text:
            chunks.append(
                ParsedChunk(
                    chunk_index=index,
                    chunk_text=chunk_text,
                    citation={"safe_location_path": safe_path},
                    metadata={"parser_extension": extension},
                )
            )
    return chunks
