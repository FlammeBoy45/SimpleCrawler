import asyncio
from collections import deque
from datetime import datetime, timezone
import threading
from types import SimpleNamespace

import pytest

from modeles import PageAnalysee, RequeteURL
from orchestrateur import Orchestrateur, Statistiques
import main as application
import signal


def test_arret_ctrl_c_compte_pages_et_interrompt_la_propagation(capsys):
    orchestrateur = Orchestrateur.__new__(Orchestrateur)
    orchestrateur.config = SimpleNamespace(concurrence_max=1, profondeur_max=1)
    orchestrateur._arret_demande = threading.Event()
    orchestrateur._actifs = 0
    orchestrateur.stats = Statistiques()

    class FauxPlanificateur:
        def __init__(self):
            self.file_attente = deque([RequeteURL(url="https://example.com/")])
            self.liens_ajoutes = []
            self.ferme = False

        def est_vide(self):
            return not self.file_attente

        def suivant(self):
            return self.file_attente.popleft() if self.file_attente else None

        def ajouter(self, requete):
            self.liens_ajoutes.append(requete)
            orchestrateur.demander_arret()
            return True

        def fermer(self):
            self.ferme = True

    class FauxRobots:
        async def verifier(self, url):
            return True

        async def delai_crawl(self, url):
            return None

        async def fermer(self):
            self.ferme = True

        def __init__(self):
            self.ferme = False

    class FauxTelechargeur:
        async def telecharger(self, url, delai_min=None):
            return SimpleNamespace(code_statut=200, erreur=None, url_finale=url)

        async def fermer(self):
            self.ferme = True

        def __init__(self):
            self.ferme = False

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
    orchestrateur.robots = FauxRobots()
    orchestrateur.analyseur = FauxAnalyseur()
    orchestrateur.pipeline = FauxPipeline()

    asyncio.run(orchestrateur.executer())

    sortie = capsys.readouterr().out
    assert "Pages crawlées  : 1" in sortie
    assert "Crawl interrompu proprement" in sortie
    assert len(orchestrateur.planificateur.liens_ajoutes) == 1
    assert orchestrateur.pipeline.pages_sauvegardees == 1
    assert orchestrateur.pipeline.ferme
    assert orchestrateur.telechargeur.ferme
    assert orchestrateur.robots.ferme
    assert orchestrateur.planificateur.ferme


def test_main_second_sigint_force_arret_et_restaure_gestionnaire(monkeypatch, capsys):
    class FauxOrchestrateur:
        instance = None

        def __init__(self, config):
            self.arrets_demandes = 0
            FauxOrchestrateur.instance = self

        def demander_arret(self):
            self.arrets_demandes += 1

        @property
        def arret_demande(self):
            return self.arrets_demandes > 0

        async def executer(self):
            pass

    gestionnaire_precedent = signal.getsignal(signal.SIGINT)

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

    assert FauxOrchestrateur.instance.arrets_demandes == 1
    assert "Arrêt forcé" in capsys.readouterr().out
    assert signal.getsignal(signal.SIGINT) is gestionnaire_precedent


def test_executer_ferme_les_ressources_si_une_exception_survient():
    orchestrateur = Orchestrateur.__new__(Orchestrateur)
    orchestrateur.config = SimpleNamespace(concurrence_max=1)
    orchestrateur.stats = Statistiques()

    class RessourceAsync:
        def __init__(self):
            self.fermee = False

        async def fermer(self):
            self.fermee = True

    class RessourceSync:
        def __init__(self):
            self.fermee = False

        def fermer(self):
            self.fermee = True

    orchestrateur.telechargeur = RessourceAsync()
    orchestrateur.robots = RessourceAsync()
    orchestrateur.pipeline = RessourceSync()
    orchestrateur.planificateur = RessourceSync()

    async def echouer():
        raise RuntimeError("erreur de test")

    orchestrateur._travailleur = echouer

    with pytest.raises(RuntimeError, match="erreur de test"):
        asyncio.run(orchestrateur.executer())

    assert orchestrateur.telechargeur.fermee
    assert orchestrateur.robots.fermee
    assert orchestrateur.pipeline.fermee
    assert orchestrateur.planificateur.fermee


def test_main_sans_url_signale_file_vide_et_ne_demarre_pas(
    monkeypatch, capsys, tmp_path
):
    def orchestrateur_inattendu(_config):
        raise AssertionError("ne doit pas démarrer")

    monkeypatch.setattr("sys.argv", ["main.py", "--db", str(tmp_path / "test.db")])
    monkeypatch.setattr(
        application, "Orchestrateur", orchestrateur_inattendu
    )

    application.main()

    sortie = capsys.readouterr().out
    assert "Aucune URL en attente dans la file" in sortie
    assert "Veuillez ajouter une URL de départ" in sortie


def test_main_sans_url_reprend_la_file_persistante(monkeypatch, tmp_path):
    from configuration import Configuration
    from modeles import RequeteURL
    from planificateur.planificateur import Planificateur

    chemin_db = str(tmp_path / "test.db")
    planificateur = Planificateur(
        Configuration(urls_initiales=["https://example.com/"]),
        db_path=chemin_db,
    )
    planificateur.ajouter(
        RequeteURL(url="https://example.com/page1", profondeur=1)
    )
    planificateur.fermer()

    class FauxOrchestrateur:
        config = None

        def __init__(self, config):
            FauxOrchestrateur.config = config

        async def executer(self):
            pass

    monkeypatch.setattr(application, "Orchestrateur", FauxOrchestrateur)
    monkeypatch.setattr("sys.argv", ["main.py", "--db", chemin_db])
    monkeypatch.setattr(application.asyncio, "run", lambda coroutine: coroutine.close())

    application.main()

    assert FauxOrchestrateur.config.urls_initiales == []

    reprise = Planificateur(Configuration(urls_initiales=[]), db_path=chemin_db)
    try:
        assert any(
            requete.url == "https://example.com/page1"
            for requete in reprise.file_attente
        )
    finally:
        reprise.fermer()
