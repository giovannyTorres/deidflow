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
| ES-CCC | ES | `BANK_ACCOUNT` | check digit | — |
| AR-CUIT (CUIT/CUIL) | AR | `TAX_ID` | check digit | — |
| AR-CBU | AR | `BANK_ACCOUNT` | check digit | — |
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
| GT-DPI (CUI) | GT | `NATIONAL_ID` | field label required | dpi, dni |
| SV-DUI | SV | `NATIONAL_ID` | field label required | dui |
| MX-NSS (IMSS) | MX | `INSURANCE_ID` | field label required | nss |
| MX-CLAVE-ELECTOR (INE) | MX | `NATIONAL_ID` | distinctive format | — |
| US-SSN | US, PR | `NATIONAL_ID` | distinctive format | — |
| LATAM-DNI | AR, BO, CL, CO, GT, HN, PE, PY, UY | `NATIONAL_ID` | field label required | dni, cedula |
| LATAM-CEDULA | BO, CO, CR, CU, EC, HN, NI, PA, PY, VE | `NATIONAL_ID` | field label required | cedula |

Also in the international pack, for every country:

- Phone numbers in international format for Spain, Equatorial Guinea, Latin
  America and the NANP (`+34 612 345 678`, `+54 9 11 4123-4567`), and Spanish
  national groupings (`612 34 56 78`, `91 123 45 67`). Labelled numbers of 7–12
  digits are also detected by the core rules.
- IPv4 and IPv6 addresses (`IP_ADDRESS`), validated by the standard library.
- Spanish textual dates (`3 de marzo de 1985`, `marzo de 2020`) and short
  numeric dates with the same separator twice (`15/3/2021`); with a birth-date
  label they become `DATE_OF_BIRTH`.

## Verification

`tests/test_international.py` compares 13 of these validators with
[python-stdnum](https://arthurdejong.org/python-stdnum/) on thousands of random
values, one check character at a time, plus Ecuador's RUC variants; uses
published example values for the others; checks negatives such as amounts,
times, versions and scores; and bounds runtime on adversarial input. Spain's
NSS and Mexico's IMSS NSS have no python-stdnum module, so they require a field
label.

On validation data the pack raised MEDDOCAN dev rules exact F1 from 0.493 to
0.515 (precision 0.685 to 0.697, recall 0.385 to 0.408; dates 0.72 to 0.88,
phones 0.07 to 0.68) and Gretel validation rules recall for national IDs from
0.00 to 0.45 and IP addresses from 0.00 to 0.83, with rules + tagger character
coverage unchanged or slightly higher.
