# Suivi de syndication (migration 0022)

Le module importe le classeur interne « Suivi de Syndication Deals TOMASTEED » et permet de tenir à jour
les mandats, les contreparties approchées et les contacts. Ce sont des **données internes** : les routes
`/api/v1/syndication/*` et `/api/v1/mandates` exigent le jeton interne (`X-Internal-Token`, ajouté par le
proxy Next après la Basic Auth). En production, sans `INTERNAL_API_TOKEN`, elles répondent 503 : elles ne
sont jamais ouvertes par erreur.

## 1. Parcours

1. Page **Syndication** → « Importer le fichier de suivi (Excel) » → **Aperçu**. Le fichier est lu, rien
   n'est écrit dans les tables métier ; un plan est enregistré (`syndication_imports`).
2. Le plan liste ce qui serait créé, mis à jour, inchangé ou **en conflit** (valeur modifiée à la fois dans
   la plateforme et dans le fichier depuis le dernier import).
3. Les **feuilles de détail** (ex. « Cité Administrative ») et les **seconds tableaux** trouvés sous le
   tableau principal (ex. `SUIVI SYNDICATION!94`, les LOI d'un deal) ne sont importés qu'une fois
   **associés à un mandat** par l'utilisateur.
4. **Appliquer** : une décision (plateforme ou fichier) est exigée pour chaque conflit ; tout est écrit en
   une transaction.

## 2. Lecture du classeur (`app/mandates/syndication_xlsx.py`)

- Feuilles trouvées par le **titre imprimé**, colonnes par leur **libellé** (jamais par position) ; une
  colonne absente est signalée, jamais lue décalée.
- **SUIVI SYNDICATION** → mandats (pays ISO seulement pour l'UMOA ; Gabon, Guinée… restent bruts),
  événements de contreparties, contacts de la ligne. La lecture s'arrête au premier **en-tête répété** :
  le tableau suivant (colonnes différentes) n'est jamais lu avec les colonnes du tableau principal. Trois
  lignes vides séparent deux blocs : ce qui suit ne prolonge pas le dernier deal.
- **Second tableau** (LOI) : une ligne portant seulement un libellé de statut (« LOI reçus », « LOI à
  recevoir ») titre les lignes suivantes ; montant numérique lu en millions (en-tête de la feuille), en XOF
  seulement pour un pays de l'UMOA ; taux numériques convertis en pourcentage.
- **CRM Interne** et **Liste des personnes dataroom** → contacts (accès data room).
- Cartographie des prêteurs, base des conditions : **recalculées** par la plateforme, non importées.

## 3. Règles

- **Stade** d'une contrepartie (le libellé d'origine est toujours conservé) : engagement préliminaire →
  `interested` ; engagement ferme → `committed` ; term sheet → `term_sheet` ; décaissement → `disbursed` ;
  « en cours d'étude » → `approached` ; appétit « Non » → `declined` ; appétit « Oui » ou montant explicite →
  `interested` ; sinon `approached`. LOI reçue → `interested`.
- **Montant** : un nombre seulement pour **un** montant explicite avec sa devise (« jusqu'à », fourchette,
  « sollicités », tranches → texte seul). FCFA = XOF seulement pour un pays de l'UMOA.
- **Contreparties** : « X / autres » reste une ligne, signalée pour être scindée à la main ; les variantes
  d'un même nom sont rapprochées par la table d'alias `backend/reference/syndication_aliases.json`.
- **E-mails** : une adresse au format invalide (ex. `.ccom`) n'est pas importée ; elle reste dans les notes du
  contact et un avertissement est affiché.

## 4. Données personnelles

Les contacts (nom, fonction, e-mail, téléphone, accès data room) sont des données personnelles :
- accès limité aux utilisateurs authentifiés (Basic Auth + jeton interne) ; jamais exposés par une route
  publique ni par la recherche globale ;
- suppression = suppression logique (`deleted_at`), confirmée dans l'interface ;
- le fichier Excel source n'est jamais versionné (`*.xlsx` est ignoré par git) ; les tests utilisent un
  classeur synthétique (`tests/fixtures_syndication.py`).

Durée de conservation : à fixer par le responsable des données de TOMASTEED (question ouverte).
