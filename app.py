import html
import re
from datetime import datetime, timedelta
from io import BytesIO

import requests
import streamlit as st
import urllib3

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

# ==========================================
# CONFIGURAÇÕES
# ==========================================

ZABBIX_URL = (
    "https://noc-totens.videosoft.com.br/"
    "api_jsonrpc.php"
)

TOKEN = st.secrets["TOKEN"]

# Valor inicial; será substituído pela opção escolhida na tela.
DIAS_ANALISE = 7

# Não exibir eventos N5 (Informação)
EXIBIR_N5 = False

# Eventos ignorados no relatório e na análise.
TERMOS_EVENTOS_IGNORADOS = (
    "reiniciado",
    "uptime < 10m",
    "boot",
    "active checks are not available",
    "verificações ativas não estão disponíveis",
    "sem comunicação por mais de 2 minutos",
)

# ==========================================
# API ZABBIX
# ==========================================

def zabbix_api(method, params, request_id=1):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "auth": TOKEN,
        "id": request_id,
    }

    response = requests.post(
        ZABBIX_URL,
        json=payload,
        verify=False,
        timeout=90,
    )

    response.raise_for_status()

    resposta = response.json()

    if "error" in resposta:
        raise RuntimeError(
            f"Erro na API do Zabbix em {method}: "
            f"{resposta['error']}"
        )

    return resposta.get("result", [])


# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================

def limpar_texto(valor):
    if valor is None:
        return ""

    return str(valor).strip()


def valor_hardware_valido(valor):
    texto = limpar_texto(valor)

    if not texto:
        return False

    valores_invalidos = {
        "0",
        "null",
        "none",
        "n/a",
        "na",
        "-",
        "desconhecido",
        "não encontrado",
        "not found",
    }

    if texto.lower() in valores_invalidos:
        return False

    mensagens_invalidas = (
        "arquivo ou diretório inexistente",
        "no such file",
        "cat:",
        "not supported",
        "unsupported item",
        "cannot open",
        "permission denied",
        "command not found",
    )

    texto_lower = texto.lower()

    return not any(
        mensagem in texto_lower
        for mensagem in mensagens_invalidas
    )


def dividir_linhas_inventario(inventario):
    registros = []

    for campo, valor in inventario.items():
        texto = limpar_texto(valor)

        if not texto:
            continue

        partes = re.split(
            r"[\r\n;|]+",
            texto,
        )

        for parte in partes:
            parte = parte.strip()

            if parte:
                registros.append(
                    {
                        "campo": campo,
                        "linha": parte,
                    }
                )

    return registros


def remover_rotulo(texto):
    texto = limpar_texto(texto)

    return re.sub(
        r"^\s*"
        r"(cpu|processador|processor|modelo da cpu|"
        r"modelo do processador|mem[oó]ria|memory|ram|"
        r"ssd|disco|disk|armazenamento|storage|nvme)"
        r"\s*[:=\-]\s*",
        "",
        texto,
        flags=re.IGNORECASE,
    ).strip()


def normalizar_memoria(valor):
    texto = limpar_texto(valor)

    if not valor_hardware_valido(texto):
        return "NULL"

    # Quando vier apenas um número grande, considera bytes.
    try:
        numero = float(
            texto.replace(",", ".")
        )

        if numero > 1_000_000:
            gb = numero / (1024 ** 3)
            return f"{round(gb, 2)} GB"

    except (ValueError, TypeError):
        pass

    correspondencia = re.search(
        r"(\d+(?:[.,]\d+)?)\s*"
        r"(kb|mb|gb|tb|kib|mib|gib|tib)",
        texto,
        flags=re.IGNORECASE,
    )

    if correspondencia:
        numero = (
            correspondencia.group(1)
            .replace(",", ".")
        )

        unidade = (
            correspondencia.group(2)
            .upper()
        )

        return f"{numero} {unidade}"

    return texto


