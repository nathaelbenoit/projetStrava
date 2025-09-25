# -*- coding: utf-8 -*-
"""
strava_auto.py – Version simplifiée sans interface graphique (patché GPX + colonnes forcées)

Au lancement, le script :
1) Cherche le dernier fichier .gz (tri par NOM décroissant) dans ./activities/ (dossier à côté du script)
2) Le décompresse en .fit/.gpx/.tcx selon le contenu dans le dossier activities
3) Convertit en CSV (track.csv) dans le dossier du script
   - Pour FIT et GPX : colonnes forcées et valeurs manquantes -> 0
     "timestamp","position_lat_deg","position_long_deg","altitude",
     "distance","speed","speed_kmh","heart_rate","enhanced_altitude",
     "enhanced_speed","cadence"
4) Ouvre automatiquement un fichier Power BI si trouvé (priorité : myStrava.bi, sinon myStrava.pbix)

Utilisation simple :
  python strava_auto.py
Options (facultatives) :
  python strava_auto.py --pbix "chemin/vers/mon.pbix"

Dépendances nécessaires :
  - fitparse (pour FIT) : pip install fitparse
  - gpxpy (pour GPX) : pip install gpxpy
"""
from __future__ import annotations
import os
import sys
import csv
import gzip
import shutil
import traceback
import subprocess
import math
import re
from datetime import datetime
from pathlib import Path
import gpxpy
import gpxpy.gpx

# Dépendance externe
try:
    from fitparse import FitFile
except ImportError:
    FitFile = None

# ----------------------------- Chemins applicatifs --------------------------------
def get_app_dir() -> Path:
    """Dossier de l'application.
    - En .exe (PyInstaller) : dossier de l'exécutable
    - En script : dossier du fichier .py
    """
    if getattr(sys, "frozen", False):  # exécutable PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_activities_dir() -> Path:
    """Dossier des activités Strava gzippées (relatif à l'appli)."""
    return get_app_dir() / "activities"


# ------------------------- Utilitaires conversion / traitement --------------------
SEMICIRCLES_TO_DEGREES = 180 / (2**31)


def to_degrees(semicircles):
    if semicircles is None:
        return None
    try:
        return float(semicircles) * SEMICIRCLES_TO_DEGREES
    except Exception:
        return None


def to_float(x):
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def normalize_header_order(headers):
    priority = [
        "timestamp",
        "position_lat_deg",
        "position_long_deg",
        "altitude",
        "distance",
        "speed",
        "speed_kmh",
        "heart_rate",
        "enhanced_altitude",
        "enhanced_speed",
        "cadence",
    ]
    in_priority = [h for h in priority if h in headers]
    remaining = sorted([h for h in headers if h not in in_priority])
    return in_priority + remaining


def extract_record_rows(fit_path):
    fit = FitFile(fit_path)
    rows = []
    all_headers = set()
    for msg in fit.get_messages("record"):
        row = {}
        for data in msg:
            name = data.name
            value = data.value
            if name == "position_lat":
                row["position_lat_deg"] = to_degrees(value)
                all_headers.add("position_lat_deg")
                continue
            if name == "position_long":
                row["position_long_deg"] = to_degrees(value)
                all_headers.add("position_long_deg")
                continue
            if name == "speed":  # m/s
                sp = to_float(value)
                row["speed"] = sp
                all_headers.add("speed")
                if sp is not None:
                    row["speed_kmh"] = sp * 3.6
                all_headers.add("speed_kmh")
                continue
            if name == "timestamp":
                if isinstance(value, datetime):
                    row["timestamp"] = value.isoformat()
                else:
                    row["timestamp"] = str(value) if value is not None else None
                all_headers.add("timestamp")
                continue
            row[name] = value
            all_headers.add(name)
        rows.append(row)
    headers = normalize_header_order(all_headers)
    return rows, headers


def fallback_all_messages_long_format(fit_path):
    fit = FitFile(fit_path)
    rows = []
    for msg in fit.get_messages():
        msg_type = msg.name
        ts = None
        for d in msg:
            if d.name == "timestamp":
                v = d.value
                ts = v.isoformat() if isinstance(v, datetime) else (str(v) if v is not None else None)
                break
        for d in msg:
            name = d.name
            value = d.value
            if name == "position_lat":
                name = "position_lat_deg"
                value = to_degrees(value)
            elif name == "position_long":
                name = "position_long_deg"
                value = to_degrees(value)
            if name == "speed":
                rows.append(
                    {
                        "message_type": msg_type,
                        "timestamp": ts,
                        "field": "speed",
                        "value": value,
                    }
                )
                v = to_float(value)
                rows.append(
                    {
                        "message_type": msg_type,
                        "timestamp": ts,
                        "field": "speed_kmh",
                        "value": (v * 3.6) if v is not None else None,
                    }
                )
            else:
                rows.append(
                    {
                        "message_type": msg_type,
                        "timestamp": ts,
                        "field": name,
                        "value": value,
                    }
                )
    headers = ["message_type", "timestamp", "field", "value"]
    return rows, headers


