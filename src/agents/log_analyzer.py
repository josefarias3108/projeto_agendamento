import os
import json
import logging
import asyncio
from datetime import datetime
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from src.services.email_service import send_email

logger = logging.getLogger("CardioAgent")
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

async def read_recent_logs(prefix: str, max_lines: int = 150) -> str:
    """Lê as N últimas linhas de um arquivo .jsonl mensal."""
    now = datetime.now()
    filename = f"{prefix}_{now.strftime('%Y-%m')}.jsonl"
    filepath = os.path.join(LOGS_DIR, filename)
    
    if not os.path.exists(filepath):
        return f"[Aviso: Nenhum registro encontrado para {prefix} este mês]"

    def tail_file():
        lines = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                # Otimizado para não carregar arquivos massivos (lê inteiro, mas fatia o fim)
                # Em cenários robustos, poderia usar um buffer reverso real.
                all_lines = f.readlines()
                lines = all_lines[-max_lines:]
        except Exception as e:
            logger.error(f"Erro ao ler logs de {prefix}: {e}")
        return "".join(lines)
        
    return await asyncio.to_thread(tail_file)

async def run_log_analysis() -> bool:
    """Agente de Inteligência para consolidar logs recentes."""
    try:
        if not GROQ_API_KEY or GROQ_API_KEY == "sua_groq_api_key_aqui":
            logger.warning("Agent IA Audit: GROQ API Key ausente.")
            return False

        tech_logs = await read_recent_logs("technical", 50)
        conv_logs = await read_recent_logs("conversational", 100)
        audit_logs = await read_recent_logs("audit", 50)
        
        # Filtro basico de logs vazios
        has_logs = "}" in tech_logs or "}" in conv_logs or "}" in audit_logs
        if not has_logs:
            logger.info("Agent IA Audit: Sem logs novos para auditar.")
            return True

        llm = ChatGroq(api_key=GROQ_API_KEY, model="llama-3.3-70b-versatile", max_retries=1, temperature=0.3)
        
        system_prompt = (
            "Você é o Agente Auditor da Clínica de Cardiologia.\n"
            "Sua única tarefa é ler o log bruto do sistema fornecido e gerar um 'Relatório de Diagnóstico' para a diretoria.\n\n"
            "O relatório DEVE conter:\n"
            "1. 🛑 ERROS CRÍTICOS: Listar gargalos ou falhas graves em evidência.\n"
            "2. 👥 COMPORTAMENTO DO PACIENTE: Analisar se muitos estão fora de contexto, confusos ou mudando cadastros.\n"
            "3. 🕵️ AUDITORIA: Há cancelamentos manuais e em massa ocorrendo pela secretária?\n\n"
            "Seja profissional, direto e utilize formatação elegante baseada em Markdown. Nunca mencione que você é uma IA e não divague."
            "Se os logs estiverem com avisos de vazios, indique apenas que a operação foi tranquila sem alterações vitais."
        )

        user_content = (
            f"--- LOGS TÉCNICOS ---\n{tech_logs}\n\n"
            f"--- LOGS CONVERSACIONAIS ---\n{conv_logs}\n\n"
            f"--- LOGS DE CANCELAMENTO / AUDITORIA ---\n{audit_logs}\n"
        )
        
        # Evitando context limit de tokens explodirem muito (hard trim)
        if len(user_content) > 30000:
             user_content = user_content[-30000:]

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content)
        ]
        
        logger.info("Agent IA Audit: Analisando padrões comportamentais via ChatGroq...")
        response = await llm.ainvoke(messages)
        ai_report = response.content

        # Disparo assíncrono para seu email
        title = f"Diagnóstico de Agente IA: Clínica Dr. João ({datetime.now().strftime('%d/%m/%Y %H:%M')})"
        await asyncio.to_thread(send_email, "gutofatias.32@gmail.com", title, ai_report)
        logger.info("Agent IA Audit: Relatório gerado e e-mail disparado com sucesso.")
        return True
    
    except Exception as e:
        logger.error(f"Erro no Agente de Auditoria IA: {e}")
        return False
