import streamlit as st
import requests
import urllib3


from datetime import datetime, timedelta
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak
)

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

urllib3.disable_warnings()

# ==========================================
# CONFIG
# ==========================================

ZABBIX_URL = "https://noc-totens.videosoft.com.br/api_jsonrpc.php"

TOKEN = st.secrets["TOKEN"]

DIAS_ANALISE = 30

# ==========================================
# API ZABBIX
# ==========================================

def zabbix_api(method, params):

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "auth": TOKEN,
        "id": 1
    }

    response = requests.post(
        ZABBIX_URL,
        json=payload,
        verify=False
    )

    return response.json()

# ==========================================
# STREAMLIT
# ==========================================

st.set_page_config(
    page_title="Relatório Operacional Totem",
    layout="centered"
)



col1, col2 = st.columns([1, 5])

with col1:
    st.image("logo.png", width=90)

with col2:
    st.markdown("""
    # Relatório Operacional Totem

    <span style='color:gray'>
    Videosoft • Wow Service
    </span>
    """, unsafe_allow_html=True)

serial = st.text_input(
    "Número de Série do Totem"
)

# ==========================================
# BOTÃO
# ==========================================

if st.button("Gerar Relatório"):

    if not serial:

        st.warning(
            "Digite um número de série."
        )

    else:

        st.info(
            f"Consultando serial {serial}..."
        )

        # ======================================
        # HOST
        # ======================================

        host_data = zabbix_api(
            "host.get",
            {
                "output": [
                    "hostid",
                    "host"
                ],
                "search": {
                    "host": serial
                },
                "searchByAny": True
            }
        )

        # ======================================
        # VALIDAR HOST
        # ======================================

        if "result" not in host_data:

            st.error(host_data)

        elif not host_data["result"]:

            st.error(
                "Host não encontrado."
            )

        else:

            host_info = host_data["result"][0]

            hostid = host_info["hostid"]

            HOST_NAME = host_info["host"]

            st.success(
                f"Host encontrado: {HOST_NAME}"
            )

            # ======================================
            # ITEMS
            # ======================================

            items_data = zabbix_api(
                "item.get",
                {
                    "hostids": hostid,
                    "output": [
                        "name",
                        "lastvalue"
                    ],
                    "sortfield": "name"
                }
            )

            items = items_data["result"]

            # ======================================
            # CAMPOS
            # ======================================

            campos = {

                "Hostname": [
                    HOST_NAME
                ],

                "Modelo Processador": [
                    "CPU Model",
                    "model name",
                    "Processor"
                ],

                "Total Memória": [
                    "Total memory"
                ],

                "Modelo SSD": [
                    "Disk Model NVMe",
                    "Disk Model SATA",
                    "nvme",
                    "SSD"
                ],

                "Impressora": [
                    "Impressora conectada USB",
                    "Impressora USB"
                ],

                "Pinpad": [
                    "Pinpad conectado USB"
                ],

                "Touch": [
                    "Touch conectado USB"
                ],

                "Temperatura CPU": [
                    "temperatura da CPU"
                ],

                "Temperatura Core 0": [
                    "temperatura do Core 0"
                ],

                "Temperatura Core 1": [
                    "temperatura do Core 1"
                ]
            }

            # ======================================
            # INVENTÁRIO
            # ======================================

            resultado = {}

            resultado["Hostname"] = HOST_NAME

            for campo, palavras in campos.items():

                if campo == "Hostname":
                    continue

                resultado[campo] = "NULL"

                for palavra in palavras:

                    encontrado = False

                    for item in items:

                        nome_item = item["name"]
                        valor_item = item["lastvalue"]

                        if palavra.lower() in nome_item.lower():

                            # MEMÓRIA EM GB

                            if campo == "Total Memória":

                                try:

                                    gb = round(
                                        int(valor_item) / (1024**3),
                                        2
                                    )

                                    resultado[campo] = f"{gb} GB"

                                    encontrado = True

                                    break

                                except:
                                    continue

                            # IGNORAR VALORES RUINS

                            valor_invalido = (

                                valor_item.strip() == ""

                                or "arquivo ou diretório inexistente"
                                in valor_item.lower()

                                or "no such file"
                                in valor_item.lower()

                                or "cat:"
                                in valor_item.lower()
                            )

                            if valor_invalido:
                                continue

                            resultado[campo] = valor_item

                            encontrado = True

                            break

                    if encontrado:
                        break

            # ======================================
            # TEMPERATURA CPU
            # ======================================

            temperatura_cpu = 0

            try:

                temperatura_cpu = int(
                    str(resultado["Temperatura CPU"])
                    .replace("°C", "")
                    .strip()
                )

            except:
                temperatura_cpu = 0

            # ======================================
            # EVENTOS
            # ======================================

            agora = datetime.now()

            inicio = agora - timedelta(days=DIAS_ANALISE)

            time_from = int(inicio.timestamp())

            eventos_data = zabbix_api(
                "event.get",
                {
                    "output": "extend",
                    "hostids": hostid,
                    "source": 0,
                    "object": 0,
                    "sortfield": "clock",
                    "sortorder": "DESC",
                    "time_from": time_from,
                    "value": 1
                }
            )

            lista_eventos = []

            if "result" in eventos_data:

                for evento in eventos_data["result"]:

                    nome = evento["name"]

                    data_evento = datetime.fromtimestamp(
                        int(evento["clock"])
                    ).strftime("%d/%m/%Y %H:%M")

                    severidade = evento["severity"]

                    mapa_severidade = {
                        "0": "N0",
                        "1": "N1",
                        "2": "N2",
                        "3": "N3",
                        "4": "N4",
                        "5": "N5"
                    }

                    severidade_texto = mapa_severidade.get(
                        severidade,
                        severidade
                    )

                    lista_eventos.append([
                        data_evento,
                        nome,
                        severidade_texto
                    ])

            # ======================================
            # ANÁLISE
            # ======================================

            total_eventos = len(lista_eventos)

            reinicializacoes = 0
            usb_eventos = 0
            eventos_temperatura = 0
            eventos_disco = 0
            eventos_memoria = 0

            dias_reboot = {}

            for evento in lista_eventos:

                nome = evento[1].lower()

                # REBOOT

                if (
                    "reiniciado" in nome
                    or "uptime < 10m" in nome
                    or "boot" in nome
                ):

                    reinicializacoes += 1

                    data_reboot = evento[0].split(" ")[0]

                    if data_reboot not in dias_reboot:
                        dias_reboot[data_reboot] = 0

                    dias_reboot[data_reboot] += 1

                # USB

                if (
                    "usb" in nome
                    or "pinpad" in nome
                    or "impressora" in nome
                    or "touch" in nome
                ):

                    usb_eventos += 1

                # TEMPERATURA

                if (
                    "temperatura" in nome
                    or "80ºc" in nome
                    or "cpu está acima" in nome
                ):

                    eventos_temperatura += 1

                # DISCO

                if (
                    "solicitação de leitura" in nome
                    or "gravação >" in nome
                    or "nvme0n1" in nome
                    or "sda:" in nome
                    or "i/o" in nome
                ):

                    eventos_disco += 1

                # MEMÓRIA

                if (
                    "utilização de memoria" in nome
                    or "memoria ram > 90%" in nome
                    or "ram >" in nome
                ):

                    eventos_memoria += 1

            # ======================================
            # DIA COM MAIS REBOOTS
            # ======================================

            dia_mais_reboots = "N/A"

            maior_qtd = 0

            for dia, qtd in dias_reboot.items():

                if qtd > maior_qtd:

                    maior_qtd = qtd

                    dia_mais_reboots = dia

            # ======================================
            # CONCLUSÃO
            # ======================================

            conclusoes = []

            if total_eventos == 0:

                conclusoes.append(
                    "Não foram identificadas ocorrências operacionais durante o período analisado."
                )

            if reinicializacoes > 0:

                conclusoes.append(
                    f"Foram identificadas {reinicializacoes} possíveis reinicializações."
                )

                conclusoes.append(
                    f"O maior volume ocorreu em {dia_mais_reboots}, totalizando {maior_qtd} eventos."
                )

            if usb_eventos > 0:

                conclusoes.append(
                    f"Foram detectados {usb_eventos} eventos relacionados a dispositivos USB."
                )

            if eventos_disco > 0:

                conclusoes.append(
                    f"Foram encontrados {eventos_disco} eventos relacionados a lentidão de disco."
                )

                conclusoes.append(
                    "Recomenda-se validar integridade do SSD e possíveis impactos de performance."
                )

            if eventos_memoria > 0:

                conclusoes.append(
                    f"Foram encontrados {eventos_memoria} eventos de alto consumo de memória RAM."
                )

            if eventos_temperatura > 0:

                conclusoes.append(
                    f"Foram identificados {eventos_temperatura} eventos de temperatura elevada."
                )

            if temperatura_cpu >= 85:

                conclusoes.append(
                    "A temperatura atual da CPU encontra-se em estado crítico."
                )

            elif temperatura_cpu >= 70:

                conclusoes.append(
                    "A temperatura atual da CPU está acima da faixa recomendada."
                )

            elif temperatura_cpu > 0:

                conclusoes.append(
                    "As temperaturas permaneceram dentro da faixa operacional esperada."
                )

            if not conclusoes:

                conclusoes.append(
                    "Nenhuma anomalia operacional relevante foi identificada."
                )

            texto_conclusao = "<br/><br/>".join(
                conclusoes
            )

            # ======================================
            # PDF
            # ======================================

            buffer = BytesIO()

            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter
            )

            styles = getSampleStyleSheet()

            elementos = []

            # TÍTULO

            titulo = Paragraph(
                f"<b>Relatório Operacional Totem</b><br/>{HOST_NAME}",
                styles['Title']
            )

            elementos.append(titulo)

            elementos.append(
                Spacer(1, 30)
            )

            # RESUMO

            resumo_titulo = Paragraph(
                "<b>Resumo Executivo</b>",
                styles['Heading2']
            )

            elementos.append(resumo_titulo)

            elementos.append(
                Spacer(1, 15)
            )

            dados_resumo = [

                ["Indicador", "Valor"],

                ["Host", HOST_NAME],

                ["Período analisado",
                 f"{DIAS_ANALISE} dias"],

                ["Total de eventos",
                 str(total_eventos)],

                ["Eventos USB",
                 str(usb_eventos)],

                ["Eventos temperatura",
                 str(eventos_temperatura)],

                ["Eventos disco/IO",
                 str(eventos_disco)],

                ["Eventos memória",
                 str(eventos_memoria)],

                ["Possíveis reinicializações",
                 str(reinicializacoes)],

                ["Dia com mais reinicializações",
                 f"{dia_mais_reboots} ({maior_qtd})"]
            ]

            tabela_resumo = Table(
                dados_resumo,
                colWidths=[250, 250]
            )

            tabela_resumo.setStyle(TableStyle([

                ('BACKGROUND', (0,0), (-1,0), colors.grey),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('GRID', (0,0), (-1,-1), 1, colors.black),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('BACKGROUND', (0,1), (-1,-1), colors.beige),

            ]))

            elementos.append(tabela_resumo)

            elementos.append(
                Spacer(1, 30)
            )

            # INVENTÁRIO

            inventario_titulo = Paragraph(
                "<b>Inventário Técnico</b>",
                styles['Heading2']
            )

            elementos.append(inventario_titulo)

            elementos.append(
                Spacer(1, 15)
            )

            dados_inventario = [
                ["Campo", "Valor"]
            ]

            for chave, valor in resultado.items():

                dados_inventario.append([
                    chave,
                    str(valor)
                ])

            tabela_inventario = Table(
                dados_inventario,
                colWidths=[220, 300]
            )

            tabela_inventario.setStyle(TableStyle([

                ('BACKGROUND', (0,0), (-1,0), colors.grey),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('GRID', (0,0), (-1,-1), 1, colors.black),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('BACKGROUND', (0,1), (-1,-1), colors.beige),

            ]))

            elementos.append(tabela_inventario)

            elementos.append(PageBreak())

            # EVENTOS

            eventos_titulo = Paragraph(
                f"<b>Eventos dos Últimos {DIAS_ANALISE} Dias</b>",
                styles['Heading2']
            )

            elementos.append(eventos_titulo)

            elementos.append(
                Spacer(1, 15)
            )

            dados_eventos = [
                ["Data", "Evento", "Severidade"]
            ]

            if lista_eventos:

                for evento in lista_eventos[:40]:

                    dados_eventos.append([
                        evento[0],
                        evento[1][:70],
                        evento[2]
                    ])

            else:

                dados_eventos.append([
                    "-",
                    "Nenhum evento encontrado",
                    "-"
                ])

            tabela_eventos = Table(
                dados_eventos,
                colWidths=[110, 330, 80]
            )

            tabela_eventos.setStyle(TableStyle([

                ('BACKGROUND', (0,0), (-1,0), colors.grey),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('GRID', (0,0), (-1,-1), 1, colors.black),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('BACKGROUND', (0,1), (-1,-1), colors.beige),

            ]))

            elementos.append(tabela_eventos)

            elementos.append(
                Spacer(1, 30)
            )

            # CONCLUSÃO

            conclusao_titulo = Paragraph(
                "<b>Conclusão Técnica</b>",
                styles['Heading2']
            )

            elementos.append(conclusao_titulo)

            elementos.append(
                Spacer(1, 15)
            )

            conclusao = Paragraph(
                texto_conclusao,
                styles['BodyText']
            )

            elementos.append(conclusao)

            elementos.append(
                Spacer(1, 40)
            )

            # RODAPÉ

            rodape = Paragraph(
                "Relatório gerado automaticamente via API Zabbix.",
                styles['Italic']
            )

            elementos.append(rodape)

            # BUILD PDF

            doc.build(elementos)

            buffer.seek(0)

            # DOWNLOAD

            st.download_button(
                label="📥 Baixar Relatório PDF",
                data=buffer,
                file_name=f"{HOST_NAME}_relatorio.pdf",
                mime="application/pdf"
            )

