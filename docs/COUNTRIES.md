# Identifiers across the Spanish-speaking world

`DeidEngine(country="ALL")` (the default) enables every recognizer below in
addition to the core rules: Mexican CURP/RFC/CLABE, checksum-validated IBAN and
payment cards, e-mail, labelled names, addresses, secrets and health terms.
Restrict the pack with an ISO code or list, for example `country="ES"` or
`country="AR,CL,UY"`. Unknown codes raise an error.

A passing check digit shows that a value is well formed, not that it was issued
or who holds it. Values made of one repeated digit are treated as placeholders.

## Acceptance rules

- **check digit**: reported when the official check digit validates; with a
  field label an invalid value is still reported, scored 0.55, so the document
  needs review.
- **distinctive format**: fixed separators, embedded dates or a letter prefix
  make the value recognizable on its own.
- **field label required**: the digits alone are ambiguous (for example an
  8-digit DNI or a 10-digit Ecuadorian cédula that looks like a phone number),
  so a label such as `DNI`, `cédula`, `C.I.`, `RUC`, `NIT`, `RNC`, `DUI`, `DPI`,
  `NSS` or `seguridad social` must precede the value. Short connectors are
  allowed: `DNI nº`, `su DNI es`, `cédula de ciudadanía`.

## Supported identifiers

| Recognizer | Countries | Category | Acceptance | Field labels |
| --- | --- | --- | --- | --- |
| ES-DNI | ES | `NATIONAL_ID` | check digit | dni |
| ES-NIE | ES | `NATIONAL_ID` | check digit | nie, dni |
| ES-CIF | ES | `TAX_ID` | check digit | nit |
| ES-NSS | ES | `INSURANCE_ID` | field label required | nss |
| ES-CCC | ES | `BANK_ACCOUNT` | check digit | account |
| AR-CUIT (CUIT/CUIL) | AR | `TAX_ID` | check digit | — |
| AR-CBU | AR | `BANK_ACCOUNT` | check digit | account |
| CL-RUT (RUT/RUN) | CL | `NATIONAL_ID` | check digit | cedula, dni |
| UY-CI | UY | `NATIONAL_ID` | check digit | cedula |
| CO-NIT | CO | `TAX_ID` | check digit | nit |
| PE-RUC | PE | `TAX_ID` | check digit | ruc |
| EC-CI | EC | `NATIONAL_ID` | field label required | cedula |
| EC-RUC | EC | `TAX_ID` | field label required | ruc |
| VE-CI (V-/E-) | VE | `NATIONAL_ID` | distinctive format | — |
| VE-RIF | VE | `TAX_ID` | check digit | rif, nit |
| PY-RUC | PY | `TAX_ID` | field label required | ruc |
| CU-NI (carné de identidad) | CU | `NATIONAL_ID` | field label required | carne, cedula |
| HN-DNI | HN | `NATIONAL_ID` | distinctive format | — |
| NI-CEDULA | NI | `NATIONAL_ID` | distinctive format | — |
| PA-CEDULA | PA | `NATIONAL_ID` | field label required | cedula |
| CR-CEDULA | CR | `NATIONAL_ID` | distinctive format | — |
| DO-CEDULA | DO | `NATIONAL_ID` | check digit (Luhn) | cedula |
| DO-RNC | DO | `TAX_ID` | field label required | rnc |
| GT-NIT | GT | `TAX_ID` | field label required | nit |
| SV-NIT | SV | `TAX_ID` | check digit | nit |
| CR-CEDULA-JURIDICA | CR | `TAX_ID` | distinctive format | — |
| UY-RUT | UY | `TAX_ID` | field label required (check digit scored) | rut |
| US-EIN | US, PR | `TAX_ID` | field label required | ein |
| GT-DPI (CUI) | GT | `NATIONAL_ID` | field label required | dpi, dni |
| SV-DUI | SV | `NATIONAL_ID` | field label required | dui |
| MX-NSS (IMSS) | MX | `INSURANCE_ID` | field label required | nss |
| MX-CLAVE-ELECTOR (INE) | MX | `NATIONAL_ID` | distinctive format | — |
| US-SSN | US, PR | `NATIONAL_ID` | distinctive format | — |
| LATAM-DNI | AR, BO, CL, CO, GT, HN, PE, PY, UY | `NATIONAL_ID` | field label required | dni, cedula |
| LATAM-CEDULA | BO, CO, CR, CU, EC, HN, NI, PA, PY, VE | `NATIONAL_ID` | field label required | cedula |
| BANK-ACCOUNT | all | `BANK_ACCOUNT` | field label required | account (`cuenta`, `cta.`, `CBU`, `CVU`, `CLABE`, `número de cuenta`) |

