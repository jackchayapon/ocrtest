from tempfile import SpooledTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from app.core.errors import AppError
from app.repositories.dataset_repository import DatasetRepository


def escape_label(text):
    """Reversible TSV: decode backslash escapes (\\, \t, \r, \n), in one pass."""
    return text.replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")


class DatasetService:
    def __init__(self, cases):
        self.cases = cases
        self.repository = DatasetRepository(cases.repository.session)

    def samples(self, category, document, limit, offset):
        total, records = self.repository.samples(category, document, limit, offset)
        return dict(
            total=total,
            items=[
                dict(
                    id=c.id,
                    document_id=c.document_id,
                    filename=c.document.filename,
                    page_number=c.page_number,
                    roi=c.roi,
                    ground_truth_raw=c.ground_truth_raw,
                    updated_at=c.updated_at,
                    source_sha256=c.document.sha256,
                    categories=[tag.code for tag in c.categories],
                )
                for c in records
            ],
        )

    def export(self, ids):
        records = self.repository.selected(ids)
        output = SpooledTemporaryFile(max_size=16 * 1024 * 1024, mode="w+b")

        # Generated names only, fixed ZIP metadata, sorted case IDs. Nothing persists in StorageService.
        def write(archive, name, data):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)

        try:
            labels, byte_count = [], 0
            with ZipFile(output, "w") as archive:
                for index, case in enumerate(records, 1):
                    source, _, _ = self.cases.page_image(case.document, case.page_number)
                    with self.cases.images.open(source) as image:
                        crop = self.cases.images.canonical_crop(image, case.roi)
                    byte_count += len(crop.png)
                    if byte_count > 512 * 1024 * 1024:
                        raise AppError("Export exceeds 512 MB; select fewer samples", 413)
                    name = f"images/{index:06d}.png"
                    write(archive, f"dataset/{name}", crop.png)
                    labels.append(f"{name}\t{escape_label(case.ground_truth_raw)}\n")
                write(archive, "dataset/label.txt", "".join(labels).encode("utf-8"))
            output.seek(0)
            return output
        except Exception:
            output.close()
            raise
