# tests/test_planificateur.py
from modeles import RequeteURL
from configuration import Configuration
from planificateur.planificateur import Planificateur


def test_planificateur_ajout_et_recuperation(tmp_path):
    config = Configuration(
        urls_initiales=["https://example.com/"],
        profondeur_max=2,
        respecter_robots_txt=False,
    )
    planificateur = Planificateur(config, db_path=str(tmp_path / "test.db"))

    req = RequeteURL(url="https://example.com/page1", profondeur=0)
    assert planificateur.ajouter(req) is True
    
    # Doublon
    assert planificateur.ajouter(req) is False

    suivant = planificateur.suivant()
    assert suivant is not None
    assert suivant.url == "https://example.com/page1"
    assert planificateur.est_vide() is True


def test_planificateur_profondeur_max(tmp_path):
    config = Configuration(profondeur_max=1, respecter_robots_txt=False)
    planificateur = Planificateur(config, db_path=str(tmp_path / "test.db"))

    req = RequeteURL(url="https://example.com/loin", profondeur=2)
    assert planificateur.ajouter(req) is False
    assert planificateur.est_vide() is True