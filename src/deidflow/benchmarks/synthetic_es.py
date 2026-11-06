"""Seeded synthetic Spanish documents with exact gold spans, for every country pack.

Values come from Faker locales (names, companies, streets) and from DeidFlow's
own validators (identifiers are generated with valid check digits). Templates
were written by hand for many document genres and are split by template family,
so validation and test documents use phrasings never seen in training.
Everything is fictional; the corpus measures coverage of formats and contexts,
not real-world prevalence.
"""

from __future__ import annotations

import random
import re
import string
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from deidflow.validators import clabe_check_digit
from deidflow.validators import international as v

from .datasets import Example, GoldSpan

MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre",
]  # fmt: skip


def _digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(string.digits) for _ in range(n))


def _with_check(
    rng: random.Random,
    body: Callable[[], str],
    validator: Callable[[str], Any],
    checks: str = string.digits,
) -> str:
    for _ in range(200):
        prefix = body()
        valid = [prefix + c for c in checks if validator(prefix + c).status == "checksum"]
        if valid:
            return valid[0]
    raise RuntimeError("Could not generate a valid identifier")


def _group(value: str, sizes: tuple[int, ...], sep: str) -> str:
    parts, index = [], 0
    for size in sizes:
        parts.append(value[index : index + size])
        index += size
    if index < len(value):
        parts.append(value[index:])
    return sep.join(p for p in parts if p)


def _dots(number: str) -> str:
    return f"{int(number):,}".replace(",", ".")


@dataclass
class CountryProfile:
    code: str
    locale: str
    cities: tuple[str, ...]
    id_labels: tuple[str, ...]
    national_id: Callable[[random.Random], str]
    tax_labels: tuple[str, ...]
    tax_id: Callable[[random.Random], str]
    phone: Callable[[random.Random], str]
    account_labels: tuple[str, ...] = ("cuenta",)
    account: Callable[[random.Random], str] | None = None
    currency: str = "$"
    extra: dict[str, Any] = field(default_factory=dict)


def _es_dni(rng: random.Random) -> str:
    return _with_check(rng, lambda: _digits(rng, 8), v.validate_es_dni, "TRWAGMYFPDXBNJZSQVHLCKE")


def _es_nie(rng: random.Random) -> str:
    return _with_check(
        rng,
        lambda: rng.choice("XYZ") + _digits(rng, 7),
        v.validate_es_nie,
        "TRWAGMYFPDXBNJZSQVHLCKE",
    )


def _es_cif(rng: random.Random) -> str:
    return _with_check(rng, lambda: rng.choice("ABG") + _digits(rng, 7), v.validate_es_cif)


def _iban_es(rng: random.Random) -> str:
    entity, office, account = _digits(rng, 4), _digits(rng, 4), _digits(rng, 10)
    bban = f"{entity}{office}{v._ccc_digit('00' + entity + office)}{v._ccc_digit(account)}{account}"
    number = int("".join(str(int(c, 36)) for c in bban + "ES00"))
    iban = f"ES{98 - number % 97:02d}{bban}"
    return _group(iban, (4, 4, 4, 4, 4, 4), " ") if rng.random() < 0.6 else iban


def _ar_cbu(rng: random.Random) -> str:
    first, second = _digits(rng, 7), _digits(rng, 13)
    return first + v._cbu_digit(first) + second + v._cbu_digit(second)


def _mx_curp(rng: random.Random) -> str:
    from deidflow.validators import curp_check_digit

    letters = (
        "".join(rng.choice("BCDFGHJKLMNPRSTVZ") for _ in range(1))
        + rng.choice("AEIOU")
        + "".join(rng.choice(string.ascii_uppercase) for _ in range(2))
    )
    birth = date(1950, 1, 1) + timedelta(days=rng.randrange(20000))
    prefix = (
        letters
        + birth.strftime("%y%m%d")
        + rng.choice("HM")
        + rng.choice(["DF", "JC", "NL", "PL", "MC", "GT", "VZ", "YN"])
        + "".join(rng.choice("BCDFGHJKLMNPRSTVZ") for _ in range(3))
        + rng.choice("0A")
    )
    return prefix + curp_check_digit(prefix)


def _mx_rfc(rng: random.Random) -> str:
    from deidflow.validators import rfc_check_digit

    birth = date(1950, 1, 1) + timedelta(days=rng.randrange(20000))
    prefix = (
        "".join(rng.choice("BCDFGHJKLMNPRSTVZ") for _ in range(1))
        + rng.choice("AEIOU")
        + "".join(rng.choice(string.ascii_uppercase) for _ in range(2))
        + birth.strftime("%y%m%d")
        + "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(2))
    )
    return prefix + rfc_check_digit(prefix)


def _mx_clabe(rng: random.Random) -> str:
    prefix = _digits(rng, 17)
    return prefix + clabe_check_digit(prefix)


def _phone(
    code: str, groups: tuple[int, ...], national_prefix: str = ""
) -> Callable[[random.Random], str]:
    def make(rng: random.Random) -> str:
        body = [_digits(rng, n) for n in groups]
        if rng.random() < 0.55:
            return f"+{code} " + " ".join(body)
        return national_prefix + " ".join(body)

    return make


