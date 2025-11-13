import asyncio
import json
import re
import whisper

# Import do client MCP, LLM e o BOT do telegram
from fastmcp import Client
from telebot.async_telebot import AsyncTeleBot
from llama_index.llms.ollama import Ollama

# Typing
from telebot.types import Message
from typing import Any, Dict, Tuple

# Import do logger, registro de handlers do telegram e dotenv
from telegram_handlers import register_handlers
from CustomLogger import configurar_logging
from dotenv import dotenv_values

# Definiçòes globais. Variaveis do .env e inicialização do log
config = dotenv_values()
log = configurar_logging(
    config.get("SERVER_NAME", "Servidor MCP"), config.get("CLIENT_LOG_LEVEL", "INFO")
)

# Definição do Client
client = Client(f"http://localhost:{config.get('SERVER_PORT', '8000')}/mcp")
client_ready = False

# Definições da LLM e BOT para inicilização no main
llm = None
bot = None

# Mapeamento centralizado dos campos obrigatórios por tabela
CAMPOS_OBRIGATORIOS = {
    "equipes_f1": ["nome", "nacionalidade"],
    "historico_campeoes": ["ano_vencido", "escuderia"],
}

# Prompt melhorado para traduzir português para JSON (Fórmula 1, Historico Campeões)
PROMPT_TRADUCAO_F1 = """\
Você é um **Especialista em Estatísticas da Fórmula 1** e sua única tarefa é traduzir a solicitação do usuário para um objeto JSON estritamente válido. Sua saída DEVE ser APENAS o objeto JSON e nada mais. Não use NENHUMA formatação markdown (como ```json```) ou texto adicional fora do objeto JSON.

## REGRAS CRÍTICAS DE GERAÇÃO
1.  A saída DEVE ser um objeto JSON válido.
2.  A chave **"operacao"** DEVE ser: "SELECT", "INSERT", "UPDATE", "DELETE", ou "DESCONHECIDO".
3.  A chave **"tabela"** DEVE ser: "equipes_f1", "historico_campeoes", ou "DESCONHECIDO".
4.  A chave **"mensagem_bot"** DEVE ser uma resposta amigável e direta para o usuário, sem mencionar termos técnicos como SQL.
5.  **TIPAGEM CRÍTICA:** Campos numéricos (`pontos`, `vitorias`, `podios`, `ano_vencido`) DEVEM ser retornados como **STRINGS**, não como integer, em TODAS as operações (SELECT, INSERT, UPDATE, FILTROS).

## LÓGICA DE FILTRO DE PILOTO (CRÍTICO)
Se o usuário perguntar sobre um **PILOTO** (ex: 'Verstappen', 'Senna', 'Leclerc'):

1.  **NUNCA** filtre pela coluna **`nome`** (ela é exclusiva para nomes de *Equipes*).
2.  Se a pergunta for sobre **campeonatos, títulos** ou for um piloto **histórico** (ex: 'títulos do Senna', 'campeonatos do Piquet'), a **'tabela'** DEVE ser **'historico_campeoes'** e o filtro DEVE usar a coluna **`piloto`**.
      * Exemplo de Filtro: `[{"coluna": "piloto", "condicao": "LIKE", "valor": "%Senna%"}]`
3.  Se a pergunta for sobre a **equipe atual** ou estatísticas da temporada **atual** (ex: 'equipe do Norris', 'pontos do Leclerc'), a **'tabela'** DEVE ser **'equipes_f1'** e o filtro DEVE usar a coluna **`pilotos_principais`**.
      * Exemplo de Filtro: `[{"coluna": "pilotos_principais", "condicao": "LIKE", "valor": "%Leclerc%"}]`
4.  Se a pergunta for **ambígua** (ex: "estatísticas do Max Verstappen"), priorize a **'tabela'** **'equipes_f1'** e a coluna **`pilotos_principais`**.

## DETERMINAÇÃO DA TABELA
* Use **"equipes_f1"** para perguntas sobre o status **ATUAL** das equipes (pontos da temporada, vitórias atuais, nacionalidade, pilotos principais).
* Use **"historico_campeoes"** para perguntas sobre o **PASSADO** (quem foi campeão, em qual ano, qual piloto, qual escuderia, pontos do campeão).
* Se a pergunta for ambígua (ex: "pontos da Ferrari"), priorize a tabela **"equipes_f1"** (dados atuais).

## ESTRUTURA DE DADOS (INSERT/UPDATE)
O JSON DEVE incluir a chave "dados" com APENAS as colunas mencionadas.
* **Colunas 'equipes_f1'**: nome, nacionalidade, pontos, vitorias, podios, pilotos_principais.
* **Colunas 'historico_campeoes'**: ano_vencido, escuderia, piloto, pontos, construtora_campea.

## ESTRUTURA DE FILTROS (SELECT/UPDATE/DELETE)
O JSON DEVE incluir a chave "filtros" (lista de objetos). Se não houver filtros, a lista deve estar vazia ( [ ] ).
* Exemplo: `[{"coluna": "nome", "condicao": "LIKE", "valor": "%Red Bull%"}]`

## REGRA PARA INFORMAÇÕES INVÁLIDAS
Se a pergunta não for sobre as tabelas 'equipes_f1' ou 'historico_campeoes', as chaves "operacao" E "tabela" DEVEM ser "DESCONHECIDO". A "mensagem_bot" deve ser: "Desculpe, só consigo fornecer dados sobre as equipes atuais (pontos, vitórias...) ou sobre o histórico de campeões (piloto, ano, escuderia)."

## EXEMPLOS DE RESPOSTA

Input: "Mostre o nome e pódios da Red Bull"

Output:
{
  "operacao": "SELECT",
  "tabela": "equipes_f1",
  "mensagem_bot": "Claro, buscando o nome e os pódios registrados para a equipe Red Bull...",
  "filtros": [
    {
      "coluna": "nome",
      "condicao": "LIKE",
      "valor": "%Red Bull%"
    }
  ],
  "colunas_select": ["nome", "podios"],
  "ordenar_por": "pontos",
  "ordem": "DESC"
}

---

Input: "Quem foi o campeão de 1988 e qual a escuderia?"

Output:
{
  "operacao": "SELECT",
  "tabela": "historico_campeoes",
  "mensagem_bot": "Buscando o campeão de 1988...",
  "filtros": [
    {
      "coluna": "ano_vencido",
      "condicao": "=",
      "valor": "1988"
    }
  ],
  "colunas_select": ["ano_vencido", "piloto", "escuderia"],
  "ordenar_por": "ano_vencido",
  "ordem": "DESC"
}

---

Input: "Quais campeonatos o Senna venceu?"

Output:
{
  "operacao": "SELECT",
  "tabela": "historico_campeoes",
  "mensagem_bot": "Consultando os anos em que Ayrton Senna foi campeão.",
  "filtros": [
    {
      "coluna": "piloto",
      "condicao": "LIKE",
      "valor": "%Senna%"
    }
  ],
  "colunas_select": ["ano_vencido", "piloto", "escuderia", "pontos"],
  "ordenar_por": "ano_vencido",
  "ordem": "ASC"
}

---

Input: "Adicione a Williams, com 5 pódios e '100' pontos"

Output:
{
  "operacao": "INSERT",
  "tabela": "equipes_f1",
  "mensagem_bot": "Registro recebido! Adicionando a Williams com os dados fornecidos.",
  "dados": {
    "nome": "Williams",
    "podios": "5",
    "pontos": "100"
  }
}

---

Input: "Quais equipes têm mais de '300' pontos?"

Output:
{
  "operacao": "SELECT",
  "tabela": "equipes_f1",
  "mensagem_bot": "Consultando as equipes que ultrapassaram a marca de 300 pontos.",
  "filtros": [
    {
      "coluna": "pontos",
      "condicao": ">",
      "valor": "300"
    }
  ],
  "colunas_select": ["nome", "pontos", "vitorias"],
  "ordenar_por": "pontos",
  "ordem": "DESC"
}

---

Input: "Mude a nacionalidade da Alpine para França"

Output:
{
  "operacao": "UPDATE",
  "tabela": "equipes_f1",
  "mensagem_bot": "Atualizando a nacionalidade da equipe Alpine.",
  "filtros": [
    {
      "coluna": "nome",
      "condicao": "=",
      "valor": "Alpine"
    }
  ],
  "dados": {
    "nacionalidade": "França"
  }
}

---

Input: "Me diga uma curiosidade sobre o GP de Mônaco"

Output:
{
  "operacao": "DESCONHECIDO",
  "tabela": "DESCONHECIDO",
  "mensagem_bot": "Desculpe, só consigo fornecer dados sobre as equipes atuais (pontos, vitórias...) ou sobre o histórico de campeões (piloto, ano, escuderia)."
}
"""
async def traduzir_para_json(input_text: str) -> Tuple[Dict[str, Any] | None, bool, str]:
    """Usa o Ollama para traduzir português para JSON estruturado."""
    prompt = PROMPT_TRADUCAO_F1 + f'\nInput: "{input_text}"\nOutput:'

    try:
        # Chama a LLM com o input do usuario
        response = await llm.acomplete(prompt)

        log.debug(f"Resposta bruta do LLM: {response.text}")

        # Remove '```json' ou '```'
        resposta_limpa = re.sub(
            r"^\s*```[a-zA-Z]*\s*(.*?)\s*```\s*$",
            r"\1",
            response.text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        resposta_limpa = resposta_limpa.strip()

        # Tentar parsear o retorno JSON
        try:
            dados_json = json.loads(resposta_limpa)
        except json.JSONDecodeError as e:
            log.error(f"Erro ao tentar carregar o JSON: {e}")
            log.debug(f"Resposta limpa (após tentativa de limpeza): {resposta_limpa}")
            return (
                None,
                False,
                "Ocorreu um erro ao interpretar a resposta do assistente (JSON inválido).",
            )

        # Validação básica das chaves JSON
        chaves_obrigatorias = ["operacao", "mensagem_bot"]
        if not all(chave in dados_json for chave in chaves_obrigatorias):
            log.error(
                f"Erro de Validação: Chaves faltando. Recebido: {dados_json.keys()}"
            )
            return (
                None,
                False,
                "A resposta do assistente está incompleta (faltando 'operacao' ou 'mensagem_bot').",
            )

        # Sucesso, retornanod JSON
        return dados_json, True, ""

    except Exception as e:
        # Captura erros de rede ou do próprio Ollama (ex: modelo não carregado)
        log.error(f"Erro ao chamar o LLM: {e}")
        return None, False, f"Ocorreu um erro interno ao contatar o assistente: {e}"


def transcrever_audio(filepath: str) -> str:
    """
    Carrega o arquivo de áudio e usa o modelo Whisper para transcrevê-lo.
    """

    # Carrega o modelo "SMALL" pois o base tem dificuldade em entender português direito.
    MODELO_WHISPER = whisper.load_model("small")

    try:
        resultado = MODELO_WHISPER.transcribe(filepath)
        return resultado["text"]
    except Exception as e:
        log.error(f"Erro na transcrição do Whisper: {e}")
        return ""


# Funções para construir queries SQL a partir do JSON
def construir_clausula_where(filtros):
    """Constrói a clausula WHERE"""

    if not filtros:
        return "", [], True, ""

    clausulas = []
    parametros = []

    for filtro in filtros:
        coluna = filtro.get("coluna")
        condicao = filtro.get("condicao")
        valor = filtro.get("valor")

        if not all([coluna, condicao, valor is not None]):
            return "", [], False, "Filtro inválido: faltando coluna, condição ou valor."

        clausulas.append(f"{coluna} {condicao.upper()} ?")
        parametros.append(valor)

    where_clausula = " WHERE " + " AND ".join(clausulas)

    return where_clausula, parametros, True, ""


def construir_query_sql_do_json(dados_json: Dict[str, Any]) -> Tuple[str, Tuple, bool, str]:
    """Constroi a query SQL a partir do JSON traduzido."""
    operacao = dados_json.get("operacao")
    tabela = dados_json.get("tabela", "DESCONHECIDO")
    filtros = dados_json.get("filtros", [])

    # Retorna se não tiver tabela especificada
    if tabela not in CAMPOS_OBRIGATORIOS:
         # DESCONHECIDO já é tratado no fluxo principal, mas isso pega tabelas mal formatadas
        if operacao != "DESCONHECIDO":
             return "", (), False, f"Tabela '{tabela}' desconhecida ou não suportada para operações de banco."
        return "", (), False, ""

    campos_requeridos = CAMPOS_OBRIGATORIOS[tabela]

    parametros_finais = []

    if operacao == "SELECT":
        # Pega os dados
        colunas = dados_json.get("colunas_select", ["*"])
        ordenar_por = dados_json.get("ordenar_por")
        ordem = dados_json.get("ordem")
        
        # Verifica se no json tem ordenar_por
        order_by_clausula = ""

        if ordenar_por:
            # Se 'ordenar_por' foi dado, mas 'ordem' não, usamos DESC
            if not ordem:
                ordem = "DESC"

            order_by_clausula = f" ORDER BY {ordenar_por} {ordem}"

        # Constroi a clausula wHERE
        where_clausula, params_where, sucesso_where, erro_where = (
            construir_clausula_where(filtros)
        )

        if not sucesso_where:
            return "", (), False, erro_where

        parametros_finais.extend(params_where)
        colunas_select = ", ".join(colunas)

        # Criação do query
        sql_query = (
            f"SELECT {colunas_select} FROM {tabela}"
            f"{where_clausula}"
            f"{order_by_clausula};"
        )

        return sql_query, tuple(parametros_finais), True, ""

    elif operacao == "INSERT":
        dados = dados_json.get("dados", {})
        
        for campo in campos_requeridos:
        # Verifica se o campo não está nas chaves OU se o valor é vazio/nulo
            if campo not in dados or not dados[campo].strip():
                return (
                    "",
                    (),
                    False,
                    f"Para INSERT na tabela '{tabela}', o campo '{campo}' é obrigatório.",
                )

        colunas = []
        placeholders = []

        # Criação do sql insert usando placeholders.
        for chave, valor in dados.items():
            colunas.append(chave)
            placeholders.append("?")
            parametros_finais.append(valor)

        if not colunas:
            return "", (), False, "Nenhum dado fornecido para INSERT."

        sql_query = f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({', '.join(placeholders)});"
        return sql_query, tuple(parametros_finais), True, ""

    elif operacao == "UPDATE":
        dados = dados_json.get("dados", {})

        if not dados:
            return "", (), False, "Nenhum dado fornecido para UPDATE."
                
        where_clausula, params_where, sucesso_where, erro_where = (
            construir_clausula_where(filtros)
        )

        if not sucesso_where:
            return "", (), False, erro_where
        if not where_clausula:
            return (
                "",
                (),
                False,
                "ERRO: A atualização falhou. Você deve especificar quais registros devem ser alterados. Não é permitido modificar toda a tabela.",
            )

        set_clausulas = []
        
        # Criação das clausulas e parametros
        for chave, valor in dados.items():
            set_clausulas.append(f"{chave} = ?") 
            parametros_finais.append(valor)
            
        # Parâmetros de SET vêm primeiro, depois os de WHERE!
        parametros_finais.extend(params_where)

        sql_query = f"UPDATE {tabela} SET {', '.join(set_clausulas)}{where_clausula};"
        return sql_query, tuple(parametros_finais), True, ""

    elif operacao == "DELETE":
        # É importante que tenha WHERE no delete
        where_clausula, params_where, sucesso_where, erro_where = (
            construir_clausula_where(filtros)
        )

        # Sem WHERE retornamos, mesmo sendo um ADM rodando o codigo
        if not sucesso_where:
            return "", (), False, erro_where
        if not where_clausula:
            return (
                "",
                (),
                False,
                "ERRO: Não foi possível realizar a exclusão. É obrigatório especificar exatamente quais registros você deseja remover.",
            )

        parametros_finais.extend(params_where)  # Adiciona os parâmetros do WHERE

        sql_query = f"DELETE FROM {tabela}{where_clausula};"
        return sql_query, tuple(parametros_finais), True, ""

    return "", (), False, "Operação de banco de dados não suportada."


# PROCESSAMENTO DO INPUT DO USUÁRIO E GERAÇÃO DA RESPOSTA FINAL
async def processar_input_usuario(input: Message) -> str:
    # Verifica se o client está pronto e funcioanndo para rodar, caso contrario retorna.
    if not client_ready or client is None:
        log.error("MCP Client não está conectado.")
        bot.send_message(
            input.chat.id,
            "Serviço indisponível no momento. Tente novamente mais tarde.",
        )
        return

    log.info(
        f"Processando input do usuário ({input.from_user.first_name} - {input.from_user.id}): {input.text}"
    )

    # Pede para IA parsear o input do usuário para JSON
    dados_json, sucesso_llm, erro_llm = await traduzir_para_json(input.text)
    log.debug(f"JSON processado: {dados_json}")

    # Se tivermos erro na llm, retornamos com o erro para o usuario
    if not sucesso_llm:
        await bot.send_message(input.chat.id, erro_llm)
        return

    await bot.send_message(input.chat.id, dados_json["mensagem_bot"])

    # Retornamos se a operacao for desconhecida
    if dados_json.get("operacao") == "DESCONHECIDO":
        await bot.send_message(input.chat.id, "Desculpe, não entendi o que gostaria de fazer! Tente novamente e seja mais claro!")
        return

    sql_query, sql_parametros, sucesso_sql, erro_sql = construir_query_sql_do_json(
        dados_json
    )
    
    log.debug("Query SQL construída: %s", sql_query)
    log.debug(
        f"Parâmetros SQL: {sql_parametros}"
    )  # Veja se os parâmetros estão corretos

    # Se não tiver sucesso construindo a query SQL então retornamos e avisamos o usuario
    if not sucesso_sql:
        await bot.send_message(input.chat.id, erro_sql)
        return

    # Finalmente executamos a operação na database
    async with client:
        try:
            # Usamos a ferramenta no servidor MCP passando a SQL, Parametros e o ID do usuario para verificação de privilegio
            resultado = await client.call_tool(
                "executar_operacao_db",
                arguments={
                    "sql_query": sql_query,
                    "parametros": sql_parametros,
                    "id_usuario": input.from_user.id,
                },
            )
            
            # Log na resposta bruta para podermos acompanhar o processo do bot.
            resposta_bruta_db = resultado.content[0].text
            log.info(f"Resultado da query SQL: \n{resposta_bruta_db}")

            # Passamos a resposta bruta para a LLM novamente para ela fazer a formatação.
            resposta_final = await gerar_resposta_final(resposta_bruta_db, input.text)
            log.info(f"Resposta final gerada para o usuário: {resposta_final}")

            await bot.send_message(input.chat.id, resposta_final)
        except Exception as e:
            log.error(f"Erro ao executar a query SQL: {e}")
            await bot.send_message(
                input.chat.id, f"Erro ao executar a operação no banco de dados: {e}"
            )


async def gerar_resposta_final(dados_brutos: str, input_original: str) -> str:
    """Usa a LLM para transformar dados brutos do DB em uma resposta amigável."""

    log.info("Gerando resposta final para o usuário com base nos dados brutos.")

    prompt_geracao = f"""\
    Você é um Expert em Estatísticas da Fórmula 1 e sua missão é apresentar os dados de forma clara, amigável e em linguagem natural para o usuário.
    
    1. A pergunta original do usuário era: "{input_original}"
    2. Os dados de estatísticas retornados do banco de dados para essa pergunta são:
    --- DADOS ---
    {dados_brutos}
    ---
    
    Use APENAS as informações contidas nos DADOS. Não inclua termos técnicos como 'query', 'banco de dados' ou 'dicionário'. Comece a resposta diretamente.
    """

    try:
        response = await llm.acomplete(prompt_geracao)
        return response.text.strip()
    except Exception as e:
        log.error(f"Erro na segunda chamada do LLM para geração de resposta: {e}")
        return "Desculpe, obtive os dados, mas não consegui formatar a resposta. Tente novamente."


async def main():
    global client_ready, llm, bot
    try:
        # Cria e testa a conexão com o Ollama LLM
        try:
            # A inicialização já está no seu código
            modelo_llm = config.get("CLIENT_LLM", "qwen2.5-coder:3b")
            llm = Ollama(model=modelo_llm, request_timeout=900.0, context_window=32768)

            # Tente uma chamada de API muito simples e rápida para confirmar a conexão
            log.info("🧠 Testando conexão com Ollama...")

            # Use um prompt trivial para testar a comunicação
            response = await llm.acomplete("diga 'olá' em uma palavra")

            if response.text.strip():
                log.info("✅ Ollama está conectado e o modelo está respondendo.")
            else:
                log.warning("⚠️ Ollama está acessado, mas retornou uma resposta vazia.")
        except Exception as e:
            # Onde a maioria dos erros de conexão ocorreriam
            log.error(
                f"❌ Erro na conexão Ollama: O serviço pode estar offline ou o modelo não existe. Detalhes: {e}"
            )
            return

        # Testa conexão com o MCP antes de iniciar o bot
        try:
            async with client:
                resultado = await client.call_tool("ping")
                log.info(
                    f"✅ MCP Client conectado! Resposta do servidor: {resultado.content[0].text}"
                )
                client_ready = True
        except Exception as e:
            log.warning(f"⚠️ Erro ao conectar com o MCP Server: {e}")
            client_ready = False
            
        
        botToken = config.get("TELEGRAM_BOT_TOKEN", None)
        
        if not botToken:
            log.error("Para a aplicação rodar, você precisa inserir sua API Key no arquivo .env")
            return
        
        # Configura o BOT do telegram com a KEY
        bot = AsyncTeleBot(config.get("TELEGRAM_BOT_TOKEN", ""))
        
        # Registra os handlers do telegram, passamos as funções também para uso direto!
        register_handlers(bot, processar_input_usuario, transcrever_audio, log)

        log.info("✅ Cliente pronto para uso.")
        await bot.polling()
    except Exception as e:
        log.error(f"Erro na inicialização do cliente: {e}")
        return


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("\n[Desligamento] Sinal de interrupção recebido.")
    except Exception as e:
        log.error(f"Erro inesperado durante a execução principal: {e}")
