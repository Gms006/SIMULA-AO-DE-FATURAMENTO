from __future__ import annotations
from typing import Dict, Sequence, Optional, Tuple, List
import pandas as pd
import numpy as np

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


def calc_mes(lat: float) -> Dict[str, Dict]:
    """Calcula tributos e cenários de faturamento para um LAT mensal."""
    pis = 0.0065 * lat
    cofins = 0.03 * lat
    margens = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    cenarios: Dict[float, Dict[str, float]] = {}
    for m in margens:
        fat = lat / m if m else 0.0
        compras = fat - lat
        icms = 0.05 * fat
        cenarios[m] = {"FAT": fat, "COMPRAS": compras, "ICMS": icms}
    return {"PIS": pis, "COFINS": cofins, "cenarios": cenarios}


def irpj_csll_trimestre(lat_por_mes: Dict[int, float], tri_key: str) -> Tuple[float, float, int]:
    """Retorna IRPJ, CSLL totais do trimestre e mês de fechamento."""
    ano = int(tri_key[:4])
    tri = int(tri_key[-1])
    mapa = {1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12]}
    meses = [ano * 100 + m for m in mapa[tri]]
    bases = [0.32 * lat_por_mes.get(m, 0.0) for m in meses]
    base_total = sum(bases)
    irpj = 0.15 * base_total
    if base_total > 60000:
        irpj += 0.10 * (base_total - 60000)
    csll = 0.09 * base_total
    fechamento = meses[-1]
    return irpj, csll, fechamento


def ultimo_yyyymm(df: pd.DataFrame) -> int:
    """Retorna o último yyyymm encontrado no DataFrame."""
    if "yyyymm" in df.columns and not df["yyyymm"].dropna().empty:
        return int(df["yyyymm"].dropna().astype(int).max())
    return 0


def meses_simulaveis(ultimo: int) -> List[int]:
    """Lista meses yyyymm posteriores ao último mês realizado."""
    return [m for m in range(202501, 202513) if m > ultimo]


def trimestre_de(mes: int) -> str:
    """Retorna a chave do trimestre (YYYYQn) para um yyyymm."""
    q = ((mes % 100 - 1) // 3) + 1
    return f"{mes // 100}Q{q}"


def progresso_trimestre(lat_por_mes: Dict[int, float], tri_key: str) -> Tuple[int, int, List[int]]:
    """Avalia o progresso do trimestre: meses preenchidos e faltantes."""
    ano = int(tri_key[:4])
    tri = int(tri_key[-1])
    mapa = {1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12]}
    meses = [ano * 100 + m for m in mapa[tri]]
    preenchidos = [m for m in meses if lat_por_mes.get(m, 0.0) > 0]
    faltantes = [m for m in meses if lat_por_mes.get(m, 0.0) <= 0]
    return len(preenchidos), len(meses), faltantes

if __name__ == "__main__":
    # Cenário 1
    res = calc_mes(100000.0)
    assert round(res["PIS"], 2) == 650.00
    assert round(res["COFINS"], 2) == 3000.00
    cen20 = res["cenarios"][0.20]
    assert round(cen20["FAT"], 2) == 500000.00
    assert round(cen20["COMPRAS"], 2) == 400000.00
    assert round(cen20["ICMS"], 2) == 25000.00

    # Cenário 2
    lat_mes = {202501: 83333.33, 202502: 83333.33, 202503: 83333.34}
    irpj, csll, fechamento = irpj_csll_trimestre(lat_mes, "2025Q1")
    assert round(irpj, 2) == 14000.00
    assert round(csll, 2) == 7200.00
    assert fechamento == 202503

    # Cenário 3
    prog0 = progresso_trimestre({}, "2025Q1")
    assert prog0[0] == 0
    prog2 = progresso_trimestre({202501: 1000.0, 202502: 1000.0}, "2025Q1")
    assert prog2[0] == 2
    prog3 = progresso_trimestre(lat_mes, "2025Q1")
    assert prog3[0] == 3
    print("Testes rápidos OK!")
