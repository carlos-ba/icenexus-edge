"""
Abre Configuracoes dos Servidores pelo menu do Sitrad Pro e mapeia os controles.
Requer que o Sitrad Pro esteja aberto e na janela principal.
"""
from pywinauto import Desktop, Application
import time

# Conecta ao Sitrad Pro
app = Application(backend='uia').connect(title_re="Sitrad Pro.*", found_index=0)
main = app.top_window()
print(f"Janela principal: '{main.window_text()}'")
main.set_focus()
time.sleep(0.5)

# Clica no menu Configuracoes
print("\n[1] Abrindo menu Configuracoes...")
try:
    menu_cfg = main.child_window(title="Configurações", control_type="MenuItem")
    menu_cfg.click_input()
    time.sleep(0.8)
except Exception as e:
    print(f"  Erro menu: {e}")
    # Tenta MenuBar
    menubar = main.child_window(control_type="MenuBar")
    for item in menubar.descendants(control_type="MenuItem"):
        print(f"  MenuItem: '{item.window_text()}'")

# Lista submenus visíveis
print("\n[2] Submenus abertos:")
desktop = Desktop(backend='uia')
for win in desktop.windows():
    try:
        ctype = win.element_info.control_type
        name = win.window_text()
        if ctype in ("Menu", "Popup") or "menu" in name.lower():
            print(f"  [{ctype}] '{name}'")
            for item in win.descendants(control_type="MenuItem"):
                print(f"    - '{item.window_text()}'")
    except:
        pass

time.sleep(0.5)

# Clica em Configuracoes dos Servidores
print("\n[3] Clicando em 'Configurações dos Servidores'...")
try:
    item = desktop.window(title_re=".*Configurações dos Servidores.*", control_type="MenuItem")
    item.click_input()
    time.sleep(1.5)
except Exception as e:
    print(f"  Erro: {e}")
    # Tenta clicar direto
    try:
        item = main.child_window(title="Configurações dos Servidores", control_type="MenuItem")
        item.click_input()
        time.sleep(1.5)
    except Exception as e2:
        print(f"  Erro2: {e2}")

# Mapeia a nova janela
print("\n[4] Janelas abertas apos clicar:")
for win in desktop.windows():
    try:
        name = win.window_text()
        if name and name not in ("", "Program Manager"):
            rect = win.rectangle()
            if rect.width() > 100:
                print(f"  '{name}' [{rect.width()}x{rect.height()}]")
    except:
        pass
