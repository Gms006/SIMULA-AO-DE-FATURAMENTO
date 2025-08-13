import os
import sys
import pandas as pd
import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from calc import compute_realizado, apurar_irpj_csll_trimestral, simulate

def test_pis_cofins_icms():
    df = pd.DataFrame({
        "Data Emissão": ["01/01/2025", "01/01/2025"],
        "Valor Total": ["200000,00", "100000,00"],
        "Tipo Nota": ["Saída", "Entrada"],
        "Classificação": ["", "MERCADORIA PARA REVENDA"],
        "Natureza Operação": ["Venda", "Compra"],
    })
    mensal = compute_realizado(df)
    assert mensal.at[1, "PIS"] == pytest.approx(650.0)
    assert mensal.at[1, "COFINS"] == pytest.approx(3000.0)
    assert mensal.at[1, "ICMS"] == pytest.approx(10000.0)

def test_irpj_csll_rateio():
    tri = pd.DataFrame(index=[1,2,3], data={"LAT":[83333.33,83333.33,83333.34]})
    tri = apurar_irpj_csll_trimestral(tri)
    assert tri["IRPJ"].sum() == pytest.approx(14000.0)
    assert tri["CSLL"].sum() == pytest.approx(7200.0)

def test_simulation_margin():
    vazio = pd.DataFrame(
        index=range(1,13),
        columns=["FAT","CMV","CONSUMO","LB","LAT","PIS","COFINS","ICMS","IRPJ","CSLL","LL","Compras"],
        data=0.0,
    )
    sim = simulate(vazio, 50000.0, [0.20], [1])[0.20]
    assert sim.at[1, "FAT"] == pytest.approx(250000.0)
    assert sim.at[1, "CMV"] == pytest.approx(200000.0)
