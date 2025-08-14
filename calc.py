from __future__ import annotations
from typing import Dict, Sequence, Optional, Tuple, List
import pandas as pd
import numpy as np
from datetime import datetime

# Margens padrão utilizadas no app
MARGENS: List[float] = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]

def parse_brl(valor_str: str) -> float:
    """Parse seguro de valores BRL removendo pontos de milhar e convertendo vírgula."""
    if pd.isna(valor_str) or valor_str == "":
        return 0.0
    try:
        # Remove pontos de milhar e substitui vírgula por ponto
        valor_clean = str(valor_str).replace(".", "").replace(",", ".")
        return float(valor_clean)
    except (ValueError, AttributeError):
        return 0.0

def normalize_tipo_nota(tipo: str) -> str:
    """Normaliza tipo de nota removendo acentos e padronizando case."""
    if pd.isna(tipo):
        return ""
    return str(tipo).strip().lower().replace("saída", "saida")

def yyyy_mm(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona coluna yyyymm padronizada ao DataFrame."""
    df = df.copy()
    df["data_emissao"] = pd.to_datetime(df["data_emissao"], errors="coerce", dayfirst=True)
    df["ano"] = df["data_emissao"].dt.year
    df["mes"] = df["data_emissao"].dt.month
    df["yyyymm"] = df["ano"] * 100 + df["mes"]
    return df

def realizado_por_mes(df: pd.DataFrame) -> pd.DataFrame:
    """Consolida valores realizados de 2025 por mês (sem CONSUMO)."""
    df = prepare_dataframe(df)
    df = df[df["ano"] == 2025]
    
    # Máscaras para diferentes tipos de operação
    mask_devol = df["natureza_operacao"].str.contains("devolucao de compra", case=False, na=False)
    mask_saida = df["tipo_nota"] == "saida"
    mask_entrada = df["tipo_nota"] == "entrada"
    mask_compras = mask_entrada & (df["classificacao"] == "mercadoria para revenda")
    
    # Consolida por mês
    mensal = pd.DataFrame(index=range(1, 13), columns=["FAT", "COMPRAS", "LAT"], data=0.0)
    
    # FAT = saídas (exceto devoluções)
    mensal["FAT"] = df[mask_saida & ~mask_devol].groupby("mes")["valor_total"].sum()
    
    # COMPRAS = entradas de mercadoria - devoluções
    mensal["COMPRAS"] = df[mask_compras].groupby("mes")["valor_total"].sum()
    mensal["COMPRAS"] -= df[mask_devol].groupby("mes")["valor_total"].sum().reindex(mensal.index, fill_value=0)
    
    mensal = mensal.fillna(0.0)
    
    # LAT = FAT - COMPRAS (sem consumo na simulação)
    mensal["LAT"] = mensal["FAT"] - mensal["COMPRAS"]
    
    # Tributos mensais
    mensal["PIS"] = 0.0065 * mensal["LAT"]
    mensal["COFINS"] = 0.03 * mensal["LAT"]
    mensal["ICMS"] = 0.05 * mensal["FAT"]
    
    # IRPJ/CSLL trimestrais
    mensal = calcular_irpj_csll_trimestral(mensal)
    
    # Lucro Líquido
    mensal["LL"] = mensal["LAT"] - (mensal["PIS"] + mensal["COFINS"] + mensal["ICMS"] + mensal["IRPJ"] + mensal["CSLL"])
    
    mensal["yyyymm"] = [202500 + i for i in range(1, 13)]
    
    return mensal

def cenarios_por_margem(LAT: float) -> dict[int, dict[str, float]]:
    """Retorna cenários de FAT/COMPRAS/ICMS para um LAT em diferentes margens."""
    cenarios = {}
    LAT = max(0.0, float(LAT))
    
    for margem in MARGENS:
        margem_pct = int(margem * 100)
        fat = LAT / margem if margem > 0 else 0.0
        compras = fat - LAT
        icms = 0.05 * fat
        
        cenarios[margem_pct] = {
            "FAT": fat,
            "COMPRAS": compras,
            "ICMS": icms
        }
    
    return cenarios

def irpj_csll_trimestre(lat_por_mes: Dict[int, float]) -> Dict[int, Tuple[float, float]]:
    """Calcula IRPJ/CSLL trimestrais, lançando apenas no mês de fechamento."""
    resultado = {}
    if not lat_por_mes:
        return resultado
    
    # Mapeamento dos trimestres
    mapa_tri = {1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12]}
    
    anos = {m // 100 for m in lat_por_mes.keys()}
    
    for ano in anos:
        for tri, meses in mapa_tri.items():
            meses_yyyymm = [ano * 100 + m for m in meses]
            
            # Base total do trimestre (32% do LAT)
            base_total = sum(0.32 * lat_por_mes.get(m, 0.0) for m in meses_yyyymm)
            
            if base_total <= 0:
                continue
                
            # IRPJ: 15% + 10% sobre o que exceder 60k
            irpj = 0.15 * base_total
            if base_total > 60000:
                irpj += 0.10 * (base_total - 60000)
            
            # CSLL: 9% sobre a base
            csll = 0.09 * base_total
            
            # Lança no mês de fechamento (último do trimestre)
            mes_fechamento = meses_yyyymm[-1]
            resultado[mes_fechamento] = (irpj, csll)
    
    return resultado

def calcular_irpj_csll_trimestral(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica IRPJ/CSLL trimestrais ao DataFrame mensal."""
    df = df.copy()
    df["IRPJ"] = 0.0
    df["CSLL"] = 0.0
    
    # Constrói dict de LAT por yyyymm
    lat_dict = {}
    for idx in df.index:
        if idx >= 1 and idx <= 12:
            yyyymm = 202500 + idx
            lat_dict[yyyymm] = df.at[idx, "LAT"]
    
    # Calcula IRPJ/CSLL trimestrais
    tributos = irpj_csll_trimestre(lat_dict)
    
    # Aplica aos meses de fechamento
    for yyyymm, (irpj, csll) in tributos.items():
        mes = yyyymm % 100
        if mes in df.index:
            df.at[mes, "IRPJ"] = irpj
            df.at[mes, "CSLL"] = csll
    
    return df

def meses_simulaveis(ultimo_real: int, sim_vigente: bool, ano: int = 2025) -> List[int]:
    """Retorna lista de meses yyyymm disponíveis para simulação."""
    hoje = datetime.today()
    
    if sim_vigente and hoje.year == ano:
        # Permite simular a partir do mês vigente
        mes_inicio = ultimo_real % 100 if ultimo_real > 0 else hoje.month
        limite = 12
    else:
        # Simula apenas meses futuros
        mes_inicio = (ultimo_real % 100) + 1 if ultimo_real > 0 else hoje.month + 1
        limite = 12
    
    return [ano * 100 + m for m in range(mes_inicio, limite + 1)]

def mes_vigente(df: pd.DataFrame) -> int:
    """Retorna o maior yyyymm existente na planilha."""
    if df.empty or "yyyymm" not in df.columns:
        return 0
    
    return int(df[df["FAT"] > 0]["yyyymm"].max()) if not df[df["FAT"] > 0]["yyyymm"].empty else 0

# ========= Funções auxiliares de preparação de dados =========

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
    # Mapeia colunas para nomes padronizados
    cols_lower = {c.lower(): c for c in df.columns}
    rename_map = {}
    for k, v in COL_MAP.items():
        if k in cols_lower:
            rename_map[cols_lower[k]] = v
    
    df = df.rename(columns=rename_map)
    
    # Garante que colunas essenciais existem
    for col in ["valor_total", "data_emissao", "tipo_nota", "classificacao", "natureza_operacao"]:
        if col not in df.columns:
            df[col] = np.nan
    
    # Parsing seguro de valores BRL
    df["valor_total"] = df["valor_total"].apply(lambda x: parse_brl(x) if pd.notna(x) else 0.0)
    
    # Normalização de datas e tipos
    df = yyyy_mm(df)
    df["tipo_nota"] = df["tipo_nota"].apply(normalize_tipo_nota)
    df["classificacao"] = df["classificacao"].astype(str).str.strip().str.lower()
    df["natureza_operacao"] = df["natureza_operacao"].astype(str).str.strip().str.lower()
    
    return df
