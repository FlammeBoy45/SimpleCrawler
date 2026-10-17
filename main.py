# main.py

import argparse
import asyncio
import logging
import os
import signal
import sys

from configuration import Configuration
from orchestrateur import Orchestrateur


def _configurer_logs(verbeux: bool) -> None:
    # Évite les UnicodeEncodeError (emojis) quand la sortie est redirigée sous
    # Windows (cp1252) : on force l'UTF-8.
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(
        level=logging.DEBUG if verbeux else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # httpx journalise chaque requête en INFO : trop bavard.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _supprimer_etat(chemin_db: str) -> None:
    """Efface la base de résultats et la base d'état du planificateur."""
    base = os.path.splitext(chemin_db)[0]
    for fichier in (chemin_db, base + "_etat.db"):
        for suffixe in ("", "-wal", "-shm"):
            try:
                os.remove(fichier + suffixe)
            except FileNotFoundError:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "ALEXIA-BF — Analyse en Ligne et EXploration pour l’Investigation "
            "et l’Archivage au Burkina Faso"
        )
    )
    parser.add_argument("url", help="URL de départ du crawl")
    parser.add_argument("--profondeur", type=int, default=3, help="profondeur maximale (défaut : 3)")
    parser.add_argument("--concurrence", type=int, default=5, help="téléchargements simultanés (défaut : 5)")
    parser.add_argument("--delai", type=float, default=0.5,
                        help="délai minimal entre deux requêtes vers un même site, en secondes (défaut : 0.5)")
    parser.add_argument("--externes", action="store_true", help="suivre aussi les liens vers d'autres domaines")
    parser.add_argument("--ignorer-robots", action="store_true",
                        help="ne pas consulter robots.txt (par défaut, il est respecté)")
    parser.add_argument("--db", default="resultats_crawl.db", help="fichier de résultats SQLite")
    parser.add_argument("--repartir-de-zero", action="store_true",
                        help="supprime les résultats et l'état précédents avant de commencer")
    parser.add_argument("-v", "--verbeux", action="store_true", help="journal détaillé")
    args = parser.parse_args()

    _configurer_logs(args.verbeux)

    if args.repartir_de_zero:
        _supprimer_etat(args.db)
        print(f"🧹 Résultats et état précédents supprimés ({args.db}).")

    config = Configuration(
        urls_initiales=[args.url],
        profondeur_max=args.profondeur,
        respecter_robots_txt=not args.ignorer_robots,
        suivre_liens_externes=args.externes,
        concurrence_max=args.concurrence,
        delai_aspiration_sec=args.delai,
        chemin_db=args.db,
    )

    orchestrateur = Orchestrateur(config)

    def _sur_sigint(_signum, _frame) -> None:
        if orchestrateur.arret_demande:
            raise KeyboardInterrupt  # deuxième Ctrl+C : arrêt immédiat
        print("\n🛑 Arrêt demandé : fin des requêtes en cours "
              "(Ctrl+C à nouveau pour forcer)...")
        orchestrateur.demander_arret()

    gestionnaire_precedent = signal.signal(signal.SIGINT, _sur_sigint)
    try:
        asyncio.run(orchestrateur.executer())
    except KeyboardInterrupt:
        print("\n🛑 Arrêt forcé.")
    finally:
        signal.signal(signal.SIGINT, gestionnaire_precedent)


if __name__ == "__main__":
    main()
