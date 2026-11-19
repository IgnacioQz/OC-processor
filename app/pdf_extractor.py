"""
Capa 1 — Extracción de líneas crudas del PDF.

Estrategia:
- Se extrae el texto completo del PDF con pdfplumber y se detecta el formato:
    * "registro de pedido" (formato heredado): todo en una línea por producto.
    * "confirm. pedido" (confirmación Danfoss): línea de producto + bloque de
      detalle con la fecha de envío en las líneas siguientes.
- Una línea de producto empieza con el número de línea (10, 20, 30 ...).
- La descripción no se utiliza en el CSV de Softland, por lo que se ignora.
"""
import re
import pdfplumber
import io
import logging

logger = logging.getLogger(__name__)

# Formato nuevo (confirmación de pedido Danfoss): "10 1 pc 2512+059 1.098,26 1.098,26"
_RE_LINE_NEW = re.compile(
    r"^(\d{2,3})\s+(\d+)\s+pc\s+([A-Za-z0-9][A-Za-z0-9\-\+\.]{2,})\s+([\d.,]+)\s+([\d.,]+)$"
)

# Fecha de envío en el bloque de detalle de cada línea (formato nuevo): DD.MM.YYYY
_RE_FECHA_NUEVA = re.compile(
    r"(?:Fecha prevista de salida|Entregado):.*?(\d{2}\.\d{2}\.\d{4})"
)

# El PDF nuevo repite líneas de producto en un anexo de cambios al final —
# todo lo que esté a partir de este marcador se descarta para evitar duplicados.
_STOP_MARKER_NUEVO = "Resumen/Listado de Cambios"

# Fecha de pedido del encabezado (formato nuevo), usada como piso de fecha por línea
_RE_FECHA_PEDIDO = re.compile(r"Fecha de Pedido\s+(\d{2}\.\d{2}\.\d{4})")


def extract_order_lines(pdf_bytes: bytes) -> list[dict]:
    """Extrae líneas de producto del PDF de la OC, detectando el formato del proveedor."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    if "confirm. pedido" in full_text:
        logger.info("Formato de PDF detectado: confirmación de pedido")
        raw_rows = _extract_formato_nuevo(full_text)
    else:
        logger.info("Formato de PDF detectado: registro de pedido")
        raw_rows = _extract_formato_antiguo(full_text)

    logger.info(f"Total filas extraídas: {len(raw_rows)}")
    return raw_rows


def _extract_formato_antiguo(full_text: str) -> list[dict]:
    """Formato heredado: "10 148B6230 ... 1 PCE Fecha pendiente $ 1.098,26 ..."."""
    raw_rows = []

    for line in full_text.split('\n'):
        line = line.strip()
        if len(line) < 10:
            continue

        # Patrón: NÚMERO_LÍNEA (10,20,30...) + space + CÓDIGO
        match = re.match(r'^(\d{2,3})\s+([A-Z0-9][A-Z0-9\-+]{3,})', line)
        if not match:
            continue

        num_linea, codigo = match.groups()
        resto = line[match.end():].strip()

        # Cantidad: número ANTES de "PCE"
        cantidad_match = re.search(r'(\d+)\s+PCE', resto)

        # Fecha: DD/MM/YYYY
        fecha_match = re.search(r'(\d{2}/\d{2}/\d{4})', resto)

        # Precio unitario: primer $ del resto
        precio_match = re.search(r'\$\s*([\d.,]+)', resto)

        row = {
            "cod_fabrica": codigo,
            "cantidad": cantidad_match.group(1) if cantidad_match else "",
            "fecha": fecha_match.group(1) if fecha_match else "",
            "precio": precio_match.group(1).strip() if precio_match else "",
            "fecha_pedido": "",
        }
        raw_rows.append(row)
        logger.debug(
            f"LÍNEA {num_linea}: {codigo} "
            f"x{row['cantidad']} | {row['fecha']} | ${row['precio']}"
        )

    return raw_rows


def _extract_formato_nuevo(full_text: str) -> list[dict]:
    """
    Formato de confirmación de pedido Danfoss:
        "10 1 pc 2512+059 1.098,26 1.098,26"
        LLG 740S VISOR NIVEL / 1 pc
        País de origen Poland
        ...
        Fecha prevista de salida: 1 pc 05.10.2026
        Pendiente de entrega: 1 pc

    La fecha de envío está en el bloque de texto que sigue a cada línea de
    producto (no en la misma línea), así que se busca en el rango de texto
    entre una línea de producto y la siguiente.
    """
    fecha_pedido_match = _RE_FECHA_PEDIDO.search(full_text)
    fecha_pedido = fecha_pedido_match.group(1).replace(".", "/") if fecha_pedido_match else ""

    lines = full_text.split('\n')

    # Descartar el anexo "Resumen/Listado de Cambios": repite líneas ya
    # incluidas en el detalle principal y produciría duplicados.
    for i, line in enumerate(lines):
        if _STOP_MARKER_NUEVO in line:
            lines = lines[:i]
            break

    matches = [(i, m) for i, line in enumerate(lines)
               if (m := _RE_LINE_NEW.match(line.strip()))]

    raw_rows = []
    for idx, (line_i, m) in enumerate(matches):
        num_linea, cantidad, codigo, precio_unit, _precio_neto = m.groups()

        bloque_fin = matches[idx + 1][0] if idx + 1 < len(matches) else len(lines)
        bloque = "\n".join(lines[line_i + 1: bloque_fin])

        fecha_match = _RE_FECHA_NUEVA.search(bloque)
        fecha = fecha_match.group(1).replace(".", "/") if fecha_match else ""

        row = {
            "cod_fabrica": codigo,
            "cantidad": cantidad,
            "fecha": fecha,
            "precio": precio_unit,
            "fecha_pedido": fecha_pedido,
        }
        raw_rows.append(row)
        logger.debug(
            f"LÍNEA {num_linea}: {codigo} x{cantidad} | {fecha} | {precio_unit}"
        )

    return raw_rows
