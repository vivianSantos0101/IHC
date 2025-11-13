import asyncio
import sqlite3

# Import do Logger (Customizado) e do dotenv
from CustomLogger import configurar_logging
from dotenv import dotenv_values

# Import do servidor
from fastmcp import FastMCP

# Função de popular a db e função para carregar as tools
from populate_db import populate_db
from mcp_tools import register_tools

# Definiçòes globais. Variaveis do .env e inicialização do log
config = dotenv_values()
log = configurar_logging(config.get("SERVER_NAME", "Servidor MCP"), config.get("SERVER_LOG_LEVEL", "INFO"))

def init_db():
    """Inicializa o banco de dados SQLite."""
    
    try:
        conn = sqlite3.connect(config.get("DB_NAME", "database.db"))
        cursor = conn.cursor()

        # Criação da tabela 'equipes_f1' se não existir
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS equipes_f1 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                nacionalidade TEXT NOT NULL DEFAULT 'Não informado',
                pontos INTEGER DEFAULT 0,
                vitorias INTEGER DEFAULT 0,
                podios INTEGER DEFAULT 0,
                pilotos_principais TEXT
            )
        """)

        # Criação da tabela 'equipes_f1' se não existir
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historico_campeoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ano_vencido TEXT NOT NULL UNIQUE,
                escuderia TEXT NOT NULL DEFAULT 'Não informado',
                piloto TEXT DEFAULT 'Não informado',
                pontos INTEGER DEFAULT 0,
                construtora_campea TEXT DEFAULT 'Não informado'
            )
        """)

        cursor.execute("SELECT COUNT(*) FROM equipes_f1")
        count = cursor.fetchone()[0]

        # Se o resultado do SELECT for 0 a gente preenche a tabela com os dados
        if count == 0:
            log.info(
                f"Banco de dados '{config.get("DB_NAME", "database.db")}' criado ou vazio. Chamando populate_db()."
            )
            populate_db(conn, log)  # Chama a função de população

        return True

    except Exception as e:
        log.error(f"Erro ao inicializar banco: {e}")
        return False


async def main():
    log.info("Iniciando a aplicação...")
    mcp = FastMCP(config.get("SERVER_NAME", "Servidor MCP"))
    
    # Inicializa a database
    databaseInicializada = init_db()

    if not databaseInicializada:
        log.error("Falha na inicialização do banco de dados. Encerrando o programa.")
        return

    # Carrega a string de administradores (Ex: "8567488684")
    admin_ids_str = config.get("ADMINISTRATORS", "")
    administradores = []
    
    try:
        # Converte a string (separada por vírgula) em uma lista de números inteiros
        administradores = [
            int(id.strip()) 
            for id in admin_ids_str.split(',') 
            if id.strip()
        ]
    except ValueError:
        log.error("ADMINISTRATORS no .env deve conter IDs numéricos válidos. Usando lista vazia.")
    
    log.info(f'Lista de administradores (IDs numéricos): {administradores}')
    # Registra as funções disponiveis pelo mcp
    register_tools(mcp, log, administradores)

    await mcp.run_async(transport=config.get("SERVER_TRANSPORT", "http"), port=int(config.get("SERVER_PORT", 8000)))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("\n[Desligamento] Sinal de interrupção recebido.")
    except Exception as e:
        log.error(f"Erro inesperado durante a execução principal: {e}")
