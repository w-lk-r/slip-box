import os
import uuid

from fastapi import APIRouter, HTTPException

from clients import UPLOADS_BUCKET, s3
from models import PresignedFile, PresignRequest, PresignResponse

router = APIRouter()

PRESIGN_EXPIRES_SECONDS = 600


@router.post("/uploads/presign", response_model=PresignResponse)
def presign_uploads(req: PresignRequest):
    upload_id = uuid.uuid4().hex
    files = []
    for f in req.files:
        # basename strips any path components a client sent (e.g. a
        # webkitdirectory folder-relative path, or an attempted traversal) —
        # every upload lands flat under this batch's own prefix.
        filename = os.path.basename(f.filename)
        if not filename or not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=422, detail=f"{f.filename!r} is not a .pdf file")

        key = f"uploads/{upload_id}/{filename}"
        upload_url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": UPLOADS_BUCKET, "Key": key, "ContentType": "application/pdf"},
            ExpiresIn=PRESIGN_EXPIRES_SECONDS,
        )
        files.append(PresignedFile(filename=filename, key=key, upload_url=upload_url))

    return PresignResponse(upload_id=upload_id, files=files)
