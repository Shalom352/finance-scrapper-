# Règles de développement — UMOA Banking Intelligence

## Règle fondamentale — Données financières

> **Il est strictement interdit d'inventer, d'estimer ou de deviner une donnée financière.**

Si une information est absente : **laisser le champ vide**, taguer `needs_review`, documenter l'absence.

Ne jamais :
- Inventer une valeur de remplacement
- Utiliser une estimation non signalée
- Présenter une donnée `extracted` comme `verified`
- Supprimer la source d'une donnée
- Perdre la période de référence
- Perdre l'unité originale
- Perdre la page du document source

---

## Intégrité des données

Chaque donnée financière doit pouvoir être reliée à :

```
source → document → page → période → valeur originale → unité originale
→ valeur normalisée → unité normalisée → méthode d'extraction → statut
```

### Statuts valides

| Statut | Signification |
|--------|--------------|
| `extracted` | Extrait automatiquement, non vérifié |
| `needs_review` | Extraction incertaine ou valeur ambiguë |
| `reviewed` | Examiné manuellement |
| `verified` | Vérifié contre la source originale |
| `rejected` | Rejeté (erreur, valeur non exploitable) |

**Une donnée ne peut jamais passer à `verified` sans `verified_at` et `verified_by` renseignés.**

---

## Sources

### Priorité des sources

1. BCEAO (bceao.int)
2. Commission Bancaire de l'UMOA (cb-umoa.org)
3. Sites officiels des banques et groupes bancaires
4. Rapports annuels, états financiers, documents réglementaires
5. Autres sources institutionnelles

### Enregistrement obligatoire

Toute source doit être enregistrée avec :
- Nom
- URL
- Type
- Date de consultation
- Langue

---

## Institutions

**Ne jamais générer artificiellement une liste d'institutions.**

Si une institution est enregistrée, elle doit provenir d'une source officielle vérifiable.

Chaque institution doit conserver :
- Nom officiel
- Pays
- Groupe bancaire (si applicable)
- Statut (actif, fermé, en liquidation…)
- Source d'origine + URL source
- Date de collecte

---

## Code

### Python (backend)

- Python 3.11+
- Typage obligatoire (type hints sur toutes les fonctions publiques)
- Pydantic v2 pour la validation des données
- SQLAlchemy 2.0 async pour l'ORM
- Black pour le formatage
- Ruff pour le linting
- pytest pour les tests
- Couverture de tests minimale sur tout code nouveau

### TypeScript (frontend)

- TypeScript strict mode
- Pas de `any` sans justification commentée
- Tous les types partagés dans `src/types/`
- Composants React fonctionnels uniquement

### Général

- Aucun secret dans le code source
- Toute configuration via variables d'environnement
- Toute modification de schéma de base de données via migration Alembic
- Commits atomiques avec messages descriptifs

---

## Pipeline de scraping

Chaque étape est strictement isolée :

```
Discovery  → Identifier les URLs de nouveaux documents
Download   → Télécharger, hasher (SHA-256), dédupliquer
Storage    → Enregistrer le fichier + métadonnées en DB
Parsing    → Extraire le texte et les tableaux du PDF
Normalization → Standardiser les valeurs et unités
Validation → Contrôle qualité, tagging statut
```

**Interdictions** :
- Ne pas mélanger scraping et extraction financière dans une même fonction
- Ne pas perdre les logs d'une opération échouée
- Ne pas supprimer un document téléchargé sans archivage
- Toujours enregistrer les erreurs et statuts de chaque opération

---

## Architecture

- Séparation stricte des couches : scraping / extraction / API / UI
- Versioning des endpoints API : `/api/v1/`
- Soft delete sur les données financières (pas de suppression physique)
- Migrations Alembic obligatoires pour toute modification de schéma
- Logging structuré (JSON) en production

---

## Git

- Branch principale : `main`
- Ne jamais committer `.env`
- Messages de commit : `[phase] type: description` (ex: `[phase0] feat: add FastAPI health endpoint`)
- Revue de code recommandée pour les changements d'architecture

---

## Ce qu'il ne faut jamais faire

- Inventer des données de démonstration présentées comme réelles
- Mettre de faux chiffres financiers dans l'interface
- Créer de faux liens vers des sources
- Faire un refactor massif non demandé
- Modifier des fichiers sans rapport avec la tâche
- Implémenter plusieurs grandes phases simultanément
- Ajouter des fonctionnalités non demandées
