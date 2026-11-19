"""
Logger estructurado.

Configura logging con formato consistente para trazabilidad.
Cada OC procesada queda registrada con: códigos encontrados,
faltantes en Odoo, tiempos y errores.
"""
import logging
import sys

# Librerías de terceros muy verbosas en DEBUG (pdfminer loguea cada objeto del PDF)
_LIBRERIAS_RUIDOSAS = ("pdfminer", "pdfplumber", "PIL")


def setup_logger(name: str) -> logging.Logger:
    """
    Configura el logger raíz (stdout + archivo) para que TODOS los módulos
    (pdf_extractor, order_parser, odoo_service, csv_builder...) hereden los
    handlers, y retorna el logger con el nombre pedido.
    """
    root = logging.getLogger()

    if not getattr(root, "_oc_configurado", False):
        root.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Handler stdout
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.INFO)
        stdout_handler.setFormatter(formatter)
        root.addHandler(stdout_handler)

        # Handler archivo
        try:
            file_handler = logging.FileHandler("oc_processor.log", encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except Exception:
            pass  # En entornos sin permisos de escritura, solo stdout

        for nombre in _LIBRERIAS_RUIDOSAS:
            logging.getLogger(nombre).setLevel(logging.WARNING)

        root._oc_configurado = True

    return logging.getLogger(name)


def log_processing_summary(
    logger: logging.Logger,
    orden: str,
    parsed_lines: list[dict],
    mapeo_odoo: dict[str, str],
) -> None:
    """
    Registra un resumen completo del procesamiento de una OC.
    Útil para auditoría y diagnóstico rápido.
    """
    total = len(parsed_lines)
    encontrados = [l for l in parsed_lines if mapeo_odoo.get(l["cod_fabrica"])]
    faltantes   = [l for l in parsed_lines if not mapeo_odoo.get(l["cod_fabrica"])]

    logger.info("=" * 60)
    logger.info(f"RESUMEN OC {orden}")
    logger.info(f"  Total líneas procesadas : {total}")
    logger.info(f"  Encontrados en Odoo     : {len(encontrados)}")
    logger.info(f"  No encontrados en Odoo  : {len(faltantes)}")

    if faltantes:
        logger.warning(f"  Códigos FALTANTES:")
        for line in faltantes:
            logger.warning(
                f"    → {line['cod_fabrica']} "
                f"(qty={line['cantidad']}, precio={line['precio_float']})"
            )

    logger.info("=" * 60)
