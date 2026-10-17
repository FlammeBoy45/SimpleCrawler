# tests/test_telechargeur.py
import asyncio

from configuration import Configuration
from telechargeur.telechargeur import Telechargeur


def test_telechargeur_erreur_url_invalide():
    config = Configuration(delai_aspiration_sec=0.0)
    telechargeur = Telechargeur(config)
    
    # URL invalide / domaine inexistant
    page = asyncio.run(
        telechargeur.telecharger("https://domaine-inexistant-123456789.com")
    )
    assert page.code_statut == 0
    assert page.erreur is not None