PROFILES: dict[str, CountryProfile] = {
    "MX": CountryProfile(
        "MX", "es_MX", ("Ciudad de México", "Guadalajara", "Monterrey", "Puebla", "Mérida", "Querétaro", "Toluca", "León"),
        ("CURP",), _mx_curp, ("RFC",), _mx_rfc, _phone("52", (2, 4, 4)), ("CLABE", "cuenta CLABE"), _mx_clabe,
    ),
    "ES": CountryProfile(
        "ES", "es_ES", ("Madrid", "Barcelona", "Valencia", "Sevilla", "Zaragoza", "Málaga", "Bilbao", "Valladolid"),
        ("DNI", "NIF", "NIE"), lambda r: _es_nie(r) if r.random() < 0.2 else _es_dni(r), ("CIF",), _es_cif,
        _phone("34", (3, 3, 3)), ("IBAN", "cuenta"), _iban_es, "€",
    ),
    "AR": CountryProfile(
        "AR", "es_AR", ("Buenos Aires", "Córdoba", "Rosario", "Mendoza", "La Plata", "Mar del Plata", "Salta"),
        ("DNI",), lambda r: _dots(str(r.randrange(10_000_000, 45_000_000))), ("CUIT", "CUIL"),
        lambda r: _group(_with_check(r, lambda: r.choice(["20", "23", "27", "30"]) + _digits(r, 8), v.validate_ar_cuit), (2, 8, 1), "-"),
        _phone("54", (2, 4, 4)), ("CBU",), _ar_cbu,
    ),
    "CO": CountryProfile(
        "CO", "es_CO", ("Bogotá", "Medellín", "Cali", "Barranquilla", "Cartagena", "Bucaramanga", "Pereira"),
        ("cédula de ciudadanía", "C.C.", "cédula"), lambda r: _dots(str(r.randrange(10_000_000, 1_200_000_000))),
        ("NIT",), lambda r: (lambda n: _dots(n[:-1]) + "-" + n[-1])(_with_check(r, lambda: "9" + _digits(r, 8), v.validate_co_nit)),
        _phone("57", (3, 3, 4)),
    ),
    "CL": CountryProfile(
        "CL", "es_CL", ("Santiago", "Valparaíso", "Concepción", "La Serena", "Antofagasta", "Temuco", "Rancagua"),
        ("RUT", "RUN"), lambda r: (lambda n: _dots(n[:-1]) + "-" + n[-1])(_with_check(r, lambda: str(r.randrange(5_000_000, 25_000_000)), v.validate_cl_rut, string.digits + "K")),
        ("RUT",), lambda r: (lambda n: _dots(n[:-1]) + "-" + n[-1])(_with_check(r, lambda: str(r.randrange(76_000_000, 77_999_999)), v.validate_cl_rut, string.digits + "K")),
        _phone("56", (1, 4, 4)),
    ),
    "PE": CountryProfile(
        "PE", "es", ("Lima", "Arequipa", "Trujillo", "Cusco", "Chiclayo", "Piura", "Iquitos"),
        ("DNI",), lambda r: _digits(r, 8), ("RUC",), lambda r: _with_check(r, lambda: "20" + _digits(r, 8), v.validate_pe_ruc),
        _phone("51", (3, 3, 3)), currency="S/",
    ),
    "EC": CountryProfile(
        "EC", "es", ("Quito", "Guayaquil", "Cuenca", "Ambato", "Manta", "Loja", "Machala"),
        ("cédula", "C.I."), lambda r: _with_check(r, lambda: f"{r.randint(1, 24):02d}{r.randint(0, 5)}" + _digits(r, 6), v.validate_ec_ci),
        ("RUC",), lambda r: _with_check(r, lambda: f"{r.randint(1, 24):02d}{r.randint(0, 5)}" + _digits(r, 6), v.validate_ec_ci) + "001",
        _phone("593", (2, 3, 4)),
    ),
    "VE": CountryProfile(
        "VE", "es", ("Caracas", "Maracaibo", "Valencia", "Barquisimeto", "Maracay", "Mérida"),
        ("C.I.", "cédula"), lambda r: r.choice("VE") + "-" + _dots(str(r.randrange(5_000_000, 32_000_000))),
        ("RIF",), lambda r: (lambda n: n[0] + "-" + n[1:9] + "-" + n[9])(_with_check(r, lambda: r.choice("VJ") + _digits(r, 8), v.validate_ve_rif)),
        _phone("58", (3, 3, 4)), currency="Bs.",
    ),
    "UY": CountryProfile(
        "UY", "es", ("Montevideo", "Salto", "Paysandú", "Maldonado", "Rivera"),
        ("C.I.", "cédula de identidad"), lambda r: (lambda n: _dots(n[:-1]) + "-" + n[-1])(_with_check(r, lambda: str(r.randrange(1_000_000, 6_999_999)), v.validate_uy_ci)),
        ("RUT",), lambda r: _with_check(r, lambda: f"{r.randint(1, 22):02d}" + _digits(r, 6) + "001", v.validate_uy_rut),
        _phone("598", (2, 3, 3)),
    ),
    "GT": CountryProfile(
        "GT", "es", ("Ciudad de Guatemala", "Quetzaltenango", "Escuintla", "Antigua Guatemala"),
        ("DPI", "CUI"), lambda r: f"{_digits(r, 4)} {_digits(r, 5)} {r.randint(1, 22):02d}{_digits(r, 2)}",
        ("NIT",), lambda r: (lambda n: n[:-1] + "-" + n[-1])(_with_check(r, lambda: _digits(r, 7), v.validate_gt_nit, string.digits + "K")),
        _phone("502", (4, 4)), currency="Q",
    ),
    "DO": CountryProfile(
        "DO", "es", ("Santo Domingo", "Santiago de los Caballeros", "La Romana", "Puerto Plata"),
        ("cédula",), lambda r: _group(_with_check(r, lambda: _digits(r, 10), v.validate_do_cedula), (3, 7, 1), "-"),
        ("RNC",), lambda r: _with_check(r, lambda: "1" + _digits(r, 7), v.validate_do_rnc),
        _phone("1", (3, 3, 4)),
    ),
    "SV": CountryProfile(
        "SV", "es", ("San Salvador", "Santa Ana", "San Miguel", "Soyapango"),
        ("DUI",), lambda r: (lambda n: n[:8] + "-" + n[8])(_with_check(r, lambda: _digits(r, 8), v.validate_sv_dui)),
        ("NIT",), lambda r: _group(_with_check(r, lambda: "0" + _digits(r, 12), v.validate_sv_nit), (4, 6, 3, 1), "-"),
        _phone("503", (4, 4)),
    ),
    "CR": CountryProfile(
        "CR", "es", ("San José", "Alajuela", "Cartago", "Heredia", "Liberia"),
        ("cédula",), lambda r: f"{r.randint(1, 9)}-{_digits(r, 4)}-{_digits(r, 4)}",
        ("cédula jurídica",), lambda r: f"3-101-{_digits(r, 6)}", _phone("506", (4, 4)), currency="₡",
    ),
    "US": CountryProfile(
        "US", "es", ("Miami", "Los Ángeles", "Houston", "San Juan", "Nueva York", "Chicago"),
        ("SSN", "número de seguro social"), lambda r: f"{r.randint(100, 665)}-{r.randint(10, 99)}-{r.randint(1000, 9999)}",
        ("EIN",), lambda r: f"{_digits(r, 2)}-{_digits(r, 7)}", _phone("1", (3, 3, 4)), currency="US$",
    ),
}  # fmt: skip


