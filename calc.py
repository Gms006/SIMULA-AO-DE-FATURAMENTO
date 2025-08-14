from __future__ import annotations
from typing import Dict, List, Tuple, Optional
from datetime import datetime

import pandas as pd
import numpy as np
import unicodedata
import math
import re

# ============================================================
# Constantes (puras)
# ============================================================
# Margens padrão utilizadas em cenários (5% a 30%)
MARGENS: List[float] = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]

# Mapeamento de nomes de colunas comuns -> nomes padronizados
COL_MAP: Dict[str, str] = {
    "cfop": "cfop",
    "data emissão": "data_emissao",
    "data emissao": "data_emissao",
    "data": "data_emissao",
    "emitente cnpj/cpf": "emitente",
    "destinatário cnpj/cpf": "destinatario",
    "destinatario cnpj/cpf": "destinatario",
    "chassi": "chassi",
    "placa": "placa",
    "produto": "produto",
    "valor total": "valor_total",
    "valor_total": "valor_total",
    "renavam": "renavam",
    "km": "km",
    "ano modelo": "ano_modelo",
    "ano fabricação": "ano_fabricacao",
    "cor": "cor",
    "icms alíquota": "icms_aliquota",
    "icms aliquota": "icms_aliquota",
    "icms valor": "icms_valor",
    "icms base": "icms_base",
    "cst icms": "cst_icms",
    "redução bc": "reducao_bc",
    "reducao bc": "reducao_bc",
    "modalidade bc": "modalidade_bc",
    "natureza operação": "natureza_operacao",
    "natureza operacao": "natureza_operacao",
    "chave xml": "chave_xml",
    "xml path": "xml_path",
    "item": "item",
    "número nf": "numero_nf",
    "numero nf": "numero_nf",
    "tipo nota": "tipo_nota",
    "classificação": "classificacao",
    "classificacao": "classificacao",
    "combustível": "combustivel",
    "combustivel": "combustivel",
    "motor": "motor",
    "modelo": "modelo",
    "potência": "potencia",
    "potencia": "potencia",
}

# ============================================================
# Utilidades de parsing/normalização (puras)
# ============================================================
def parse_brl(valor: object) -> float:
    """
    Parse seguro de BRL:
    - Aceita float/int diretamente
    - Remove 'R$' e espaços
    - Remove pontos de milhar e converte vírgula para ponto quando ambos existem
    - Fallback com regex se necessário
    """
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        v = float(valor)
        return 0.0 if math.isnan(v) else v

    s = str(valor).strip()
    if s == "" or s.upper() == "NAN":
        return 0.0

    s = s.replace("R$", "").replace(" ", "").replace("\u00a0", "")
    try:
        if "," in s:
            # Formato BR: '.' milhar, ',' decimal
            s = s.replace(".", "").replace(",", ".")
            return float(s)
        # Caso só ponto (.) como decimal
        return float(s)
    except Exception:
        m = re.search(r"-?\d+(?:[.,]\d+)?", s)
        if not m:
            return 0.0
        frag = m.group(0).replace(".", "").replace(",", ".")
        try:
            return float(frag)
        except Exception:
            return 0.0