def convert_fit_to_csv(fit_path, csv_path):
    """Convertit un .FIT en .CSV. Priorité aux messages 'record', sinon export long.
    Colonnes forcées : timestamp; position_lat_deg; position_long_deg; altitude; distance; speed; speed_kmh; heart_rate; enhanced_altitude; enhanced_speed; cadence.
    Les valeurs manquantes sont remplacées par 0.
    """
    if FitFile is None:
        raise RuntimeError(
            "Le module 'fitparse' n'est pas installé.\n"
            "Installez-le avec : pip install fitparse"
        )
    if not os.path.exists(fit_path):
        raise FileNotFoundError(f"Fichier FIT introuvable : {fit_path}")
    try:
        rows, _ = extract_record_rows(fit_path)
        if not rows:
            rows, _ = fallback_all_messages_long_format(fit_path)
        # Colonnes forcées
        forced_headers = [
            "timestamp",
            "position_lat_deg",
            "position_long_deg",
            "altitude",
            "distance",
            "speed",
            "speed_kmh",
            "heart_rate",
            "enhanced_altitude",
            "enhanced_speed",
            "cadence",
        ]
        Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=forced_headers, extrasaction="ignore", delimiter=';')
            writer.writeheader()
            for r in rows:
                out_row = {}
                for h in forced_headers:
                    v = r.get(h)
                    if v is None or v == "":
                        out_row[h] = 0
                    else:
                        out_row[h] = v
                writer.writerow(out_row)
    except Exception as e:
        raise RuntimeError(f"Erreur pendant la conversion : {e}\n{traceback.format_exc()}")

# ------------------------------ GPX: parse tolérant + conversion ------------------

