# tests/test_analyseur.py
from sharingan_crawl.modeles import PageBrute
from sharingan_crawl.analyseur.analyseur import Analyseur


def test_analyseur_extraction_titre_et_liens():
    html = "<html><head><title>Test Page</title></head><body><a href='/page2'>Lien</a></body></html>"
    page_brute = PageBrute(url="https://example.com", code_statut=200, contenu_html=html)
    
    analyseur = Analyseur()
    page_analysee = analyseur.analyser(page_brute)
    
    assert page_analysee.titre == "Test Page"
    assert "https://example.com/page2" in page_analysee.liens_extraits
    