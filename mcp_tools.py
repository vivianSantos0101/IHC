def register_tools(mcp, log, administrators: list):
    """Registra todos os tools do MCP"""
    
    import sqlite3
    
    @mcp.tool
    def ping():
        return "Pong!"

    @mcp.tool
    def executar_operacao_db(sql_query, parametros=(), id_usuario=0):
        """
        Executa qualquer operação de banco de dados (CREATE, READ, UPDATE, DELETE).

        :param sql_query: A string de consulta SQL a ser executada (com placeholders ?).
        :param parametros: Uma tupla ou lista de valores para substituir na consulta.
        :param id_usuario: O ID do usuário para checagem de permissão.
        :return: O resultado da consulta (para SELECT) ou mensagem de status/erro.
        """

        # A lista de operações aqui é maior do que a LLM tem para processar
        # A LLM é limitada a SELECT, INSERT, UPDATE E DELETE
        # Mas não quero que com o prompt certo ela crie um dDROP ou ALTER
        # Por isso a verificação para as operações extras
        lista_de_operacoes_adm = [
            "INSERT",
            "UPDATE",
            "DELETE",
            "CREATE",
            "DROP",
            "ALTER",
        ]
        
        operacao = sql_query.strip().split()[0].upper()
        if operacao in lista_de_operacoes_adm:
            if not checkar_permissao(id_usuario):
                log.error(
                    "Usuário não autorizado para operações administrativas no banco de dados."
                )
                return "Ação não autorizada. Você não tem permissão para realizar esta operação."

        conn = None
        try:
            # 1. Conecta ao banco de dados
            conn = sqlite3.connect("formula.db")
            cursor = conn.cursor()

            # 2. Executa a consulta com os parâmetros
            cursor.execute(sql_query, parametros)

            # 3. Confirma (commit) a alteração se não for um SELECT
            if sql_query.strip().upper().startswith("SELECT"):
                # Retorna todos os resultados para consultas de leitura
                resultados = cursor.fetchall()
                
                if not resultados:
                    return "A consulta não retornou resultados."

                # Formata o resultado para uma string amigável (pode ser JSON se preferir)
                colunas = [desc[0] for desc in cursor.description]
                linhas_formatadas = []
                
                for linha in resultados:
                    # Cria um dicionário para cada linha e formata como string
                    linha_dict = dict(zip(colunas, linha))
                    linhas_formatadas.append(str(linha_dict))
                    
                return "\n".join(linhas_formatadas)
            else:
                # Confirma a operação e retorna o ID do último registro inserido (se aplicável)
                conn.commit()
                linhas_afetadas = cursor.rowcount
                
                if operacao == "INSERT":
                    # Retorna o ID se for um INSERT, senão o número de linhas afetadas
                    return f"Sucesso! Registro inserido. ID: {cursor.lastrowid}."
                
                return f"Sucesso! {linhas_afetadas} linha(s) afetada(s) pela operação {operacao}."

        except sqlite3.Error as e:
            # Logar o erro no servidor é crucial
            log.error(f"Erro no banco de dados (SQLITE): {e} | Query: {sql_query}")
            return f"Erro no banco de dados: {e}"
        except Exception as e:
            log.error(f"Erro inesperado: {e}")
            return f"Erro inesperado no servidor: {e}"
        finally:
            # 4. Garante que a conexão seja fechada
            if conn:
                conn.close()
                

    def checkar_permissao(id):
        """Verifica se o ID do usuário está na lista de IDs permitidos (ADMs)."""

        log.warning(f'Verificando se {id} está na lista')
        return id in administrators

