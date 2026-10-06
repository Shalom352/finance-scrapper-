# Règles de développement — UMOA Banking Intelligence

> Référence de vérité : `docs/specification-v1.md`. En cas de divergence, la spécification prévaut.

---

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
- Perdre la devise originale
- Perdre la page du document source

---

## Intégrité des données

Chaque donnée financière doit pouvoir être reliée à :

```
institution → source → document → page → période → métrique
→ valeur originale → unité originale → devise originale
→ valeur normalisée → unité normalisée → devise normalisée
→ méthode d'extraction → statut de validation
```

### Statuts valides

| Statut | Signification |
|--------|--------------|
| `extracted` | Extrait automatiquement, non vérifié |
| `needs_review` | Extraction incertaine ou valeur ambiguë |
| `reviewed` | Examiné manuellement |
| `verified` | Vérifié contre la source originale |
| `rejected` | Rejeté (erreur, valeur non exploitable) |

---

## Workflow de validation

**Aucun processus automatique d'extraction, de parsing ou de normalisation ne peut attribuer directement `verified`.**

> **Exception décidée par le propriétaire le 06/10/2026 (Phase 21) — validation automatique réversible.**
> Le seul processus automatique autorisé à poser `reviewed` ou `verified` est `scraping/validation/automatic.py`,
> et uniquement quand **tous** ses contrôles passent (voir `docs/data-quality.md` §9). Chaque décision est marquée
> `validation_method = 'automatic'`, tracée (événement `auto_validate`, détail de chaque contrôle) et **retirable
> par une personne** (`revoke_automatic`) : la ligne repasse `needs_review` et n'est plus jamais validée
> automatiquement. L'extraction, le parsing et la normalisation restent interdits de poser ces statuts.

Transitions autorisées :

```
extracted ──▶ needs_review ──▶ reviewed ──▶ verified
     │              │              │
     └──────────────┴──────────────┴──▶ rejected
```

- **Interdit** : `extracted → verified` (et tout saut de `reviewed`).
- **`reviewed`** exige `value_normalized` non NULL.
- **`verified`** exige `value_normalized` non NULL **ET** `verified_at` non NULL **ET** `verified_by` non NULL.
- **`rejected`** : valeur conservée (jamais de suppression physique).

Seule une **action humaine explicite** peut produire `reviewed`, `verified` ou `rejected`. Les transitions doivent être contrôlées par la logique applicative et **couvertes par des tests**.

### `verified_by`

