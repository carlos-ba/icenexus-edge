from pywinauto import Application

app = Application(backend='uia').connect(title_re="SITRAD.*")
win = app.top_window()

# Busca em todos os descendentes por textos relacionados a API/Licenca/Servidor
print("=== Todos elementos com texto relevante ===")
keywords = ['api', 'licen', 'ativar', 'servidor', 'chave', 'porta', 'configura',
            'instru', 'usu', 'grupo', 'permiss']

for ctrl in win.descendants():
    try:
        name = ctrl.window_text().lower()
        ctype = ctrl.element_info.control_type
        aid = ctrl.element_info.automation_id
        if any(k in name for k in keywords) and name not in ['sitrad - 1.8.32', '']:
            print(f"  [{ctype}] '{ctrl.window_text()}' id={aid}")
    except:
        pass