# Templates: {SLOT} placeholders; {ID_LABEL}/{TAX_LABEL}/{ACCOUNT_LABEL} insert
# the country's own label words (not entities). Each tuple is (family, text).
TEMPLATES: tuple[tuple[str, str], ...] = (
    (
        "correo-1",
        "Asunto: Confirmación de cita\n\nEstimado/a {PERSON}:\n\nLe confirmamos su cita para el {DATE} en nuestra oficina de {ADDRESS}, {CITY}. Si necesita reprogramar, escríbanos a {EMAIL} o llame al {PHONE}.\n\nAtentamente,\n{PERSON2}\n{ORG}",
    ),
    (
        "correo-2",
        "Hola {FIRST},\n\nte reenvío el contrato que firmamos con {ORG}. Mi número nuevo es {PHONE}. Avísame si {PERSON2} ya lo revisó.\n\nSaludos",
    ),
    (
        "contrato-1",
        "CONTRATO DE ARRENDAMIENTO\n\nEn {CITY}, a {DATE}, comparecen por una parte {PERSON}, con {ID_LABEL} {ID}, con domicilio en {ADDRESS}, en adelante EL ARRENDADOR; y por la otra {PERSON2}, con {ID_LABEL} {ID2}, en adelante EL ARRENDATARIO. La renta mensual de {AMOUNT} se depositará en la {ACCOUNT_LABEL} {ACCOUNT}.",
    ),
    (
        "contrato-2",
        "CONTRATO DE PRESTACIÓN DE SERVICIOS celebrado entre {ORG}, {TAX_LABEL} {TAX}, representada por {PERSON}, y el profesional {PERSON2}, nacido el {DOB}, quien señala como domicilio {ADDRESS}. Correo de contacto: {EMAIL}.",
    ),
    (
        "factura-1",
        "FACTURA N.º {INVOICE}\nEmisor: {ORG}  {TAX_LABEL}: {TAX}\nCliente: {PERSON}  {ID_LABEL}: {ID}\nDirección: {ADDRESS}, {CITY}\nFecha de emisión: {DATE}\nTotal: {AMOUNT}\nForma de pago: transferencia a {ACCOUNT_LABEL} {ACCOUNT}",
    ),
    (
        "factura-2",
        "Recibo de pago\nRecibimos de {PERSON} la cantidad de {AMOUNT} por concepto de servicios profesionales del mes de {MONTH_YEAR}.\nTeléfono del cliente: {PHONE}\n{CITY}, {DATE}",
    ),
    (
        "nomina-1",
        "RECIBO DE NÓMINA\nEmpleado: {PERSON}\nNúmero de empleado: {EMPLOYEE}\n{ID_LABEL}: {ID}\nPuesto: {JOB}\nPeriodo: {MONTH_YEAR}\nDepósito en {ACCOUNT_LABEL} {ACCOUNT}",
    ),
    (
        "rrhh-1",
        "Expediente de personal\n\nNombre completo: {PERSON}\nFecha de nacimiento: {DOB}\nEdad: {AGE} años\nDomicilio: {ADDRESS}, {CITY}\nTeléfono: {PHONE}\nCorreo personal: {EMAIL}\nContacto de emergencia: {PERSON2} ({PHONE2})",
    ),
    (
        "clinica-1",
        "NOTA DE EVOLUCIÓN\nPaciente: {PERSON}, {AGE} años. Expediente {PATIENT}.\nAcude acompañado de su esposa {PERSON2} por dolor torácico de dos días de evolución. Se indica valoración por cardiología en el {ORG}.\nMédico tratante: Dr. {PERSON3}",
    ),
    (
        "clinica-2",
        "Receta médica\nNombre del paciente: {PERSON}\n{ID_LABEL}: {ID}\nFecha: {DATE}\nParacetamol 500 mg cada 8 horas por 5 días.\nFirma: {PERSON2}, cédula profesional {PROF}",
    ),
    (
        "clinica-3",
        "Informe de alta. El paciente {PERSON}, de {AGE} años, con domicilio en {CITY}, ingresó el {DATE} y egresa el {DATE2} en buen estado general. Se recomienda control con su médico familiar. Teléfono de contacto: {PHONE}.",
    ),
    (
        "denuncia-1",
        "ACTA DE DENUNCIA\nEn la ciudad de {CITY}, siendo el {DATE}, se presenta {PERSON}, quien se identifica con {ID_LABEL} {ID}, y manifiesta que su vecino {PERSON2}, domiciliado en {ADDRESS}, le sustrajo su teléfono celular con número {PHONE}.",
    ),
    (
        "sentencia-1",
        "VISTOS para resolver los autos del expediente {CASE}, promovido por {PERSON} en contra de {ORG}, y considerando que la parte actora, con domicilio en {ADDRESS}, acreditó la relación laboral mediante el recibo de nómina a su nombre, se resuelve condenar a la demandada.",
    ),
    (
        "sentencia-2",
        "El tribunal, integrado por los magistrados {PERSON} y {PERSON2}, dicta la presente resolución en la causa seguida contra {PERSON3}, de {AGE} años, natural de {CITY}, con {ID_LABEL} {ID}.",
    ),
    (
        "chat-1",
        "[{TIME}] {FIRST}: oye me pasas el número de {FIRST2}?\n[{TIME2}] {FIRST2B}: sí, es {PHONE}\n[{TIME3}] {FIRST}: gracias!! y su correo? \n[{TIME4}] {FIRST2B}: {EMAIL}",
    ),
    (
        "chat-2",
        "Buenas tardes, soy {PERSON} y quiero cancelar mi tarjeta terminación {CARD_LAST}. Mi {ID_LABEL} es {ID} y vivo en {ADDRESS}.",
    ),
    (
        "formulario-1",
        "SOLICITUD DE CRÉDITO\nNombre(s): {FIRST}\nApellidos: {LAST}\n{ID_LABEL}: {ID}\n{TAX_LABEL}: {TAX}\nFecha de nacimiento: {DOB}\nIngresos mensuales: {AMOUNT}\nEmpresa donde labora: {ORG}\nTeléfono: {PHONE}\nCorreo electrónico: {EMAIL}",
    ),
    (
        "formulario-2",
        "Registro de usuario\nUsuario: {USER}\nCorreo: {EMAIL}\nÚltimo acceso desde la IP {IP} el {DATE}.\nDispositivo registrado a nombre de {PERSON}.",
    ),
    (
        "cv-1",
        "{PERSON_UPPER}\n{ADDRESS} · {CITY} · {PHONE} · {EMAIL}\n\nEXPERIENCIA\n{ORG} — {JOB} (2018 - actualidad)\n{ORG2} — Analista (2014 - 2018)\n\nREFERENCIAS\n{PERSON2}, gerente en {ORG}, tel. {PHONE2}",
    ),
    (
        "carta-1",
        "{CITY}, {DATE}\n\nA quien corresponda:\n\nPor medio de la presente hago constar que {PERSON}, con {ID_LABEL} {ID}, labora en {ORG} desde el {DATE2} desempeñando el puesto de {JOB}.\n\n{PERSON2}\nRecursos Humanos",
    ),
    (
        "banco-1",
        "{ORG}: Estimado(a) {PERSON}, se realizó un cargo por {AMOUNT} a su tarjeta {CARD}. Si no reconoce este movimiento llame al {PHONE}.",
    ),
    (
        "banco-2",
        "Estado de cuenta\nTitular: {PERSON}\n{ACCOUNT_LABEL}: {ACCOUNT}\nSucursal: {ADDRESS}, {CITY}\nPeriodo: {MONTH_YEAR}\nSaldo al corte: {AMOUNT}",
    ),
    (
        "soporte-1",
        "Ticket #{TICKET}\nCliente: {PERSON} ({EMAIL})\nDescripción: no puedo entrar a mi cuenta {USER}, el sistema me bloqueó desde la dirección {IP}. Por favor llamen al {PHONE}.",
    ),
    (
        "llamada-1",
        "Transcripción de llamada. Agente: ¿Me confirma su nombre completo? Cliente: Sí, {PERSON}. Agente: ¿Y su número de {ID_LABEL}? Cliente: {ID}. Agente: Gracias, ¿sigue viviendo en {ADDRESS}? Cliente: No, ahora estoy en {CITY}.",
    ),
    (
        "escolar-1",
        "Boleta de calificaciones\nAlumno: {PERSON}\nMatrícula: {STUDENT}\nTutor: {PERSON2}\nTeléfono del tutor: {PHONE}\nEscuela: {ORG}",
    ),
    (
        "viaje-1",
        "Reserva confirmada para {PERSON}. Vuelo con salida el {DATE} desde {CITY} hacia {CITY2}. Pasaporte: {PASSPORT}. Contacto: {EMAIL}.",
    ),
    (
        "inmobiliaria-1",
        "Se vende departamento en {ADDRESS}, {CITY}. Informes con {PERSON} al {PHONE} o al correo {EMAIL}.",
    ),
    (
        "seguro-1",
        "Póliza {POLICY}\nAsegurado: {PERSON}\nFecha de nacimiento: {DOB}\nBeneficiario: {PERSON2}\n{ID_LABEL} del asegurado: {ID}",
    ),
    (
        "notaria-1",
        "Ante mí, {PERSON}, notario público número {NUMBER} de {CITY}, comparece {PERSON2}, mayor de edad, de ocupación {JOB}, quien se identifica con {ID_LABEL} {ID} y declara tener su domicilio en {ADDRESS}.",
    ),
    (
        "acta-1",
        "Minuta de reunión del {DATE}. Asistentes: {PERSON}, {PERSON2} y {PERSON3}. Se acordó que {FIRST} enviará la propuesta a {ORG} antes del {DATE2}.",
    ),
    (
        "logistica-1",
        "Guía de envío {TRACKING}\nRemitente: {ORG}, {ADDRESS}\nDestinatario: {PERSON}\nDirección de entrega: {ADDRESS2}, {CITY}\nTeléfono: {PHONE}",
    ),
    (
        "prensa-1",
        "{CITY}.— La empresa {ORG} anunció este {DATE} el nombramiento de {PERSON} como nueva directora general. En entrevista, {LAST} señaló que la compañía abrirá oficinas en {CITY2}.",
    ),
    (
        "redes-1",
        "Publicación de @{USER}: ¡Feliz cumpleaños a mi hermana {FIRST}! Nació un {DOB_TEXT} y hoy cumple {AGE}. La celebramos en casa de mi tía {PERSON2}.",
    ),
    (
        "medica-admin-1",
        "Solicitud de reembolso de gastos médicos. Titular de la póliza: {PERSON}, {ID_LABEL} {ID}. Paciente atendido: {PERSON2}. Hospital: {ORG}. Fecha de atención: {DATE}. Depositar en {ACCOUNT_LABEL} {ACCOUNT}.",
    ),
    (
        "legal-2",
        "Por medio del presente escrito, {PERSON}, por mi propio derecho y señalando como domicilio para oír notificaciones el ubicado en {ADDRESS}, autorizo a {PERSON2} para recibir documentos en mi nombre.",
    ),
    (
        "gobierno-1",
        "Trámite de licencia de conducir. Solicitante: {PERSON}. {ID_LABEL}: {ID}. Domicilio: {ADDRESS}. Tipo de sangre: O+. Teléfono: {PHONE}.",
    ),
)

