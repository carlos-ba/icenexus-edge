"""
Testa o caminho completo a partir da tela inicial do Sitrad (Listagem).
Usa uma chave ficticia e cancela no final - nao instala de verdade.
"""
from pywinauto import Application, Desktop
from pywinauto.keyboard import send_keys
import time

CHAVE_TESTE = "AAAAA-BBBBB-CCCCC-DDDDD"

print("Conectando ao Sitrad...")
app = Application(backend='uia').connect(title_re="SITRAD.*", found_index=0)
sitrad = app.top_window()
sitrad.set_focus()
time.sleep(0.5)
print(f"OK - '{sitrad.window_text()}'")

# 1. Clica em Configuracoes na toolbar
print("\n[1] Clicando em Configuracoes...")
clicou = False
for aid in ("mnuiConfiguration", "mnuConfiguration"):
    try:
        btn = sitrad.child_window(auto_id=aid, control_type="Custom")
        btn.click_input()
        clicou = True
        print(f"    OK via auto_id={aid}")
        break
    except Exception:
        pass

if not clicou:
    # Fallback: todos os Custom na toolbar, pega o segundo (Configuracoes)
    customs = [c for c in sitrad.descendants(control_type="Custom")
               if c.rectangle().top < 80 and c.rectangle().height() > 20]
    customs.sort(key=lambda c: c.rectangle().left)
    if len(customs) >= 2:
        customs[1].click_input()
        clicou = True
        print(f"    OK via posicao (segundo botao da toolbar)")

if not clicou:
    print("    ERRO: botao Configuracoes nao encontrado")
    exit(1)

time.sleep(0.8)

# 2. Clica em Configuracoes dos servidores (no popup menu via Desktop)
print("[2] Clicando em Configuracoes dos servidores...")
encontrou = False
desktop = Desktop(backend='uia')
for _ in range(10):  # tenta por ate 2 segundos
    for win in desktop.windows():
        try:
            for item in win.descendants(control_type="MenuItem"):
                txt = item.window_text()
                if "servidores" in txt.lower():
                    print(f"    Encontrado: '{txt}'")
                    item.click_input()
                    encontrou = True
                    break
        except Exception:
            pass
        if encontrou:
            break
    if encontrou:
        break
    time.sleep(0.2)

if not encontrou:
    print("    ERRO: item 'Configuracoes dos servidores' nao encontrado")
    exit(1)

time.sleep(1.2)

# 3. Navega na arvore de configuracoes
# Agora o painel direito mudou para "Recursos de servidores"
# A arvore de configuracao usa o pane id="NodeList"
print("[3] Navegando na arvore de configuracoes...")

def clicar_tree_item(nome_parcial):
    """Clica num TreeItem pelo nome parcial, retorna True se encontrou."""
    for ti in sitrad.descendants(control_type="TreeItem"):
        if nome_parcial.lower() in ti.window_text().lower():
            rect = ti.rectangle()
            if rect.width() > 0:  # visivel
                ti.click_input()
                time.sleep(0.4)
                print(f"    Clicado: '{ti.window_text()}'")
                return True
    return False

# Clica em Servidor Local para expandir
if not clicar_tree_item("Servidor Local"):
    print("    ERRO: 'Servidor Local' nao encontrado")
    exit(1)
time.sleep(0.5)

# Clica em Configuracoes gerais para expandir
if not clicar_tree_item("gerais"):
    print("    ERRO: 'Configuracoes gerais' nao encontrado")
    exit(1)
send_keys("{RIGHT}")   # expande o no
time.sleep(0.8)        # aguarda filhos carregarem

# 4. Duplo clique em Licencas
print("[4] Abrindo Licencas...")
encontrou_lic = False
for ti in sitrad.descendants(control_type="TreeItem"):
    nome = ti.window_text()
    if nome in ("Licencas", "Licenças") and ti.rectangle().width() > 0:
        ti.double_click_input()
        print(f"    Duplo clique em '{nome}'")
        encontrou_lic = True
        time.sleep(1.5)
        break

if not encontrou_lic:
    print("    ERRO: 'Licencas' nao encontrado")
    exit(1)

# Verifica se abriu a tela certa
try:
    lbl = sitrad.child_window(auto_id="lblInstallationKey", control_type="Text")
    lbl.wait("exists", timeout=3)
    chave_inst = lbl.window_text().split(":", 1)[-1].strip()
    print(f"    Tela de Licencas aberta OK. Chave instalacao: {chave_inst}")
except Exception:
    print("    AVISO: tela de Licencas pode nao ter aberto corretamente")

# 5. Clica no botao +
print("[5] Clicando no botao + (adicionar licenca)...")
try:
    btn_add = sitrad.child_window(auto_id="btnAddLicense", control_type="Button")
    btn_add.wait("exists visible", timeout=5)
    btn_add.click_input()
    print("    OK - wizard aberto")
    time.sleep(1.5)
except Exception as e:
    print(f"    ERRO: {e}")
    exit(1)

# 6. Digita a chave
print("[6] Digitando chave de teste...")
try:
    campo = sitrad.child_window(auto_id="txtLicenseKey", control_type="Edit")
    campo.wait("exists visible", timeout=5)
    campo.click_input()
    time.sleep(0.4)
    send_keys("^a")
    time.sleep(0.2)
    send_keys(CHAVE_TESTE, pause=0.05)
    time.sleep(0.5)
    print(f"    Chave digitada: '{CHAVE_TESTE}'")
except Exception as e:
    print(f"    ERRO: {e}")
    exit(1)

# 7. Cancela (nao instala de verdade)
print("[7] Cancelando (este e apenas o teste)...")
for btn in sitrad.descendants(control_type="Button"):
    if "ancelar" in btn.window_text():
        btn.click_input()
        print("    OK - cancelado")
        break

print("\n========================================")
print(" CAMINHO COMPLETO FUNCIONOU!")
print("========================================")
