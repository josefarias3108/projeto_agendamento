import asyncio
import sys
import os
from datetime import datetime, timedelta

# Ajuste de path para rodar como módulo a partir da raiz
sys.path.append(os.getcwd())

from src.services.evolution import evo_service
from src.config.messages import MSG_REMINDER_CONFIRM_PROMPT

async def send_test_reminder(phone_number):
    print(f"🚀 Enviando lembrete de TESTE para {phone_number}...")
    
    # Simulando os dados que viriam do banco
    name = "José (Teste)"
    delta_target = datetime.now() + timedelta(days=1)
    time_str = delta_target.strftime("%d/%m/%Y às %H:%M")
    insurance = "Unimed"
    
    msg_wa = (
        f"⚠️ *ESTE É UM TESTE DO NOVO LEMBRETE* ⚠️\n\n"
        f"Olá, {name}! 😊\n\n"
        f"Lembrando que você tem uma consulta com o *Dr. João* amanhã em {time_str}.\n\n"
        f"📄 *Documentos para trazer:*\n"
        f"• Carteirinha do plano de saúde ({insurance})\n"
        f"• Documento de identidade (RG, CNH ou outro)\n\n"
        "Até lá! 💙\n\n"
        f"Confirma a sua presença?\n\n"
        "1️⃣ Sim\n"
        "2️⃣ Não"
    )
    
    # Remote JID de WhatsApp pessoal
    remote_jid = f"{phone_number}@s.whatsapp.net"
    
    try:
        await evo_service.send_text_message(remote_jid, msg_wa)
        print("✅ Mensagem enviada com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao enviar: {e}")

if __name__ == "__main__":
    # O número fornecido pelo usuário: 5521980223703
    target = "5521980223703"
    asyncio.run(send_test_reminder(target))