# Training-only families added for es-general-2: more genres from Latin America and
# places mentioned in running text. Validation and test families are unchanged.
EXTRA_TEMPLATES: tuple[tuple[str, str], ...] = (
    (
        "traslado-1",
        "Solicito el traslado de mi expediente de la sede de {CITY} a la de {CITY2}, donde resido desde {MONTH_YEAR}. Atentamente, {PERSON}, {ID_LABEL} {ID}.",
    ),
    (
        "traslado-2",
        "{PERSON} fue trasladado desde el hospital de {CITY} hasta {CITY2} el {DATE}; lo acompañó su hija {PERSON2}.",
    ),
    (
        "biografia-1",
        "{PERSON} nació en {CITY} el {DOB_TEXT} y se mudó con su familia a {CITY2} a los {AGE} años. Hoy trabaja como {JOB} en {ORG}.",
    ),
    (
        "biografia-2",
        "Originaria de {CITY}, {FIRST} estudió en {ORG} y vive actualmente en {ADDRESS}. Su teléfono es {PHONE}.",
    ),
    (
        "aviso-1",
        "AVISO DE FALLECIMIENTO. Con profundo pesar comunicamos el sensible fallecimiento de {PERSON_UPPER}, ocurrido en {CITY} el {DATE}. Sus restos serán velados en {ADDRESS}.",
    ),
    (
        "aviso-2",
        "Se busca a {PERSON}, de {AGE} años, vista por última vez en {CITY} el {DATE}. Cualquier información al {PHONE}.",
    ),
    (
        "whatsapp-1",
        "[{TIME}] {FIRST}: ya llegué a {CITY}, mañana paso por tu casa en {ADDRESS}\n[{TIME2}] {FIRST2}: dale, avísale a {PERSON3} también",
    ),
    (
        "whatsapp-2",
        "{FIRST}: me pasas el número de {PERSON2}?\n{FIRST2}: claro, es {PHONE}\n{FIRST}: gracias, y su correo?\n{FIRST2}: {EMAIL}",
    ),
    (
        "eps-1",
        "FORMULARIO DE AFILIACIÓN\nAfiliado: {PERSON}\n{ID_LABEL}: {ID}\nFecha de nacimiento: {DOB}\nMunicipio de residencia: {CITY}\nDirección: {ADDRESS}\nCelular: {PHONE}\nBeneficiario: {PERSON2}, {ID_LABEL} {ID2}",
    ),
    (
        "cfdi-1",
        "Comprobante fiscal\nEmisor: {ORG}\n{TAX_LABEL} emisor: {TAX}\nReceptor: {PERSON}\nLugar de expedición: {CITY}\nFecha: {DATE}\nImporte: {AMOUNT}",
    ),
    (
        "credito-1",
        "Solicitud de crédito de consumo. Solicitante: {PERSON}, {ID_LABEL} {ID}, {AGE} años, con domicilio en {ADDRESS} de la ciudad de {CITY}. Ingresos mensuales: {AMOUNT}. Referencia personal: {PERSON2}, teléfono {PHONE2}.",
    ),
    (
        "beca-1",
        "Comité de becas:\nLa estudiante {PERSON}, matrícula {STUDENT}, originaria de {CITY}, solicita la renovación de su beca. Su madre, {PERSON2}, es la responsable económica.",
    ),
    (
        "certificado-1",
        "CERTIFICADO MÉDICO\nCertifico que {PERSON}, de {AGE} años, con {ID_LABEL} {ID}, fue atendido en {ORG} de {CITY} el {DATE} y requiere reposo por tres días.\n{PERSON2}\nMédico cirujano, registro {PROF}",
    ),
    (
        "historia-1",
        "Paciente femenina de {AGE} años, natural y procedente de {CITY}, acude con su esposo {PERSON2}. Antecedente de cirugía en {ORG} en {MONTH_YEAR}. Historia clínica {PATIENT}.",
    ),
    (
        "historia-2",
        "Varón de {AGE} años remitido desde {CITY} por cefalea. Vive con su madre, {PERSON2}, en {ADDRESS}. Teléfono de la familia: {PHONE}.",
    ),
    (
        "expediente-1",
        "Juzgado Civil de {CITY}. Expediente {CASE}. Demandante: {PERSON}. Demandado: {PERSON2}, con domicilio procesal en {ADDRESS}. Se cita a las partes para el {DATE}.",
    ),
    (
        "policia-1",
        "Parte informativo: siendo las {TIME} del {DATE}, en la intersección cercana a {ADDRESS} de {CITY}, se detuvo al ciudadano {PERSON}, quien dijo llamarse así y portar {ID_LABEL} {ID}.",
    ),
    (
        "residencia-1",
        "CONSTANCIA DE RESIDENCIA\nSe hace constar que {PERSON}, {ID_LABEL} {ID}, reside en {ADDRESS}, municipio de {CITY}, desde hace {AGE} años.\nExpedida el {DATE}.",
    ),
    (
        "recomendacion-1",
        "A quien corresponda:\nConozco a {PERSON} desde hace varios años, cuando trabajábamos juntos en {ORG} en {CITY}. Puede contactarme al {PHONE} o a {EMAIL}.\n{PERSON2}",
    ),
    (
        "reclamo-1",
        "Buenas tardes, soy {PERSON} y vivo en {ADDRESS}, {CITY}. El pedido {TRACKING} nunca llegó. Mi tarjeta terminación {CARD_LAST} fue cargada dos veces. Mi correo es {EMAIL}.",
    ),
    (
        "reserva-1",
        "Reserva confirmada a nombre de {PERSON} para el {DATE} en {CITY}. Huéspedes: {FIRST2} y {PERSON3}. Pasaporte del titular: {PASSPORT}.",
    ),
    (
        "escuela-2",
        "Estimada {PERSON2}: le informamos que su hijo {PERSON}, alumno con matrícula {STUDENT}, no asistió a clases el {DATE}. Escuela {ORG}, {CITY}.",
    ),
    (
        "vecinos-1",
        "Acta de la junta de vecinos de {CITY}. Asistieron {PERSON}, {PERSON2} y {PERSON3}. La señora {LAST} denunció ruidos en el departamento de {ADDRESS}.",
    ),
    (
        "migracion-1",
        "Declaración de ingreso. Viajero: {PERSON_UPPER}. Pasaporte: {PASSPORT}. Procedencia: {CITY}. Destino final: {CITY2}. Dirección durante la estancia: {ADDRESS}.",
    ),
    (
        "pension-1",
        "Resolución de pensión. Se concede pensión de viudez a {PERSON}, {ID_LABEL} {ID}, cónyuge del fallecido {PERSON2}, con domicilio en {CITY}. Pago en {ACCOUNT_LABEL} {ACCOUNT}.",
    ),
    (
        "nota-1",
        "Nota de voz transcrita: hola, habla {FIRST} de {CITY}, le marco por lo del crédito; mi número es {PHONE} y mi cédula termina en {CARD_LAST}.",
    ),
    (
        "encuesta-1",
        "Encuestado: {PERSON}. Edad: {AGE}. Ciudad: {CITY}. Ocupación: {JOB}. Correo para resultados: {EMAIL}.",
    ),
    (
        "seguro-2",
        "Siniestro reportado por {PERSON}, póliza {POLICY}, ocurrido el {DATE} en la carretera de {CITY} a {CITY2}. Conductor del otro vehículo: {PERSON2}, teléfono {PHONE2}.",
    ),
    (
        "laboral-1",
        "Constancia laboral: se hace constar que {PERSON}, con número de empleado {EMPLOYEE}, labora en {ORG} desde el {DATE} como {JOB}, en la sucursal de {CITY}.",
    ),
    (
        "redes-2",
        "Felicidades a {PERSON} por su graduación en {CITY}!! te queremos mucho, att. {FIRST2} y {PERSON3} #orgullo",
    ),
)
# Name formats seen in real documents: surname-first lists, initials, all caps,
# lowercase chats and courtesy titles. Training only, like EXTRA_TEMPLATES.
NAME_TEMPLATES: tuple[tuple[str, str], ...] = (
    (
        "lista-1",
        "LISTA DE ASISTENCIA\n1. {NAME_REVERSED}\n2. {NAME_REVERSED}\n3. {NAME_REVERSED}\nCoordinador: {NAME_INITIAL}",
    ),
    (
        "lista-2",
        "Alumnos inscritos en el grupo B:\n- {NAME_UPPER} ({STUDENT})\n- {NAME_UPPER}\n- {NAME_REVERSED}",
    ),
    (
        "firma-1",
        "Sin otro particular, quedo a sus órdenes.\n\nAtentamente,\n{NAME_INITIAL}\nGerente de Operaciones\n{ORG}",
    ),
    ("firma-2", "Saludos cordiales,\n\n{NAME_UPPER}\n{JOB} | {ORG}\nTel. {PHONE}"),
    (
        "correo-3",
        "De: {NAME_REVERSED} <{EMAIL}>\nPara: {NAME_REVERSED}\nAsunto: Seguimiento del caso {CASE}\n\nBuen día, adjunto lo solicitado.",
    ),
    (
        "chat-3",
        "{NAME_LOWER}: hola!! ya hablaste con {NAME_LOWER}?\nyo: todavía no, me pasas su cel?\n{NAME_LOWER}: {PHONE}",
    ),
    ("chat-4", "jajaja si, {NAME_LOWER} vive por {CITY}, dile a {FIRST} que me escriba al {PHONE}"),
    (
        "titulo-1",
        "Se turna el asunto al {TITLE} {NAME_TITLED}, quien deberá responder antes del {DATE}. Copia al {TITLE} {NAME_TITLED}.",
    ),
    (
        "titulo-2",
        "Reunión con la {TITLE} {NAME_TITLED} y el {TITLE} {NAME_TITLED} en las oficinas de {ORG}, {CITY}.",
    ),
    (
        "apellidos-1",
        "La familia {NAME_SURNAMES} solicitó el cambio de domicilio a {ADDRESS}. Contacto: {NAME_INITIAL}, {PHONE}.",
    ),
    (
        "apellidos-2",
        "Según el informe, los hermanos {NAME_SURNAMES} declararon ante el juez en {CITY} el {DATE}.",
    ),
    (
        "cv-2",
        "{NAME_UPPER}\n{JOB}\n{EMAIL} | {PHONE} | {CITY}\n\nFORMACIÓN\nLicenciatura, {ORG} ({MONTH_YEAR})",
    ),
    (
        "acta-2",
        "ACTA DE ENTREGA. Entrega: {NAME_UPPER}, {ID_LABEL} {ID}. Recibe: {NAME_UPPER}, {ID_LABEL} {ID2}. Testigo: {NAME_INITIAL}.",
    ),
    (
        "planilla-1",
        "APELLIDOS Y NOMBRES: {NAME_REVERSED}\nDOCUMENTO: {ID}\nCARGO: {JOB}\nSUELDO: {AMOUNT}",
    ),
    (
        "planilla-2",
        "Nombre | Documento | Teléfono\n{NAME_REVERSED} | {ID} | {PHONE}\n{NAME_REVERSED} | {ID2} | {PHONE2}",
    ),
    (
        "mencion-1",
        "Gracias a {NAME_INITIAL} y a {NAME_INITIAL} por su apoyo en el proyecto de {ORG}.",
    ),
    ("mencion-2", "en la foto salen {NAME_LOWER} y {NAME_LOWER} en la playa de {CITY} 😍"),
    (
        "judicial-2",
        "Comparece el C. {NAME_UPPER}, quien manifiesta llamarse como ha quedado escrito, ser originario de {CITY} y tener {AGE} años de edad.",
    ),
    (
        "medico-3",
        "Paciente {NAME_REVERSED}, {AGE} años, referido por el {TITLE} {NAME_TITLED} del servicio de urgencias.",
    ),
    (
        "banco-3",
        "Titular de la cuenta: {NAME_UPPER}\n{ACCOUNT_LABEL}: {ACCOUNT}\nCotitular: {NAME_REVERSED}",
    ),
)
TEMPLATES = TEMPLATES + EXTRA_TEMPLATES + NAME_TEMPLATES

