import logging
import sys

from dotenv import dotenv_values

# Carrega as configurações globais e do ambiente
config = dotenv_values()

LOG_FORMAT = config.get("LOG_FORMAT", "[%(asctime)s] | %(levelname)-8s | %(name)s | %(message)s")

NIVEL_PADRAO = config.get("LOG_LEVEL", "INFO")

class ColorFormatter(logging.Formatter):
    """Formatador customizado para colorir o nível do log."""

    CORES_ANSI = {
        "VERMELHO": "\033[91m",
        "AMARELO": "\033[93m",
        "MAGENTA": "\033[95m",
        "CIANO": "\033[96m",
        "VERDE": "\033[92m",
        "RESET": "\033[0m",
    }

    LOG_CORES = {
        logging.DEBUG: CORES_ANSI["CIANO"],
        logging.INFO: CORES_ANSI["VERDE"],
        logging.WARNING: CORES_ANSI["AMARELO"],
        logging.ERROR: CORES_ANSI["VERMELHO"],
        logging.CRITICAL: CORES_ANSI["VERMELHO"],
    }

    def __init__(self, fmt, datefmt=None, style="%"):
        # Injeta o código ANSI CIANO ao redor do %(asctime)s no formato
        # Isso garante que a data/hora fique colorida (CIANO)
        fmt_com_cores = fmt.replace(
            "%(asctime)s",
            f"{self.CORES_ANSI['MAGENTA']}%(asctime)s{self.CORES_ANSI['RESET']}",
        )

        # Chama o construtor da classe pai (logging.Formatter) com o formato customizado
        super().__init__(fmt_com_cores, datefmt, style)

    def format(self, record):
        # 1. Obtém a cor baseada no nível do registro
        cor_nivel = self.LOG_CORES.get(record.levelno, self.CORES_ANSI["RESET"])

        # 2. Insere a cor ANSI antes do nível e reseta no final do nível
        record.levelname = f"{cor_nivel}{record.levelname}{self.CORES_ANSI['RESET']}"

        return super().format(record)

# Função para configurar o logging colorido padrozinada
def configurar_logging(nome: str, nivel: str = NIVEL_PADRAO) -> logging.Logger:
    """
    Configura e retorna a instância do logger.
    
    Args:
        nome (str): O nome único para este logger (ex: 'client', 'server.db').
        nivel (str, opcional): Nível de log (DEBUG, INFO, etc.). Padrão lido do .env.
    """
    if not nome:
        raise ValueError("O nome do logger não pode ser vazio.")

    log_level = getattr(logging, nivel.upper(), logging.INFO)
    logger = logging.getLogger(nome)

    # Previne a reconfiguração se o logger já tiver handlers
    if not logger.handlers:
        logger.setLevel(log_level)
        logger.propagate = False  # Evita que logs subam para o logger root

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)

        # Usando a classe CustomLogger definida acima
        formatter = ColorFormatter(LOG_FORMAT, datefmt="%d-%m-%Y %H:%M:%S")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger