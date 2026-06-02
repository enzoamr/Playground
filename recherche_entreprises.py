#!/usr/bin/env python3
"""Recherche d'entreprises françaises par nom.

Interroge l'API publique et gratuite « Recherche d'entreprises » de
l'État français (https://recherche-entreprises.api.gouv.fr) et renvoie
toutes les entreprises dont le nom contient le terme fourni.

Exemples :
    python3 recherche_entreprises.py Enzo
    python3 recherche_entreprises.py "Enzo" --json
    python3 recherche_entreprises.py Enzo --limit 50 --json > enzo.json
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://recherche-entreprises.api.gouv.fr/search"
VIES_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms"
PER_PAGE = 25          # maximum autorisé par l'API
MAX_RESULTS_API = 10000  # plafond imposé par l'API (page * per_page <= 10000)


def _fetch_page(query, page):
    """Récupère une page de résultats de l'API.

    Reprend sur les erreurs réseau et sur les 429/503 (l'API limite le débit
    et renvoie un 503 quand on l'interroge trop vite), avec backoff progressif.
    """
    params = urllib.parse.urlencode(
        {"q": query, "page": page, "per_page": PER_PAGE}
    )
    url = f"{API_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "recherche-entreprises-cli"})

    last_err = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            last_err = err
            if err.code in (429, 503):  # rate-limit / surcharge : on réessaie
                time.sleep(min(2 ** attempt, 20))
            else:
                raise RuntimeError(f"Échec de la requête API : {err}")
        except (urllib.error.URLError, TimeoutError) as err:
            last_err = err
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"Échec de la requête API : {last_err}")


def search_companies(query, limit=None, pause=0.6):
    """Renvoie la liste de toutes les entreprises correspondant à `query`.

    `limit` borne le nombre d'entreprises renvoyées (None = tout récupérer,
    dans la limite du plafond de l'API). `pause` espace les pages pour rester
    sous la limite de débit de l'API.
    """
    first = _fetch_page(query, 1)
    total = first.get("total_results", 0)
    total_pages = first.get("total_pages", 1)

    results = list(first.get("results", []))
    page = 2
    while page <= total_pages and page * PER_PAGE <= MAX_RESULTS_API + PER_PAGE:
        if limit is not None and len(results) >= limit:
            break
        time.sleep(pause)  # throttling pour éviter les 503
        results.extend(_fetch_page(query, page).get("results", []))
        page += 1

    if limit is not None:
        results = results[:limit]
    return results, total


def tva_intracommunautaire(siren):
    """Calcule le numéro de TVA intracommunautaire français à partir du SIREN.

    Format officiel : FR + clé (2 chiffres) + SIREN (9 chiffres),
    avec clé = (12 + 3 * (SIREN mod 97)) mod 97.
    """
    if not siren or not str(siren).isdigit() or len(str(siren)) != 9:
        return None
    cle = (12 + 3 * (int(siren) % 97)) % 97
    return f"FR{cle:02d}{siren}"


def verifier_tva_vies(tva):
    """Vérifie un numéro de TVA auprès du service officiel VIES de l'UE.

    Renvoie un dict {'valide': bool, 'nom': str|None, 'adresse': str|None}
    ou {'valide': None, ...} si le service est injoignable (réseau bloqué,
    indisponibilité, etc.). Confirme qu'un numéro est réellement *actif*,
    et pas seulement de format correct.
    """
    inconnu = {"valide": None, "nom": None, "adresse": None}
    if not tva or len(tva) < 3:
        return inconnu
    pays, numero = tva[:2], tva[2:]
    url = f"{VIES_URL}/{pays}/vat/{numero}"
    req = urllib.request.Request(url, headers={"User-Agent": "recherche-entreprises-cli"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {
            "valide": bool(data.get("valid")),
            "nom": (data.get("name") or "").strip() or None,
            "adresse": (data.get("address") or "").strip() or None,
        }
    except (urllib.error.URLError, TimeoutError, ValueError):
        return inconnu


def _simplify(company, verifier=False):
    """Extrait les données les plus utiles d'une entreprise.

    Si `verifier` est vrai, interroge VIES pour confirmer la TVA.
    """
    siege = company.get("siege") or {}
    dirigeants = [
        " ".join(filter(None, [d.get("prenoms"), d.get("nom")])).strip()
        or d.get("denomination")
        for d in (company.get("dirigeants") or [])
    ]
    tva = tva_intracommunautaire(company.get("siren"))
    data = {
        "siren": company.get("siren"),
        "tva_intracommunautaire": tva,
        "nom": company.get("nom_complet") or company.get("nom_raison_sociale"),
        "sigle": company.get("sigle"),
        "categorie": company.get("categorie_entreprise"),
        "nature_juridique": company.get("nature_juridique"),
        "activite_principale": company.get("activite_principale"),
        "date_creation": company.get("date_creation"),
        "etat": "Active" if company.get("etat_administratif") == "A" else "Fermée",
        "nb_etablissements": company.get("nombre_etablissements"),
        "adresse_siege": siege.get("adresse"),
        "code_postal": siege.get("code_postal"),
        "commune": siege.get("libelle_commune"),
        "dirigeants": [d for d in dirigeants if d],
    }
    if verifier:
        vies = verifier_tva_vies(tva)
        data["tva_valide_vies"] = vies["valide"]
        data["tva_nom_vies"] = vies["nom"]
    return data


def _statut_tva(c):
    """Libellé du statut VIES s'il a été vérifié."""
    if "tva_valide_vies" not in c:
        return ""
    if c["tva_valide_vies"] is True:
        return "  ✅ actif (VIES)"
    if c["tva_valide_vies"] is False:
        return "  ❌ inactif/non assujetti (VIES)"
    return "  ⚠️ vérification VIES indisponible"


def _print_table(companies):
    """Affiche un résumé lisible dans le terminal (entreprises déjà simplifiées)."""
    for i, c in enumerate(companies, 1):
        print(f"\n{i}. {c['nom']}  (SIREN {c['siren']}) — {c['etat']}")
        print(f"   N° TVA          : {(c['tva_intracommunautaire'] or '—')}{_statut_tva(c)}")
        if c["sigle"]:
            print(f"   Sigle           : {c['sigle']}")
        print(f"   Catégorie       : {c['categorie'] or '—'}")
        print(f"   Activité (NAF)  : {c['activite_principale'] or '—'}")
        print(f"   Création        : {c['date_creation'] or '—'}")
        print(f"   Établissements  : {c['nb_etablissements'] or '—'}")
        adresse = ", ".join(filter(None, [c["adresse_siege"]]))
        print(f"   Siège           : {adresse or '—'}")
        if c["dirigeants"]:
            print(f"   Dirigeant(s)    : {', '.join(c['dirigeants'])}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("nom", help="Terme à rechercher dans le nom des entreprises")
    parser.add_argument("--json", action="store_true",
                        help="Sortie JSON complète (données brutes simplifiées)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Nombre maximum d'entreprises à récupérer")
    parser.add_argument("--verify-tva", action="store_true",
                        help="Vérifie chaque numéro de TVA auprès de VIES (UE) "
                             "pour confirmer qu'il est réellement actif")
    args = parser.parse_args(argv)

    companies, total = search_companies(args.nom, limit=args.limit)
    simplified = [_simplify(c, verifier=args.verify_tva) for c in companies]

    if args.json:
        print(json.dumps(simplified, ensure_ascii=False, indent=2))
    else:
        print(f"« {args.nom} » : {total} entreprise(s) au total, "
              f"{len(simplified)} récupérée(s).")
        _print_table(simplified)
    return 0


if __name__ == "__main__":
    sys.exit(main())
