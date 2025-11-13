import os
import tempfile

from telebot.types import Message

def register_handlers(bot, processar_input_usuario, transcrever_audio, log):
    """Registra todos os handlers do bot."""

    # Handle '/start' and '/help'
    @bot.message_handler(commands=['help', 'start'])
    async def send_welcome(message: Message):
        text = (
            '🏁 Assistente de Estatísticas da F1 🏎️\n\n'
            'Sou o seu assistente para qualquer informação sobre a Fórmula 1. Pergunte sobre equipes, pilotos e campeonatos passados e presentes!\n\n'
            'O que você pode me perguntar?\n'
            '1. Estatísticas Atuais: "Quantos pontos tem a Ferrari?" ou "Qual piloto principal da Red Bull?".\n'
            '2. Histórico de Campeões: "Quem venceu em 1988?" ou "Quais títulos o Senna ganhou?".\n'
            '3. Gerenciamento de Dados: "Adicione a Williams com 5 pódios" ou "Mude a nacionalidade da Alpine para França". (Somente ADMs)\n\n'
            '🗣️ Dica: Aceito comandos por áudio também!\n\n'
            'Extra. ID de Usuario: Para saber seu ID de usuario apenas de /id e responderei com ele\n\n'
            'Mande sua primeira pergunta para a pista!'
        )
        await bot.reply_to(message, text)

    @bot.message_handler(commands=['id'])
    async def send_ind(message: Message):
        await bot.reply_to(message, message.from_user.id)

    # Handle all other messages with content_type 'text' (content_types defaults to ['text'])
    @bot.message_handler(func=lambda message: True)
    async def message_input(message: Message):
        if message.text:
            await processar_input_usuario(message)
        
    @bot.message_handler(content_types=['voice'])
    async def voice_input(message: Message):
        file_info = await bot.get_file(message.voice.file_id)
        caminho_audio = None
        
        try:
            # Criamos um arquivo temporario para salvar o audio
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                caminho_audio = tmp.name

            # Baixa o arquivo e salva no arquivo temporario
            downloaded_file = await bot.download_file(file_info.file_path)
            with open(caminho_audio, 'wb') as new_file:
                new_file.write(downloaded_file)
                
            # Transcrevemos o audio para texto usando WHISPER
            texto_transcrito = transcrever_audio(caminho_audio)
            
            if not texto_transcrito:
                await bot.reply_to(message, "Desculpe, não consegui transcrever o áudio com clareza. Tente novamente.")
                return
            
            # Adicioamos o texto ao objeto de mensagem, assim nos da mais liberdade de como responder a pessoa e acesso a informações
            message.text = texto_transcrito
            
            await bot.reply_to(message, f"Transcrição: **{texto_transcrito}...**\n\nProcessando a consulta...")
            
            # Passamos o objeto diretamente para mesma função para processar o texto. 
            # A partir daqui a logica se torna uma só tanto para audios (agora convertidos em texto) quanto textos.
            await processar_input_usuario(message)
        except Exception as e:
            log.error(f"Erro no voice_input do chat {message.chat.id}: {e}") 
            await bot.send_message(message.chat.id, "Ocorreu um erro interno. Tente novamente.")
        finally:
            # 4. Limpar o arquivo temporário com segurança
            if caminho_audio and os.path.exists(caminho_audio):
                os.remove(caminho_audio)