"""
IceNexus - Instalador de Chave de API do Sitrad
------------------------------------------------
Pré-requisito: Sitrad Pro aberto e logado na tela principal.
O programa navega até Licencas e instala a chave automaticamente.
"""
import customtkinter as ctk
import threading
import time
from pywinauto import Application, Desktop
from pywinauto.keyboard import send_keys

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SITRAD_TITLE_RE = "SITRAD.*"

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("IceNexus — Instalar Chave de API")
        self.geometry("500x400")
        self.resizable(False, False)
        self.configure(fg_color="#0d1117")
        self._build()

    def _build(self):
        # Titulo
        ctk.CTkLabel(
            self, text="IceNexus — Chave de API Sitrad",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#00b4d8"
        ).pack(pady=(28, 4))

        ctk.CTkLabel(
            self,
            text="Deixe o Sitrad Pro aberto e logado.\nO programa instala a chave automaticamente.",
            font=ctk.CTkFont(size=12),
            text_color="#8b949e"
        ).pack(pady=(0, 20))

        # Campo da chave
        ctk.CTkLabel(
            self, text="Chave de licença da API:",
            font=ctk.CTkFont(size=13),
            text_color="#e6edf3"
        ).pack(anchor="w", padx=40)

        self.entry = ctk.CTkEntry(
            self,
            placeholder_text="XXXXX-XXXXX-XXXXX-XXXXX",
            font=ctk.CTkFont(size=14, family="Consolas"),
            height=44,
            width=420,
            fg_color="#161b22",
            border_color="#00b4d8",
            text_color="#e6edf3"
        )
        self.entry.pack(padx=40, pady=(6, 20))

        # Botão instalar
        self.btn = ctk.CTkButton(
            self,
            text="Instalar chave",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=46,
            width=420,
            fg_color="#00b4d8",
            hover_color="#0096b8",
            text_color="#000000",
            command=self._instalar
        )
        self.btn.pack(padx=40)

        # Status
        self.status = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(size=11, family="Consolas"),
            fg_color="#161b22",
            text_color="#e6edf3",
            width=420,
            height=120,
            state="disabled"
        )
        self.status.pack(padx=40, pady=20)

    def _log(self, msg):
        self.status.configure(state="normal")
        self.status.insert("end", msg + "\n")
        self.status.configure(state="disabled")
        self.status.see("end")

    def _instalar(self):
        chave = self.entry.get().strip()
        if not chave:
            self._log("Digite a chave antes de continuar.")
            return
        self.btn.configure(state="disabled", text="Instalando...")
        threading.Thread(target=self._run, args=(chave,), daemon=True).start()

    def _run(self, chave):
        try:
            self._instalar_chave(chave)
        except Exception as ex:
            self._log(f"Erro: {ex}")
        finally:
            self.btn.configure(state="normal", text="Instalar chave")

    def _instalar_chave(self, chave):
        self._log("Conectando ao Sitrad...")

        # Conecta ao Sitrad aberto
        try:
            app = Application(backend='uia').connect(title_re=SITRAD_TITLE_RE, found_index=0)
            sitrad = app.top_window()
            sitrad.set_focus()
            time.sleep(0.5)
        except Exception:
            self._log("ERRO: Sitrad Pro nao encontrado.")
            self._log("Abra o Sitrad, faca login e tente novamente.")
            return

        self._log("OK - Sitrad localizado.")

        # Clica no menu Configuracoes
        self._log("Abrindo menu Configuracoes...")
        try:
            clicou = False
            for aid in ("mnuiConfiguration", "mnuConfiguration"):
                try:
                    sitrad.child_window(auto_id=aid, control_type="Custom").click_input()
                    clicou = True
                    break
                except Exception:
                    pass
            if not clicou:
                # Fallback: segundo botao da toolbar (posicao)
                customs = [c for c in sitrad.descendants(control_type="Custom")
                           if c.rectangle().top < 80 and c.rectangle().height() > 20]
                customs.sort(key=lambda c: c.rectangle().left)
                if len(customs) >= 2:
                    customs[1].click_input()
                    clicou = True
            if not clicou:
                self._log("ERRO: botao Configuracoes nao encontrado.")
                return
            time.sleep(0.8)

            # Clica em Configuracoes dos servidores (via Desktop para pegar o popup)
            desktop = Desktop(backend='uia')
            encontrou = False
            for _ in range(10):
                for win in desktop.windows():
                    try:
                        for item in win.descendants(control_type="MenuItem"):
                            if "servidores" in item.window_text().lower():
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
                self._log("ERRO: item 'Configuracoes dos servidores' nao encontrado.")
                return
            time.sleep(1.2)
        except Exception as e:
            self._log(f"ERRO ao abrir menu: {e}")
            return

        # Navega na arvore de configuracoes
        self._log("Navegando para Licencas...")
        try:
            def clicar_tree(nome_parcial):
                for ti in sitrad.descendants(control_type="TreeItem"):
                    if nome_parcial.lower() in ti.window_text().lower():
                        if ti.rectangle().width() > 0:
                            ti.click_input()
                            time.sleep(0.4)
                            return True
                return False

            if not clicar_tree("Servidor Local"):
                self._log("ERRO: 'Servidor Local' nao encontrado.")
                return
            time.sleep(0.5)

            if not clicar_tree("gerais"):
                self._log("ERRO: 'Configuracoes gerais' nao encontrado.")
                return
            send_keys("{RIGHT}")  # expande o no
            time.sleep(0.8)

            # Abre Licencas com duplo clique
            abriu = False
            for ti in sitrad.descendants(control_type="TreeItem"):
                if ti.window_text() in ("Licencas", "Licenças") and ti.rectangle().width() > 0:
                    ti.double_click_input()
                    abriu = True
                    time.sleep(1.5)
                    break
            if not abriu:
                self._log("ERRO: 'Licencas' nao encontrado na arvore.")
                return
        except Exception as e:
            self._log(f"ERRO na navegacao: {e}")
            return

        # Clica no botao + (adicionar licenca)
        self._log("Abrindo wizard de nova licenca...")
        try:
            btn_add = sitrad.child_window(auto_id="btnAddLicense", control_type="Button")
            btn_add.click_input()
            time.sleep(1.5)
        except Exception as e:
            self._log(f"ERRO: botao + nao encontrado: {e}")
            return

        # Digita a chave
        self._log("Digitando a chave...")
        try:
            campo = sitrad.child_window(auto_id="txtLicenseKey", control_type="Edit")
            campo.wait("exists visible", timeout=5)
            campo.click_input()
            time.sleep(0.4)
            send_keys("{HOME}")        # vai para o inicio do campo mascarado
            time.sleep(0.1)
            send_keys("^a")            # seleciona tudo
            time.sleep(0.1)
            send_keys("{DELETE}")      # limpa o conteudo
            time.sleep(0.2)
            send_keys("{HOME}")        # volta ao inicio apos limpar
            time.sleep(0.1)
            send_keys(chave, pause=0.05)
            time.sleep(0.8)
        except Exception as e:
            self._log(f"ERRO ao digitar chave: {e}")
            try:
                sitrad.child_window(title="Cancelar", control_type="Button").click_input()
            except Exception:
                pass
            return

        # Clica em Proximo
        self._log("Confirmando...")
        try:
            for btn in sitrad.descendants(control_type="Button"):
                if "ximo" in btn.window_text():  # Proximo
                    btn.click_input()
                    time.sleep(2.0)
                    break
        except Exception as e:
            self._log(f"ERRO ao confirmar: {e}")
            return

        self._log("")
        self._log("CONCLUIDO! Verifique a tabela de licencas no Sitrad.")


if __name__ == "__main__":
    App().mainloop()