The `LATAM-*` and `BANK-ACCOUNT` rows are generic fallbacks: they never raise
the score of digits that a country-specific validator rejected (an invalid
check digit stays an uncertain candidate), and they do not stop CLABE or card
validation from typing the same digits.

Also in the international pack, for every country:

- Phone numbers in international format for Spain, Equatorial Guinea, Latin
  America and the NANP (`+34 612 345 678`, `+54 9 11 4123-4567`), and Spanish
  national groupings (`612 34 56 78`, `91 123 45 67`). Any national grouping of
  7–13 digits right after a phone label or call verb (`Teléfono del tutor:`,
  `llame al`, `WhatsApp`, `cel.`) is also detected.
- IPv4 and IPv6 addresses (`IP_ADDRESS`), validated by the standard library.
- Spanish textual dates (`3 de marzo de 1985`, `marzo de 2020`) and short
  numeric dates with the same separator twice (`15/3/2021`); with a birth-date
  label they become `DATE_OF_BIRTH`.

## Street addresses

Without a field label (`Domicilio:` and `Dirección:` were already recognized),
`deidflow.detectors.addresses` reports addresses written in these forms:

| Form | Example | Score |
| --- | --- | ---: |
| Colombian grid nomenclature | `Calle 45 # 12-30`, `Cra. 7 No. 71-21, Apto 502`, `Cl. 84 Bis T # 8T-94 Sur` | 0.90 |
| Introduced by a residence word (`domicilio en`, `vivo en`, `reside en`, `ubicada en`...) | `Los Alerces 33`, `416 Paseo de Martí` | 0.85 |
| Street type, capitalized name and number | `C/ Pintor Baeza, 11`, `Av. Kansas City 92, 8ºB`, `Jr. Huallaga 123` | 0.80 (0.85 with unit or colonia) |
| Mexican colonia and postal code | `Av. Insurgentes Sur 1602, Col. Crédito Constructor, C.P. 03940` | 0.80–0.85 |

Floors, doors and units (`Piso 2`, `8ºB`, `Bajo A`, `Dpto. 302`, `Int. 4`) are
included. A street without a number, or followed by a bounded measurement or
duration expression (`la Plaza Mayor 3 veces`, `Glasgow 15 puntos`), is not reported.
Ordinary prose after an apartment or colony does not shorten the address.
Overlapping candidates become one
finding, the longest. The following are historical PR #27 measurements before
the 0.6 boundary and measurement-context corrections. On validation only
(MEDDOCAN dev, the Gretel holdout and
the synthetic validation families) rules-only exact F1 rose from 0.515 to 0.531,
0.311 to 0.323 and 0.462 to 0.524, and address character coverage from 0.61 to
0.86 (clinical) and 0.00 to 0.86 (synthetic); with `builtin:auto` exact F1 stayed
within 0.005 and character coverage rose on the financial and synthetic sets
(0.824 to 0.826, 0.855 to 0.868). Most new predictions on the financial set
that matched no gold span were company addresses the corpus left unannotated.

## Verification

`tests/test_international.py` compares 15 of these validators with
[python-stdnum](https://arthurdejong.org/python-stdnum/) on thousands of random
values, one check character at a time, plus Ecuador's RUC variants; uses
published example values for the others; checks negatives such as amounts,
times, versions and scores; and bounds runtime on adversarial input. Spain's
NSS and Mexico's IMSS NSS have no python-stdnum module, so they require a field
label.

The original international rules below were developed on validation data only:
MEDDOCAN dev, the Gretel train
holdout and the training families of the synthetic multi-country corpus
(`deidflow.benchmarks.synthetic_es`). MEDDOCAN dev rules exact F1 rose from 0.493
to 0.515 (precision 0.685 to 0.697, recall 0.385 to 0.408; dates 0.72 to 0.88,
phones 0.07 to 0.71); Gretel validation rules recall rose for national IDs from
0.00 to 0.45, IP addresses from 0.00 to 0.83 and phones from 0.91 to 0.96, with
rules + tagger character coverage unchanged or slightly higher. On the synthetic
training families the rules now cover every generated national ID, tax ID, bank
account and IP address, and 145 of 153 phone numbers.

The 0.6 context rules also incorporate observed synthetic regression failures;
those updated measurements are explicitly diagnostic, not untouched validation.
See [context evaluation](CONTEXT_BENCHMARK.md) for the current configuration,
digests and results. Historical figures above do not measure the final 0.6 tree.
