"""
Mapeamento completo de TODOS os controles da janela Configuração Sitrad Service local.
Mostra tipo, nome, automation_id e posição de cada elemento.
"""
from pywinauto import Desktop
import time

win = Desktop(backend='uia').window(title="Configuração Sitrad Service local")
win.set_focus()
time.sleep(0.5)

print(f"Janela: '{win.window_text()}'")
rect = win.rectangle()
print(f"Tamanho: {rect.width()}x{rect.height()} em ({rect.left},{rect.top})")
print("=" * 80)

print("\n── TODOS OS CONTROLES (ordenados por posição vertical) ──\n")

elementos = []
for ctrl in win.descendants():
    try:
        name  = ctrl.window_text().strip()
        ctype = ctrl.element_info.control_type
        aid   = ctrl.element_info.automation_id or ''
        rect  = ctrl.rectangle()
        elementos.append((rect.top, rect.left, ctype, name, aid, rect))
    except:
        pass

elementos.sort(key=lambda x: (x[0], x[1]))

for top, left, ctype, name, aid, rect in elementos:
    nome_display = name[:50] if name else '(sem texto)'
    print(f"  top={top:4d} left={left:4d}  [{ctype:18}]  '{nome_display}'  id='{aid}'")

print("\n── CUSTOM controls (possíveis abas) ──\n")
for ctrl in win.descendants(control_type="Custom"):
    try:
        name = ctrl.window_text().strip()
        aid  = ctrl.element_info.automation_id or ''
        rect = ctrl.rectangle()
        print(f"  top={rect.top:4d} left={rect.left:4d}  '{name[:60]}'  id='{aid}'")
    except:
        pass

print("\nMapeamento completo.")
