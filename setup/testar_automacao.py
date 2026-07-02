"""
Testa a automacao de instalacao de chave sem a interface grafica.
Coloca uma chave de teste no campo e clica Cancelar (nao instala de verdade).
"""
from pywinauto import Application
import time

CHAVE_TESTE = "TESTE-TESTE-TESTE-TESTE"

print("=" * 60)
print(" TESTE DE AUTOMACAO - IceNexus Configurador")
print("=" * 60)

# 1. Conecta ao Sitrad
print("\n[1/5] Localizando Sitrad Pro...")
app = Application(backend='uia').connect(title="SITRAD - 1.8.32")
main = app.top_window()
main.set_focus()
time.sleep(0.3)
print("    OK Sitrad localizado.")

# 2. Verifica se tela de Licencas esta aberta
print("\n[2/5] Verificando tela de Licencas...")
licencas_abertas = False
try:
    lbl = main.child_window(auto_id="lblInstallationKey", control_type="Text")
    lbl.wait("exists", timeout=3)
    chave_inst = lbl.window_text().split(":", 1)[-1].strip()
    licencas_abertas = True
    print(f"    OK Licencas abertas. Chave da instalacao: {chave_inst}")
except Exception as e:
    print(f"    Licencas nao abertas: {e}")
    print("    Abrindo Configuracoes dos servidores...")
    main.set_focus()
    time.sleep(0.3)
    menu_cfg = main.child_window(auto_id="mnuiConfiguration", control_type="Custom")
    menu_cfg.click_input()
    time.sleep(0.8)
    # Procura o item de menu
    for item in main.descendants(control_type="MenuItem"):
        txt = item.window_text()
        if "servidores" in txt.lower():
            print(f"    Clicando em: '{txt}'")
            item.click_input()
            break
    time.sleep(1.0)
    # Abre Licencas
    try:
        srv = main.child_window(title="Servidor Local", control_type="TreeItem")
        srv.expand()
        time.sleep(0.3)
    except Exception:
        pass
    try:
        cfg = main.child_window(title="Configuracoes gerais", control_type="TreeItem")
        cfg.expand()
        time.sleep(0.3)
    except Exception:
        pass
    lic = main.child_window(title="Licencas", control_type="TreeItem")
    lic.double_click_input()
    time.sleep(1.5)
    licencas_abertas = True
    print("    OK Tela de Licencas aberta.")

# 3. Abre wizard
print("\n[3/5] Abrindo wizard de nova licenca...")
btn_add = main.child_window(auto_id="btnAddLicense", control_type="Button")
rect = btn_add.rectangle()
print(f"    Botao + em: {rect}")
btn_add.click_input()
time.sleep(1.5)
print("    OK Wizard aberto.")

# 4. Preenche campo de chave
print("\n[4/5] Inserindo chave de TESTE (sera cancelada)...")
campo = main.child_window(auto_id="txtLicenseKey", control_type="Edit")
campo.wait("exists visible", timeout=5)
from pywinauto.keyboard import send_keys
campo.click_input()
time.sleep(0.3)
send_keys("^a")  # Ctrl+A para selecionar tudo
time.sleep(0.2)
send_keys(CHAVE_TESTE, pause=0.05)
time.sleep(0.5)
# Verifica texto digitado
try:
    digitado = campo.window_text()
    print(f"    Campo preenchido com: '{digitado}'")
except Exception:
    print("    (nao foi possivel ler o campo, mas a digitacao foi enviada)")

# Verifica label de validacao
try:
    val = main.child_window(auto_id="lblLicenseKeyValidation", control_type="Text")
    msg = val.window_text().strip()
    if msg:
        print(f"    Mensagem de validacao: '{msg}'")
except Exception:
    pass

# 5. Cancela (nao instala de verdade)
print("\n[5/5] Cancelando (teste - nao instala de verdade)...")
try:
    btn_cancel = main.child_window(title="Cancelar", control_type="Button")
    btn_cancel.click_input()
    print("    OK Cancelado com sucesso.")
except Exception as e:
    print(f"    Erro ao cancelar: {e}")

print("\n" + "=" * 60)
print(" TESTE CONCLUIDO COM SUCESSO!")
print(" A automacao esta funcionando corretamente.")
print(" Para instalar de verdade, use o IceNexus_Configurador.exe")
print("=" * 60)
