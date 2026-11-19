"""
Configuración centralizada — todos los valores se leen de variables de entorno
(o del archivo .env en app/).

Si falta alguna variable obligatoria o tiene un valor inválido, la app falla
al arrancar con un mensaje claro, en vez de fallar al procesar la primera OC.
"""
import os
from dotenv import load_dotenv

# Carga .env desde el directorio de trabajo (app/)
load_dotenv()

_REQUERIDAS = (
    "ODOO_URL",
    "ODOO_DB",
    "ODOO_USER",
    "ODOO_PASSWORD",
    "SOFTLAND_RUT_PROVEEDOR",
    "SOFTLAND_TIPO_DOC",
    "SOFTLAND_COD_BODEGA",
    "SOFTLAND_DESCUENTO_PCT",
)


def _env(nombre: str, default: str = "") -> str:
    valor = (os.getenv(nombre) or default).strip()
    # `docker run --env-file` no quita comillas (docker compose y dotenv sí)
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        valor = valor[1:-1].strip()
    return valor


def _validar_entorno() -> None:
    errores = [f"falta la variable {n}" for n in _REQUERIDAS if not _env(n)]

    descuento = _env("SOFTLAND_DESCUENTO_PCT")
    if descuento:
        try:
            valor = float(descuento)
            if not 0 <= valor <= 100:
                errores.append(f"SOFTLAND_DESCUENTO_PCT fuera de rango 0-100: {descuento!r}")
        except ValueError:
            errores.append(f"SOFTLAND_DESCUENTO_PCT no es un número: {descuento!r}")

    puerto = _env("PORT", "5000")
    if not puerto.isdigit():
        errores.append(f"PORT no es un número: {puerto!r}")

    if errores:
        raise RuntimeError(
            "Configuración inválida (revisa app/.env o las variables de entorno):\n  - "
            + "\n  - ".join(errores)
        )


_validar_entorno()


class Config:
    # ── Odoo ──────────────────────────────────────────────────────────────────
    ODOO_URL      = _env("ODOO_URL").rstrip("/")
    ODOO_DB       = _env("ODOO_DB")
    ODOO_USER     = _env("ODOO_USER")
    ODOO_PASSWORD = _env("ODOO_PASSWORD")

    # ── Softland — campos fijos del CSV ───────────────────────────────────────
    SOFTLAND_RUT_PROVEEDOR = _env("SOFTLAND_RUT_PROVEEDOR")
    SOFTLAND_TIPO_DOC      = _env("SOFTLAND_TIPO_DOC")
    SOFTLAND_COD_BODEGA    = _env("SOFTLAND_COD_BODEGA")
    SOFTLAND_DESCUENTO_PCT = float(_env("SOFTLAND_DESCUENTO_PCT"))

    # ── Flask ─────────────────────────────────────────────────────────────────
    DEBUG = _env("FLASK_DEBUG", "false").lower() == "true"
    PORT  = int(_env("PORT", "5000"))
