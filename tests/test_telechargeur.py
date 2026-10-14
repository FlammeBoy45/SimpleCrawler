# tests/test_telechargeur.py
from sharingan_crawl.configuration import Configuration
from sharingan_crawl.telechargeur.telechargeur import Telechargeur


def test_telechargeur_erreur_url_invalide():
    config = Configuration(delai_aspiration_sec=0.0)
    telechargeur = Telechargeur(config)
    
    # URL invalide / domaine inexistant
    page = telechargeur.telecharger("https://domaine-inexistant-123456789.com")
    assert page.code_statut == 0
    assert page.erreur is not None