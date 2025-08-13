from __future__ import annotations
from typing import Dict, Sequence, Optional
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

def simulate(
    realizado: pd.DataFrame,
    lat_meta_anual: float,
    margins: Sequence[float],
    months_to_simulate: Sequence[int],
    distribution: Optional[Dict[int, float]] = None,
) -> Dict[float, pd.DataFrame]:
    """Simula meses futuros para atingir LAT anual."""
    meses_sim = list(months_to_simulate)
    locked = set(range(1, 13)) - set(meses_sim)
    lat_realizado = realizado.loc[sorted(locked), "LAT"].sum()
    lat_restante = max(lat_meta_anual - lat_realizado, 0.0)
    if distribution is None:
        distribution = {m: 1 / len(meses_sim) for m in meses_sim}
    else:
        total = sum(distribution.values())
        distribution = {m: distribution.get(m, 0) / total for m in meses_sim}
    resultados: Dict[float, pd.DataFrame] = {}
    for margem in margins:
        df = realizado.copy()
        for mes in meses_sim:
            lat_mes = lat_restante * distribution[mes]
            fat = lat_mes / margem if margem else 0.0
            cmv = fat - lat_mes
            df.loc[mes, "FAT"] = fat
            df.loc[mes, "CMV"] = cmv
            df.loc[mes, "CONSUMO"] = 0.0
            df.loc[mes, "LB"] = fat - cmv
            df.loc[mes, "LAT"] = lat_mes
            df.loc[mes, "PIS"] = 0.0065 * lat_mes
            df.loc[mes, "COFINS"] = 0.03 * lat_mes
            df.loc[mes, "ICMS"] = 0.05 * fat
            df.loc[mes, ["IRPJ", "CSLL"]] = 0.0
        df = apurar_irpj_csll_trimestral(df, locked_months=locked)
        df["LL"] = df["LAT"] - (df["PIS"] + df["COFINS"] + df["ICMS"] + df["IRPJ"] + df["CSLL"])
        df["Compras"] = df["CMV"]
        resultados[margem] = df
    return resultados

if __name__ == "__main__":
    # Cenário 1
    df1 = pd.DataFrame(
        {
            "Data Emissão": ["01/01/2025", "01/01/2025"],
            "Valor Total": ["200000,00", "100000,00"],
            "Tipo Nota": ["Saída", "Entrada"],
            "Classificação": ["", "MERCADORIA PARA REVENDA"],
            "Natureza Operação": ["Venda", "Compra"],
        }
    )
    real = compute_realizado(df1)
    assert round(real.at[1, "PIS"], 2) == 650.00
    assert round(real.at[1, "COFINS"], 2) == 3000.00
    assert round(real.at[1, "ICMS"], 2) == 10000.00

    # Cenário 2
    tri = pd.DataFrame(index=[1, 2, 3], data={"LAT": [83333.33, 83333.33, 83333.34]})
    tri = apurar_irpj_csll_trimestral(tri)
    assert round(tri["IRPJ"].sum(), 2) == 14000.00
    assert round(tri["CSLL"].sum(), 2) == 7200.00

    # Cenário 3
    vazio = pd.DataFrame(
        index=range(1, 13),
        columns=[
            "FAT",
            "CMV",
            "CONSUMO",
            "LB",
            "LAT",
            "PIS",
            "COFINS",
            "ICMS",
            "IRPJ",
            "CSLL",
            "LL",
            "Compras",
        ],
        data=0.0,
    )
    sim = simulate(vazio, 50000.0, [0.20], [1])[0.20]
    assert round(sim.at[1, "FAT"], 2) == 250000.00
    assert round(sim.at[1, "CMV"], 2) == 200000.00
    print("Testes rápidos OK!")
