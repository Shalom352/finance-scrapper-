# Qualité des données — statuts, éligibilité, revue humaine

> **DATA MISSING > DATA WRONG** — une donnée absente est affichée comme absente ;
> une donnée incertaine n'est jamais présentée comme certaine.

## 1. Statuts stockés (observations financières et transactions)

| Statut | Signification | Qui le pose |
|---|---|---|
| `extracted` | Valeur lue dans un document, non revue | pipeline |
| `needs_review` | Valeur à confirmer par une personne (confiance faible, résolution d'établissement incertaine, **périmètre non détecté**, import de transaction) | pipeline / import |
| `reviewed` | Revue humaine effectuée | Review Center |
| `verified` | Vérifiée (uniquement depuis `reviewed`), validateur et date obligatoires | Review Center |
| `rejected` | Rejetée avec motif obligatoire ; ne redevient jamais valide | Review Center |

Aucun processus automatique ne pose `reviewed` ni `verified`, sauf la validation automatique réversible (§9). Une nouvelle extraction
ne remplace **jamais** une ligne `reviewed`, `verified` ou `rejected` (garde du pipeline).

## 2. Qualifications calculées (non stockées)

| Qualification | Règle |
|---|---|
| `conflict` | Plusieurs observations non vérifiées de même clé logique (établissement, indicateur, année, type de période, **périmètre**) avec des valeurs divergentes : aucune valeur n'est retenue |
| `unavailable` | Aucune valeur admissible : affichée « — » / « Non disponible », jamais 0 |
| `authoritative` / `superseded` | Observation retenue par la règle d'autorité / observations concurrentes |

## 3. Règle d'éligibilité (analytics, classements, comparaisons)

Implémentée une seule fois (`scraping/analytics/eligibility.py`, `scraping/rankings/eligibility.py`) :

- `rejected` et valeur normalisée absente : exclus ;
- `verified` l'emporte ; sinon `reviewed` > `extracted` > `needs_review`, puis priorité de source, puis confiance ;
- valeurs non vérifiées divergentes → conflit → aucune valeur ;
- une valeur retenue en `needs_review` n'est **jamais** utilisée dans un classement, une comparaison,
  un ratio ou une agrégation (sauf `include_needs_review=true` explicite, et le total est alors
  marqué `needs_review` avec une note) ;
- jamais de mélange de périmètres (`individual` / `consolidated`), de types de période
  (`annual` / `semi_annual` / `quarterly`) ni de devises ; aucune conversion de devise.

## 4. Garde « périmètre non détecté » (Phase 13)

L'extracteur ne sait pas distinguer comptes individuels et consolidés. La colonne `scope`
reçoit la valeur technique `individual`, mais **chaque nouvelle observation extraite** est
posée en `needs_review` avec la note `scope not detected`. Elle n'entre dans aucune analyse
tant qu'une personne n'a pas confirmé le périmètre dans le Review Center.
Les observations historiques ne sont jamais modifiées rétroactivement par cette règle.

## 5. Provenance

Chaque observation : `établissement → source → document → page → période → valeur originale →
unité → valeur normalisée → méthode d'extraction → statut`.
Chaque transaction : sources au niveau de la transaction (`deal_sources` : document, source, page,
extrait) et au niveau de chaque champ (`deal_field_sources`). Un document, une source ou une page
inexistants font refuser l'import ; rien n'est inventé.

## 6. Réconciliation

- Résolution d'établissement (`scraping/reconciliation`) : une correspondance non « haute confiance »
  place l'observation en `needs_review`.
- Doublons / conflits (`scraping/consolidation`) : clé logique incluant le périmètre ; les séries
  historiques ne mélangent ni périmètres ni types de période et n'utilisent jamais une ligne rejetée.
- Transactions : doublons **potentiels** seulement (voir `deal-intelligence.md`), jamais de fusion automatique.

## 7. Revue humaine et piste d'audit

Toutes les décisions passent par le Data Quality & Review Center (`/api/v1/data-quality/...`)
ou par les anciennes routes `/financial-data/{id}/review|verify|reject|bulk-review`, qui offrent
les mêmes garanties :

- `actor` obligatoire (1 à 255 caractères) ; motif obligatoire pour un rejet ;
- `SELECT … FOR UPDATE` sur les lignes décidées ;
- `expected_status` / `expected_updated_at` → **409** si l'état a changé (pas d'écrasement silencieux) ;
- **404** si la ligne n'existe pas ; transition invalide → 400 (anciennes routes) / 422 (Review Center) ;
- bulk : 100 identifiants maximum, tout ou rien ;
- l'événement d'audit est écrit **dans la même transaction** que le changement de statut.

