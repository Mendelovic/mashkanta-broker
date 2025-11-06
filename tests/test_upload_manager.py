import io

from fastapi import UploadFile
from starlette.datastructures import Headers

from app.services.upload_manager import cleanup_temp_paths, process_uploads


def test_process_uploads_assigns_ids_and_types():
    upload = UploadFile(
        filename="Payslip_July.pdf",
        file=io.BytesIO(b"sample data"),
        headers=Headers({"content-type": "application/pdf"}),
    )

    result = process_uploads([upload])
    try:
        assert result.files_processed == 1
        assert result.documents
        document = result.documents[0]
        assert document.document_id
        assert document.document_type == "payslip"
    finally:
        cleanup_temp_paths(result.temp_paths)
