# tests/test_pipeline.py
import os
from modeles import PageAnalysee
from pipeline.pipeline import PipelineSQLite


def test_pipeline_sqlite_sauvegarde(tmp_path):
    db_file = tmp_path / "test.db"
    pipeline = PipelineSQLite(str(db_file))
    
    page = PageAnalysee(
        url="https://example.com/test",
        titre="Titre Test",
        liens_extraits=["https://example.com/1"]
    )
    
    pipeline.sauvegarder(page)
    pipeline.fermer()
    
    assert os.path.exists(db_file)