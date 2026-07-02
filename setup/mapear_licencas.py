"""
Mapeia os controles da tela de Licencas no Sitrad Pro.
"""
from pywinauto import Application, Desktop
import time

app = Application(backend='uia').connect(title="SITRAD - 1.8.32")
main = app.top_window()
main.set_focus()
time.sleep(0.3)

print(f"Janela: '{main.window_text()}'")
print("=" * 80)

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
    nome_display = name[:70] if name else '(sem texto)'
    print(f"  top={top:4d} left={left:4d}  [{ctype:18}]  '{nome_display}'  id='{aid}'")
