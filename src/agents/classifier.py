import logging
import os
from src.agents.graph import llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("CardioAgent")

# Palavrões e ofensas comuns (lista reduzida para exemplo, pode ser expandida)
PROFANITY_KEYWORDS = [
    "porra", "caralho", "foda", "vtnc", "desgraça", "merda", "filho da puta", "fdp",
    "idiota", "imbecil", "burro", "lixo", "estúpido", "estupido"
]

# Assuntos aleatórios comuns
OFF_TOPIC_KEYWORDS = [
    "futebol", "política", "politica", "bbb", "clima", "tempo", "novela"
]

async def check_out_of_context(text: str) -> str | None:
    """
    Retorna o tipo de mensagem fora de contexto: 'offensive', 'off_topic', ou None se estiver ok.
    """
    txt_lower = text.lower().strip()
    
    # 1. Verificação Determinística (Rápida)
    if any(word in txt_lower for word in PROFANITY_KEYWORDS):
        return "offensive"
    
    if any(word in txt_lower for word in OFF_TOPIC_KEYWORDS):
        return "off_topic"

    # 2. Verificação com LLM (Se houver LLM disponível)
    if not llm:
        return None

    system_prompt = (
        "Você é um classificador de intenções para um bot de consultório médico.\n"
        "Sua tarefa é identificar se a mensagem do usuário é:\n"
        "1. RELACIONADA ao consultório (agendar, remarcar, exames, dúvidas médicas, endereço, etc).\n"
        "2. FORA DE CONTEXTO (assuntos aleatórios como esportes, notícias, conversas casuais).\n"
        "3. OFENSIVA (xingamentos, insultos).\n\n"
        "Responda APENAS com uma das seguintes palavras: 'ok', 'off_topic' ou 'offensive'."
    )

    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=text)
        ]
        # Usamos ainvoke para não bloquear o loop de eventos
        response = await llm.ainvoke(messages)
        result = response.content.lower().strip()
        
        if 'offensive' in result:
            return 'offensive'
        elif 'off_topic' in result:
            return 'off_topic'
        else:
            return None
    except Exception as e:
        logger.error(f"Erro ao classificar contexto: {e}")
        return None
