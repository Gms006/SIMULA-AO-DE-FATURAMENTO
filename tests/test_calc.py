import os
import sys
import pandas as pd
import streamlit as st
import pytest

# Garantir import dos módulos locais
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui_helpers import cenarios_fat_compra, pis_cofins
from calc import irpj_csll_trimestre


def test_number_column_format_and_dtype():
    # Deve aceitar edição float com format="R$ %.2f" (sem erro de sprintf) e manter dtype float
    df = pd.DataFrame({"LAT (R$)": pd.Series([None] * 12, dtype="float")})
    _ = st.column_config.NumberColumn("LAT (R$)", format="R$ %.2f", step=100.0, min_value=0.0)
    assert str(df["LAT (R$)"].dtype) == "float64"


def test_cenarios_fat_compra_margem_20():
    # Exemplo: LAT=389.800, margem 20% => FAT=1.949.000; COMPRAS=1.559.200; ICMS=97.450
    res = cenarios_fat_compra(389_800)
    assert res[20]["FAT"] == pytest.approx(1_949_000)
    assert res[20]["COMPRAS"] == pytest.approx(1_559_200)
    assert res[20]["ICMS"] == pytest.approx(97_450)


def test_vigente_soma_real_simulado_e_tributos_mensais():
    # No mês vigente, total = realizado + simulado; PIS/COFINS sobre o LAT total do mês
    lat_real = 10_000.0
    lat_sim = 5_000.0
    lat_total = lat_real + lat_sim

    pis, cofins = pis_cofins(lat_total)
    assert pis == pytest.approx(0.0065 * lat_total)
    assert cofins == pytest.approx(0.03 * lat_total)

    # Trimestre Jan–Mar com lançamento apenas em Mar/2025
    lat_dict = {202501: lat_real, 202502: lat_total, 202503: 0.0}
    trib = irpj_csll_trimestre(lat_dict)
    base = 0.32 * (lat_real + lat_total + 0.0)
    # Base < 60k => sem adicional, só 15% de IRPJ; CSLL 9%
    assert trib[202503][0] == pytest.approx(0.15 * base)
    assert trib[202503][1] == pytest.approx(0.09 * base)
    assert 202502 not in trib  # nada em meses não-fechamento


def test_irpj_csll_trimestre_aplica_adicional_quando_excede_60k():
    # ΣBase = 0.32 * (100k + 100k + 100k) = 96k > 60k => aplica adicional 10% sobre excedente
    lat_mes = {202501: 100_000.0, 202502: 100_000.0, 202503: 100_000.0}
    trib = irpj_csll_trimestre(lat_mes)
    assert 202503 in trib and 202502 not in trib

    irpj, csll = trib[202503]
    base_total = 0.32 * (300_000.0)
    expected_irpj = 0.15 * base_total + 0.10 * (base_total - 60_000)
    expected_csll = 0.09 * base_total

    assert irpj == pytest.approx(expected_irpj)
    assert csll == pytest.approx(expected_csll)
