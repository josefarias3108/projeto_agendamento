import asyncio
from src.main import process_message, active_sessions

async def test():
    # Simulate a user sending "Encerrar" while in active_sessions
    phone = "5521999999999@s.whatsapp.net"
    active_sessions[phone] = {"conversation_step": "ask_is_patient"}
    
    # We will patch evo_service temporarily
    import src.services.evolution as evo
    async def mock_send(jid, text):
        print(">>> MSG ENVIADA:", text)
        
    evo.evo_service.send_text_message = mock_send
    
    await process_message(phone, "Encerrar")
    print("Session exists?", phone in active_sessions)

asyncio.run(test())
