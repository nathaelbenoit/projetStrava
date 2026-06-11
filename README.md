# Projet Strava - Analyse et Visualisation d'Activites Sportives

## Description

Application Python permettant de traiter automatiquement les donnees d'activites exportees depuis Strava (fichiers `.fit.gz` et `.gpx.gz`), de les convertir en CSV standardise, puis de les visualiser dans un tableau de bord Power BI personnalise.

Le pipeline complet s'execute en un clic : decompression, conversion, et ouverture automatique du dashboard.

---

## Fonctionnalites

- **Decompression automatique** des fichiers `.gz` exportes depuis Strava
- **Conversion FIT vers CSV** avec extraction des donnees GPS, vitesse, frequence cardiaque, cadence et altitude
- **Conversion GPX vers CSV** avec calcul de distance (formule de Haversine) et vitesse instantanee
- **Colonnes standardisees** : `timestamp`, `position_lat_deg`, `position_long_deg`, `altitude`, `distance`, `speed`, `speed_kmh`, `heart_rate`, `enhanced_altitude`, `enhanced_speed`, `cadence`
- **Parsing GPX tolerant** : injection automatique des espaces de noms XML manquants (Garmin, etc.)
- **Ouverture automatique** du fichier Power BI apres traitement
- **Compatible Windows, macOS et Linux**
- **Executable Windows** fourni (via PyInstaller), aucune installation Python requise

---

## Architecture du projet

```
projetStrava/
├── stravaAuto.py          # Script principal Python (~558 lignes)
├── StravaApp.exe           # Executable Windows compile (PyInstaller)
├── myStrava.pbix           # Tableau de bord Power BI
├── track.csv               # Fichier CSV genere (sortie du script)
├── activities/             # Dossier des activites Strava compressees (.gz)
│   ├── <activite>.fit.gz
│   ├── <activite>.gpx.gz
│   └── ...
└── README.md
```

### Pipeline de traitement

```
activities/*.gz  -->  Decompression  -->  .fit / .gpx  -->  Conversion  -->  track.csv  -->  Power BI
```

1. Le script identifie le dernier fichier `.gz` (tri par nom decroissant) dans `activities/`
2. Decompresse le fichier en `.fit` ou `.gpx`
3. Convertit en `track.csv` avec colonnes standardisees (delimiteur `;`)
4. Ouvre automatiquement le dashboard Power BI

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Langage principal | Python 3.6+ |
| Parsing FIT | `fitparse` |
| Parsing GPX | `gpxpy` |
| Visualisation | Power BI Desktop |
| Distribution | PyInstaller (`.exe` Windows) |

---

## Prerequis

- **Python 3.6+** (si execution depuis le code source)
- **Power BI Desktop** (pour la visualisation)
- **Un export de donnees Strava** : connectez-vous sur Strava > Parametres > Mon compte > Telecharger vos donnees

---

## Installation

### Option A : Depuis le code source

```bash
# 1. Cloner le depot
git clone https://github.com/nathaelbenoit/projetStrava.git
cd projetStrava

# 2. Installer les dependances
pip install fitparse gpxpy
```

### Option B : Executable Windows

Aucune installation necessaire. Utilisez directement `StravaApp.exe`.

---

## Preparation des donnees