def normalize_str(text: object) -> str:
    """Remove acentos, converte para MAIÚSCULAS e strip. Retorna '' para NaN/None."""
    if text is None or (isinstance(text, float) and math.isnan(text)):
        return ""
    s = str(text)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.upper().strip()


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza colunas e tipos do DataFrame de notas (puro, sem Streamlit):
    - Renomeia colunas conhecidas para nomes padronizados
    - Cria coluna 'data' padronizada (a partir de 'data_emissao' ou similar)
    - Cria chave 'yyyymm' = AAAAMM (int)
    - Normaliza 'tipo_nota', 'classificacao', 'natureza_operacao'
    - Faz parse seguro de 'valor_total' (BRL -> float)
    """
    if df is None or df.empty:
        # Retorna DF com as colunas mínimas
        return pd.DataFrame(columns=["data", "yyyymm", "tipo_nota", "classificacao", "natureza_operacao", "valor_total"])

    # Renomear colunas conforme mapa (case-insensitive)
    cols_lower = {c.lower(): c for c in df.columns}
    rename_map: Dict[str, str] = {}
    for k_lower, std_name in COL_MAP.items():
        if k_lower in cols_lower:
            rename_map[cols_lower[k_lower]] = std_name
    df = df.rename(columns=rename_map)

    # Garantir colunas essenciais
    for col in ["valor_total", "data_emissao", "tipo_nota", "classificacao", "natureza_operacao"]:
        if col not in df.columns:
            df[col] = np.nan

    # Criar 'data' e 'yyyymm'
    data_series = pd.to_datetime(df["data_emissao"], errors="coerce", dayfirst=True)
    df["data"] = data_series
    df["yyyymm"] = (df["data"].dt.year * 100 + df["data"].dt.month).astype("Int64")

    # Normalizações textuais
    df["tipo_nota"] = df["tipo_nota"].apply(normalize_str)
    df["classificacao"] = df["classificacao"].apply(normalize_str)
    df["natureza_operacao"] = df["natureza_operacao"].apply(normalize_str)

    # Valores monetários
    df["valor_total"] = df["valor_total"].apply(parse_brl)

    return df


# ============================================================
# Consolidação realizada (pura)
# ============================================================
def realizado_por_mes(df: pd.DataFrame, ano: int = 2025) -> Dict[int, Dict[str, float]]:
    """
    Consolida valores realizados por mês (por yyyymm) para o ano informado.
    Regras:
      - FAT = soma de SAIDA (exclui devolução de compra)
      - COMPRAS = soma de ENTRADA com CLASSIFICACAO='MERCADORIA PARA REVENDA'
                  menos as 'DEVOLUCAO DE COMPRA' (sempre abatendo compras)
      - LAT = FAT - COMPRAS
    Retorna: {yyyymm: {"FAT": float, "COMPRAS": float, "LAT": float}, ...}
    """
    df = prepare_dataframe(df)
    if df.empty:
        return {ano * 100 + m: {"FAT": 0.0, "COMPRAS": 0.0, "LAT": 0.0} for m in range(1, 13)}

    df = df[(df["yyyymm"].notna()) & ((df["yyyymm"] // 100) == ano)].copy()

    months = [ano * 100 + m for m in range(1, 13)]

    # Máscaras
    mask_devol = df["natureza_operacao"].str.contains("DEVOLUCAO DE COMPRA", na=False)
    mask_saida = df["tipo_nota"] == "SAIDA"
    mask_entrada = df["tipo_nota"] == "ENTRADA"
    mask_compras = mask_entrada & (df["classificacao"] == "MERCADORIA PARA REVENDA")

    # FAT: SAIDA excluindo devolução de compra
    fat_series = (
        df[mask_saida & ~mask_devol]
        .groupby("yyyymm")["valor_total"]
        .sum()
        .reindex(months, fill_value=0.0)
    )

    # COMPRAS: ENTRADA (mercadoria p/ revenda) - devoluções de compra
    compras_series = (
        df[mask_compras]
        .groupby("yyyymm")["valor_total"]
        .sum()
        .reindex(months, fill_value=0.0)
    )
    devol_series = (
        df[mask_devol]
        .groupby("yyyymm")["valor_total"]
        .sum()
        .reindex(months, fill_value=0.0)
    )
    compras_series = compras_series - devol_series
    lat_series = fat_series - compras_series

    # Monta dict final
    out: Dict[int, Dict[str, float]] = {}
    for m in months:
        out[m] = {
            "FAT": float(fat_series.loc[m]),
            "COMPRAS": float(compras_series.loc[m]),
            "LAT": float(lat_series.loc[m]),
        }
    return out


# ============================================================
# IRPJ / CSLL trimestrais (puro)
# ============================================================
def irpj_csll_trimestre(lat_por_mes: Dict[int, float]) -> Dict[int, Tuple[float, float]]:
    """
    Calcula IRPJ/CSLL por trimestre civil a partir de um dict {yyyymm: LAT}.
    Regras:
      Base_mês = 32% * LAT_mês
      IRPJ_tri = 15% * ΣBase + adicional de 10% sobre o que exceder 60.000
      CSLL_tri = 9% * ΣBase
      Lançar apenas em Mar/Jun/Set/Dez; nos outros meses do trimestre, não retorna chave.
    Retorna: {yyyymm_fechamento: (IRPJ, CSLL), ...}
    """
    if not lat_por_mes:
        return {}

    # Agrupa por ano
    anos = sorted({m // 100 for m in lat_por_mes.keys()})
    resultado: Dict[int, Tuple[float, float]] = {}

    for ano in anos:
        # Trimestres
        trimestres = {
            1: [1, 2, 3],
            2: [4, 5, 6],
            3: [7, 8, 9],
            4: [10, 11, 12],
        }
        for meses in trimestres.values():
            meses_yyyymm = [ano * 100 + m for m in meses]
            base_total = sum(0.32 * float(lat_por_mes.get(m, 0.0)) for m in meses_yyyymm)

            # Base não negativa para tributos
            base_pos = max(0.0, base_total)
            if base_pos == 0.0:
                continue

            irpj = 0.15 * base_pos
            excedente = max(0.0, base_pos - 60000.0)
            irpj += 0.10 * excedente

            csll = 0.09 * base_pos

            mes_fechamento = meses_yyyymm[-1]  # Mar/Jun/Set/Dez
            resultado[mes_fechamento] = (irpj, csll)

    return resultado


# ============================================================
# Auxiliares de período para o app (puras)
# ============================================================
def mes_vigente(df: pd.DataFrame) -> int:
    """
    Retorna o último yyyymm presente na planilha (fonte: df['yyyymm'].max()).
    Se não houver, retorna 0.
    """
    if df is None or df.empty or "yyyymm" not in df.columns:
        return 0
    vals = pd.to_numeric(df["yyyymm"], errors="coerce").dropna()
    if vals.empty:
        return 0
    return int(vals.max())


def meses_simulaveis(vigente_yyyymm: int, sim_vigente: bool) -> List[int]:
    """
    Lista meses simuláveis a partir do mês 'vigente'.
    - Se sim_vigente=True: inclui o próprio mês vigente.
    - Caso contrário: inicia no mês seguinte.
    Sempre até dezembro do mesmo ano.
    """
    if not vigente_yyyymm:
        # fallback: ano corrente
        today = datetime.today()
        vigente_yyyymm = today.year * 100 + today.month

    ano = vigente_yyyymm // 100
    mes = vigente_yyyymm % 100
    start = mes if sim_vigente else mes + 1
    start = min(max(1, start), 12)

    return [ano * 100 + m for m in range(start, 13)]


# ============================================================
# Cenários por margem (puro — opcional; útil para testes)
# ============================================================
def cenarios_por_margem(LAT: float) -> Dict[int, Dict[str, float]]:
    """
    Para um LAT mensal, retorna cenários de FAT/COMPRAS/ICMS nas margens padrão.
    (Mantido aqui para compatibilidade; a versão de exibição fica em ui_helpers.cenarios_fat_compra)
    """
    out: Dict[int, Dict[str, float]] = {}
    lat = max(0.0, float(LAT))
    for r in MARGENS:
        if r <= 0:
            continue
        fat = lat / r
        compras = fat - lat
        icms = 0.05 * fat
        out[int(r * 100)] = {"FAT": fat, "COMPRAS": compras, "ICMS": icms}
    return out


# ============================================================
# Versão DataFrame dos tributos trimestrais (conveniência)
# ============================================================
def calcular_irpj_csll_trimestral(df: pd.DataFrame, col_lat: str = "LAT") -> pd.DataFrame:
    """
    Conveniência: aplica IRPJ/CSLL trimestrais a um DataFrame que possua:
      - coluna 'yyyymm'
      - coluna de LAT (por padrão 'LAT')
    Preenche apenas nos meses de fechamento do trimestre.
    """
    if df is None or df.empty:
        return df

    if "yyyymm" not in df.columns or col_lat not in df.columns:
        return df

    df = df.copy()
    df["IRPJ"] = 0.0
    df["CSLL"] = 0.0

    lat_dict = pd.Series(df[col_lat].values, index=df["yyyymm"].values).to_dict()
    trib = irpj_csll_trimestre(lat_dict)

    if trib:
        for ymm, (irpj, csll) in trib.items():
            df.loc[df["yyyymm"] == ymm, "IRPJ"] = irpj
            df.loc[df["yyyymm"] == ymm, "CSLL"] = csll

    return df
