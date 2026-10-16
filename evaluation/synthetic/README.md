# Synthetic Task 2 cases

36 invented cases, 12 per case type, 6 `angenommen` / 6 `abgelehnt` each, in the format of the official spot-check
sets: same folder prefixes, PDFs with a text layer, the same three retrieval corpora, `ground-truth.jsonl` for the
official evaluator. Purpose: measure how the solvers generalise beyond the 21 spot-check cases their rules were
written on.

About half the cases are **new patterns**: rules from the University of Kassel intranet pages in
`university-kassel-public-de` that no spot-check case tests. The other half are **variants** of spot-check patterns
with new surface forms. Format variations the hidden set may contain: file names without a type hint
(`Anlage_1.pdf`), several receipts or attachments in one scanned PDF, English vendor documents, foreign currency,
reverse-charge offers, and TH Sallstedt cases (other state law, decided on the documents alone).

**The labels are our reading of the corpus rules, not organiser gold.** Cases marked (?) below are the ones where
a reviewer could reasonably decide the other way; check them before tuning on them.

## Generate

```bash
pip install reportlab==4.2.5            # generator only, not a solver dependency
python evaluation/synthetic/make_synthetic.py
```

Writes `datasets/<name>/inputs/` (PDFs, retrieval corpora as hard links to `uniagent-code`), `ground-truth.jsonl`,
and `datasets/cases.jsonl` (label, pattern, rule, corpus `doc_id`, new or variant). The cases are committed; the
retrieval corpora are git-ignored, so run the generator once (with `uniagent-code` next to this repo) before a run.

## Run and score

```bash
export OPENAI_BASE_URL=https://openrouter.ai/api/v1 OPENAI_API_KEY=... OPENAI_MODEL=openai/gpt-oss-20b
export DATASETS_DIR=evaluation/synthetic/datasets
export DATASETS="synthetic-business-trip synthetic-procurement synthetic-expense-reimbursement"
evaluation/run-mvp.sh team team-solver evaluation/runs/synthetic/gpt-oss-20b bridge -- python3 /app/predict.py
```

## Cases

Sources: `DRM` Dienstreisemanagement `8f78f05e…`, `FIN` Finanzbuchhaltung und Steuern `df8a9f54…`,
`BES` Beschaffung `8521d5be…`, `RV` Rahmenverträge `aef7cd6c…`, `CAT` Nachhaltiges Catering `08143d1c…`
(1,000 EUR direct-award limit).

### `synthetic-business-trip` (University of Kassel, FB 16)

| Case | Result | Kind | Pattern | Rule (source) |
|---|---|---|---|---|
| 01 | angenommen | variant | Domestic talk, hotel 78 EUR addressed to the university, on time | regular case (DRM) |
| 02 | abgelehnt | new | Domestic hotel 139 EUR/night, no reason given | > 80 EUR only with written reason at application (DRM) |
| 03 | angenommen | new, trap | Hotel 118 EUR/night during a trade fair, necessity argued and search printout attached | same rule, satisfied (DRM) |
| 04 | abgelehnt | new | Complete trip to Beirut, Lebanon | trips to Lebanon are not approved until further notice (DRM) |
| 05 | abgelehnt | new | Invited talk; the invitation (not the form) offers an 800 EUR fee | a fee indicates a side activity, no business trip (DRM) |
| 06 | angenommen | variant, trap | Organiser pays the hotel, declared and not claimed; attachments in one scanned PDF | third-party benefits declared and offset (DRM) |
| 07 | abgelehnt | new | Domestic flight Frankfurt–Berlin, no reason, no price comparison | domestic flights only if cheaper or justified (DRM) |
| 08 | angenommen | variant | Summer school in Vienna, A1 applied 10 weeks ahead, English documents | complete foreign trip (DRM) |
| 09 | abgelehnt | new | Online conference submitted as a business trip with daily allowance | online events are no business trips (DRM) |
| 10 | angenommen | new | Day trip by private car at 0.21 EUR/km, no parking claimed | mileage without compelling reason (DRM) |
| 11 | abgelehnt | new | Funding field empty, purpose "Abstimmung", no invitation or programme | forms complete, evidence of official purpose attached (DRM) |
| 12 | angenommen | variant | Training course, private BahnCard 50 used, files named `Anlage_N.pdf` | own BahnCard must be used (DRM) |

