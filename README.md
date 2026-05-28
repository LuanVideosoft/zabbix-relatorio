# zabbix-relatorio# 📊 Relatório Operacional Totem

Sistema web para geração automática de relatórios operacionais de totens via API do Zabbix.

O sistema consulta hosts automaticamente através do número de série do totem e gera um relatório técnico em PDF contendo:

- Inventário técnico
- Eventos operacionais
- Possíveis reinicializações
- Eventos de temperatura
- Eventos de memória
- Eventos de disco/IO
- Dispositivos USB conectados
- Conclusão técnica automática

---

# 🚀 Tecnologias Utilizadas

- Python
- Streamlit
- Zabbix API
- ReportLab
- Requests

---

# 🖥️ Interface

O sistema possui interface web simples para equipe de suporte:

- Digitar serial do totem
- Gerar relatório
- Baixar PDF automaticamente

---

# 📄 Funcionalidades

## ✅ Consulta automática via API Zabbix

Busca automática do host utilizando o serial do totem.

Exemplo:
```text
11904
→ TOTEM11904
```

---

## ✅ Geração automática de PDF

O sistema gera um relatório operacional contendo:

- Resumo executivo
- Inventário técnico
- Eventos dos últimos 30 dias
- Conclusão operacional automática

---

## ✅ Análise inteligente de eventos

O sistema identifica automaticamente:

- Reinicializações
- Temperatura elevada
- Alto consumo de memória RAM
- Lentidão de disco/IO
- Problemas USB

---

# ☁️ Deploy

Projeto hospedado utilizando:

- GitHub
- Streamlit Cloud

---

# 🔐 Segurança

O token da API do Zabbix NÃO fica salvo diretamente no código.

A autenticação é realizada via:

```python
st.secrets["TOKEN"]
```

Configurado no Streamlit Cloud em:

```text
Settings → Secrets
```

---

# ⚙️ Instalação Local

## Clonar repositório

```bash
git clone https://github.com/LuanVideosoft/zabbix-relatorio.git
```

---

## Instalar dependências

```bash
pip install -r requirements.txt
```

---

## Executar aplicação

```bash
streamlit run app.py
```

---

# 🔑 Configuração

Adicionar o token do Zabbix no Streamlit Secrets:

```toml
TOKEN="SEU_TOKEN"
```

---

# 📁 Estrutura do Projeto

```text
├── app.py
├── requirements.txt
├── logo.png
└── README.md
```

---

# 📌 Observações

- O projeto NÃO salva PDFs no GitHub.
- Os relatórios são gerados dinamicamente em memória.
- O download é realizado diretamente pelo navegador.

---

# 👨‍💻 Autor

Luan Santos  
Assistente de TI | Engenharia da Computação  
Videosoft

---

# 📈 Futuras Melhorias

- Login corporativo
- Dashboard operacional
- Gráficos de eventos
- Histórico de relatórios
- Exportação CSV
- Integração com IA
- Multi-host report
- Cache de consultas

---
