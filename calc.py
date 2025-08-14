from __future__ import annotations
from typing import Dict, Sequence, Optional, Tuple, List
import pandas as pd
import numpy as np
from datetime import datetime

# Margens padrão utilizadas no app
MARGENS: List[float] = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]


def calc_por_margem(lat: float, margem: float) -> Dict[str, float]:
    """Calcula FAT, Compras e ICMS para um LAT em uma margem dada."""
    if margem <= 0:
        raise ValueError("Margem deve ser maior que zero")
    fat = lat / margem if lat else 0.0
    compras = fat - lat
    icms = 0.05 * fat
    return {"FAT": fat, "COMPRAS": compras, "ICMS": icms}


def base_pis_cofins(
    base: str,
    lat: float,
    fat_ref: float,
    m_ref: float = 0.20,
    aliq_pis: float = 0.0065,
    aliq_cof: float = 0.03,
) -> Tuple[float, float]:
    """Calcula PIS/COFINS conforme a base selecionada."""
    if base == "Lucro do mês (LAT)":
        base_val = lat
    elif base == "Receita (FAT)":
        base_val = fat_ref
    else:  # "Margem (FAT*m)"
        base_val = fat_ref * m_ref
    pis = aliq_pis * base_val
    cofins = aliq_cof * base_val
    return pis, cofins


def meses_simulaveis(ultimo: int, sim_vigente: bool, ano: int = 2025) -> List[int]:
    """Retorna lista de meses yyyymm disponíveis para simulação."""
    hoje = datetime.today()
    limite = hoje.month if (sim_vigente and hoje.year == ano) else 12
    return [ano * 100 + m for m in range(1, limite + 1) if ano * 100 + m > ultimo]


