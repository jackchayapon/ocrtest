from tempfile import SpooledTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from sqlalchemy import select

from app.core.errors import AppError
from app.core.native_memory import release_native_memory
from app.db.models import GlobalField, TestCase, now
from app.repositories.dataset_repository import DatasetRepository


def escape_label(text):
    """Reversible TSV: decode backslash escapes (\\, \t, \r, \n), in one pass."""
    return text.replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")


class DatasetService:
    def __init__(self, cases):
        self.cases = cases
        self.repository = DatasetRepository(cases.repository.session)

    def samples(self, category, document, limit, offset, document_type=None):
        total, records = self.repository.samples(category, document, limit, offset, document_type)
        return dict(
            total=total,
            items=[
                dict(
                    id=c.id,
                    test_case_id=getattr(c, "test_case_id", c.id),
                    global_field_id=getattr(c, "global_field_id", None),
                    field_index=getattr(c, "field_index", None),
                    document_id=c.document_id,
                    filename=c.document.filename,
                    document_type_id=c.document.document_type_id,
                    document_type_name=c.document.business_type.name if c.document.business_type else None,
                    page_number=c.page_number,
                    roi=c.roi,
                    ground_truth_raw=c.ground_truth_raw,
                    updated_at=c.updated_at,
                    source_sha256=c.document.sha256,
                    categories=[tag.code for tag in c.categories],
                    source_available=self.cases.storage.exists(c.document.storage_key),
                )
                for c in records
            ],
        )

    def bulk_exclude(self, case_ids, field_ids):
        session = self.repository.session
        requested = len(set(case_ids)) + len(set(field_ids))
        found = []
        try:
            for model, ids in ((TestCase, set(case_ids)), (GlobalField, set(field_ids))):
                found.extend(session.scalars(select(model).where(model.id.in_(ids)).with_for_update()))
            already = sum(r.dataset_excluded_at is not None for r in found)
            stamp = now()
            for record in found:
                if record.dataset_excluded_at is None:
                    record.dataset_excluded_at = stamp
            session.commit()
            return dict(requested=requested, excluded=len(found) - already,
                        already_excluded=already, not_found=requested - len(found))
        except Exception:
            session.rollback()
            raise

    def export(self, ids, global_field_ids=()):
        records = sorted(self.repository.selected(ids) + self.repository.selected_fields(global_field_ids), key=lambda c: (getattr(c, "test_case_id", c.id), getattr(c, "field_index", 0)))
        for case in records:
            if not self.cases.storage.exists(case.document.storage_key):
                raise self.missing_source(case.id)
        # Large multi-Field archives spill early to the existing temporary disk.
        # cgroup accounting still includes that file cache; no data is dropped.
        output = SpooledTemporaryFile(max_size=512 * 1024, mode="w+b")

        # Generated names only, fixed ZIP metadata, sorted case IDs. Nothing persists in StorageService.
        def write(archive, name, data):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            # ZipFile.writestr compresses a full high-entropy PNG in one call,
            # allocating another multi-MB bytes object before the spool copies it.
            # Feed the same lossless bytes in bounded chunks instead.
            with archive.open(info, "w") as member:
                view = memoryview(data)
                for offset in range(0, len(view), 64 * 1024):
                    member.write(view[offset:offset + 64 * 1024])

        image = source = image_key = None
        try:
            labels, byte_count = [], 0
            with ZipFile(output, "w") as archive:
                for index, case in enumerate(records, 1):
                    key = (case.document.id, case.page_number)
                    if key != image_key:
                        # Keep one decoded page for adjacent Field exports.
                        # Close it BEFORE allocating a different source/page.
                        if image is not None:
                            image.close()
                        image = source = None
                        try:
                            source, _, _ = self.cases.page_image(case.document, case.page_number)
                        except AppError as exc:
                            if exc.status_code == 404:
                                raise self.missing_source(case.id) from None
                            raise
                        # A bounded file read can leave freed native chunks in
                        # the allocator. Return those pages before decoding the
                        # next large owner, rather than after ZIP cache growth.
                        if len(source) >= 512 * 1024:
                            release_native_memory()
                        image = self.cases.images.open(source)
                        image_key = key
                    crop = self.cases.images.canonical_crop(image, case.roi, encoded_source=source)
                    byte_count += len(crop.png)
                    if byte_count > 512 * 1024 * 1024:
                        raise AppError("Export exceeds 512 MB; select fewer samples", 413)
                    # Measured allocation boundary: only large encoded crops,
                    # not each small Field. Pixels and ZIP contents are unchanged.
                    if len(crop.png) >= 512 * 1024:
                        release_native_memory()
                    name = f"images/{index:06d}.png"
                    write(archive, f"dataset/{name}", crop.png)
                    del crop
                    labels.append(f"{name}\t{escape_label(case.ground_truth_raw)}\n")
                write(archive, "dataset/label.txt", "".join(labels).encode("utf-8"))
            output.seek(0)
            return output
        except Exception:
            output.close()
            raise
        finally:
            if image is not None:
                image.close()

    @staticmethod
    def missing_source(case_id):
        return AppError(
            f"ไม่พบไฟล์ต้นฉบับของตัวอย่าง {case_id} ใน storage จึงส่งออกไม่ได้ "
            "กรุณาคืนไฟล์จาก backup หรืออัปโหลดต้นฉบับและสร้างชุดทดสอบใหม่ที่ยืนยัน GT แล้ว", 409
        )