1. Rendez-vous sur [Strava](https://www.strava.com) > **Parametres** > **Mon compte** > **Telecharger vos donnees**
2. Extrayez l'archive recue
3. Copiez le dossier `activities/` (contenant les fichiers `.gz`) dans le repertoire du projet
4. Conservez egalement les fichiers `activities.csv` et `reactions.csv` si besoin

---

## Utilisation

### Execution simple

```bash
# Depuis Python
python stravaAuto.py

# Ou directement l'executable
./StravaApp.exe
```

### Avec un fichier Power BI personnalise

```bash
python stravaAuto.py --pbix "chemin/vers/mon_dashboard.pbix"
```

### Workflow typique

1. Placez vos fichiers d'activites compresses dans `activities/`
2. Lancez le script ou l'executable
3. Le fichier `track.csv` est genere automatiquement
4. Power BI s'ouvre avec les donnees actualisees
5. Actualisez les sources de donnees dans Power BI si necessaire

---

## Codes de sortie

| Code | Signification |
|------|---------------|
| `0` | Succes |
| `2` | Aucun fichier `.gz` trouve dans `activities/` |
| `3` | Erreur de permission (fichier CSV verrouille) |
| `4` | Erreur de conversion (format non supporte ou fichier corrompu) |

---

## Details techniques

### Conversion FIT
- Les coordonnees GPS sont converties de semicercles en degres (`× 180 / 2^31`)
- La vitesse est extraite en m/s puis convertie en km/h
- Si aucun message `record` n'est trouve, un export "long format" de tous les messages est tente en fallback

### Conversion GPX
- La distance cumulative est calculee via la **formule de Haversine**
- La vitesse instantanee est derivee du delta temps/distance entre points consecutifs
- La frequence cardiaque et la cadence sont extraites depuis les extensions Garmin (`gpxtpx:TrackPointExtension`)
- Le parser gere automatiquement les espaces de noms XML manquants

### Format CSV de sortie
- Delimiteur : `;` (point-virgule)
- Encodage : UTF-8
- Valeurs manquantes remplacees par `0`

---

## Axes d'amelioration

### Fonctionnalites

- **Traitement par lot** : permettre la conversion de toutes les activites d'un coup (pas seulement la derniere)
- **Support TCX** : ajouter la conversion des fichiers `.tcx` (mentionne dans le code mais non implemente)
- **Filtrage par type d'activite** : course, velo, natation, etc.
- **Historique des conversions** : garder un log des fichiers deja traites pour eviter les doublons
- **Selection interactive** : proposer a l'utilisateur de choisir quelle activite convertir

### Architecture et qualite de code

- **Separation en modules** : decouper `stravaAuto.py` en plusieurs fichiers (`parsers/fit.py`, `parsers/gpx.py`, `utils.py`, `main.py`)
- **Tests unitaires** : ajouter des tests avec `pytest` pour les fonctions de conversion et de calcul (Haversine, semicercles, etc.)
- **Typage strict** : ajouter des annotations de type completes et valider avec `mypy`
- **Gestion des logs** : remplacer les `print` implicites par le module `logging` avec niveaux configurable
- **Configuration externe** : utiliser un fichier `config.yaml` ou `.env` pour les parametres (chemin Power BI, dossier activities, etc.)

### Performance et robustesse

- **Gestion memoire** : traitement en streaming pour les fichiers volumineux au lieu de charger toutes les lignes en memoire
- **Validation des donnees** : verifier la coherence des donnees GPS (coordonnees aberrantes, timestamps non ordonnees)
- **Reprise sur erreur** : en cas d'echec, reprendre la ou le traitement s'est arrete
- **Support multi-format d'export** : generer aussi du JSON, Parquet, ou Excel en plus du CSV

### Experience utilisateur

- **Interface graphique** : ajouter une GUI simple (Tkinter, PyQt ou webapp Flask/Streamlit) pour les utilisateurs non techniques
- **Barre de progression** : afficher l'avancement du traitement pour les gros volumes
- **Notifications** : notifier l'utilisateur quand le traitement est termine
- **Documentation Power BI** : fournir un guide pour configurer et personnaliser le dashboard

### DevOps et distribution

- **CI/CD** : mettre en place GitHub Actions pour les tests automatiques et la generation de l'executable
- **Packaging Python** : creer un vrai package installable via `pip install` avec `pyproject.toml`
- **Versioning** : adopter le semantic versioning et maintenir un `CHANGELOG.md`
- **Docker** : proposer une image Docker pour l'execution sans installation locale

### Donnees et analyses

- **Statistiques agregees** : generer des metriques globales (distance totale, denivele cumule, temps total, etc.)
- **Detection de zones** : identifier les segments d'effort, pauses, et zones de frequence cardiaque
- **Comparaison d'activites** : permettre de comparer plusieurs activites entre elles
- **Export vers d'autres plateformes** : integration avec Google Sheets, Notion, ou d'autres outils d'analyse

---

## Contribution

Les contributions sont les bienvenues ! Pour contribuer :

1. Forkez le projet
2. Creez une branche (`git checkout -b feature/ma-fonctionnalite`)
3. Committez vos changements (`git commit -m "Ajout de ma fonctionnalite"`)
4. Poussez la branche (`git push origin feature/ma-fonctionnalite`)
5. Ouvrez une Pull Request

---
