# 🗺️ Mapa de Estados e Sessões Conversacionais

Todo fluxo feito pela AI de atendimento da Sofia baseia-se em uma "Machine State" na camada de Roteadores Python.
Isto significa que nenhuma mensagem do utilizador gera as mesmas consequências a todos (Ex: Se um administrador digita "1", é para o Menu de Adm, se o paciente digita "1" é para envio de exames).

Este arquivo demonstra a lógica fundamental de rotas. O mapeamento do estado da sessão é normalmente acessível via `user_state["step"]`.

---

## 🧍 Estados de Onboarding (Recepção)

Acoplados ao ficheiro `src/handlers/onboarding.py`, estes controlam clientes na primeira entrada da clínica.

* `ask_is_patient` -> Questionário se já é paciente antes do cadastro.
* `register_name` -> Esperando paciente digitar nome extenso.
* `register_cpf` -> Esperando inserção do CPF (Módulo valida integridade de tamanho).
* `register_cep` -> Recebe entrada e consome uma lookup ViaCEP.
* `waiting_for_exams` -> Fica num listener persistente verificando se media webhooks (PDFs / Imagens) chegaram.

## 🏥 Estados de Agendamento 

Focado em gerir disponibilidades acoplado em `src/handlers/scheduling.py` e `menu.py`.

* `menu` -> Posição ociosa do utilizador onde ele tem comandos macro (ex: 1 Agendar, 2 Cancelar).
* `scheduling` -> Estado genérico para travar paciente de pedir outras coisas enquanto interage com dias livres.
* `cancel_select` -> Esperando qual índice do agendamento ele deseja remover.

## 💼 Escopo Administrativo e Ficha de Clínica

Protegidos em `src/handlers/admin.py` (ou `clinic.py`), focados em pessoas que estão em `public.authorized_admins`.

* `admin_menu` / `admin_idle` -> Estado master da clínica (Agendamentos gerais, pesquisa em lote, envio).

---

## 🧹 Limpeza Automática de Ociosidade

Os jobs e rotinas do FastAPI (via Lifespan / Tarefas de Background) invalidam estados de clientes cuja janela de sessão exceda 15M (em média), voltando a sessão para null e roteando novamente o cliente do absoluto zero para evitar pendências em fluxos que ele tenha esquecido (Ex: Parou no meio de um cadastro de CEP num dia e fala algo aleatório no dia seguinte).