### `synthetic-expense-reimbursement` (Wernstadt, case 10 Sallstedt)

| Case | Result | Kind | Pattern | Rule (source) |
|---|---|---|---|---|
| 01 | angenommen | variant | Hardware-store receipt with article names and purpose note | original receipt, purpose visible (FIN) |
| 02 | abgelehnt | new (?) | Private Citavi licence | Citavi is a campus licence paid centrally (RV) |
| 03 | angenommen | new, trap | Coffee, water, pastries for a meeting with 4 external guests, participant list | courtesy for guests is operating expense (FIN) |
| 04 | abgelehnt | new (?) | One person paid and claims the workshop fees of three colleagues | costs advanced for several people are not refunded to the payer alone (DRM) |
| 05 | angenommen | variant | English GBP invoice for a standard, card statement shows EUR | foreign currency proven by statement |
| 06 | abgelehnt | variant | Till receipt with article numbers only, no keyword, no university link | receipt without articles needs a keyword (FIN) |
| 07 | abgelehnt | new | Monitor bought in a web shop and claimed as expense | monitors only via the framework partner in WPS (RV) |
| 08 | angenommen | new | 250 logo pens at 0.84 EUR for the university's trade-fair stand | give-aways up to 10 EUR at fairs (FIN) |
| 09 | abgelehnt | new | Guest gift for a partner university, 64.90 EUR | guest gifts on trips up to 30 EUR (FIN) |
| 10 | angenommen | variant | Sallstedt: urgent lab chemicals, invoice to the university | documents complete (other state law) |
| 11 | abgelehnt | new | Christmas tree and decoration for the institute foyer | decoration items not reimbursable (FIN) |
| 12 | angenommen | new, trap | Three receipts from three shops in one scan, summary adds up to 98.15 EUR | original receipts with articles and purpose (FIN) |

### `synthetic-procurement` (Wernstadt, cases 10–11 Sallstedt)

| Case | Result | Kind | Pattern | Rule (source) |
|---|---|---|---|---|
| 01 | angenommen | variant | Three offers (one in English), cheapest chosen, form and award note agree | three offers (BES) |
| 02 | abgelehnt | new | Award to the second-cheapest offer, no reason | award to the most economical offer |
| 03 | angenommen | new, trap | Not the cheapest: the cheapest reaches only -40 °C, -80 °C is required and documented | most economical suitable offer |
| 04 | abgelehnt | new (?) | Two 940 EUR direct awards for identical printers, explicitly to stay below the limit | direct award below 1,000 EUR (CAT); splitting to avoid it |
| 05 | angenommen | new, trap (?) | Direct award at 948 EUR net / 1,128.12 EUR gross | limit applies to the net order value (CAT) |
| 06 | abgelehnt | new | Microsoft Office licences from a reseller | framework contract for Microsoft software (RV) |
| 07 | abgelehnt | new | Office swivel chairs with three offers from furniture dealers | framework contract for office swivel chairs (RV) |
| 08 | angenommen | new | Bottled gases from the WPS framework catalogue, 2,142.96 EUR net, no offers | framework catalogue bottled gases (RV) |
| 09 | abgelehnt | new | Budget holder did not sign; e-mail says the professor is unreachable | orders must be commissioned by the budget holder (BES) |
| 10 | angenommen | variant | Sallstedt: three offers in a thread, invoice equals the offer, signed as correct | documents complete |
| 11 | abgelehnt | new | Sallstedt: invoice adds an unordered 285 EUR installation flat rate | invoices must match the ordered offer |
| 12 | angenommen | new, trap | Cheapest offer is a Dutch quotation without German VAT (reverse charge), net comparison | award to the cheapest offer (net) |

(?) Reasons for doubt: Citavi (02) and several payers (04) apply rules from other contexts (campus licence page,
business-trip page) to expense claims; splitting (04) is general procurement law, not stated on the Kassel pages;
whether the 1,000 EUR limit is net (05) is not stated on the Kassel pages, net is the procurement-law convention.