Table unique `financial_data_review_events` : `financial_data_id` **ou** `deal_id` (contrainte
« une seule cible »), `action`, `previous_status`, `new_status`, `reason`, `actor`,
`value_before`, `value_after`, `created_at`, et `deal_duplicate_candidate_id` pour les décisions
sur doublons. Aucun code applicatif ne met à jour ni ne supprime un événement (test automatique).

## 8. Limites connues

- Pas d'authentification : `actor` est déclaré par l'opérateur et enregistré tel quel.
- Append-only garanti par le code applicatif, pas par un trigger PostgreSQL.
- Le périmètre des observations extraites n'est pas détecté automatiquement (voir §4).

## 9. Validation automatique réversible (Phase 21, migration `0018`)

Décision du propriétaire (06/10/2026) : une ligne peut être validée **automatiquement** quand **tous** les
contrôles passent ; une personne peut **retirer** cette validation à tout moment.

```bash
cd backend
python -m app.validation.run --expect-db <base> --dry-run            # simulation
python -m app.validation.run --expect-db <base>                      # observations + transactions
python -m app.validation.run --expect-db <base> --revoke-all --actor <id> --reason "<motif>"   # tout retirer
```

Option : `AUTO_VALIDATION_ENABLED=true` lance la validation après chaque ingestion automatique ;
`AUTO_VALIDATION_SCOPE_CLASSES` (défaut `A,B,C`) fixe les classes de preuve de périmètre acceptées
(retirer `C` pour exiger une mention explicite du périmètre).

**Observations financières** — contrôles (tous obligatoires, sauf « non applicable ») :

| Contrôle | Règle |
|---|---|
| Provenance | établissement, source, document, page, valeur et unité d'origine ; devise pour un montant |
| Normalisation | valeur d'origine × multiplicateur de l'unité = valeur normalisée ; devise inchangée |
| Relecture du document | la valeur d'origine est **imprimée sur sa page** du fichier stocké (relu à chaque passage) ; fichier absent = échec |
| Périmètre | classe de preuve dans les classes acceptées |
| Signaux qualité | aucun signal bloquant (`cross_edition_mismatch`, `cross_statement_mismatch`…) |
| Aucune valeur concurrente | aucune autre observation non rejetée de même clé avec une autre valeur (tolérance d'arrondi de l'unité) |
| Cohérence comptable | postes du bilan ≤ total actif ; créances clientèle + interbancaires ≤ total actif ; dépôts + dettes interbancaires + capitaux propres ≤ total actif ; PNB et résultats ≤ total actif ; total passif = total actif (même document, même année). Total actif absent = échec |
| Années voisines | poste de bilan entre ×0,2 et ×5 de l'année précédente / suivante (si elles existent) |
| Corroboration | (information) un **autre document** donne la même valeur |

Résultat : tous les contrôles passent **et** corroboration → `verified` (automatique) ; tous passent, source unique →
`reviewed` (automatique) ; un échec → statut inchangé, rapport conservé (`auto_validation`) et affiché.

**Transactions** — au moins une source primaire (note visée, résultat UMOA-Titres, communiqué de l'émetteur ;
jamais la presse seule ni l'index AMF), tous les champs publiés attestés, rôles lus dans le texte (une lecture
de logo ou de scan exige une personne), aucun doublon en suspens, montant positif avec devise.
Deux documents **primaires** distincts (la presse et l'index AMF ne comptent pas) → `verified` ; sinon `reviewed`.

**Garde-fous** : les décisions humaines ne sont jamais modifiées ; une revue humaine est marquée
`validation_method = 'human'` ; le retrait (`POST /api/v1/data-quality/{id}/revoke-automatic`,
`/deals/{id}/revoke-automatic`, ou bouton « Retirer la validation automatique ») remet la ligne en `needs_review`,
efface le validateur, bloque toute nouvelle validation automatique de cette ligne et écrit l'événement
`revoke_automatic` (acteur et motif obligatoires). Le downgrade de `0018` est refusé tant qu'une trace existe.

**Limite** : « quasi infaillible » ne veut pas dire infaillible. Une valeur correctement imprimée mais mal
rattachée à une ligne du tableau (bonne valeur, mauvais poste) n'est détectée que si elle viole une règle
comptable ou temporelle ; c'est pourquoi une source unique ne donne que `reviewed`.
