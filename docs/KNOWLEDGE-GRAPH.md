# Knowledge Graph

The knowledge graph gives a 360-degree view of a product: every regulatory
artifact attached to a drug, patent, or sponsor, reachable from any entry point.
It is built incrementally by `app/graph/builder.py` as records are collected, and
read back by the global search and the drug 360 endpoint
(`GET /api/v1/drugs/{drug_id}/360`).

## Node types

| Node type | Backed by | Natural key |
| --- | --- | --- |
| `drug` | `drugs` | normalized name + strength + form |
| `sponsor` | `sponsors` | normalized company name |
| `patent` | `patents` | normalized patent number |
| `nda` | `orange_book_products` where `appl_type = N` | application number |
| `anda` | `ftf_records` / Orange Book `appl_type = A` | application number |
| `active_moiety` | `active_moieties` | normalized moiety name |
| `orange_book` | `orange_book_supplements` | edition |
| `ftf_event` | `ftf_records` | source key |
| `pte` | `pte_certificates` / `pte_applications` | patent + type |
| `clinical_trial` | reserved | NCT id |
| `therapy_area` | derived | area name |

Each node stores `ref_table` and `ref_id`, so a graph traversal can jump
straight to the authoritative row.

## Relationship types

```
Drug ──(MARKETED_BY)────────▶ Sponsor
Drug ──(HAS_NDA)────────────▶ NDA
Drug ──(CHALLENGED_BY)──────▶ ANDA ──(FILED_BY)──▶ Sponsor
Drug ──(PROTECTED_BY)───────▶ Patent
Drug ──(CONTAINS_MOIETY)────▶ ActiveMoiety
Drug ──(LISTED_IN)──────────▶ OrangeBook
Drug ──(STUDIED_IN)─────────▶ ClinicalTrial
Drug ──(IN_THERAPY_AREA)────▶ TherapyArea

Patent ─(EXTENDED_BY)───────▶ PTE
Patent ─(ASSERTED_IN)───────▶ FTFEvent
Patent ─(IN_FAMILY)─────────▶ Patent        (INPADOC family)
Patent ─(IN_LITIGATION)─────▶ FTFEvent      (Paragraph IV suits)

ANDA ──(CHALLENGES)─────────▶ Patent
Sponsor ─(HOLDS)────────────▶ Patent | NDA | PTE
```

Edges carry a `weight` (used to rank hop order in the 360 view) and a
`properties` JSON blob for edge-specific facts such as certification type or
filing date.

## Entity resolution

`app/graph/resolve.py` is responsible for merging raw source spellings into one
canonical entity:

1. **Normalize** — casefold, strip punctuation, expand common suffixes
   (`Inc.`, `Ltd.`, `Pharmaceuticals`).
2. **Alias match** — consult the `aliases` JSON on `sponsors` and `drugs`, which
   accumulates every spelling encountered.
3. **Fuzzy fallback** — trigram similarity above a threshold proposes a match;
   ambiguous proposals are stored as aliases rather than auto-merged, so a wrong
   merge never silently corrupts history.
4. **Backfill** — once an entity is resolved, fact rows are pointed at it via
   `drug_id` / `sponsor_id` / `patent_id`.

Patent numbers are normalized (strip country prefix, leading zeros, and
kind-code noise) before matching, because FDA and USPTO formats differ.

## Reading the graph

| Endpoint | Returns |
| --- | --- |
| `GET /api/v1/search` | Unified search hits across every node type |
| `GET /api/v1/drugs/{drug_id}/360` | The full neighborhood: NDAs, ANDAs, patents, PTE, FTF, moieties, Orange Book, alerts |
| `GET /api/v1/graph/stats` | Node and edge counts by type, for the graph dashboard |
| `GET /api/v1/patents` | Patent-centric view with linked PTE and FTF events |

## Why a graph and not just joins?

The fact tables answer "what changed in this source". The graph answers "what
does this mean for this product": a Paragraph IV certification matters because
of the patent it challenges, the drug it protects, the sponsor that owns it, and
the exclusivity it threatens. Those hops are not a fixed join path — a query can
enter from any node — so the graph stores the resolved edges once and traverses
cheaply, rather than computing multi-way joins per request.
