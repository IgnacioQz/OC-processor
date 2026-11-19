"""
Capa 3 — Servicio Odoo (API JSON-2, Odoo 19+).

  - POST /json/2/<modelo>/<metodo> autenticado con API key (Bearer).
  - UNA sola llamada search_read para TODOS los códigos del pedido.
  - Mismo cliente que usa la app "producto". El servidor ya no acepta
    XML-RPC (responde 405 en /xmlrpc/2/*).

Todos los errores se lanzan como ErrorOdoo (subclase de ConnectionError)
con un mensaje apto para mostrar al usuario.
"""
import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

NOT_FOUND_CODE = "No_Existe_en_ODOO"

# Sin timeout, una caída de Odoo deja el worker de gunicorn colgado
# hasta que gunicorn lo mata (30 s por defecto).
TIMEOUT_DEFAULT = 20

_USER_AGENT = "softland-bridge"


class ErrorOdoo(ConnectionError):
    """Falla al consultar Odoo: el mensaje se muestra al usuario."""


def _detalle_http(e: urllib.error.HTTPError) -> str:
    """Mensaje de error que Odoo incluye en el JSON de la respuesta, si lo hay."""
    try:
        return json.loads(e.read().decode("utf-8", "replace")).get("message") or ""
    except Exception:
        return ""


def _abrir(req: urllib.request.Request, timeout: float):
    """urlopen + JSON, traduciendo fallas de red a ErrorOdoo."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError:
        raise
    except TimeoutError:
        logger.warning(f"Timeout consultando Odoo ({timeout}s): {req.full_url}")
        raise ErrorOdoo("Odoo no respondió a tiempo, intenta nuevamente")
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            logger.warning(f"Timeout conectando a Odoo ({timeout}s): {req.full_url}")
            raise ErrorOdoo("Odoo no respondió a tiempo, intenta nuevamente")
        logger.error(f"No se pudo conectar con Odoo: {e.reason}")
        raise ErrorOdoo("No se pudo conectar con Odoo")
    except ValueError:  # respuesta que no es JSON
        logger.error(f"Odoo devolvió una respuesta que no es JSON: {req.full_url}")
        raise ErrorOdoo("Odoo respondió algo inesperado, revisa ODOO_URL")
    except OSError as e:
        logger.error(f"No se pudo conectar con Odoo: {e}")
        raise ErrorOdoo("No se pudo conectar con Odoo")


class OdooService:
    def __init__(self, url: str, db: str, api_key: str, timeout: float = TIMEOUT_DEFAULT):
        self.url     = url.rstrip("/")
        self.db      = db
        self.api_key = api_key
        self.timeout = timeout

    def _json2(self, modelo: str, metodo: str, parametros: dict | None = None):
        if not self.api_key:
            raise ErrorOdoo("Falta configurar ODOO_API_KEY")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "bearer " + self.api_key,
            "User-Agent": _USER_AGENT,
        }
        if self.db:
            headers["X-Odoo-Database"] = self.db
        req = urllib.request.Request(
            f"{self.url}/json/2/{modelo}/{metodo}",
            data=json.dumps(parametros or {}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            return _abrir(req, self.timeout)
        except urllib.error.HTTPError as e:
            detalle = _detalle_http(e)
            logger.error(f"Odoo {modelo}/{metodo} -> HTTP {e.code} {detalle}")
            if e.code == 401:
                raise ErrorOdoo("Odoo rechazó la API key configurada")
            if e.code == 403:
                raise ErrorOdoo("El usuario de la API key no tiene permiso para esta consulta")
            if not detalle:  # error sin JSON de Odoo: proxy, ruta equivocada, etc.
                raise ErrorOdoo(f"Odoo respondió HTTP {e.code}, revisa ODOO_URL")
            raise ErrorOdoo(f"Odoo devolvió un error: {detalle}")

    def _version(self) -> str:
        """Versión del servidor (GET /web/version, no requiere autenticación)."""
        req = urllib.request.Request(f"{self.url}/web/version", headers={"User-Agent": _USER_AGENT})
        try:
            return _abrir(req, self.timeout).get("version", "?")
        except urllib.error.HTTPError as e:
            raise ErrorOdoo(f"Odoo respondió HTTP {e.code}, revisa ODOO_URL")

    def verificar(self) -> str:
        """
        Comprueba que Odoo responde y que la API key es válida.
        Retorna la versión del servidor; lanza ErrorOdoo si falla.
        """
        version = self._version()
        self._json2("res.users", "context_get")  # valida la API key
        return "Odoo " + version.split("+")[0]

    def buscar_codigos_batch(self, codigos_fabrica: list[str]) -> dict[str, str]:
        """
        Busca TODOS los códigos de fabricante en una sola llamada a Odoo.

        Retorna dict:
            { manufacturer_code: default_code, ... }

        Los códigos no encontrados NO aparecen en el dict
        (el csv_builder usará NOT_FOUND_CODE como fallback).
        """
        # Deduplicar para no enviar duplicados a Odoo
        codigos_unicos = sorted(set(codigos_fabrica))
        logger.info(f"Consultando Odoo por {len(codigos_unicos)} códigos únicos (batch)")

        resultados = self._json2("product.template", "search_read", {
            "domain": [["manufacturer_code", "in", codigos_unicos]],
            "fields": ["default_code", "manufacturer_code", "name"],
            "context": {"lang": "es_CL"},
        })

        # Construir mapeo manufacturer_code → default_code
        mapeo = {}
        for producto in resultados:
            mfr_code = producto.get("manufacturer_code") or ""
            def_code = producto.get("default_code") or ""
            if not (mfr_code and def_code):
                continue
            if mfr_code in mapeo and mapeo[mfr_code] != def_code:
                logger.warning(
                    f"Código de fabricante {mfr_code} repetido en Odoo: "
                    f"{mapeo[mfr_code]} y {def_code}; se usa {def_code}"
                )
            mapeo[mfr_code] = def_code

        # Log de los que no se encontraron
        no_encontrados = [c for c in codigos_unicos if c not in mapeo]
        if no_encontrados:
            logger.warning(f"Códigos NO encontrados en Odoo ({len(no_encontrados)}): {no_encontrados}")

        logger.info(f"Odoo respondió: {len(mapeo)} encontrados, {len(no_encontrados)} faltantes")
        return mapeo
