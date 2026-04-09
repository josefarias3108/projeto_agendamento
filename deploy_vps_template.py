import paramiko
import os
import time

# ==============================================================================
# BLUEPRINT DE DEPLOY PARA VPS (MODO NO-SUDO)
# Este script automatiza o deploy em servidores Linux sem permissão de root.
# ==============================================================================

def deploy_automation():
    # --- 1. CONFIGURAÇÕES DO PROJETO ---
    config = {
        "host": "194.147.58.150",
        "user": "guto",
        "pass": "Aurora@22",
        "repo": "https://github.com/josefarias3108/projeto_agendamento.git", # Mude para o repositório correto
        "target_dir": "/home/guto/projeto_agendamento",                     # Caminho na VPS
        "port": "8000"                                                      # Porta do Uvicorn
    }

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"🚀 Conectando em {config['host']}...")
        ssh.connect(config['host'], 22, config['user'], config['pass'])
        sftp = ssh.open_sftp()
        
        # --- 2. DOWNLOAD DO CÓDIGO ---
        print("📂 Clonando/Atualizando repositório...")
        ssh.exec_command(f"git clone {config['repo']} {config['target_dir']} || (cd {config['target_dir']} && git pull)")
        
        # --- 3. BOOTSTRAP DO PIP (PULO DO GATO) ---
        # Como o usuário 'guto' não tem sudo, usamos o pip standalone (pip.pyz)
        print("🐍 Preparando motor de pacotes (pip.pyz)...")
        ssh.exec_command("wget -q https://bootstrap.pypa.io/pip/pip.pyz -O ~/pip.pyz")
        
        # --- 4. AMBIENTE VIRTUAL ---
        print("📦 Criando ambiente virtual e instalando bibliotecas...")
        ssh.exec_command(f"python3 -m venv --without-pip {config['target_dir']}/venv")
        
        # Instalamos as dependências do requirements.txt dentro do site-packages do venv
        install_cmd = f"python3 ~/pip.pyz install -r {config['target_dir']}/requirements.txt --target {config['target_dir']}/venv/lib/python3.12/site-packages/ --upgrade"
        stdin, stdout, stderr = ssh.exec_command(install_cmd)
        stdout.read() # Espera a instalação terminar
        
        # --- 5. SCRIPT DE INICIALIZAÇÃO (STARTUP) ---
        print("📜 Gerando script de inicialização...")
        startup_script = f"""#!/bin/bash
cd {config['target_dir']}
export PYTHONPATH={config['target_dir']}/src
export PYTHONUSERBASE={config['target_dir']}/venv

# Comando para rodar com Uvicorn em logs fixos
python3 << 'PYSCRIPT' > bot.log 2>&1
import sys
sys.path.insert(0, "{config['target_dir']}/venv/lib/python3.12/site-packages")
import uvicorn
uvicorn.run("src.main:app", host="0.0.0.0", port={config['port']}, log_level="info")
PYSCRIPT
"""
        with sftp.open(f"{config['target_dir']}/start_bot.sh", 'w') as f:
            f.write(startup_script)
        ssh.exec_command(f"chmod +x {config['target_dir']}/start_bot.sh")
        
        # --- 6. LANÇAMENTO NO SCREEN (BACKGROUND 24/7) ---
        # Usamos sessões de screen para o bot nunca morrer ao fechar o terminal
        print(f"🎬 Iniciando Sofia na porta {config['port']}...")
        ssh.exec_command("screen -S sofia_bot -X quit || true") # Remove sessão antiga se existir
        ssh.exec_command(f"screen -dmS sofia_bot bash {config['target_dir']}/start_bot.sh")
        
        print("\n✅ DEPLOY FINALIZADO COM SUCESSO!")
        print(f"🔗 Bot rodando em: http://{config['host']}:{config['port']}/docs")
        print(f"📝 Para ver os logs na VPS use: screen -r sofia_bot")
        
        sftp.close()
        ssh.close()
        
    except Exception as e:
        print(f"❌ Erro fatal durante o deploy: {e}")

if __name__ == "__main__":
    deploy_automation()
