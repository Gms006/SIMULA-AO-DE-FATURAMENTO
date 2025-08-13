#!/bin/bash
set -e
mkdir -p tests
if [ ! -f app.py ]; then
  cat <<'APP' > app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import BytesIO
from calc import prepare_dataframe, compute_realizado, simulate

st.set_page_config(page_title="Simulação de Faturamento 2025", layout="wide")

st.sidebar.header("Parâmetros GitHub")
owner = st.sidebar.text_input("Owner", value="")
repo = st.sidebar.text_input("Repo", value="SIMULACAO-DE-FATURAMENTO")
branch = st.sidebar.text_input("Branch", value="main")
path = st.sidebar.text_input("Path", value="resultado_eduardo_veiculos.xlsx")

@st.cache_data(ttl=300)
def load_data(owner: str, repo: str, branch: str, path: str):
    if owner:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        try:
            return pd.read_excel(url, engine="openpyxl")
        except Exception:
            st.warning("Falha ao carregar do GitHub.")
    try:
        return pd.read_excel(path, engine="openpyxl")
    except Exception:
        return None

df = load_data(owner, repo, branch, path)
if df is None:
    uploaded = st.file_uploader("Envie a planilha resultado_eduardo_veiculos.xlsx", type="xlsx")
    if uploaded:
        df = pd.read_excel(uploaded, engine="openpyxl")

if df is None:
    st.stop()

df = prepare_dataframe(df)
realizado = compute_realizado(df)
last_month = int(realizado[realizado["FAT"] > 0].index.max() or 0)

def fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

pagina = st.sidebar.selectbox("Página", ["Dashboard", "Simulação", "Notas/Detalhes"])

if pagina == "Dashboard":
    ano = st.sidebar.selectbox("Ano", [2025], index=0)
    mes = st.sidebar.selectbox("Mês", list(range(1, 13)), index=max(last_month - 1, 0))
    linha = realizado.loc[mes]
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Entradas", fmt_brl(linha["CMV"]))
    col2.metric("Saídas", fmt_brl(linha["FAT"]))
    col3.metric("LAT", fmt_brl(linha["LAT"]))
    col4.metric("Lucro Líquido", fmt_brl(linha["LL"]))
    col5.metric("Consumo", fmt_brl(linha["CONSUMO"]))
    mensal = realizado.copy()
    mensal["Tributos"] = mensal[["PIS", "COFINS", "ICMS", "IRPJ", "CSLL"]].sum(axis=1)
    fig = px.bar(mensal, x=mensal.index, y=["FAT", "CMV", "CONSUMO", "LAT", "Tributos", "LL"], barmode="stack")
    fig.update_layout(xaxis_title="Mês", yaxis_title="R$")
    st.plotly_chart(fig, use_container_width=True)

elif pagina == "Simulação":
    st.header("Simulação 2025")
    lat_meta = st.number_input("Meta LAT Anual (R$)", min_value=0.0, step=1000.0)
    margens_opts = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    margens = [m for m in margens_opts if st.checkbox(f"Margem {int(m*100)}%", True, key=f"m_{m}")]
    sim_mes_atual = st.checkbox("Simular mês vigente", False)
    meses_sim = list(range(last_month + 1, 13))
    locked = list(range(1, last_month + 1))
    if sim_mes_atual:
        meses_sim = list(range(last_month, 13))
        locked = list(range(1, last_month))
    manual = st.checkbox("Distribuição manual por mês", False)
    distrib = {}
    if manual:
        st.write("Distribuição (% do LAT restante)")
        total = 0
        for mes in meses_sim:
            val = st.slider(f"Mês {mes:02d}", 0, 100, value=int(100 / len(meses_sim)), key=f"d_{mes}")
            distrib[mes] = val
            total += val
        if total > 0:
            distrib = {k: v / total for k, v in distrib.items()}
        else:
            distrib = None
    else:
        distrib = None
    resultados = simulate(realizado, lat_meta, margens, meses_sim, distrib)
    for margem, dfm in resultados.items():
        st.subheader(f"Margem {int(margem*100)}%")
        df_show = dfm.copy()
        df_show["Tributos"] = df_show[["PIS", "COFINS", "ICMS", "IRPJ", "CSLL"]].sum(axis=1)
        total = df_show.sum()
        df_show = pd.concat([df_show, total.to_frame().T], ignore_index=False)
        df_show.index = list(range(1, 13)) + ["Total"]
        st.dataframe(df_show)
        if (df_show.loc[1:12, "LL"] < 0).any():
            st.warning("Lucro Líquido negativo em algum mês.")
        csv = df_show.to_csv().encode("utf-8")
        st.download_button("Exportar CSV", csv, f"simulacao_{int(margem*100)}.csv", "text/csv")
        towrite = BytesIO()
        with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
            df_show.to_excel(writer, index=True)
        st.download_button(
            "Exportar XLSX",
            towrite.getvalue(),
            f"simulacao_{int(margem*100)}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            pdf_buffer = BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=A4)
            c.drawString(30, 800, f"Simulação margem {int(margem*100)}%")
            text = c.beginText(30, 780)
            for line in df_show.to_string().split("\n"):
                text.textLine(line)
            c.drawText(text)
            c.showPage()
            c.save()
            pdf_buffer.seek(0)
            st.download_button(
                "Exportar PDF",
                pdf_buffer,
                f"simulacao_{int(margem*100)}.pdf",
                "application/pdf",
            )
        except Exception:
            st.info("reportlab não disponível para PDF.")
elif pagina == "Notas/Detalhes":
    st.header("Notas/Detalhes")
    meses = st.multiselect("Mês", sorted(df["mes"].unique()), default=sorted(df["mes"].unique()))
    tipos = st.multiselect("Tipo Nota", sorted(df["tipo_nota"].unique()), default=sorted(df["tipo_nota"].unique()))
    classifs = st.multiselect("Classificação", sorted(df["classificacao"].unique()), default=sorted(df["classificacao"].unique()))
    filtrado = df[df["mes"].isin(meses) & df["tipo_nota"].isin(tipos) & df["classificacao"].isin(classifs)]
    st.dataframe(filtrado)
    csv = filtrado.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, "notas_filtradas.csv", "text/csv")
    towrite = BytesIO()
    with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
        filtrado.to_excel(writer, index=False)
    st.download_button(
        "Download XLSX",
        towrite.getvalue(),
        "notas_filtradas.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
APP
fi
if [ ! -f calc.py ]; then
  cat <<'CALC' > calc.py
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
CALC
fi
echo "Bootstrap concluído"