HELD_OUT = {
    "validation": {"correo-2", "factura-2", "clinica-3", "chat-2", "cv-1", "notaria-1", "redes-1"},
    "test": {
        "contrato-2",
        "rrhh-1",
        "denuncia-1",
        "banco-2",
        "llamada-1",
        "acta-1",
        "legal-2",
        "gobierno-1",
    },
}

_SLOT = re.compile(r"\{([A-Z0-9_]+)\}")
_ENTITY_OF_SLOT = {
    "PERSON": "PERSON", "PERSON2": "PERSON", "PERSON3": "PERSON", "PERSON_UPPER": "PERSON",
    "NAME_REVERSED": "PERSON", "NAME_INITIAL": "PERSON", "NAME_UPPER": "PERSON",
    "NAME_LOWER": "PERSON", "NAME_TITLED": "PERSON", "NAME_SURNAMES": "PERSON",
    "FIRST": "PERSON", "FIRST2": "PERSON", "FIRST2B": "PERSON", "LAST": "PERSON",
    "ADDRESS": "ADDRESS", "ADDRESS2": "ADDRESS", "CITY": "LOCATION", "CITY2": "LOCATION",
    "DATE": "DATE", "DATE2": "DATE", "MONTH_YEAR": "DATE", "DOB": "DATE_OF_BIRTH", "DOB_TEXT": "DATE_OF_BIRTH",
    "EMAIL": "EMAIL", "PHONE": "PHONE", "PHONE2": "PHONE", "ID": "NATIONAL_ID", "ID2": "NATIONAL_ID",
    "TAX": "TAX_ID", "ACCOUNT": "BANK_ACCOUNT", "CARD": "PAYMENT_CARD", "ORG": "ORGANIZATION",
    "ORG2": "ORGANIZATION", "AGE": "AGE", "IP": "IP_ADDRESS", "USER": "CREDENTIAL",
    "EMPLOYEE": "EMPLOYEE_ID", "PATIENT": "PATIENT_ID", "PASSPORT": "PASSPORT",
    "STUDENT": "CUSTOMER_ID", "POLICY": "INSURANCE_ID", "PROF": "REGIONAL_ID",
    "CASE": "DOCUMENT_ID",
}  # fmt: skip
_NAME_VARIANTS = {
    "NAME_REVERSED", "NAME_INITIAL", "NAME_UPPER", "NAME_LOWER", "NAME_TITLED", "NAME_SURNAMES",
}  # fmt: skip
_NOT_ENTITY = {
    "ID_LABEL", "TAX_LABEL", "ACCOUNT_LABEL", "AMOUNT", "INVOICE", "JOB", "TIME", "TIME2", "TIME3",
    "TIME4", "CARD_LAST", "TICKET", "NUMBER", "TRACKING", "TITLE",
}  # fmt: skip


