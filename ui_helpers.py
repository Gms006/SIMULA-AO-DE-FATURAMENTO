from __future__ import annotations
import math
from typing import Dict

# =========================
# Formatação BRL (pura)
# =========================
def brl(value: float | int | None) -> str:
    """
    Formata número como BRL com vírgula decimal e separador de milhar.
    Retorna '—' para None/NaN.
    """
    if value is None:
        return "—"
    try:
        v = float(value)
        if math.isnan(v):
            return "—"
    except Exception:
        return "—"

    s = f"{v:,.2f}"  # 1,234,567.89
    return f"R$ {s}".replace(",", "X").replace(".", ",").replace("X", ".")


# =========================
# Rótulo AAAAMM -> 'Mmm/AAAA'
# =========================
def yyyymm_to_label(yyyymm: int | str) -> str:
    meses = {
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
    }
    try:
        i = int(yyyymm)
        ano, mes = divmod(i, 100)
        if mes < 1 or mes > 12:
            return "—"
        return f"{meses[mes]}/{ano}"
    except Exception:
        return "—"


# =========================
# Cenários por margem (puro)
# =========================
_DEFAULT_MARGENS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30)

def cenarios_fat_compra(LAT_mes: float, margens: tuple[float, ...] = _DEFAULT_MARGENS) -> Dict[int, Dict[str, float]]:
    """
    Para um LAT mensal, calcula cenários por margem r em {5%, 10%, ..., 30%}:

      FAT = LAT / r
      COMPRAS = FAT - LAT
      ICMS = 5% * FAT  (exibição)

    Retorna dict indexado pela margem em % (int):
        {
          5: {"FAT": ..., "COMPRAS": ..., "ICMS": ...},
          10: {...},
          ...
        }
    """
    LAT = max(0.0, float(LAT_mes))
    out: Dict[int, Dict[str, float]] = {}
    for r in margens:
        if r <= 0:
            continue
        fat = LAT / r
        compras = fat - LAT
        icms = 0.05 * fat
        out[int(r * 100)] = {"FAT": fat, "COMPRAS": compras, "ICMS": icms}
    return out


# =========================
# PIS / COFINS sobre LAT (puro)
# =========================
def pis_cofins(LAT_mes: float) -> tuple[float, float]:
    """
    PIS = 0,65% * LAT_mês
    COFINS = 3% * LAT_mês
    """
    lat = max(0.0, float(LAT_mes))
    return (0.0065 * lat, 0.03 * lat)
