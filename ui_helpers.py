from __future__ import annotations
import math

# ========= Formatação =========
def brl(value: float | int | None) -> str:
    """Formata número como BRL com vírgula decimal e milhar.
    Retorna '—' para None/NaN."""
    if value is None:
        return "—"
    try:
        if hasattr(value, "__float__"):
            v = float(value)
            if math.isnan(v):
                return "—"
        else:
            v = 0.0
    except Exception:
        return "—"
    s = f"{v:,.2f}"  # 1,234,567.89
    return f"R$ {s}".replace(",", "X").replace(".", ",").replace("X", ".")

def pct(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except Exception:
        return "—"
    return f"{v:.{digits}%}".replace(".", ",")

def yyyymm_to_label(yyyymm: int) -> str:
    meses = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
    try:
        m = int(yyyymm) % 100
        return f"{meses[int(m)]}/{int(yyyymm)//100}"
    except Exception:
        return "—"

# ========= Cálculos rápidos para os cards (só UI) =========
MARGENS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]

def cenarios_fat_compra(LAT_mes: float) -> dict[int, dict[str, float]]:
    """Retorna dict {5:{FAT, COMPRA, ICMS}, 10:{...}, ...} para um LAT fixo."""
    out: dict[int, dict[str, float]] = {}
    LAT = max(0.0, float(LAT_mes))
    for m in MARGENS:
        if m <= 0:
            continue
        fat = LAT / m
        comp = fat - LAT
        icms = 0.05 * fat
        out[int(m*100)] = {"FAT": fat, "COMPRA": comp, "ICMS": icms}
    return out

def pis_cofins(LAT_mes: float) -> tuple[float, float]:
    """PIS = 0,65% * LAT; COFINS = 3% * LAT."""
    lat = max(0.0, float(LAT_mes))
    return (0.0065 * lat, 0.03 * lat)