def irpj_csll_trimestrais(lat_por_mes: Dict[int, float]) -> Dict[int, Tuple[float, float]]:
    """Calcula IRPJ/CSLL trimestrais, lançando apenas no mês de fechamento."""
    resultado: Dict[int, Tuple[float, float]] = {}
    if not lat_por_mes:
        return resultado
    mapa_tri = {1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12]}
    anos = {m // 100 for m in lat_por_mes.keys()}
    for ano in anos:
        for tri, meses in mapa_tri.items():
            meses_yyyymm = [ano * 100 + m for m in meses]
            base_total = sum(0.32 * lat_por_mes.get(m, 0.0) for m in meses_yyyymm)
            if base_total <= 0:
                continue
            irpj = 0.15 * base_total
            if base_total > 60000:
                irpj += 0.10 * (base_total - 60000)
            csll = 0.09 * base_total
            resultado[meses_yyyymm[-1]] = (irpj, csll)
    return resultado

COL_MAP = {
    "cfop": "cfop",
    "data emissão": "data_emissao",
    "emitente cnpj/cpf": "emitente",
    "destinatário cnpj/cpf": "destinatario",
    "chassi": "chassi",
    "placa": "placa",
    "produto": "produto",
    "valor total": "valor_total",
    "renavam": "renavam",
    "km": "km",
    "ano modelo": "ano_modelo",
    "ano fabricação": "ano_fabricacao",
    "cor": "cor",
    "icms alíquota": "icms_aliquota",
    "icms valor": "icms_valor",
    "icms base": "icms_base",
    "cst icms": "cst_icms",
    "redução bc": "reducao_bc",
    "modalidade bc": "modalidade_bc",
    "natureza operação": "natureza_operacao",
    "chave xml": "chave_xml",
    "xml path": "xml_path",
    "item": "item",
    "número nf": "numero_nf",
    "tipo nota": "tipo_nota",
    "classificação": "classificacao",
    "combustível": "combustivel",
    "motor": "motor",
    "modelo": "modelo",
    "potência": "potencia",
}

def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza colunas e tipos do DataFrame de notas."""
    cols_lower = {c.lower(): c for c in df.columns}
    rename_map = {}
    for k, v in COL_MAP.items():
        if k in cols_lower:
            rename_map[cols_lower[k]] = v
    df = df.rename(columns=rename_map)
    for col in ["valor_total", "data_emissao", "tipo_nota", "classificacao", "natureza_operacao"]:
        if col not in df.columns:
            df[col] = np.nan
    df["valor_total"] = (
        df["valor_total"].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    )
    df["valor_total"] = pd.to_numeric(df["valor_total"], errors="coerce").fillna(0.0)
    df["data_emissao"] = pd.to_datetime(df["data_emissao"], errors="coerce", dayfirst=True)
    df["ano"] = df["data_emissao"].dt.year
    df["mes"] = df["data_emissao"].dt.month
    df["yyyymm"] = df["data_emissao"].dt.strftime("%Y%m").astype(float).fillna(0).astype(int)
    df["tipo_nota"] = df["tipo_nota"].astype(str).str.strip().str.casefold()
    df["classificacao"] = df["classificacao"].astype(str).str.strip().str.casefold()
    df["natureza_operacao"] = df["natureza_operacao"].astype(str).str.strip().str.casefold()
    return df

def apurar_irpj_csll_trimestral(df: pd.DataFrame, locked_months: Optional[Sequence[int]] = None) -> pd.DataFrame:
    """Calcula IRPJ e CSLL trimestrais com rateio mensal."""
    df = df.copy().reindex(range(1,13), fill_value=0.0)
    df["Base"] = 0.32 * df["LAT"]
    df["IRPJ"] = df.get("IRPJ", 0.0)
    df["CSLL"] = df.get("CSLL", 0.0)
    locked = set(locked_months or [])
    trimestres = [(1, [1, 2, 3]), (2, [4, 5, 6]), (3, [7, 8, 9]), (4, [10, 11, 12])]
    for _, meses in trimestres:
        base_tri = df.loc[meses, "Base"].sum()
        if base_tri == 0:
            df.loc[meses, ["IRPJ", "CSLL"]] = 0.0
            continue
        irpj_total = 0.15 * base_tri
        if base_tri > 60000:
            irpj_total += 0.10 * (base_tri - 60000)
        csll_total = 0.09 * base_tri
        meses_locked = [m for m in meses if m in locked]
        meses_livres = [m for m in meses if m not in locked]
        irpj_locked = df.loc[meses_locked, "IRPJ"].sum()
        csll_locked = df.loc[meses_locked, "CSLL"].sum()
        base_livre = df.loc[meses_livres, "Base"].sum()
        irpj_restante = max(irpj_total - irpj_locked, 0.0)
        csll_restante = max(csll_total - csll_locked, 0.0)
        if meses_livres and base_livre > 0:
            df.loc[meses_livres, "IRPJ"] = irpj_restante * df.loc[meses_livres, "Base"] / base_livre
            df.loc[meses_livres, "CSLL"] = csll_restante * df.loc[meses_livres, "Base"] / base_livre
    return df

def compute_realizado(df: pd.DataFrame) -> pd.DataFrame:
    """Consolida valores realizados de 2025 por mês."""
    df = prepare_dataframe(df)
    df = df[df["ano"] == 2025]
    mask_devol = df["natureza_operacao"].str.contains("devolucao de compra")
    mask_saida = df["tipo_nota"] == "saída"
    mask_entrada = df["tipo_nota"] == "entrada"
    mask_cmv = mask_entrada & (df["classificacao"] == "mercadoria para revenda")
    mask_consumo = mask_entrada & (df["classificacao"] == "consumo")
    mensal = pd.DataFrame(index=range(1, 13), columns=["FAT", "CMV", "CONSUMO"], data=0.0)
    mensal["FAT"] = df[mask_saida & ~mask_devol].groupby("mes")["valor_total"].sum()
    mensal["CMV"] = df[mask_cmv].groupby("mes")["valor_total"].sum()
    mensal["CMV"] -= df[mask_devol].groupby("mes")["valor_total"].sum().reindex(mensal.index, fill_value=0)
    mensal["CONSUMO"] = df[mask_consumo].groupby("mes")["valor_total"].sum()
    mensal = mensal.fillna(0.0)
    mensal["LB"] = mensal["FAT"] - mensal["CMV"]
    mensal["LAT"] = mensal["LB"] - mensal["CONSUMO"]
    mensal["PIS"] = 0.0065 * mensal["LAT"]
    mensal["COFINS"] = 0.03 * mensal["LAT"]
    mensal["ICMS"] = 0.05 * mensal["FAT"]
    mensal = apurar_irpj_csll_trimestral(mensal)
    mensal["LL"] = mensal["LAT"] - (mensal["PIS"] + mensal["COFINS"] + mensal["ICMS"] + mensal["IRPJ"] + mensal["CSLL"])
    mensal["Compras"] = mensal["CMV"]
    mensal["yyyymm"] = [202500 + i for i in range(1, 13)]
    return mensal


def calc_mes(lat: float) -> Dict[str, any]:
    """Calcula PIS, COFINS e cenários de faturamento/compras para um LAT mensal.
    
    Args:
        lat: LAT do mês em reais
        
    Returns:
        dict com chaves:
        - PIS: valor do PIS do mês
        - COFINS: valor do COFINS do mês
        - cenarios: dict com margens (0.05-0.30) -> {FAT, COMPRAS, ICMS}
    """
    pis = 0.0065 * lat
    cofins = 0.03 * lat
    margens = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    cenarios: Dict[float, Dict[str, float]] = {}
    
    for m in margens:
        fat = lat / m if m > 0 else 0.0
        compras = fat - lat
        icms = 0.05 * fat
        cenarios[m] = {"FAT": fat, "COMPRAS": compras, "ICMS": icms}
        
    return {"PIS": pis, "COFINS": cofins, "cenarios": cenarios}


def irpj_csll_trimestre(lat_por_mes: Dict[int, float], tri_key: str) -> Tuple[float, float, int]:
    """Calcula IRPJ e CSLL totais do trimestre.
    
    Args:
        lat_por_mes: dict com yyyymm -> LAT do mês
        tri_key: chave do trimestre (ex: "2025Q1")
        
    Returns:
        tuple (IRPJ total, CSLL total, yyyymm do mês de fechamento)
    """
    ano = int(tri_key[:4])
    tri = int(tri_key[-1])
    
    # Mapeamento dos meses por trimestre
    mapa_tri = {1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12]}
    meses = [ano * 100 + m for m in mapa_tri[tri]]
    
    # Calcula base total do trimestre (32% do LAT)
    base_total = sum(0.32 * lat_por_mes.get(m, 0.0) for m in meses)
    
    # IRPJ: 15% sobre a base + 10% sobre o que exceder 60k
    irpj = 0.15 * base_total
    if base_total > 60000:
        irpj += 0.10 * (base_total - 60000)
        
    # CSLL: 9% sobre a base total
    csll = 0.09 * base_total
    
    # Mês de fechamento é o último do trimestre
    fechamento = meses[-1]
    
    return irpj, csll, fechamento


def ultimo_yyyymm(df: pd.DataFrame) -> int:
    """Retorna o último yyyymm (ano+mês) presente no DataFrame.
    
    Args:
        df: DataFrame com coluna 'yyyymm'
        
    Returns:
        Último yyyymm encontrado ou 0 se não houver dados
    """
    if "yyyymm" in df.columns and not df["yyyymm"].dropna().empty:
        return int(df["yyyymm"].dropna().astype(int).max())
    return 0

def trimestre_de(mes: int) -> str:
    """Retorna a chave do trimestre (YYYYQn) para um yyyymm.
    
    Args:
        mes: yyyymm
        
    Returns:
        String no formato "YYYYQn" (ex: "2025Q1")
    """
    ano = mes // 100
    m = mes % 100
    q = ((m - 1) // 3) + 1
    return f"{ano}Q{q}"


def progresso_trimestre(lat_por_mes: Dict[int, float], tri_key: str) -> Tuple[int, int, List[int]]:
    """Avalia o progresso do trimestre: quantos meses foram preenchidos.
    
    Args:
        lat_por_mes: dict com yyyymm -> LAT do mês
        tri_key: chave do trimestre (ex: "2025Q1")
        
    Returns:
        tuple (meses_preenchidos, total_meses, lista_meses_faltantes)
    """
    ano = int(tri_key[:4])
    tri = int(tri_key[-1])
    
    # Mapeamento dos meses por trimestre
    mapa_tri = {1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12]}
    meses = [ano * 100 + m for m in mapa_tri[tri]]
    
    # Verifica quais meses têm LAT > 0
    preenchidos = [m for m in meses if lat_por_mes.get(m, 0.0) > 0]
    faltantes = [m for m in meses if lat_por_mes.get(m, 0.0) <= 0]

    return len(preenchidos), len(meses), faltantes