def buscar_no_inventario(
    inventario,
    termos,
    campos_prioritarios=None,
    normalizador=None,
):
    registros = dividir_linhas_inventario(
        inventario
    )

    campos_prioritarios = (
        campos_prioritarios or []
    )

    def procurar(registros_filtrados):
        for registro in registros_filtrados:
            linha = registro["linha"]
            linha_lower = linha.lower()

            if not any(
                termo in linha_lower
                for termo in termos
            ):
                continue

            valor = remover_rotulo(
                linha
            )

            if not valor_hardware_valido(
                valor
            ):
                continue

            if normalizador:
                valor = normalizador(
                    valor
                )

            if valor != "NULL":
                return (
                    valor,
                    registro["campo"],
                )

        return "NULL", None

    if campos_prioritarios:
        prioritarios = [
            registro
            for registro in registros
            if registro["campo"]
            in campos_prioritarios
        ]

        valor, campo = procurar(
            prioritarios
        )

        if valor != "NULL":
            return valor, campo

    return procurar(registros)


def buscar_item_por_termos(
    items,
    termos,
    normalizador=None,
):
    for termo in termos:
        termo_lower = termo.lower()

        for item in items:
            nome_item = limpar_texto(
                item.get("name")
            )

            chave_item = limpar_texto(
                item.get("key_")
            )

            valor_item = limpar_texto(
                item.get("lastvalue")
            )

            encontrou = (
                termo_lower
                in nome_item.lower()
                or termo_lower
                in chave_item.lower()
            )

            if not encontrou:
                continue

            if not valor_hardware_valido(
                valor_item
            ):
                continue

            if normalizador:
                valor_item = normalizador(
                    valor_item
                )

            if valor_item != "NULL":
                return (
                    valor_item,
                    f"Item: {nome_item}",
                )

    return "NULL", "Não encontrado"


def buscar_hardware(
    inventario,
    items,
    termos_inventario,
    termos_itens,
    campos_prioritarios=None,
    normalizador=None,
):
    valor, campo = buscar_no_inventario(
        inventario=inventario,
        termos=termos_inventario,
        campos_prioritarios=campos_prioritarios,
        normalizador=normalizador,
    )

    if valor != "NULL":
        return (
            valor,
            "Inventário do host — "
            f"campo: {campo}",
        )

    return buscar_item_por_termos(
        items=items,
        termos=termos_itens,
        normalizador=normalizador,
    )


def montar_paragrafo(valor, estilo):
    texto = html.escape(
        str(valor)
    ).replace(
        "\n",
        "<br/>",
    )

    return Paragraph(
        texto,
        estilo,
    )


# ==========================================
# STREAMLIT
# ==========================================

st.set_page_config(
    page_title="Relatório Operacional Totem",
    layout="centered",
)

col1, col2 = st.columns(
    [1, 5]
)

with col1:
    st.image(
        "logo.png",
        width=90,
    )

with col2:
    st.markdown(
        """
        # Relatório Operacional Totem

        <span style="color:gray">
        Videosoft • Wow Service
        </span>
        """,
        unsafe_allow_html=True,
    )

serial = st.text_input(
    "Número de Série do Totem",
    placeholder="Exemplo: 19284",
)

DIAS_ANALISE = st.radio(
    "Período do relatório",
    options=[7, 15, 30, 90],
    index=0,
    horizontal=True,
    format_func=lambda dias: f"{dias} dias",
)

# ==========================================
# BOTÃO
# ==========================================

