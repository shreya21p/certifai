from docling.document_converter import DocumentConverter

def parse_document(file_path: str) -> str:
    """
    Parses a document (PDF, etc.) using Docling and returns Markdown text.
    """
    try:
        converter = DocumentConverter()
        result = converter.convert(file_path)
        return result.document.export_to_markdown()
    except Exception as e:
        raise Exception(f"Docling parsing failed: {e}")
