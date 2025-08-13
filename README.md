# Simulação de Faturamento 2025 — Revenda de Veículos (Streamlit)

App Streamlit para **apurar resultados de 2025** a partir de uma planilha real de **notas de veículos** e **simular o que falta faturar** para atingir um **lucro-alvo (LAT)**, mês a mês, considerando **PIS, COFINS, ICMS, IRPJ (com adicional trimestral) e CSLL**.

> **Público-alvo:** diretoria/financeiro.  
> **Verdades fiscais:** especificadas abaixo; o app e os testes devem seguir **exatamente** estas fórmulas.

---

## 1) Objetivos
- Exibir **KPIs** e **gráficos** do realizado em 2025 (entradas, saídas, consumo, LAT, tributos, LL).
- **Simular** meses restantes (inclusive o **mês vigente**, se habilitado) para atingir um **LAT anual** com margens de **5/10/15/20/25/30%**.
- Calcular **PIS, COFINS, ICMS** (mensais) e **IRPJ/CSLL** (trimestrais com rateio mensal), seguindo as regras definidas.
- Permitir **exportar** a simulação (CSV/XLSX). PDF é opcional.

---

## 2) Dados de entrada
- Arquivo: `resultado_eduardo_veiculos.xlsx`
- Colunas relevantes (case-insensitive):  
  `CFOP`, `Data Emissão`, `Emitente CNPJ/CPF`, `Destinatário CNPJ/CPF`, `Chassi`, `Placa`, `Produto`, `Valor Total`, `ICMS Alíquota`, `ICMS Valor`, `ICMS Base`, `Natureza Operação`, `Número NF`, `Tipo Nota`, `Classificação`, etc.
- `Valor Total` usa **vírgula decimal**.  
- **Devolução de compra**: se `Natureza Operação` contém “DEVOLUCAO DE COMPRA”, tratar como **abatimento de compras**, não como receita.

---

## 3) Apuração do realizado (mês a mês, 2025)
- **FAT** = soma `Valor Total` com `Tipo Nota = Saída`.
- **CMV_base** = soma `Valor Total` com `Tipo Nota = Entrada` e `Classificação = MERCADORIA PARA REVENDA`.
- **CONSUMO** = soma `Valor Total` com `Tipo Nota = Entrada` e `Classificação = CONSUMO`.
- **Lucro Bruto (LB)** = `FAT – CMV_base`.  
- **Lucro Antes de Tributos (LAT)** = `LB – CONSUMO`.

### Tributos mensais
- **PIS** = `0,0065 * LAT`  
- **COFINS** = `0,03 * LAT`  
- **ICMS** = `0,05 * FAT`

### IRPJ/CSLL (trimestrais com rateio mensal)
- Trimestres: **Jan–Mar**, **Abr–Jun**, **Jul–Set**, **Out–Dez**.  
- **Base_mês = 0,32 * LAT_mês** (regra específica para revenda de veículos, conforme solicitado).  
- **IRPJ do trimestre**  
  `IRPJ_tri = 0,15 * ΣBase_tri + max(0, 0,10 * (ΣBase_tri – 60000))`  
- **CSLL do trimestre**  
  `CSLL_tri = 0,09 * ΣBase_tri` (não há adicional).  
- **Rateio mensal** proporcional à `Base_mês` de cada mês do trimestre.
- **Lucro Líquido (LL)** = `LAT – (PIS + COFINS + ICMS) – IRPJ_rateado – CSLL_rateada`.

---

## 4) Simulação (meses restantes, incluindo mês vigente)
- Detectar o **último mês** presente na planilha:
  - Meses **≤ último** → **travados** com os valores reais.
  - Meses **> último** → **simulados**.
  - **Opcional**: simular o **mês vigente** substituindo o parcial por projeção.
- **Meta anual**: **LAT 2025** (antes de tributos).
  - `LAT_restante = LAT_meta_anual – LAT_realizado_YTD`.
  - Distribuição por padrão **uniforme** (opção **manual** com sliders % que somam 100%).
- Para cada **margem** `m ∈ {0,05, 0,10, 0,15, 0,20, 0,25, 0,30}`:
  - Por mês simulado:  
    `FAT = LAT/m` • `CMV = FAT – LAT` • calcular tributos mensais;  
    recomputar **IRPJ/CSLL do trimestre** (realizado + simulado) e **ratear**.

> **Compras necessárias** = `CMV` (não usamos estoque; assumimos giro integral no mês).

---

## 5) Telas do app
1. **Dashboard**: KPIs (Entradas/Compras, Saídas/FAT, CONSUMO, LAT, Tributos, LL), gráficos mensais.  
2. **Simulação**: meta LAT anual, margens, opção “simular mês vigente”, distribuição uniforme/manual, tabela mês a mês + totais, exportações.  
3. **Notas/Detalhes**: tabela filtrável e download do dataset filtrado.

---

## 6) Execução
### Local
```bash
python -m venv .venv && source .venv/bin/activate  # (Windows: .venv\Scripts\activate)
pip install -U streamlit pandas numpy plotly openpyxl
streamlit run app.py
.
├─ agents/
│  └─ planejador_streamlit.agent.md
├─ app.py
├─ calc.py
├─ tests/
│  └─ test_calc.py
├─ bootstrap.sh
└─ README.md
