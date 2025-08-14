# Simulação de Faturamento 2025 — Revenda de Veículos (Streamlit)

App Streamlit para apurar resultados de 2025 a partir da planilha de notas e simular os meses restantes a partir do mês vigente.

## Principais regras

- **FAT** = soma de notas com `Tipo Nota = Saída`.
- **COMPRAS** = soma de notas com `Tipo Nota = Entrada` e `Classificação = MERCADORIA PARA REVENDA`, descontando notas com `Natureza Operação` contendo `DEVOLUCAO DE COMPRA`.
- **LAT** = `FAT - COMPRAS`.
- Tributos mensais: `PIS = 0,0065 * LAT`; `COFINS = 0,03 * LAT`; `ICMS = 0,05 * FAT`.
- **IRPJ/CSLL trimestrais**: Base = `0,32 * LAT_mês`.
  `IRPJ = 0,15 * ΣBase + max(0, 0,10 * (ΣBase - 60000))`.
  `CSLL = 0,09 * ΣBase`.
  Valores lançados apenas em **Mar/Jun/Set/Dez**.

## Simulação

- Meses anteriores ao mês vigente são travados com os valores reais.
- Opcionalmente é possível editar o mês vigente (adicionando ao parcial). Meses futuros são totalmente simulados.
- Ao informar o LAT de um mês, o app calcula automaticamente FAT, Compras e ICMS para margens de 5% a 30%. PIS/COFINS sempre usam o LAT do mês.
- Exportações disponíveis: resumo do mês (CSV) e consolidado anual (XLSX).

## Execução

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Testes

```bash
pytest
```

## Changelog

- Remoção de parâmetros GitHub e de campos de PIS/COFINS na UI.
- Simulação focada do mês vigente em diante com PIS/COFINS fixos sobre o LAT.
- Funções puras de parsing, cenários e IRPJ/CSLL em `calc.py`.
- Tema acessível e helpers de formatação em `ui_helpers.py`.