def _text_date(rng: random.Random, start: int = 2015, years: int = 10) -> str:
    day = date(start, 1, 1) + timedelta(days=rng.randrange(365 * years))
    style = rng.random()
    if style < 0.4:
        return f"{day.day} de {MONTHS[day.month - 1]} de {day.year}"
    if style < 0.7:
        return day.strftime("%d/%m/%Y")
    if style < 0.85:
        return day.isoformat()
    return f"{day.day:02d}-{day.month:02d}-{day.year}"


def _luhn_card(rng: random.Random) -> str:
    digits = [int(c) for c in rng.choice(["4", "5"]) + _digits(rng, 14)]
    total = 0
    for index, digit in enumerate(reversed(digits)):
        value = digit * 2 if index % 2 == 0 else digit
        total += value - 9 if value > 9 else value
    number = "".join(map(str, digits)) + str(-total % 10)
    return _group(number, (4, 4, 4, 4), rng.choice([" ", "-", ""]))


class _Values:
    """Per-document value factory; one Faker instance per locale."""

    def __init__(self, rng: random.Random, profile: CountryProfile, fakers: dict[str, Any]) -> None:
        self.rng, self.profile = rng, profile
        self.faker = fakers[profile.locale]
        self.cache: dict[str, str] = {}

    def person(self) -> tuple[str, str]:
        first = self.faker.first_name()
        last = self.faker.last_name() + (
            " " + self.faker.last_name() if self.rng.random() < 0.7 else ""
        )
        return first, last

    def slot(self, name: str) -> str:
        if name in self.cache:
            return self.cache[name]
        rng, profile, faker = self.rng, self.profile, self.faker
        if name in _NAME_VARIANTS:
            first, last = self.person()
            if name == "NAME_REVERSED":
                value = f"{last}, {first}"
            elif name == "NAME_INITIAL":
                value = f"{first[0]}. {last}"
            elif name == "NAME_UPPER":
                value = f"{first} {last}".upper()
            elif name == "NAME_LOWER":
                value = f"{first} {last}".lower()
            elif name == "NAME_TITLED":
                value = f"{first} {last}"
            else:  # NAME_SURNAMES
                value = last
            return value  # not cached: every occurrence in a list is another person
        if name == "TITLE":
            return rng.choice(["Lic.", "Ing.", "Dr.", "Dra.", "Mtro.", "Mtra.", "Sr.", "Sra."])
        if name in {"PERSON", "PERSON2", "PERSON3"}:
            first, last = self.person()
            value = f"{first} {last}"
            if name == "PERSON":
                self.cache["FIRST"], self.cache["LAST"] = first, last
                self.cache["PERSON_UPPER"] = value.upper()
        elif name in {"FIRST", "LAST", "PERSON_UPPER"}:
            self.slot("PERSON")
            return self.cache[name]
        elif name in {"FIRST2", "FIRST2B"}:
            value = self.cache.get("FIRST2") or faker.first_name()
            self.cache["FIRST2"] = self.cache["FIRST2B"] = value
        elif name in {"ADDRESS", "ADDRESS2"}:
            value = faker.street_address().strip()
        elif name in {"CITY", "CITY2"}:
            value = rng.choice(profile.cities)
        elif name in {"DATE", "DATE2"}:
            value = _text_date(rng)
        elif name == "MONTH_YEAR":
            value = f"{rng.choice(MONTHS)} de {rng.randint(2018, 2025)}"
        elif name == "DOB":
            value = _text_date(rng, 1950, 50)
        elif name == "DOB_TEXT":
            birth = date(1960, 1, 1) + timedelta(days=rng.randrange(365 * 40))
            value = f"{birth.day} de {MONTHS[birth.month - 1]} de {birth.year}"
        elif name == "EMAIL":
            first = self.slot("PERSON").split()[0]
            base = re.sub(r"[^a-z]", "", first.lower().encode("ascii", "ignore").decode())
            value = f"{base or 'usuario'}{rng.randint(1, 99)}@{rng.choice(['correo.example', 'mail.example', 'empresa.example'])}"
        elif name in {"PHONE", "PHONE2"}:
            value = profile.phone(rng)
        elif name == "ID":
            value = profile.national_id(rng)
        elif name == "ID2":
            value = profile.national_id(rng)
        elif name == "TAX":
            value = profile.tax_id(rng)
        elif name == "ACCOUNT":
            value = (profile.account or (lambda r: _group(_digits(r, 16), (4, 4, 4, 4), " ")))(rng)
        elif name == "CARD":
            value = _luhn_card(rng)
        elif name in {"ORG", "ORG2"}:
            value = faker.company()
        elif name == "AGE":
            value = str(rng.randint(18, 90))
        elif name == "IP":
            value = ".".join(str(rng.randint(1, 254)) for _ in range(4))
        elif name == "USER":
            value = self.slot("PERSON").split()[0].lower()[:6] + "_" + _digits(rng, 3)
        elif name == "EMPLOYEE":
            value = "EMP-" + _digits(rng, 5)
        elif name == "PATIENT":
            value = _digits(rng, 7)
        elif name == "PASSPORT":
            value = rng.choice(["G", "P", "X"]) + _digits(rng, 8)
        elif name == "STUDENT":
            value = _digits(rng, 9)
        elif name == "POLICY":
            value = "POL-" + _digits(rng, 8)
        elif name == "PROF":
            value = _digits(rng, 8)
        elif name == "CASE":
            value = f"{rng.randint(100, 9999)}/{rng.randint(2015, 2025)}"
        elif name == "ID_LABEL":
            value = rng.choice(profile.id_labels)
        elif name == "TAX_LABEL":
            value = rng.choice(profile.tax_labels)
        elif name == "ACCOUNT_LABEL":
            value = rng.choice(profile.account_labels)
        elif name == "AMOUNT":
            value = f"{profile.currency}{rng.randint(100, 99999):,}.{rng.randint(0, 99):02d}"
        elif name == "INVOICE":
            value = f"A-{rng.randint(1000, 99999)}"
        elif name == "JOB":
            value = faker.job()
        elif name.startswith("TIME"):
            value = f"{rng.randint(8, 22):02d}:{rng.randint(0, 59):02d}"
        elif name == "CARD_LAST":
            value = _digits(rng, 4)
        elif name in {"TICKET", "TRACKING", "NUMBER"}:
            value = _digits(rng, rng.choice([3, 6, 10]))
        else:
            raise KeyError(name)
        self.cache[name] = value
        return value


