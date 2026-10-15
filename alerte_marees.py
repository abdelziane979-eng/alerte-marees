#!/usr/bin/env python3
"""
Alerte Marees - Ports de peche (Atlantique / Manche)
Version GitHub avec cle API + topic depuis variables d'environnement
"""

import requests
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw

# ============================================================
# CONFIGURATION
# ============================================================

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "ALERTEMAREES24")
API_KEY = os.environ.get("MAREES_API_KEY", "")

FICHIER_ETAT = "etat_marees.json"
FICHIER_RECAP = "recap_dernier.json"
DOSSIER_PUBLIC = "."
HEURE_RECAP = 8

# Ports surveilles (code port -> nom + zone)
PORTS = {
    "le_havre":        {"nom": "Le Havre",        "zone": "Manche Est"},
    "cherbourg":       {"nom": "Cherbourg",       "zone": "Manche Ouest"},
    "saint_malo":      {"nom": "Saint-Malo",      "zone": "Manche Ouest"},
    "brest":           {"nom": "Brest",           "zone": "Atlantique Nord"},
    "concarneau":      {"nom": "Concarneau",      "zone": "Atlantique Nord"},
    "lorient":         {"nom": "Lorient",         "zone": "Atlantique Sud"},
    "saint_nazaire":   {"nom": "Saint-Nazaire",   "zone": "Atlantique Sud"},
    "les_sables":      {"nom": "Les Sables",      "zone": "Atlantique Sud"},
    "la_rochelle":     {"nom": "La Rochelle",     "zone": "Atlantique Sud"},
    "arcachon":        {"nom": "Arcachon",        "zone": "Atlantique Sud"},
}

# Seuils d'alerte (coefficient de maree)
SEUIL_GRANDE_MAREE = 100
SEUIL_TRES_GRANDE_MAREE = 110

URL_API_BASE = "https://api-maree.fr/v1"

# ============================================================

