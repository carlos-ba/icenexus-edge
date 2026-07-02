"""
Abre o dialogo de adicionar licenca e mapeia seus controles.
"""
from pywinauto import Application, Desktop
import time

app = Application(backend='uia').connect(title="SITRAD - 1.8.32")
main = app.top_window()
main.set_focus()
time.sleep(0.3)

# Encontra o botao + (btnAddLicense)
btn = main.child_window(auto_id="btnAddLicense", control_type="Button")
print(f"Botao + encontrado: '{btn.window_text()}' rect={btn.rectangle()}")
btn.click_input()
time.sleep(1.5)

# Mapeia novos controles apos abrir o dialogo
print("\n-- Controles apos abrir dialogo --\n")
elementos = []
for ctrl in main.descendants():
    try:
        name  = ctrl.window_text().strip()
        ctype = ctrl.element_info.control_type
        aid   = ctrl.element_info.automation_id or ''
        rect  = ctrl.rectangle()
        elementos.append((rect.top, rect.left, ctype, name, aid))
    except:
        pass

elementos.sort(key=lambda x: (x[0], x[1]))

for top, left, ctype, name, aid in elementos:
    if top > 200:  # foca na area do dialogo
        nome_display = name[:60] if name else '(sem texto)'
        print(f"  top={top:4d} left={left:4d}  [{ctype:18}]  '{nome_display}'  id='{aid}'")

# Cancela
time.sleep(0.5)
try:
    cancel = main.child_window(title="Cancelar", control_type="Button")
    cancel.click_input()
    print("\n[OK] Dialogo cancelado.")
except Exception as e:
    print(f"\nErro ao cancelar: {e}")