def _parse_gpx_tolerant(gpx_path: str):
    """
    Parse GPX en ajoutant au besoin des espaces de noms (xmlns:...) manquants
    pour des préfixes utilisés (ex. gpxtpx).
    """
    with open(gpx_path, "r", encoding="utf-8") as f:
        xml = f.read()
    # 1) tentative normale
    try:
        return gpxpy.parse(xml)
    except Exception as e:
        if "unbound prefix" not in str(e):
            raise
    # 2) injecter les xmlns manquants dans la balise <gpx ...>
    m_root = re.search(r"<gpx\b[^>]*>", xml, flags=re.IGNORECASE)
    if not m_root:
        raise RuntimeError("GPX invalide : balise <gpx> introuvable.")
    root_tag = m_root.group(0)
    declared = set(p for p, _ in re.findall(r'xmlns:([A-Za-z_]\w*)\s*=\s*"[^"]*"', root_tag))
    used = set(re.findall(r'(?:(?<=</)|(?<=<)|(?<=\s))([A-Za-z_]\w*):[A-Za-z_]\w*', xml))
    missing = [p for p in used if p not in declared and p not in ("xml",)]
    if not missing:
        # si rien de manquant, relancer l’erreur d’origine
        raise
    NSMAP = {
        "gpxtpx":  "http://www.garmin.com/xmlschemas/TrackPointExtension/v1",
        # Ajoutez ici si nécessaire :
        "gpxx":    "http://www.garmin.com/xmlschemas/GpxExtensions/v3",
        "gpxtrkx": "http://www.garmin.com/xmlschemas/TrackStatsExtension/v1",
        # alias parfois rencontrés
        "ns2":     "http://www.garmin.com/xmlschemas/GpxExtensions/v3",
        "ns3":     "http://www.garmin.com/xmlschemas/TrackPointExtension/v1",
    }
    additions = " " + " ".join(
        f'xmlns:{p}="{NSMAP.get(p, f"urn:unknown:{p}")}"' for p in missing
    )
    fixed_root = root_tag[:-1] + additions + ">"
    xml_fixed = xml[:m_root.start()] + fixed_root + xml[m_root.end():]
    return gpxpy.parse(xml_fixed)


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Distance en mètres entre deux points (lat, lon) en degrés."""
    if None in (lat1, lon1, lat2, lon2):
        return 0.0
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _extract_hr_cad_from_extensions(point) -> tuple[int | None, int | None]:
    """
    Essaie d’extraire heart_rate (bpm) et cadence (rpm) depuis gpxtpx:TrackPointExtension.
    Gère gpxtpx:hr et gpxtpx:cad / gpxtpx:cadence.
    """
    hr = None
    cad = None
    try:
        for ext in (point.extensions or []):
            # ext est typiquement <extensions> ou un enfant, selon gpxpy
            children = list(getattr(ext, "iter", lambda: [])()) if hasattr(ext, "iter") else list(ext)
            if not children:
                children = list(ext)
            for child in children:
                tag = getattr(child, "tag", "")
                if tag and tag.endswith("TrackPointExtension"):
                    for node in list(child):
                        ntag = getattr(node, "tag", "")
                        text = (getattr(node, "text", None) or "").strip()
                        if not text:
                            continue
                        if ntag.endswith("hr"):
                            try:
                                hr = int(float(text))
                            except Exception:
                                pass
                        elif ntag.endswith("cad") or ntag.endswith("cadence"):
                            try:
                                cad = int(float(text))
                            except Exception:
                                pass
    except Exception:
        pass
    return hr, cad


def convert_gpx_to_csv(gpx_path, csv_path):
    """Convertit un fichier .GPX en .CSV avec colonnes forcées et calcul distance/speed."""
    if not os.path.exists(gpx_path):
        raise FileNotFoundError(f"Fichier GPX introuvable : {gpx_path}")
    try:
        gpx = _parse_gpx_tolerant(gpx_path)
        rows = []

        # Calcul cumulatif de distance/speed
        cumulative_distance = 0.0
        for track in gpx.tracks:
            for segment in track.segments:
                prev_lat = prev_lon = None
                prev_time = None
                for point in segment.points:
                    lat = point.latitude
                    lon = point.longitude
                    ele = point.elevation
                    t = point.time

                    # distance instantanée
                    dist = 0.0
                    if prev_lat is not None and prev_lon is not None and t is not None and prev_time is not None:
                        dist = _haversine_m(prev_lat, prev_lon, lat, lon)
                        cumulative_distance += dist

                    # speed
                    sp = None
                    if t is not None and prev_time is not None:
                        dt = (t - prev_time).total_seconds()
                        if dt and dt > 0:
                            sp = dist / dt  # m/s

                    # HR & cadence via extensions
                    hr, cad = _extract_hr_cad_from_extensions(point)

                    row = {
                        "timestamp": t.isoformat() if t else None,
                        "position_lat_deg": lat,
                        "position_long_deg": lon,
                        "altitude": ele,
                        "distance": cumulative_distance if cumulative_distance else (0 if dist == 0 else cumulative_distance),
                        "speed": sp,
                        "speed_kmh": (sp * 3.6) if sp is not None else None,
                        "heart_rate": hr,
                        # Les champs "enhanced_*" n'existent pas en GPX -> laisser None pour écrire 0
                        "enhanced_altitude": None,
                        "enhanced_speed": None,
                        "cadence": cad,
                    }
                    rows.append(row)

                    prev_lat, prev_lon, prev_time = lat, lon, t

        # Colonnes forcées et écriture CSV
        forced_headers = [
            "timestamp",
            "position_lat_deg",
            "position_long_deg",
            "altitude",
            "distance",
            "speed",
            "speed_kmh",
            "heart_rate",
            "enhanced_altitude",
            "enhanced_speed",
            "cadence",
        ]
        Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=forced_headers, extrasaction="ignore", delimiter=';')
            writer.writeheader()
            for r in rows:
                out_row = {}
                for h in forced_headers:
                    v = r.get(h)
                    if v is None or v == "":
                        out_row[h] = 0
                    else:
                        out_row[h] = v
                writer.writerow(out_row)
    except Exception as e:
        raise RuntimeError(f"Erreur pendant la conversion GPX : {e}\n{traceback.format_exc()}")

# ------------------------------ Détection & décompression .gz ---------------------

def find_latest_gz_by_name_desc(root: Path) -> Path:
    """Cherche le premier .gz trié par NOM décroissant dans `root`."""
    if not root.exists():
        raise FileNotFoundError(f"Dossier introuvable : {root}")
    gz_files = sorted(root.glob("*.gz"), key=lambda p: p.name, reverse=True)
    if not gz_files:
        raise FileNotFoundError(f"Aucun fichier .gz trouvé dans : {root}")
    return gz_files[0]


def gunzip_to_fit(gz_path: Path, out_dir: Path = None) -> Path:
    """Décompresse un fichier .gz en .fit dans out_dir (défaut: dossier activities).
    - Si le nom est 'xxx.fit.gz' => produit 'xxx.fit'
    - Sinon, ajoute .fit à la racine du nom.
    Écrase la cible si elle existe déjà.
    """
    if out_dir is None:
        out_dir = get_activities_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    base = gz_path.name
    if base.lower().endswith(".fit.gz"):
        out_name = base[:-3]  # retire uniquement '.gz'
    else:
        stem = gz_path.stem
        out_name = stem if stem.lower().endswith(".fit") else (stem + ".fit")
    fit_path = out_dir / out_name
    with gzip.open(gz_path, "rb") as gzf, open(fit_path, "wb") as out:
        shutil.copyfileobj(gzf, out)
    return fit_path


def gunzip_to_file(gz_path: Path, out_dir: Path = None) -> Path:
    """Décompresse un fichier .gz et conserve l'extension d'origine.
    - Si le nom est 'xxx.fit.gz' => produit 'xxx.fit'
    - Si le nom est 'xxx.gpx.gz' => produit 'xxx.gpx'
    - Sinon, ajoute .fit par défaut si aucune extension n'est détectée.
    Écrase la cible si elle existe déjà.
    """
    if out_dir is None:
        out_dir = get_activities_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    base = gz_path.name
    if base.lower().endswith(".gz"):
        out_name = base[:-3]  # retire uniquement '.gz'
    else:
        out_name = base
    file_path = out_dir / out_name
    with gzip.open(gz_path, "rb") as gzf, open(file_path, "wb") as out:
        shutil.copyfileobj(gzf, out)
    return file_path


def auto_prepare_fit_from_activities() -> Path:
    """Trouve ./activities/<dernier_par_nom>.gz, le décompresse en .fit dans ./activities et retourne le chemin du .fit."""
    activities = get_activities_dir()
    latest_gz = find_latest_gz_by_name_desc(activities)
    fit_path = gunzip_to_fit(latest_gz, activities)
    return fit_path


def auto_prepare_file_from_activities() -> Path:
    """Trouve ./activities/<dernier_par_nom>.gz, le décompresse et retourne le chemin du fichier décompressé."""
    activities = get_activities_dir()
    latest_gz = find_latest_gz_by_name_desc(activities)
    decompressed_path = gunzip_to_file(latest_gz, activities)
    return decompressed_path

# ------------------------------ Ouverture de fichier (cross-plateforme) ----------

def open_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    try:
        if os.name == "nt":  # Windows
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":  # macOS
            subprocess.run(["open", str(path)], check=False)
        else:  # Linux/Unix
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as e:
        raise RuntimeError(f"Impossible d'ouvrir {path}: {e}")

# -------------------------------- Programme principal ----------------------------

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Paramètre optionnel : --pbix <chemin>
    custom_pbix: Path | None = None
    if "--pbix" in argv:
        try:
            idx = argv.index("--pbix")
            custom_pbix = Path(argv[idx + 1]).expanduser().resolve()
        except Exception:
            pass
    app_dir = get_app_dir()
    csv_path = app_dir / "track.csv"

    # 1) Trouver et décompresser
    try:
        decompressed_path = auto_prepare_file_from_activities()
    except Exception as e:
        return 2

    # 2) Convertir en CSV
    try:
        if decompressed_path.suffix.lower() == ".fit":
            convert_fit_to_csv(str(decompressed_path), str(csv_path))
        elif decompressed_path.suffix.lower() == ".gpx":
            convert_gpx_to_csv(str(decompressed_path), str(csv_path))
        else:
            return 4
    except PermissionError:
        return 3
    except Exception as e:
        return 4

    # 3) Ouvrir Power BI
    candidates = []
    if custom_pbix:
        candidates.append(custom_pbix)
    # Priorité demandée : myStrava.bi, puis .pbix
    candidates.extend([
        app_dir / "myStrava.bi",
        app_dir / "myStrava.pbix",
    ])
    opened = False
    last_err = None
    for p in candidates:
        try:
            if p and p.exists():
                open_file(p)
                opened = True
                break
        except Exception as e:
            last_err = e
            continue
    return 0


if __name__ == "__main__":
    sys.exit(main())