if st.button(
    "Gerar Relatório",
    type="primary",
):

    serial = serial.strip()

    if not serial:
        st.warning(
            "Digite um número de série."
        )

        st.stop()

    host_pesquisado = (
        serial
        if serial.upper().startswith("TOTEM")
        else f"TOTEM{serial}"
    )

    with st.spinner(
        f"Consultando {host_pesquisado}..."
    ):
        try:
            # ==================================
            # HOST + INVENTÁRIO
            # ==================================

            host_data = zabbix_api(
                "host.get",
                {
                    "filter": {
                        "host": [
                            host_pesquisado
                        ]
                    },
                    "output": [
                        "hostid",
                        "host",
                        "name",
                        "status",
                    ],
                    "selectInventory": "extend",
                },
                request_id=1,
            )

            if not host_data:
                st.error(
                    "Host não encontrado."
                )

                st.stop()

            host_info = host_data[0]

            hostid = host_info["hostid"]

            HOST_NAME = host_info["host"]

            # Segurança adicional:
            # mesmo usando filter exato, confirma que a API
            # devolveu exatamente o host solicitado.
            if HOST_NAME.upper() != host_pesquisado.upper():
                st.error(
                    "A API retornou um host diferente do solicitado. "
                    f"Solicitado: {host_pesquisado} | "
                    f"Retornado: {HOST_NAME}"
                )
                st.stop()

            nome_visivel = host_info.get(
                "name",
                HOST_NAME,
            )

            status_host_api = str(
                host_info.get("status", "1")
            )

            status_host_texto = (
                "Ativo"
                if status_host_api == "0"
                else "Desativado"
            )

            inventario_host = (
                host_info.get(
                    "inventory",
                    {},
                )
                or {}
            )

            st.success(
                f"Host encontrado: {HOST_NAME}"
            )

            # ==================================
            # ITENS
            # ==================================

            items = zabbix_api(
                "item.get",
                {
                    "hostids": hostid,
                    "output": [
                        "itemid",
                        "name",
                        "key_",
                        "lastvalue",
                    ],
                    "sortfield": "name",
                },
                request_id=2,
            )

            # ==================================
            # HARDWARE:
            # INVENTÁRIO PRIMEIRO,
            # ITEM COMO FALLBACK
            # ==================================

            processador, origem_processador = (
                buscar_hardware(
                    inventario=inventario_host,
                    items=items,
                    termos_inventario=[
                        "intel",
                        "amd",
                        "celeron",
                        "pentium",
                        "core i3",
                        "core i5",
                        "core i7",
                        "core i9",
                        "ryzen",
                        "athlon",
                        "atom",
                        "xeon",
                        "processor",
                        "processador",
                        "cpu model",
                        "modelo da cpu",
                        "modelo do processador",
                    ],
                    termos_itens=[
                        "CPU Model",
                        "model name",
                        "Processor Model",
                        "Processor",
                        "Nome do processador",
                        "Modelo do processador",
                    ],
                    campos_prioritarios=[
                        "hardware",
                        "hardware_full",
                        "model",
                        "type",
                        "type_full",
                        "notes",
                    ],
                )
            )

            memoria, origem_memoria = (
                buscar_hardware(
                    inventario=inventario_host,
                    items=items,
                    termos_inventario=[
                        "memória",
                        "memoria",
                        "memory",
                        "ram",
                        "total memory",
                        "memória total",
                        "memoria total",
                    ],
                    termos_itens=[
                        "Total memory",
                        "Memória total",
                        "Memoria total",
                        "Total de memória",
                        "Total de memoria",
                    ],
                    campos_prioritarios=[
                        "hardware",
                        "hardware_full",
                        "notes",
                    ],
                    normalizador=normalizar_memoria,
                )
            )

            modelo_ssd, origem_ssd = (
                buscar_hardware(
                    inventario=inventario_host,
                    items=items,
                    termos_inventario=[
                        "ssd",
                        "nvme",
                        "sata",
                        "m.2",
                        "kingston",
                        "sandisk",
                        "western digital",
                        "wd ",
                        "crucial",
                        "adata",
                        "samsung",
                        "hikvision",
                        "lexar",
                        "patriot",
                        "seagate",
                        "toshiba",
                        "kioxia",
                        "micron",
                        "sk hynix",
                    ],
                    termos_itens=[
                        "Disk Model NVMe",
                        "Disk Model SATA",
                        "NVMe Model",
                        "SSD Model",
                        "Modelo NVMe",
                        "Modelo SSD",
                        "Modelo do SSD",
                        "nvme model",
                        "sata model",
                    ],
                    campos_prioritarios=[
                        "hardware",
                        "hardware_full",
                        "model",
                        "type",
                        "type_full",
                        "notes",
                    ],
                )
            )

            # ==================================
            # DEMAIS ITENS
            # ==================================

            impressora, _ = (
                buscar_item_por_termos(
                    items,
                    [
                        "Impressora conectada USB",
                        "Impressora USB",
                    ],
                )
            )

            pinpad, _ = (
                buscar_item_por_termos(
                    items,
                    [
                        "Pinpad conectado USB",
                        "Pinpad USB",
                    ],
                )
            )

            touch, _ = (
                buscar_item_por_termos(
                    items,
                    [
                        "Touch conectado USB",
                        "Touch USB",
                    ],
                )
            )

            temperatura_cpu_texto, _ = (
                buscar_item_por_termos(
                    items,
                    [
                        "temperatura da CPU",
                        "CPU temperature",
                    ],
                )
            )

            temperatura_core0, _ = (
                buscar_item_por_termos(
                    items,
                    [
                        "temperatura do Core 0",
                        "Core 0 temperature",
                    ],
                )
            )

            temperatura_core1, _ = (
                buscar_item_por_termos(
                    items,
                    [
                        "temperatura do Core 1",
                        "Core 1 temperature",
                    ],
                )
            )

            resultado = {
                "Hostname": HOST_NAME,
                "Modelo Processador": processador,
                "Total Memória": memoria,
                "Modelo SSD": modelo_ssd,
                "Impressora": impressora,
                "Pinpad": pinpad,
                "Touch": touch,
                "Temperatura CPU": temperatura_cpu_texto,
                "Temperatura Core 0": temperatura_core0,
                "Temperatura Core 1": temperatura_core1,
            }

            # ==================================
            # QUALIDADE DO INVENTÁRIO
            # ==================================

            campos_avaliados = {
                "Processador": processador,
                "Memória": memoria,
                "SSD": modelo_ssd,
                "Impressora": impressora,
                "Pinpad": pinpad,
                "Touch": touch,
            }

            campos_encontrados = sum(
                1
                for valor in campos_avaliados.values()
                if valor_hardware_valido(valor)
            )

            total_campos_avaliados = len(
                campos_avaliados
            )

            percentual_inventario = round(
                (
                    campos_encontrados
                    / total_campos_avaliados
                ) * 100
            )

            if percentual_inventario == 100:
                qualidade_inventario = "Completo"
                icone_inventario = "🟢"

            elif percentual_inventario >= 50:
                qualidade_inventario = "Parcial"
                icone_inventario = "🟡"

            else:
                qualidade_inventario = "Incompleto"
                icone_inventario = "🔴"

            # Mostra uma prévia no Streamlit.
            st.subheader(
                "Totem consultado"
            )

            coluna_host, coluna_nome, coluna_status = st.columns(
                [1, 2, 1]
            )

            coluna_host.metric(
                "Host",
                HOST_NAME,
            )

            coluna_nome.metric(
                "Nome visível",
                nome_visivel,
            )

            coluna_status.metric(
                "Cadastro no Zabbix",
                status_host_texto,
            )

            st.caption(
                "Consulta feita por correspondência exata do nome técnico "
                f"do host: {host_pesquisado}."
            )

            st.subheader(
                "Inventário localizado"
            )

            st.dataframe(
                {
                    "Campo": list(
                        resultado.keys()
                    ),
                    "Valor": list(
                        resultado.values()
                    ),
                },
                use_container_width=True,
                hide_index=True,
            )

            st.markdown(
                f"### {icone_inventario} Status do inventário"
            )

            st.progress(
                percentual_inventario / 100
            )

            st.write(
                f"**{qualidade_inventario} "
                f"({percentual_inventario}%)** — "
                f"{campos_encontrados} de "
                f"{total_campos_avaliados} campos encontrados."
            )

            for nome_campo, valor_campo in campos_avaliados.items():
                if valor_hardware_valido(valor_campo):
                    st.write(
                        f"✅ {nome_campo}"
                    )
                else:
                    st.write(
                        f"❌ {nome_campo}"
                    )

            with st.expander(
                "Ver origem dos dados de hardware"
            ):
                st.write(
                    f"**Processador:** "
                    f"{origem_processador}"
                )

                st.write(
                    f"**Memória:** "
                    f"{origem_memoria}"
                )

                st.write(
                    f"**SSD:** "
                    f"{origem_ssd}"
                )

            # ==================================
            # TEMPERATURA CPU
            # ==================================

            temperatura_cpu = 0

            try:
                temperatura_cpu = int(
                    float(
                        str(
                            resultado[
                                "Temperatura CPU"
                            ]
                        )
                        .replace("°C", "")
                        .replace("ºC", "")
                        .replace(",", ".")
                        .strip()
                    )
                )

            except (
                ValueError,
                TypeError,
            ):
                temperatura_cpu = 0

            # ==================================
            # EVENTOS
            # ==================================

            agora = datetime.now()

            inicio = agora - timedelta(
                days=DIAS_ANALISE
            )

            time_from = int(
                inicio.timestamp()
            )

            eventos = zabbix_api(
                "event.get",
                {
                    "output": "extend",
                    "hostids": hostid,
                    "source": 0,
                    "object": 0,
                    "sortfield": "clock",
                    "sortorder": "DESC",
                    "time_from": time_from,
                    "value": 1,
                },
                request_id=3,
            )

            # Busca as triggers em lote.
            trigger_ids = list(
                {
                    evento["objectid"]
                    for evento in eventos
                    if evento.get(
                        "objectid"
                    )
                }
            )

            triggers_por_id = {}

            if trigger_ids:
                triggers = zabbix_api(
                    "trigger.get",
                    {
                        "triggerids": (
                            trigger_ids
                        ),
                        "output": [
                            "triggerid",
                            "priority",
                        ],
                    },
                    request_id=4,
                )

                triggers_por_id = {
                    trigger["triggerid"]:
                    trigger
                    for trigger
                    in triggers
                }

            mapa_severidade = {
                "0": "Não classificada",
                "1": "N5",
                "2": "N4",
                "3": "N3",
                "4": "N2",
                "5": "N1",
            }

            lista_eventos = []

            for evento in eventos:
                nome = evento.get(
                    "name",
                    "Evento sem nome",
                )

                nome_normalizado = (
                    nome.lower()
                )

                if any(
                    termo
                    in nome_normalizado
                    for termo
                    in TERMOS_EVENTOS_IGNORADOS
                ):
                    continue

                trigger_id = evento.get(
                    "objectid"
                )

                trigger = (
                    triggers_por_id.get(
                        trigger_id
                    )
                )

                if not trigger:
                    continue

                prioridade_atual = str(
                    trigger.get(
                        "priority",
                        "0",
                    )
                )

                if (
                    not EXIBIR_N5
                    and prioridade_atual == "1"
                ):
                    continue

                data_evento = (
                    datetime.fromtimestamp(
                        int(
                            evento["clock"]
                        )
                    )
                    .strftime(
                        "%d/%m/%Y %H:%M"
                    )
                )

                severidade_historica = str(
                    evento.get(
                        "severity",
                        "0",
                    )
                )

                severidade_texto = (
                    mapa_severidade.get(
                        severidade_historica,
                        "N/A",
                    )
                )

                lista_eventos.append(
                    [
                        data_evento,
                        nome,
                        severidade_texto,
                    ]
                )

            # ==================================
            # ANÁLISE
            # ==================================

            total_eventos = len(
                lista_eventos
            )

            usb_eventos = 0
            eventos_temperatura = 0
            eventos_disco = 0
            eventos_memoria = 0

            for evento in lista_eventos:
                nome = evento[1].lower()

                if (
                    "usb" in nome
                    or "pinpad" in nome
                    or "impressora" in nome
                    or "touch" in nome
                ):
                    usb_eventos += 1

                if (
                    "temperatura" in nome
                    or "80ºc" in nome
                    or "80°c" in nome
                    or "cpu está acima"
                    in nome
                ):
                    eventos_temperatura += 1

                if (
                    "disco são muito altas"
                    in nome
                    or "solicitação de leitura"
                    in nome
                    or "gravação >" in nome
                    or "disk read" in nome
                    or "disk write" in nome
                    or "nvme0n1" in nome
                    or "sda:" in nome
                    or "i/o" in nome
                ):
                    eventos_disco += 1

                if (
                    "utilização de memoria"
                    in nome
                    or "utilização de memória"
                    in nome
                    or "memoria ram > 90%"
                    in nome
                    or "memória ram > 90%"
                    in nome
                    or "memory >" in nome
                    or "ram >" in nome
                ):
                    eventos_memoria += 1

            # ==================================
            # CONCLUSÃO
            # ==================================

            conclusoes = []

            if total_eventos == 0:
                conclusoes.append(
                    "Não foram identificadas "
                    "ocorrências operacionais "
                    "durante o período analisado."
                )

            if usb_eventos > 0:
                conclusoes.append(
                    f"Foram detectados "
                    f"{usb_eventos} eventos "
                    f"relacionados a "
                    f"dispositivos USB."
                )

            if eventos_disco > 0:
                conclusoes.append(
                    f"Foram encontrados "
                    f"{eventos_disco} eventos "
                    f"relacionados a lentidão "
                    f"ou alta latência de disco."
                )

                conclusoes.append(
                    "Recomenda-se validar a "
                    "integridade do SSD e "
                    "possíveis impactos de "
                    "performance."
                )

            if eventos_memoria > 0:
                conclusoes.append(
                    f"Foram encontrados "
                    f"{eventos_memoria} eventos "
                    f"de alto consumo de "
                    f"memória RAM."
                )

            if eventos_temperatura > 0:
                conclusoes.append(
                    f"Foram identificados "
                    f"{eventos_temperatura} "
                    f"eventos de temperatura "
                    f"elevada."
                )

            if temperatura_cpu >= 85:
                conclusoes.append(
                    "A temperatura atual da CPU "
                    "encontra-se em estado "
                    "crítico."
                )

            elif temperatura_cpu >= 70:
                conclusoes.append(
                    "A temperatura atual da CPU "
                    "está acima da faixa "
                    "recomendada."
                )

            elif temperatura_cpu > 0:
                conclusoes.append(
                    "As temperaturas permaneceram "
                    "dentro da faixa operacional "
                    "esperada."
                )

            if not conclusoes:
                conclusoes.append(
                    "Nenhuma anomalia operacional "
                    "relevante foi identificada."
                )

            texto_conclusao = (
                "<br/><br/>".join(
                    conclusoes
                )
            )

            # ==================================
            # DIAGNÓSTICO OPERACIONAL
            # ==================================

            eventos_n1_n2 = sum(
                1
                for evento in lista_eventos
                if evento[2] in ("N1", "N2")
            )

            if (
                temperatura_cpu >= 85
                or eventos_n1_n2 > 0
                or eventos_disco >= 10
            ):
                status_operacional = "CRÍTICO"
                icone_operacional = "🔴"
                texto_operacional = (
                    "O equipamento apresenta ocorrências "
                    "que exigem atenção imediata."
                )

            elif (
                total_eventos > 0
                or temperatura_cpu >= 70
                or percentual_inventario < 100
            ):
                status_operacional = "ATENÇÃO"
                icone_operacional = "🟡"
                texto_operacional = (
                    "Foram encontrados pontos que merecem "
                    "acompanhamento ou validação."
                )

            else:
                status_operacional = "SAUDÁVEL"
                icone_operacional = "🟢"
                texto_operacional = (
                    "Nenhuma anomalia operacional relevante "
                    "foi identificada."
                )

            st.divider()

            st.subheader(
                "Diagnóstico rápido"
            )

            col_status, col_eventos, col_temperatura = st.columns(
                3
            )

            col_status.metric(
                "Status operacional",
                f"{icone_operacional} {status_operacional}",
            )

            col_eventos.metric(
                f"Eventos em {DIAS_ANALISE} dias",
                total_eventos,
            )

            temperatura_exibicao = (
                f"{temperatura_cpu} °C"
                if temperatura_cpu > 0
                else "Sem dado"
            )

            col_temperatura.metric(
                "Temperatura CPU",
                temperatura_exibicao,
            )

            st.info(
                texto_operacional
            )

            if eventos_n1_n2 > 0:
                st.write(
                    f"⚠️ Eventos N1/N2 encontrados: "
                    f"{eventos_n1_n2}"
                )

            if eventos_disco > 0:
                st.write(
                    f"💾 Eventos de disco/IO: "
                    f"{eventos_disco}"
                )

            if eventos_memoria > 0:
                st.write(
                    f"🧠 Eventos de memória: "
                    f"{eventos_memoria}"
                )

            if eventos_temperatura > 0:
                st.write(
                    f"🌡️ Eventos de temperatura: "
                    f"{eventos_temperatura}"
                )

            if usb_eventos > 0:
                st.write(
                    f"🔌 Eventos de USB/periféricos: "
                    f"{usb_eventos}"
                )

            # ==================================
            # PDF
            # ==================================

            buffer = BytesIO()

            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=35,
                leftMargin=35,
                topMargin=35,
                bottomMargin=35,
            )

            styles = (
                getSampleStyleSheet()
            )

            elementos = []

            titulo = Paragraph(
                "<b>Relatório Operacional "
                "Totem</b>"
                f"<br/>{HOST_NAME}",
                styles["Title"],
            )

            elementos.extend(
                [
                    titulo,
                    Spacer(1, 30),
                ]
            )

            # RESUMO

            elementos.append(
                Paragraph(
                    "<b>Resumo Executivo</b>",
                    styles["Heading2"],
                )
            )

            elementos.append(
                Spacer(1, 15)
            )

            dados_resumo = [
                ["Indicador", "Valor"],
                ["Host", HOST_NAME],
                [
                    "Nome visível",
                    nome_visivel,
                ],
                [
                    "Período analisado",
                    f"{DIAS_ANALISE} dias",
                ],
                [
                    "Status operacional",
                    status_operacional,
                ],
                [
                    "Qualidade do inventário",
                    (
                        f"{qualidade_inventario} "
                        f"({percentual_inventario}%)"
                    ),
                ],
                [
                    "Total de eventos",
                    str(total_eventos),
                ],
                [
                    "Eventos USB",
                    str(usb_eventos),
                ],
                [
                    "Eventos temperatura",
                    str(
                        eventos_temperatura
                    ),
                ],
                [
                    "Eventos disco/IO",
                    str(eventos_disco),
                ],
                [
                    "Eventos memória",
                    str(eventos_memoria),
                ],
            ]

            tabela_resumo = Table(
                dados_resumo,
                colWidths=[240, 260],
                repeatRows=1,
            )

            tabela_resumo.setStyle(
                TableStyle(
                    [
                        (
                            "BACKGROUND",
                            (0, 0),
                            (-1, 0),
                            colors.grey,
                        ),
                        (
                            "TEXTCOLOR",
                            (0, 0),
                            (-1, 0),
                            colors.whitesmoke,
                        ),
                        (
                            "GRID",
                            (0, 0),
                            (-1, -1),
                            1,
                            colors.black,
                        ),
                        (
                            "FONTNAME",
                            (0, 0),
                            (-1, 0),
                            "Helvetica-Bold",
                        ),
                        (
                            "BACKGROUND",
                            (0, 1),
                            (-1, -1),
                            colors.beige,
                        ),
                        (
                            "VALIGN",
                            (0, 0),
                            (-1, -1),
                            "TOP",
                        ),
                    ]
                )
            )

            elementos.extend(
                [
                    tabela_resumo,
                    Spacer(1, 30),
                ]
            )

            # INVENTÁRIO

            elementos.append(
                Paragraph(
                    "<b>Inventário Técnico</b>",
                    styles["Heading2"],
                )
            )

            elementos.append(
                Spacer(1, 15)
            )

            dados_inventario = [
                [
                    Paragraph(
                        "<b>Campo</b>",
                        styles["BodyText"],
                    ),
                    Paragraph(
                        "<b>Valor</b>",
                        styles["BodyText"],
                    ),
                ]
            ]

            for chave, valor in (
                resultado.items()
            ):
                dados_inventario.append(
                    [
                        montar_paragrafo(
                            chave,
                            styles[
                                "BodyText"
                            ],
                        ),
                        montar_paragrafo(
                            valor,
                            styles[
                                "BodyText"
                            ],
                        ),
                    ]
                )

            tabela_inventario = Table(
                dados_inventario,
                colWidths=[205, 315],
                repeatRows=1,
            )

            tabela_inventario.setStyle(
                TableStyle(
                    [
                        (
                            "BACKGROUND",
                            (0, 0),
                            (-1, 0),
                            colors.grey,
                        ),
                        (
                            "TEXTCOLOR",
                            (0, 0),
                            (-1, 0),
                            colors.whitesmoke,
                        ),
                        (
                            "GRID",
                            (0, 0),
                            (-1, -1),
                            1,
                            colors.black,
                        ),
                        (
                            "FONTNAME",
                            (0, 0),
                            (-1, 0),
                            "Helvetica-Bold",
                        ),
                        (
                            "BACKGROUND",
                            (0, 1),
                            (-1, -1),
                            colors.beige,
                        ),
                        (
                            "VALIGN",
                            (0, 0),
                            (-1, -1),
                            "TOP",
                        ),
                        (
                            "LEFTPADDING",
                            (0, 0),
                            (-1, -1),
                            7,
                        ),
                        (
                            "RIGHTPADDING",
                            (0, 0),
                            (-1, -1),
                            7,
                        ),
                    ]
                )
            )

            elementos.extend(
                [
                    tabela_inventario,
                    PageBreak(),
                ]
            )

            # EVENTOS

            elementos.append(
                Paragraph(
                    f"<b>Eventos dos Últimos "
                    f"{DIAS_ANALISE} Dias</b>",
                    styles["Heading2"],
                )
            )

            elementos.append(
                Spacer(1, 15)
            )

            dados_eventos = [
                [
                    Paragraph(
                        "<b>Data</b>",
                        styles["BodyText"],
                    ),
                    Paragraph(
                        "<b>Evento</b>",
                        styles["BodyText"],
                    ),
                    Paragraph(
                        "<b>Severidade</b>",
                        styles["BodyText"],
                    ),
                ]
            ]

            if lista_eventos:
                for evento in (
                    lista_eventos[:40]
                ):
                    dados_eventos.append(
                        [
                            montar_paragrafo(
                                evento[0],
                                styles[
                                    "BodyText"
                                ],
                            ),
                            montar_paragrafo(
                                evento[1],
                                styles[
                                    "BodyText"
                                ],
                            ),
                            montar_paragrafo(
                                evento[2],
                                styles[
                                    "BodyText"
                                ],
                            ),
                        ]
                    )

            else:
                dados_eventos.append(
                    [
                        "-",
                        (
                            "Nenhum evento "
                            "encontrado"
                        ),
                        "-",
                    ]
                )

            tabela_eventos = Table(
                dados_eventos,
                colWidths=[105, 330, 85],
                repeatRows=1,
            )

            tabela_eventos.setStyle(
                TableStyle(
                    [
                        (
                            "BACKGROUND",
                            (0, 0),
                            (-1, 0),
                            colors.grey,
                        ),
                        (
                            "TEXTCOLOR",
                            (0, 0),
                            (-1, 0),
                            colors.whitesmoke,
                        ),
                        (
                            "GRID",
                            (0, 0),
                            (-1, -1),
                            1,
                            colors.black,
                        ),
                        (
                            "FONTNAME",
                            (0, 0),
                            (-1, 0),
                            "Helvetica-Bold",
                        ),
                        (
                            "BACKGROUND",
                            (0, 1),
                            (-1, -1),
                            colors.beige,
                        ),
                        (
                            "VALIGN",
                            (0, 0),
                            (-1, -1),
                            "TOP",
                        ),
                    ]
                )
            )

            elementos.extend(
                [
                    tabela_eventos,
                    Spacer(1, 30),
                ]
            )

            # CONCLUSÃO

            elementos.append(
                Paragraph(
                    "<b>Conclusão Técnica</b>",
                    styles["Heading2"],
                )
            )

            elementos.append(
                Spacer(1, 15)
            )

            elementos.append(
                Paragraph(
                    texto_conclusao,
                    styles["BodyText"],
                )
            )

            elementos.append(
                Spacer(1, 40)
            )

            elementos.append(
                Paragraph(
                    "Relatório gerado "
                    "automaticamente via "
                    "API Zabbix.",
                    styles["Italic"],
                )
            )

            doc.build(
                elementos
            )

            buffer.seek(0)

            st.download_button(
                label=(
                    "📥 Baixar Relatório PDF"
                ),
                data=buffer.getvalue(),
                file_name=(
                    f"{HOST_NAME}_"
                    "relatorio.pdf"
                ),
                mime="application/pdf",
            )

        except requests.RequestException as erro:
            st.error(
                "Falha de comunicação com "
                f"o Zabbix: {erro}"
            )

        except RuntimeError as erro:
            st.error(
                str(erro)
            )

        except Exception as erro:
            st.exception(
                erro
            )