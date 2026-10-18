# ALEXIA-BF

**Analyse en Ligne et EXploration pour l’Investigation et l’Archivage au Burkina Faso**

ALEXIA-BF est un outil Python d’exploration de sites web et d’archivage local des
informations extraites. Il parcourt les pages à partir d’une URL de départ,
repère leur titre et leurs liens, puis enregistre les résultats dans une base
SQLite.

## Fonctionnalités

- Téléchargement asynchrone des pages avec un nombre limité de requêtes simultanées.
- Extraction du titre HTML et des liens HTTP/HTTPS, avec suppression des doublons.
- Limitation de la profondeur et du parcours au domaine de départ.
- Enregistrement des résultats et de la file d’attente dans SQLite.
- Reprise des URL en attente lors d’une exécution ultérieure.
- Arrêt avec `Ctrl+C` : le lot de requêtes en cours se termine, puis le programme
  affiche les métriques avant de quitter.

> **Respect des sites :** la commande actuelle ne consulte pas `robots.txt`.
> Avant tout crawl, vérifiez les conditions d’utilisation et les règles du site,
> obtenez les autorisations nécessaires et limitez la charge imposée au serveur.

## Prérequis

- Python 3.11 ou version ultérieure
- Accès réseau pour télécharger les pages

Depuis PowerShell, installez la dépendance de l’application :

```powershell
py -m pip install httpx
```

Pour lancer les tests, installez également `pytest` :

```powershell
py -m pip install pytest
```

## Lancer un crawl

À la racine du projet, indiquez l’URL de départ :

```powershell
py .\main.py https://example.bf/
```

L’aide de la commande est disponible avec :

```powershell
py .\main.py --help
```

La commande configure actuellement une profondeur maximale de 3, une concurrence
de 5 requêtes et un délai de 0,5 seconde. Les liens externes ne sont pas suivis.
Appuyez une fois sur `Ctrl+C` pour demander l’arrêt propre du crawl.

## Résultats et reprise

Le programme crée `resultats_crawl.db` dans le répertoire courant. Cette base
SQLite contient les pages archivées (URL, titre, date d’extraction, liens
extraits et données associées) ainsi que les URL en attente.

Les informations archivées sont les métadonnées et les liens extraits : le HTML
complet des pages n’est pas conservé. Gardez la base de données pour reprendre
une file d’attente après l’arrêt du programme. Pour repartir de zéro, arrêtez
l’application puis supprimez explicitement `resultats_crawl.db`.

## Tests

Depuis la racine du projet, exécutez :

```powershell
py -m pytest
```

## Organisation du projet

- [analyseur/](./analyseur/) — Extraction des titres et des liens HTML
- [pipeline/](./pipeline/) — Enregistrement SQLite des pages
- [planificateur/](./planificateur/) — File d’attente, dédoublonnage et profondeur
- [telechargeur/](./telechargeur/) — Téléchargement asynchrone des pages
- [tests/](./tests/) — Tests automatisés
- [configuration.py](./configuration.py) — Paramètres du crawl
- [modeles.py](./modeles.py) — Structures de données
- [orchestrateur.py](./orchestrateur.py) — Coordination du crawl et rapport de fin
- [main.py](./main.py) — Point d’entrée en ligne de commande
