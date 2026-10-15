#!/usr/bin/env python3
"""
Alerte Marees - Ports de France
Surveille les marees de 25 ports (Manche, Atlantique, Mer du Nord)
Version GitHub avec cle API + topic depuis variables d'environnement
"""

import requests
import json
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw

# ============================================================
# CONFIGURATION
# ============================================================

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "ALERTEMAREES24")
API_KEY = os.environ.get("MAREES_API_KEY", "")

URL_API = "https://api-maree.fr/tide-extrema"

# Ports groupes par region
PORTS = {
    "Manche Est": [
        {"id": "le-havre", "nom": "Le Havre"},
        {"id": "dieppe", "nom": "Dieppe"},
    ],
    "Normandie": [
        {"id": "ouistreham", "nom": "Ouistreham"},
        {"id": "port-en-bessin", "nom": "Port-en-Bessin"},
        {"id": "cherbourg", "nom": "Cherbourg"},
        {"id": "carteret", "nom": "Carteret"},
        {"id": "granville", "nom": "Granville"},
    ],
    "Bretagne Nord": [
        {"id": "saint-malo", "nom": "Saint-Malo"},
        {"id": "cancale", "nom": "Cancale"},
        {"id": "paimpol", "nom": "Paimpol"},
        {"id": "perros-guirec", "nom": "Perros-Guirec"},
        {"id": "roscoff", "nom": "Roscoff"},
        {"id": "brest", "nom": "Brest"},
    ],
    "Bretagne Sud": [
        {"id": "concarneau", "nom": "Concarneau"},
        {"id": "lorient", "nom": "Lorient"},
        {"id": "vannes", "nom": "Vannes"},
        {"id": "le-croisic", "nom": "Le Croisic"},
    ],
    "Vendee & Charente": [
        {"id": "saint-nazaire", "nom": "Saint-Nazaire"},
        {"id": "pornic", "nom": "Pornic"},
        {"id": "la-rochelle-pallice", "nom": "La Rochelle"},
        {"id": "royan", "nom": "Royan"},
    ],
    "Gironde & Landes": [
        {"id": "cap-ferret", "nom": "Cap Ferret"},
        {"id": "biscarrosse", "nom": "Biscarrosse"},
        {"id": "mimizan", "nom": "Mimizan"},
    ],
    "Pays Basque": [
        {"id": "saint-jean-de-luz", "nom": "Saint-Jean-de-Luz"},
    ],
}

SEUIL_GRANDE_MAREE = 90

FICHIER_MEMOIRE = "etat_marees.json"
FICHIER_RECAP = "recap_dernier.json"
HEURE_RECAP = 8

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
    """Genere les icones PNG 192x192 et 512x512 - vague bleue foncee."""
    for taille in (192, 512):
        img = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        marge = taille // 16
        draw.rounded_rectangle(
            [marge, marge, taille - marge, taille - marge],
            radius=taille // 8,
            fill=(12, 74, 110, 255),
        )

        points = []
        for i in range(0, taille + 1, 8):
            x = i
            y = int(taille * 0.55 + taille * 0.12 *
                    (1 if (i // 8) % 2 == 0 else -1) *
                    (1 - abs(i - taille/2) / (taille/2)))
            points.append((x, y))

        for offset, epaisseur in [(0, 6), (int(taille*0.12), 6), (int(taille*0.24), 6)]:
            wave = [(x, y + offset) for (x, y) in points]
            for i in range(len(wave) - 1):
                draw.line([wave[i], wave[i+1]], fill=(255, 255, 255, 255), width=epaisseur)

        img.save(f"icon-{taille}.png")
        print(f"   Icone {taille}x{taille} generee")


def creer_manifest():
    manifest = {
        "name": "Alerte Marees",
        "short_name": "Marees",
        "description": "Horaires de maree et coefficients des ports de France",
        "start_url": "./",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0c4a6e",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    with open("manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"   Manifest cree")


def envoyer_notification(titre, message, priorite="max"):
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": titre.encode("utf-8"),
                "Priority": priorite,
                "Tags": "ocean,water,wave",
            },
            timeout=10,
        )
        print(f"[{datetime.now():%H:%M:%S}] Notification envoyee : {titre}")
    except Exception as e:
        print(f"[ERREUR] Envoi notification : {e}")


