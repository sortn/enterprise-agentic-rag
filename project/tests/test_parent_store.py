from db.parent_store_manager import ParentStoreManager
from ingestion.models import ParentChunk


class StoreSettings:
    def __init__(self, path):
        self.parent_store_dir = path


def test_parent_store_round_trip_and_delete(tmp_path):
    store = ParentStoreManager(StoreSettings(tmp_path / "parents"))
    doc_id = "a" * 24
    parent = ParentChunk(
        parent_id=f"{doc_id}-p0",
        doc_id=doc_id,
        source="policy.txt",
        heading="第一章",
        locator="section:1",
        text="完整父块",
    )

    assert store.save_document(doc_id, [parent]) == 1
    assert store.get(parent.parent_id)["text"] == "完整父块"
    assert store.has_document(doc_id)
    store.delete_document(doc_id)
    assert not store.has_document(doc_id)