Aucune table `User` en V1. `verified_by` est un **identifiant texte du validateur** (ex. code d'agent ou e-mail), **identifiant technique de validation** — et **non** un nom libre destiné à l'affichage. Une future authentification remplacera ce champ par une FK utilisateur.

---

## Unités et devises

**L'unité et la devise sont deux concepts distincts.** Ne jamais utiliser la devise comme substitut de l'unité, ni l'inverse.

`financial_data` conserve six champs :

```
value_original,   unit_original,   currency_original
value_normalized, unit_normalized, currency_normalized
```

Règle de normalisation par `value_type` :

| `value_type` | `unit_normalized` | `value_normalized` |
|--------------|-------------------|--------------------|
| `amount` | `"absolute"` | `value_original × multiplicateur` |
| `percentage` | `"%"` | pourcentage numérique |
| `ratio` | `"ratio"` | décimal |
| `rate` | `"%"` | pourcentage numérique |

Multiplicateurs (`amount`) : `absolute/unit` ×1 · `thousand` ×1 000 · `million` ×1 000 000 · `milliard/billion` ×1 000 000 000.

**Aucune conversion de devise en V1 : `currency_normalized = currency_original`.** Une valeur en USD/EUR reste en USD/EUR. La normalisation d'un montant **n'est pas** une conversion de devise.

Exemples :

```
"8542" million XOF → value_normalized = 8542000000, unit_normalized = "absolute", currency_normalized = "XOF"
"125.4" million USD → value_normalized = 125400000, unit_normalized = "absolute", currency_normalized = "USD"
"57" %            → value_normalized = 57,   unit_normalized = "%",     currency_normalized = NULL
"1,25" ratio      → value_normalized = 1.25, unit_normalized = "ratio", currency_normalized = NULL
```

### Rankings — comparabilité

Un classement n'est possible qu'entre données de : même `metric_code`, même `period_type`, même `period_year`/`period_label`, même `scope`, unités compatibles, et **même `currency_normalized`**. Les rankings n'incluent que des données `verified`.

---

## Scopes

`financial_data.institution_id` est NOT NULL. Seuls les scopes rattachables à une institution sont autorisés :

```
individual   → institution isolée
consolidated → entité consolidante (rattachée à l'institution déclarante)
```

Les agrégats `country`, `sector`, `umoa` ne sont **pas** stockés dans `financial_data` ; ils sont calculés à partir des données institutionnelles. Ne jamais créer d'institution artificielle pour les représenter.

---

## Règles de garde (implémentation)

### Garde n°1 — `facilities_de_change`

- **Aucun mapping sémantique automatique.** Un poste « proche » (engagements de financement, lignes de crédit confirmées, facilités de caisse, concours bancaires, position de change) ne doit **jamais** être converti en `facilities_de_change` par ressemblance de libellé.
- Collecte **uniquement** si un document publie un poste explicitement identifiable comme facilité/engagement de change.
- Le libellé source exact est conservé dans `notes` ; en cas de doute → `needs_review`, jamais `extracted`.
- Si aucun libellé exploitable n'existe → métrique au catalogue **sans collecte**.

### Garde n°2 — données `consolidated`

- Pour `scope = consolidated`, l'`institution_id` doit correspondre à l'**entité déclarante/consolidante** du document, **jamais** à une filiale du périmètre.
- Si l'entité déclarante n'est pas identifiable sans ambiguïté → `needs_review`, rattachement non forcé.

---

## Métriques

Les 26 métriques de la V1 sont définies dans `metric_definitions` (voir `docs/specification-v1.md` §6–§9). En V1, `is_calculated = false` pour toutes : seules des valeurs **publiées** sont collectées.

- **`chiffre_affaires`** : collecté uniquement si explicitement publié comme tel. **Interdiction de le dériver du produit net bancaire.**
- **`endettement_actifs`** : collecté uniquement s'il est explicitement publié ; jamais recalculé.
- **`taux_interet_moyen`** : valeur publiée en pourcentage ; aucun calcul.

---

## Documents

### Déduplication

- `file_hash` = SHA-256, **UNIQUE lorsqu'il est renseigné** ; stockage adressé par contenu.
- **Même fichier = déduplication.** **Fichier différent = nouveau Document potentiel**, même institution et même période.
- Ne jamais dédupliquer par `institution + année`.

### Versionnement

Une nouvelle version ou correction produit un **nouveau Document** distinct avec ses propres `financial_data`. La provenance historique n'est jamais modifiée rétroactivement. Pas de `supersedes_document_id` en V1.

---

## Sources

### Priorité des sources

1. BCEAO (bceao.int)
2. Commission Bancaire de l'UMOA (cb-umoa.org)
3. Sites officiels des banques et groupes bancaires
4. Rapports annuels, états financiers, documents réglementaires
5. Autres sources institutionnelles

### Enregistrement obligatoire

Toute source doit être enregistrée avec : nom, URL, type, date de consultation, langue.

Types de source (canonique, backend = frontend) :

```
regulatory | central_bank | bank | banking_group | government | financial_market | secondary
```

---

## Institutions

**Ne jamais générer artificiellement une liste d'institutions.** Si une institution est enregistrée, elle doit provenir d'une source officielle vérifiable.

Chaque institution conserve : nom officiel, pays, groupe bancaire (si applicable), statut, source d'origine + URL, date de collecte.

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
- Types alignés sur le backend : `source_type` = `banking_group` (jamais `group`), `document_type` inclut `web_page`, `period_type` = `semi_annual`

### Général

- Aucun secret dans le code source
- Toute configuration via variables d'environnement
- Toute modification de schéma de base de données via migration Alembic
- Commits atomiques avec messages descriptifs

---

## Pipeline de scraping

Chaque étape est strictement isolée :

```
Discovery    → Identifier les URLs de nouveaux documents
Download     → Télécharger, hasher (SHA-256), dédupliquer
Storage      → Enregistrer le fichier + métadonnées en DB
Parsing      → Extraire le texte et les tableaux (PDF / HTML)
Normalization → Standardiser les valeurs, unités et devises
Validation   → Contrôle qualité, tagging statut
```

**Interdictions** :
- Ne pas mélanger scraping et extraction financière dans une même fonction
- Ne pas perdre les logs d'une opération échouée
- Ne pas supprimer un document téléchargé sans archivage
- Toujours enregistrer les erreurs et statuts de chaque opération
- Ne jamais attribuer `verified` automatiquement

---

## Architecture

- Séparation stricte des couches : scraping / parsing / normalization / validation / API / UI
- Versioning des endpoints API : `/api/v1/`, sans slash final
- Soft delete sur les données financières (pas de suppression physique)
- Migrations Alembic obligatoires pour toute modification de schéma
- Logging structuré (JSON) en production

---

## Git

- Branche principale : `main`
- Ne jamais committer `.env`
- Messages de commit : `[phase] type: description` (ex: `[phase1] feat: add metric_definitions model`)
- Revue de code recommandée pour les changements d'architecture

---

## Ce qu'il ne faut jamais faire

- Inventer des données de démonstration présentées comme réelles
- Mettre de faux chiffres financiers dans l'interface
- Créer de faux liens vers des sources
- Convertir une devise en V1 (aucune conversion FX)
- Confondre unité et devise
- Mapper automatiquement un poste proche vers `facilities_de_change`
- Rattacher une donnée `consolidated` à une filiale plutôt qu'à l'entité consolidante
- Faire un refactor massif non demandé
- Modifier des fichiers sans rapport avec la tâche
- Implémenter plusieurs grandes phases simultanément
- Ajouter des fonctionnalités non demandées