# Playground

## Recherche d'entreprises françaises

`recherche_entreprises.py` recherche toutes les entreprises françaises dont le
nom contient un terme donné, via l'API publique et gratuite de l'État
([recherche-entreprises.api.gouv.fr](https://recherche-entreprises.api.gouv.fr)).
Aucune clé d'API n'est nécessaire.

### Utilisation

```bash
# Affichage lisible dans le terminal
python3 recherche_entreprises.py Enzo

# Sortie JSON complète
python3 recherche_entreprises.py Enzo --json

# Limiter le nombre de résultats récupérés
python3 recherche_entreprises.py Enzo --limit 50 --json > enzo.json

# Vérifier que chaque numéro de TVA est réellement actif (via VIES)
python3 recherche_entreprises.py Enzo --limit 50 --verify-tva
```

Pour chaque entreprise : SIREN, **numéro de TVA intracommunautaire**, nom,
sigle, catégorie, activité (code NAF), date de création, état (active/fermée),
nombre d'établissements, adresse du siège et dirigeant(s).

### À propos du numéro de TVA

Le numéro de TVA intracommunautaire français est, par construction légale,
`FR` + clé + SIREN (clé = `(12 + 3 × (SIREN mod 97)) mod 97`). Il est donc
calculé de façon déterministe — c'est le numéro officiel.

L'option `--verify-tva` interroge le service officiel **VIES** de l'Union
européenne pour confirmer que le numéro est **réellement actif** (entreprise
assujettie et non radiée). Cette option nécessite un accès réseau au domaine
`ec.europa.eu` ; si VIES est injoignable, le statut affiché est
« vérification VIES indisponible » et les autres données restent correctes.
