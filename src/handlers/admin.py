import logging
from src.config.messages import (
    MSG_ADMIN_ACESSAR_MENU, MSG_ADMIN_ADD_PHONE, MSG_ADMIN_ADD_CONFIRM,
    MSG_ADMIN_ADD_SUCCESS, MSG_ADMIN_REMOVE_CONFIRM, MSG_ADMIN_REMOVE_SUCCESS,
    MSG_ENCERRAR, SIM_OPTIONS
)
from src.database.client import db_service

logger = logging.getLogger("CardioAgent")

async def send(remote_jid: str, text: str):
    from src.services.evolution import evo_service
    await evo_service.send_text_message(remote_jid, text)

async def handle_admin(remote_jid: str, state: dict, text: str):
    """
    Fluxo do comando /acessar. Exclusivo do proprietário.
    state mantém admin_step, pending_phone, pending_removes
    """
    txt_lower = text.lower().strip()
    
    # Init step se acabou de vir
    if "admin_step" not in state:
        state["admin_step"] = "start"

    step = state["admin_step"]

    # Atalhos Globais:
    if txt_lower in ("9", "3", "encerrar", "encerrar atendimento") and txt_lower != "1":
        # Check against simple numbers to not clash with index 3 of removals, but 'encerrar' is safe
        if "encerrar" in txt_lower or step == "choosing_action" and txt_lower == "3" or step in ["adding_phone", "removing_phone"] and txt_lower == "9":
            state["conversation_step"] = "menu"
            del state["admin_step"]
            from src.services.sessions import active_sessions
            if remote_jid in active_sessions: del active_sessions[remote_jid]
            await send(remote_jid, MSG_ENCERRAR)
            return

    if step == "start":
        state["admin_step"] = "choosing_action"
        await send(remote_jid, MSG_ADMIN_ACESSAR_MENU)
        return

    elif step == "choosing_action":
        if text == "1":
            state["admin_step"] = "adding_phone"
            await send(remote_jid, MSG_ADMIN_ADD_PHONE)
        elif text == "2":
            admins = db_service.list_admins()
            if not admins:
                await send(remote_jid, "Não há números cadastrados para remover.\nVoltando ao menu inicial...")
                state["admin_step"] = "start"
                await handle_admin(remote_jid, state, "start_dummy")
                return
            
            # Formata lista
            msg = "📋 Selecione o número que deseja remover:\n"
            admin_map = {}
            for i, adm in enumerate(admins):
                idx = i + 1
                msg += f"{idx}️⃣ {adm['phone']} ({adm['name']})\n"
                admin_map[str(idx)] = adm['phone']
                
            msg += "\n👉 Digite o número correspondente (ex: 1 ou 1,2).\n9️⃣ Encerrar atendimento"
            state["admin_list_map"] = admin_map
            state["admin_step"] = "removing_phone"
            
            await send(remote_jid, msg)
        else:
            await send(remote_jid, "Opção inválida. Digite 1, 2 ou 3.")

    elif step == "adding_phone":
        # O usuário digitou um telefone
        import re
        phone = re.sub(r'\D', '', text)
        if len(phone) < 10:
            await send(remote_jid, "⚠️ Formato inválido. Digite DDI + DDD + Número. Ex: 5521999998888")
            return
            
        state["pending_phone"] = phone
        state["admin_step"] = "confirm_add"
        await send(remote_jid, MSG_ADMIN_ADD_CONFIRM.format(phone=phone))

    elif step == "confirm_add":
        if text == "1" or txt_lower in SIM_OPTIONS:
            db_service.add_admin(state["pending_phone"])
            await send(remote_jid, MSG_ADMIN_ADD_SUCCESS)
            from src.services.sessions import active_sessions
            if remote_jid in active_sessions: del active_sessions[remote_jid]
            await send(remote_jid, MSG_ENCERRAR)
        elif text == "2" or "voltar" in txt_lower:
            state["admin_step"] = "choosing_action"
            await send(remote_jid, MSG_ADMIN_ACESSAR_MENU)
        else:
            await send(remote_jid, "Digite 1 para Confirmar ou 2 para Voltar.")

    elif step == "removing_phone":
        admin_map = state.get("admin_list_map", {})
        parts = [p.strip() for p in text.replace(",", " ").split()]
        to_remove = []
        for p in parts:
            if p in admin_map:
                to_remove.append(admin_map[p])
                
        if not to_remove:
            await send(remote_jid, "❌ Seleção inválida. Digite os números da lista correspondentes ou 9 para encerrar.")
            return
            
        state["pending_removes"] = to_remove
        state["admin_step"] = "confirm_remove"
        
        rem_list = "\n".join([f"- {r}" for r in to_remove])
        await send(remote_jid, MSG_ADMIN_REMOVE_CONFIRM.format(removed_list=rem_list))

    elif step == "confirm_remove":
        if text == "1" or txt_lower in SIM_OPTIONS:
            for phone in state["pending_removes"]:
                db_service.remove_admin(phone)
            await send(remote_jid, MSG_ADMIN_REMOVE_SUCCESS)
            from src.services.sessions import active_sessions
            if remote_jid in active_sessions: del active_sessions[remote_jid]
            await send(remote_jid, MSG_ENCERRAR)
        elif text == "2" or "voltar" in txt_lower:
            state["admin_step"] = "choosing_action"
            await send(remote_jid, MSG_ADMIN_ACESSAR_MENU)
        else:
            await send(remote_jid, "Digite 1 para Confirmar ou 2 para Voltar.")
