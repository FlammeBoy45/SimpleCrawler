import asyncio
from collections import deque
from datetime import datetime, timezone
import threading
from types import SimpleNamespace

from modeles import PageAnalysee, RequeteURL
from orchestrateur import Orchestrateur
import main as application
import signal


def test_arret_ctrl_c_compte_pages_et_interrompt_la_propagation(capsys):
    orchestrateur = Orchestrateur.__new__(Orchestrateur)
    orchestrateur.config = SimpleNamespace(concurrence_max=1, profondeur_max=1)
    orchestrateur._arret_demande = threading.Event()

    class FauxPlanificateur:
        def __init__(self):
            self.file_attente = deque([RequeteURL(url="https://example.com/")])
            self.liens_ajoutes = []

        def est_vide(self):
            return not self.file_attente

        def suivant(self):
            return self.file_attente.popleft() if self.file_attente else None

        def ajouter(self, requete):
            self.liens_ajoutes.append(requete)
            orchestrateur.demander_arret()
            return True

    class FauxTelechargeur:
        async def telecharger(self, url):
            return SimpleNamespace(code_statut=200, erreur=None)

    class FauxAnalyseur:
        def analyser(self, page_brute):
            return PageAnalysee(
                url="https://example.com/",
                titre="Page",
                liens_extraits=[
                    "https://example.com/1",
                    "https://example.com/2",
                ],
                date_extraction=datetime.now(timezone.utc),
            )

    class FauxPipeline:
        def __init__(self):
            self.pages_sauvegardees = 0
            self.ferme = False

        def sauvegarder(self, page):
            self.pages_sauvegardees += 1

        def fermer(self):
            self.ferme = True

    orchestrateur.planificateur = FauxPlanificateur()
    orchestrateur.telechargeur = FauxTelechargeur()
    orchestrateur.analyseur = FauxAnalyseur()
    orchestrateur.pipeline = FauxPipeline()

    asyncio.run(orchestrateur.executer())

    sortie = capsys.readouterr().out
    assert "Pages crawlées : 1" in sortie
    assert "Crawl interrompu proprement" in sortie
    assert len(orchestrateur.planificateur.liens_ajoutes) == 1
    assert orchestrateur.pipeline.pages_sauvegardees == 1
    assert orchestrateur.pipeline.ferme


def test_main_intercepte_plusieurs_sigint_sans_exception(monkeypatch):
    class FauxOrchestrateur:
        instance = None

        def __init__(self, config):
            self.arrets_demandes = 0
            FauxOrchestrateur.instance = self

        def demander_arret(self):
            self.arrets_demandes += 1

        async def executer(self):
            pass

    def faux_run(coroutine):
        try:
            signal.raise_signal(signal.SIGINT)
            signal.raise_signal(signal.SIGINT)
        finally:
            coroutine.close()

    monkeypatch.setattr(application, "Orchestrateur", FauxOrchestrateur)
    monkeypatch.setattr(application.asyncio, "run", faux_run)
    monkeypatch.setattr("sys.argv", ["main.py", "https://example.com/"])

    application.main()

    assert FauxOrchestrateur.instance.arrets_demandes == 2