def recuperer_marees(port_id, date_debut, date_fin):
    """Recupere les marees pour un port sur une periode donnee."""
    params = {
        "site": port_id,
        "from": date_debut,
        "to": date_fin,
        "tz": "Europe/Paris",
        "key": API_KEY,
    }
    try:
        r = requests.get(URL_API, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 400:
            print(f"   [ERREUR] Port invalide : {port_id}")
        elif r.status_code == 401:
            print(f"   [ERREUR] Cle API invalide ou rate limit")
        else:
            print(f"   [ERREUR] Status {r.status_code} pour {port_id}")
    except Exception as e:
        print(f"   [ERREUR] {port_id} : {type(e).__name__}")
    return None


def extraire_marees_jour(data, date_jour):
    """Extrait les marees d'un jour donne."""
    for j in data.get("data", []):
        if j.get("date") == date_jour:
            return j.get("extrema", [])
    return []


def generer_page_html(ports_data, chemin="index.html"):
    """Genere la page web avec toutes les marees."""
    paris = datetime.now(ZoneInfo("Europe/Paris"))
    date_heure = paris.strftime("%d/%m/%Y a %Hh%M")
    aujourdhui = paris.strftime("%d/%m/%Y")

    sections_html = ""
    for region, ports in PORTS.items():
        cards = []
        for port in ports:
            data = ports_data.get(port["id"])
            if not data:
                continue

            aujourd = data.get("aujourd", {})
            pm = aujourd.get("pm", {}) or {}
            bm = aujourd.get("bm", {}) or {}
            coef = aujourd.get("coef", "?")

            coef_class = "coef-bas"
            try:
                c = int(coef)
                if c >= 90:
                    coef_class = "coef-haut"
                elif c >= 70:
                    coef_class = "coef-moyen"
            except (ValueError, TypeError):
                pass

            cards.append(f'''
            <div class="port">
                <div class="port-nom">{port["nom"]}</div>
                <div class="maree">
                    <span class="label">🌊 Pleine mer</span>
                    <span class="valeur">{pm.get("time", "?")} - {pm.get("height", "?")}m</span>
                </div>
                <div class="maree">
                    <span class="label">🏖️ Basse mer</span>
                    <span class="valeur">{bm.get("time", "?")} - {bm.get("height", "?")}m</span>
                </div>
                <div class="coef {coef_class}">Coef : {coef}</div>
            </div>''')

        if cards:
            sections_html += f'<h2>{region}</h2><div class="ports">{"".join(cards)}</div>'

    html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alerte Marees</title>
<link rel="icon" type="image/png" sizes="192x192" href="icon-192.png">
<link rel="apple-touch-icon" href="icon-192.png">
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#0c4a6e">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif;
         background: #f0f4f8; color: #222; padding: 12px;
         max-width: 700px; margin: 0 auto; }}
  header {{ background: linear-gradient(135deg, #0c4a6e, #082f49);
            color: white; padding: 20px; border-radius: 12px;
            margin-bottom: 16px; text-align: center; }}
  h1 {{ font-size: 1.3em; margin-bottom: 6px; }}
  .date {{ font-size: 0.9em; opacity: 0.95; }}
  h2 {{ font-size: 1.05em; color: #0c4a6e; margin: 20px 0 10px 0;
        border-bottom: 2px solid #0c4a6e; padding-bottom: 4px; }}
  .ports {{ display: grid; gap: 10px; grid-template-columns: 1fr; }}
  @media (min-width: 600px) {{
    .ports {{ grid-template-columns: 1fr 1fr; }}
  }}
  .port {{ background: white; padding: 12px; border-radius: 10px;
           box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
  .port-nom {{ font-weight: bold; font-size: 1.05em; color: #0c4a6e;
               margin-bottom: 8px; }}
  .maree {{ display: flex; justify-content: space-between;
            font-size: 0.9em; padding: 3px 0; }}
  .maree .label {{ color: #666; }}
  .maree .valeur {{ font-weight: bold; color: #0369a1; }}
  .coef {{ margin-top: 8px; padding: 4px 8px; border-radius: 4px;
           text-align: center; font-weight: bold; font-size: 0.85em; }}
  .coef-bas {{ background: #d1fae5; color: #065f46; }}
  .coef-moyen {{ background: #fef3c7; color: #92400e; }}
  .coef-haut {{ background: #fee2e2; color: #991b1b; }}
  .maj {{ text-align: center; color: #888; font-size: 0.8em; margin: 20px 0; }}
</style>
</head>
<body>
<header>
  <h1>🌊 Marees de France</h1>
  <div class="date">{aujourdhui}</div>
</header>
{sections_html}
<div class="maj">Derniere mise a jour : {date_heure}</div>
</body>
</html>'''

    with open(chemin, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   Page HTML generee")


def envoyer_recap(ports_data):
    """Envoie un recap quotidien groupe par region."""
    lignes = []
    for region, ports in PORTS.items():
        lignes_region = []
        for port in ports:
            data = ports_data.get(port["id"])
            if not data:
                continue
            aujourd = data.get("aujourd", {})
            pm = aujourd.get("pm") or {}
            bm = aujourd.get("bm") or {}
            coef = aujourd.get("coef", "?")
            lignes_region.append(
                f"  {port['nom']} : PM {pm.get('time', '?')} | BM {bm.get('time', '?')} | Coef {coef}"
            )
        if lignes_region:
            lignes.append(f"\n{region} :")
            lignes.extend(lignes_region)

    message = "\n".join(lignes)
    titre = "Recap marees du jour"
    envoyer_notification(titre, message)


def main():
    print("=== Alerte Marees ===")
    paris = datetime.now(ZoneInfo("Europe/Paris"))
    print(f"Execution : {paris.strftime('%d/%m/%Y %H:%M')}\n")

    if not API_KEY:
        print("[ERREUR] Cle API MAREES_API_KEY non definie")
        return

    aujourdhui = paris.strftime("%Y-%m-%d")
    date_debut = aujourdhui
    date_fin = (paris + timedelta(days=1)).strftime("%Y-%m-%d")
    date_aujourdhui = paris.strftime("%Y-%m-%d")

    memoire = charger_json(FICHIER_MEMOIRE, {})
    recap_dernier = charger_json(FICHIER_RECAP, {})

    ports_data = {}
    total_ports = sum(len(p) for p in PORTS.values())
    compteur = 0

    for region, ports in PORTS.items():
        for port in ports:
            compteur += 1
            print(f"[{compteur}/{total_ports}] {port['nom']}...")
            data = recuperer_marees(port["id"], date_debut, date_fin)
            if not data:
                time.sleep(2)
                continue

            extrema_aujourd = extraire_marees_jour(data, aujourdhui)
            extrema_demain = extraire_marees_jour(data, (paris + timedelta(days=1)).strftime("%Y-%m-%d"))

            pm_aujourd = next((e for e in extrema_aujourd if e.get("type") == "PM"), None)
            bm_aujourd = next((e for e in extrema_aujourd if e.get("type") == "BM"), None)
            coef_aujourd = pm_aujourd.get("coef") if pm_aujourd else None

            if not pm_aujourd and extrema_demain:
                pm_aujourd = next((e for e in extrema_demain if e.get("type") == "PM"), None)
            if not bm_aujourd and extrema_demain:
                bm_aujourd = next((e for e in extrema_demain if e.get("type") == "BM"), None)

            ports_data[port["id"]] = {
                "nom": port["nom"],
                "region": region,
                "aujourd": {
                    "pm": pm_aujourd,
                    "bm": bm_aujourd,
                    "coef": coef_aujourd,
                },
            }

            time.sleep(2)

    print(f"\n{len(ports_data)} ports recuperes sur {total_ports}\n")

    print("-> Generation de la page web...")
    generer_page_html(ports_data)

    print("-> Generation des icones...")
    creer_icones_png()
    creer_manifest()

    grandes_marees = []
    for port_id, info in ports_data.items():
        coef = info["aujourd"].get("coef")
        try:
            if coef and int(coef) >= SEUIL_GRANDE_MAREE:
                grandes_marees.append({
                    "nom": info["nom"],
                    "coef": coef,
                })
        except (ValueError, TypeError):
            pass

    if grandes_marees:
        lignes = [f"{gm['nom']} : coefficient {gm['coef']}" for gm in grandes_marees]
        titre = f"🌊 Grande maree ! Coef {grandes_marees[0]['coef']} max"
        message = "\n".join(lignes)
        print(f"\n{titre}\n{message}\n")
        envoyer_notification(titre, message)

    derniere_date_recap = recap_dernier.get("date", "")
    if (paris.hour >= HEURE_RECAP and date_aujourdhui != derniere_date_recap):
        print(f"\n-> Envoi du recap quotidien")
        envoyer_recap(ports_data)
        recap_dernier["date"] = date_aujourdhui
        recap_dernier["heure_envoi"] = paris.isoformat()
        sauvegarder_json(FICHIER_RECAP, recap_dernier)

    if not grandes_marees:
        print("\nAucune grande maree aujourd'hui.")

    sauvegarder_json(FICHIER_MEMOIRE, ports_data)
    print(f"\nDonnees sauvegardees : {len(ports_data)} ports")


if __name__ == "__main__":
    main()
