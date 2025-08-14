from __future__ import annotations
from typing import Dict, Tuple
import unicodedata
import pandas as pd

# ==== Parsing & Normalização ====

def parse_brl(value: str | float | int | None) -> float:
    """Converte texto no formato brasileiro para float."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0

def normalize_tipo_nota(texto: str) -> str:
    """Remove acentos e retorna texto em maiúsculas."""
    if texto is None:
        return ""
    text = unicodedata.normalize("NFKD", str(texto))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.strip().upper()

def yyyy_mm(df: pd.DataFrame, col: str = "data_emissao") -> pd.Series:
    """Retorna série yyyymm a partir de uma coluna de datas."""
    return df[col].dt.year * 100 + df[col].dt.month

# ==== Apuração do realizado ====

def realizado_por_mes(df: pd.DataFrame) -> pd.DataFrame:
    """Apura FAT, COMPRAS e LAT por mês de 2025."""
    cols = {c.lower(): c for c in df.columns}
    rename = {}
    for raw, norm in {
        "valor total": "valor_total",
        "tipo nota": "tipo_nota",
        "classificacao": "classificacao",
        "natureza operacao": "natureza_operacao",
        "data emissao": "data_emissao",
    }.items():
        if raw in cols:
            rename[cols[raw]] = norm
    df = df.rename(columns=rename)
    for col in ["valor_total", "tipo_nota", "classificacao", "natureza_operacao", "data_emissao"]:
        if col not in df.columns:
            df[col] = ""
    df["valor_total"] = df["valor_total"].map(parse_brl)
    df["tipo_nota"] = df["tipo_nota"].map(normalize_tipo_nota)
    df["classificacao"] = df["classificacao"].map(normalize_tipo_nota)
    df["natureza_operacao"] = df["natureza_operacao"].map(normalize_tipo_nota)
    df["data_emissao"] = pd.to_datetime(df["data_emissao"], errors="coerce", dayfirst=True)
    df["yyyymm"] = yyyy_mm(df)
    df = df[df["data_emissao"].dt.year == 2025]

    idx = [202500 + m for m in range(1, 13)]
    mensal = pd.DataFrame(index=idx, columns=["FAT", "COMPRAS"], data=0.0)

    mask_devol = df["natureza_operacao"].str.contains("DEVOLUCAO DE COMPRA", na=False)
    mask_saida = df["tipo_nota"] == "SAIDA"
    mask_entrada = df["tipo_nota"] == "ENTRADA"
    mask_cmv = mask_entrada & (df["classificacao"] == "MERCADORIA PARA REVENDA")

    mensal.loc[:, "FAT"] = (
        df[mask_saida & ~mask_devol].groupby("yyyymm")["valor_total"].sum().reindex(idx, fill_value=0.0)
    )
    compras = df[mask_cmv].groupby("yyyymm")["valor_total"].sum()
    devol = df[mask_devol].groupby("yyyymm")["valor_total"].sum()
    mensal.loc[:, "COMPRAS"] = compras.reindex(idx, fill_value=0.0) - devol.reindex(idx, fill_value=0.0)
    mensal["LAT"] = mensal["FAT"] - mensal["COMPRAS"]
    return mensal

# ==== Cenários por margem ====

def cenarios_por_margem(lat: float) -> Dict[int, Dict[str, float]]:
    """Retorna cenário de FAT/COMPRAS/ICMS para margens 5-30%."""
    from ui_helpers import MARGENS  # evitar dependência circular pesada

    out: Dict[int, Dict[str, float]] = {}
    base = max(0.0, float(lat))
    for m in MARGENS:
        if m <= 0:
            continue
        fat = base / m
        comp = fat - base
        icms = 0.05 * fat
        out[int(m * 100)] = {"FAT": fat, "COMPRAS": comp, "ICMS": icms}
    return out

# ==== IRPJ/CSLL ====

def irpj_csll_trimestre(lat_por_mes: Dict[int, float]) -> Dict[int, Tuple[float, float]]:
    """Calcula IRPJ/CSLL trimestrais, lançando apenas no mês de fechamento."""
    resultado: Dict[int, Tuple[float, float]] = {}
    trimestres = [([1, 2, 3], 3), ([4, 5, 6], 6), ([7, 8, 9], 9), ([10, 11, 12], 12)]
    anos = {m // 100 for m in lat_por_mes.keys()}
    for ano in anos:
        for meses, ultimo in trimestres:
            meses_yyyymm = [ano * 100 + m for m in meses]
            base_total = sum(0.32 * lat_por_mes.get(m, 0.0) for m in meses_yyyymm)
            if base_total <= 0:
                continue
            irpj = 0.15 * base_total
            if base_total > 60000:
                irpj += 0.10 * (base_total - 60000)
            csll = 0.09 * base_total
            resultado[ano * 100 + ultimo] = (irpj, csll)
    return resultado