def charger_json(fichier, defaut):
    if os.path.exists(fichier):
        try:
            with open(fichier, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return defaut
    return defaut


def sauvegarder_json(fichier, data):
    with open(fichier, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def creer_icones_png():
    """Genere les icones PNG 192x192 et 512x512 - vague bleue."""
    for taille in (192, 512):
        img = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        marge = taille // 16
        draw.rounded_rectangle(
            [marge, marge, taille - marge, taille - marge],
            radius=taille // 8,
            fill=(30, 58, 138, 255),
        )

        # Vague blanche
        points = []
        for i in range(21):
            x = int(taille * (0.15 + 0.70 * i / 20))
            y = int(taille * (0.55 + 0.10 * (1 if i % 4 < 2 else -1)))
            points.append((x, y))
        draw.line(points, fill=(255, 255, 255, 255), width=max(3, taille // 50))

        # Lune
        draw.ellipse(
            [int(taille * 0.68), int(taille * 0.15),
             int(taille * 0.88), int(taille * 0.35)],
            fill=(255, 255, 255, 255),
        )

        img.save(f"icon-{taille}.png")
        print(f"   Icone {taille}x{taille} generee")


def creer_manifest():
    manifest = {
        "name": "Alerte Marees",
        "short_name": "Marees",
        "description": "Alertes grandes marees sur les ports francais",
        "start_url": "./",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#1e3a8a",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    with open("manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"   Manifest cree")


def envoyer_notification(titre, message):
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": titre.encode("utf-8"),
                "Priority": "high",
                "Tags": "ocean,moon,rotating_light",
            },
            timeout=10,
        )
        print(f"[{datetime.now():%H:%M:%S}] Notification envoyee : {titre}")
    except Exception as e:
        print(f"[ERREUR] Envoi notification : {e}")


def recuperer_marees(port_code, date_debut, date_fin):
    """Recupere les marees depuis l'API api-maree.fr."""
    if not API_KEY:
        print("[ERREUR] Cle API manquante")
        return None

    url = f"{URL_API_BASE}/tides"
    params = {
        "key": API_KEY,
        "port": port_code,
        "start": date_debut,
        "end": date_fin,
    }

    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"   [ERREUR] API marees ({port_code}) : {e}")
        return None


def extraire_coef_max(data_api):
    """Extrait le coefficient de maree max d'une reponse API."""
    if not data_api:
        return None

    coefs = []
    for jour in data_api.get("data", data_api.get("tides", [])):
        coef = jour.get("coef") or jour.get("coefficient")
        if coef:
            try:
                coefs.append(float(coef))
            except (ValueError, TypeError):
                pass

    if not coefs:
        return None
    return max(coefs)


def generer_page_html(resultats, chemin="index.html"):
    paris = datetime.now(ZoneInfo("Europe/Paris"))
    date_heure = paris.strftime("%d/%m/%Y a %Hh%M")

    zones = {}
    for port_code, info in resultats.items():
        zone = info.get("zone", "Autre")
        if zone not in zones:
            zones[zone] = []
        zones[zone].append((port_code, info))

    cards_html = ""
    for zone, ports in sorted(zones.items()):
        cards_html += f'<h2>{zone}</h2><div class="stations">'
        for port_code, info in sorted(ports, key=lambda x: x[1].get("nom", "ZZZ")):
            coef = info.get("coef_max")
            if coef is None:
                badge_class = "badge-info"
                badge_txt = "N/A"
            elif coef >= SEUIL_TRES_GRANDE_MAREE:
                badge_class = "badge-danger"
                badge_txt = f"COEF {coef:.0f}"
            elif coef >= SEUIL_GRANDE_MAREE:
                badge_class = "badge-warn"
                badge_txt = f"COEF {coef:.0f}"
            else:
                badge_class = "badge-ok"
                badge_txt = f"COEF {coef:.0f}"

            cards_html += f'''
            <div class="station">
                <div class="badge {badge_class}">{badge_txt}</div>
                <div class="nom">{info.get("nom", "?")}</div>
            </div>'''
        cards_html += '</div>'

    html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alerte Marees</title>
<link rel="icon" type="image/png" sizes="192x192" href="icon-192.png">
<link rel="apple-touch-icon" href="icon-192.png">
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#1e3a8a">
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif;
         margin: 0; padding: 16px; background: #f0f4f8; color: #222;
         display: flex; flex-direction: column; align-items: center; }}
  header, h2, .stations, .date {{ width: 100%; max-width: 700px; }}
  header {{ background: linear-gradient(135deg, #1e3a8a, #1e40af);
            color: white; padding: 20px; border-radius: 12px;
            margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  h1 {{ margin: 0; font-size: 1.3em; }}
  .compteur {{ margin-top: 8px; font-size: 1em; opacity: 0.95; }}
  h2 {{ font-size: 1em; color: #1e3a8a; margin: 20px 0 10px 0;
        border-bottom: 2px solid #1e3a8a; padding-bottom: 4px; }}
  .stations {{ display: grid; gap: 10px; grid-template-columns: 1fr; }}
  @media (min-width: 600px) {{
    .stations {{ grid-template-columns: 1fr 1fr; }}
  }}
  .station {{ background: white; padding: 14px; border-radius: 10px;
              box-shadow: 0 1px 4px rgba(0,0,0,0.08); position: relative; }}
  .nom {{ font-weight: bold; font-size: 1em; padding-right: 90px; }}
  .badge {{ position: absolute; top: 10px; right: 10px;
            font-size: 0.7em; color: white; padding: 4px 8px;
            border-radius: 4px; font-weight: bold; }}
  .badge-ok {{ background: #059669; }}
  .badge-warn {{ background: #e80; }}
  .badge-danger {{ background: #c00; }}
  .badge-info {{ background: #888; }}
  .date {{ text-align: center; color: #888; font-size: 0.85em; margin: 20px 0; }}
</style>
</head>
<body>
<header>
  <h1>🌊 Alerte Marees</h1>
  <div class="compteur">{len(resultats)} ports surveilles</div>
</header>
{cards_html}
<div class="date">Derniere mise a jour : {date_heure}</div>
</body>
</html>'''

    with open(chemin, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   Page HTML generee ({len(resultats)} ports)")


def main():
    print("=== Alerte Marees ===")
    paris = datetime.now(ZoneInfo("Europe/Paris"))
    print(f"Execution : {paris.strftime('%d/%m/%Y %H:%M')}\n")

    if not API_KEY:
        print("[ERREUR] Cle API MAREES_API_KEY non definie")
        return

    etat_precedent = charger_json(FICHIER_ETAT, {})
    recap_dernier = charger_json(FICHIER_RECAP, {})

    date_debut = paris.strftime("%Y-%m-%d")
    date_fin = (paris + timedelta(days=7)).strftime("%Y-%m-%d")

    resultats = {}
    grandes_marees = []

    for port_code, info in PORTS.items():
        print(f"[{info['nom']}]")
        data = recuperer_marees(port_code, date_debut, date_fin)
        if not data:
            print("   Aucune donnee.\n")
            resultats[port_code] = {**info, "coef_max": None}
            continue

        coef_max = extraire_coef_max(data)
        resultats[port_code] = {**info, "coef_max": coef_max}

        if coef_max:
            print(f"   Coefficient max : {coef_max:.0f}")
            if coef_max >= SEUIL_GRANDE_MAREE:
                grandes_marees.append({
                    "nom": info["nom"],
                    "zone": info["zone"],
                    "coef": coef_max,
                })
        else:
            print("   Aucun coefficient trouve")
        print()

    print("-> Generation de la page web...")
    generer_page_html(resultats)

    print("-> Generation des icones...")
    creer_icones_png()
    creer_manifest()

    # Alertes pour grandes marees
    aujourdhui = paris.strftime("%Y-%m-%d")
    deja_alerte = etat_precedent.get("derniere_alerte_date") == aujourdhui

    if grandes_marees and not deja_alerte:
        lignes = []
        for g in sorted(grandes_marees, key=lambda x: -x["coef"]):
            niveau = "TRES GRANDE" if g["coef"] >= SEUIL_TRES_GRANDE_MAREE else "GRANDE"
            lignes.append(f"{g['nom']} ({g['zone']})\n   Coefficient : {g['coef']:.0f} - {niveau} MAREE")

        titre = f"{len(grandes_marees)} grande(s) maree(s) cette semaine"
        message = "\n\n".join(lignes)
        print(f"\n{titre}\n{message}\n")
        envoyer_notification(titre, message)
        etat_precedent["derniere_alerte_date"] = aujourdhui

    # Recap quotidien
    derniere_date_recap = recap_dernier.get("date", "")
    if paris.hour >= HEURE_RECAP and aujourdhui != derniere_date_recap:
        lignes = []
        for port_code, info in sorted(resultats.items(), key=lambda x: x[1].get("nom", "ZZZ")):
            coef = info.get("coef_max")
            if coef:
                lignes.append(f"{info['nom']:20s} : {coef:.0f}")
            else:
                lignes.append(f"{info['nom']:20s} : N/A")

        titre = f"Recap Marees - {aujourdhui}"
        message = "\n".join(lignes)
        print(f"\n-> Envoi du recap quotidien")
        envoyer_notification(titre, message)
        recap_dernier["date"] = aujourdhui
        recap_dernier["heure_envoi"] = paris.isoformat()

    if not grandes_marees:
        print("\nAucune grande maree cette semaine.")

    sauvegarder_json(FICHIER_ETAT, etat_precedent)
    sauvegarder_json(FICHIER_RECAP, recap_dernier)
    sauvegarder_json("marees_data.json", resultats)
    print(f"\nEtat sauvegarde")


if __name__ == "__main__":
    main()
