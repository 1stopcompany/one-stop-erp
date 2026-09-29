import os

from django.core.exceptions import ValidationError

# Documents and drawings only -- no executables/scripts -- and a size cap so one upload
# can't fill the disk (CAD drawings and scanned tender packs are big, hence 50 MB).
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv",
    ".jpg", ".jpeg", ".png", ".tif", ".tiff",
    ".dwg", ".dxf", ".rvt", ".ifc", ".zip", ".rar",
}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def validate_document_file(uploaded):
    ext = os.path.splitext(uploaded.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"'{ext or 'no extension'}' files are not accepted. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )
    if uploaded.size > MAX_UPLOAD_BYTES:
        raise ValidationError(f"File is {uploaded.size / 1024 / 1024:.0f} MB; the limit is {MAX_UPLOAD_BYTES // 1024 // 1024} MB.")
