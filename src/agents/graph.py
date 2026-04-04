import os
import logging
from datetime import datetime
from langchain_groq import ChatGroq
from src.agents.state import AgentState
from src.agents.tools import get_tools
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("CardioAgent")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
# Mixtral é rápido e costuma ter bons limites no Groq
MODEL_NAME = "mixtral-8x7b-32768" 

if not GROQ_API_KEY or GROQ_API_KEY == "sua_groq_api_key_aqui":
    llm = None
else:
    llm = ChatGroq(api_key=GROQ_API_KEY, model=MODEL_NAME, max_retries=1, temperature=0.2)

if llm:
    tools = get_tools()
    llm_with_tools = llm.bind_tools(tools)
else:
    llm_with_tools = None


def agent_node(state: AgentState):
    """Nó principal do agente."""
    if not llm_with_tools:
        return {"messages": [AIMessage(content="Serviço offline.")], "loop_count": state["loop_count"] + 1}

    # Data atual para o prompt
    now = datetime.now()
    hoje_fmt = now.strftime('%A, %d de %B de %Y')
    
    # Prompt focado em resolver rápido e evitar loops
    system_prompt = f"""\
Você é a Sofia, assistente virtual do Dr. João (Cardiologista).
Hoje é {hoje_fmt}.

Sua missão é agendar consultas. O paciente já passou pelo cadastro.

DIRETRIZES:
1. **DISPONIBILIDADE**: Se o usuário perguntar "qual a próxima?" ou "horários livres", use 'buscar_proximas_vagas' imediatamente. NÃO tente adivinhar.
2. **AGENDAMENTO**: Ao agendar, use 'agendar_consulta'. Se falhar, explique o motivo ao usuário.
3. **RESPOSTAS**: Seja breve, empática e evite gerar muitas mensagens. 
4. **DATAS**: Se o usuário disser apenas o dia (ex: "Sexta"), o sistema Python já resolve se você passar "Sexta-feira".

Regras:
- Consultas: Seg, Qua, Sex (08h-19h). Almoço 12h-14h.
- Ter e Qui: Cirurgias.
- Preço: R$ 450,00.
"""

    msgs = list(state["messages"])
    
    # Contexto do paciente embutido no sistema
    patient_info = ""
    if state.get("is_registered"):
        patient_info = f"\n\nPACIENTE ATUAL: {state.get('name')} | ID: {state.get('patient_id')}"

    system_message = SystemMessage(content=system_prompt + patient_info)

    if not msgs or not isinstance(msgs[0], SystemMessage):
        msgs = [system_message] + msgs
    else:
        msgs[0] = system_message

    try:
        response = llm_with_tools.invoke(msgs)
        return {"messages": [response], "loop_count": state["loop_count"] + 1}
    except Exception as e:
        logger.error(f"Erro LLM: {e}")
        return {"messages": [AIMessage(content="Estou com lentidão na agenda. Pode aguardar um instante? 🙏")], "loop_count": state["loop_count"] + 1}


def should_continue(state: AgentState):
    if state["loop_count"] > 5:
        return "human_fallback"
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

def human_fallback_node(state: AgentState):
    return {"messages": [AIMessage(content="Tive dificuldade de conexão com o banco de dados. Um atendente humano vai te ajudar em instantes!")]}

def create_workflow():
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    
    if llm_with_tools:
        workflow.add_node("tools", ToolNode(get_tools()))
    else:
        workflow.add_node("tools", lambda x: {"messages": [AIMessage(content="Erro técnico.")]})

    workflow.add_node("human_fallback", human_fallback_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "human_fallback": "human_fallback", END: END})
    workflow.add_edge("tools", "agent")
    workflow.add_edge("human_fallback", END)
    return workflow.compile()

graph_app = create_workflow()
