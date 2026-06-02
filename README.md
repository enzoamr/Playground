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
```

Pour chaque entreprise : SIREN, nom, sigle, catégorie, activité (code NAF),
date de création, état (active/fermée), nombre d'établissements, adresse du
siège et dirigeant(s).