def render(template: str, values: _Values) -> tuple[str, tuple[GoldSpan, ...]]:
    parts: list[str] = []
    spans: list[GoldSpan] = []
    cursor = 0
    length = 0
    for match in _SLOT.finditer(template):
        literal = template[cursor : match.start()]
        parts.append(literal)
        length += len(literal)
        name = match.group(1)
        value = values.slot(name)
        kind = _ENTITY_OF_SLOT.get(name)
        if kind is None and name not in _NOT_ENTITY:
            raise KeyError(name)
        if kind is not None:
            spans.append(GoldSpan(kind, length, length + len(value)))
        parts.append(value)
        length += len(value)
        cursor = match.end()
    parts.append(template[cursor:])
    return "".join(parts), tuple(spans)


def generate(
    count: int, *, split: str, seed: int = 1729, countries: tuple[str, ...] | None = None
) -> Iterator[Example]:
    """Yield ``count`` documents of the requested split (train, validation, test)."""
    try:
        from faker import Faker
    except ImportError:
        raise RuntimeError("Synthetic generation requires Faker (deidflow[training])") from None
    if split not in {"train", "validation", "test"}:
        raise ValueError("Unknown split")
    held = set().union(*HELD_OUT.values())
    families = [
        (family, text)
        for family, text in TEMPLATES
        if (family in HELD_OUT.get(split, set()) if split != "train" else family not in held)
    ]
    codes = countries or tuple(PROFILES)
    rng = random.Random(f"{seed}:{split}")
    fakers: dict[str, Any] = {}
    for code in codes:
        locale = PROFILES[code].locale
        if locale not in fakers:
            fakers[locale] = Faker(locale)
            fakers[locale].seed_instance(rng.randrange(2**31))
    for index in range(count):
        family, template = families[index % len(families)]
        profile = PROFILES[rng.choice(codes)]
        text, spans = render(template, _Values(rng, profile, fakers))
        yield Example(
            f"synthetic-{split}-{index}",
            text,
            spans,
            split,
            f"{family}:{profile.code}",
            challenge="synthetic_multicountry",
        )


__all__ = ["HELD_OUT", "PROFILES", "TEMPLATES", "generate", "render"]
