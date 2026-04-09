# 🚀 Guia de Deploy na VPS (Manual de Sobrevivência)

Este guia descreve o processo recomendado para implantar o Sistema Sofia AI em um servidor Linux (como a Contabo) utilizando o plano de execução contínua `screen` e estratégias sem acesso `sudo`.

---

## 🏗️ 1. O Blueprint Autorizado

No repositório raiz, existe o arquivo `deploy_vps_template.py`. Ele foi criado para automatizar completamente a implantação na VPS.

### Como ele funciona:
1. Conecta-se à VPS via SSH (`paramiko`).
2. Faz o clone ou o `git pull` do repositório no diretório alvo do usuário (`/home/[USUARIO]/projeto_agendamento`).
3. Baixa o **pip standalone** (`pip.pyz`) via `wget`, contornando a falta de permissões de root.
4. Cria um ambiente virtual em modo isolado (`python3 -m venv --without-pip venv`).
5. Instala os pacotes do `requirements.txt` apontando para a pasta interna do venv.
6. Gera o script inicializador `start_bot.sh`.
7. Inicia (ou reinicia) o Uvicorn dentro de uma sessão remota isolada chamada **`sofia_bot`** usando o pacote `screen`.

---

## 🖥️ 2. Como usar o Blueprint (Sua Máquina Local)

Você deve rodar o template *na sua máquina local* (onde as regras estão configuradas), que então injetará o código remotamente na VPS.

1. Copie o arquivo: `cp deploy_vps_template.py deploy_vps_prod.py` (ou rode com variáveis de ambiente configuradas).
2. Tenha certeza de configurar corretamente:
   - `VPS_HOST`: O IP público da VPS.
   - `VPS_USER`: O nome de usuário na nuvem (nunca use `root` para rodar aplicações).
   - `VPS_PASS`: A senha de SSH do usuário.
3. Execute o script nativo: `python deploy_vps_template.py`

---

## 🛠️ 3. Como Gerenciar na VPS Manualmente

Quando precisar olhar o funcionamento interno do bot:

1. **Acessando a Máquina via SSH:**
   ```bash
   ssh usuario@185.x.x.x
   ```

2. **Acesando os Logs Nativos (Em tempo real):**
   Acesse a sessão invisível do `screen` executando:
   ```bash
   screen -r sofia_bot
   ```
   > **Atenção:** Para sair desta tela sem matar o bot, pressione as teclas `Ctrl+A` e logo depois aperte `D` (C de Detach). Se você apertar `Ctrl+C`, vai desligar a plataforma.

3. **Arquivos de Log:**
   Se preferir ler no arquivo estático da sessão gerada:
   ```bash
   tail -f ~/projeto_agendamento/bot.log
   ```

4. **Reiniciando o Bot Nativamente:**
   ```bash
   screen -S sofia_bot -X quit
   screen -dmS sofia_bot bash ~/projeto_agendamento/start_bot.sh
   ```
