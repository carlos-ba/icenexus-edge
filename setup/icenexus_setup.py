"""
IceNexus Configurador - Instalacao da Chave de API do Sitrad
Versao simplificada: apenas instala a chave de licenca da API.

O usuario deve:
1. Abrir o Sitrad Pro
2. Estar logado
3. Este configurador faz o restante automaticamente
"""
import customtkinter as ctk
import threading
import time
import sys

# ── Pywinauto (opcional, sem travar no import) ─────────────────────────────
try:
    from pywinauto import Application, Desktop
    PYWINAUTO_OK = True
except ImportError:
    PYWINAUTO_OK = False

# ── Tema ───────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COR_BG      = "#0d1117"
COR_PAINEL  = "#161b22"
COR_ACCENT  = "#00b4d8"
COR_VERDE   = "#06d6a0"
COR_AMARELO = "#ffd166"
COR_VERMELHO= "#ef476f"
COR_TEXTO   = "#e6edf3"
COR_MUTED   = "#8b949e"


class IceNexusApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("IceNexus Configurador  |  Ativacao da API")
        self.geometry("560x520")
        self.resizable(False, False)
        self.configure(fg_color=COR_BG)
        self._build_ui()

    # ── UI ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Cabecalho
        header = ctk.CTkFrame(self, fg_color=COR_PAINEL, corner_radius=0, height=70)
        header.pack(fill="x")
        ctk.CTkLabel(
            header, text="IceNexus Configurador",
            font=ctk.CTkFont(size=20, weight="bold"), text_color=COR_ACCENT
        ).pack(side="left", padx=20, pady=20)
        ctk.CTkLabel(
            header, text="Ativacao da Chave de API",
            font=ctk.CTkFont(size=12), text_color=COR_MUTED
        ).pack(side="left", padx=0, pady=20)

        # Instrucao
        instr = ctk.CTkFrame(self, fg_color=COR_PAINEL, corner_radius=8)
        instr.pack(fill="x", padx=20, pady=(18, 0))
        ctk.CTkLabel(
            instr,
            text=(
                "Antes de continuar:\n"
                "  1. Abra o Sitrad Pro e faca login\n"
                "  2. Clique em Configuracoes -> Configuracoes dos servidores\n"
                "  3. Expanda Servidor Local -> Configuracoes gerais\n"
                "  4. Clique em API -> Licencas\n\n"
                "Depois insira a chave abaixo e clique em Instalar."
            ),
            font=ctk.CTkFont(size=12),
            text_color=COR_TEXTO,
            justify="left",
            anchor="w",
        ).pack(padx=16, pady=14, fill="x")

        # Campo da chave
        campo = ctk.CTkFrame(self, fg_color="transparent")
        campo.pack(fill="x", padx=20, pady=(14, 0))
        ctk.CTkLabel(
            campo, text="Chave de licenca da API:",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=COR_TEXTO
        ).pack(anchor="w")
        self.entry_chave = ctk.CTkEntry(
            campo,
            placeholder_text="XXXXX-XXXXX-XXXXX-XXXXX",
            font=ctk.CTkFont(size=14, family="Consolas"),
            height=42,
            fg_color=COR_PAINEL,
            border_color=COR_ACCENT,
            text_color=COR_TEXTO,
        )
        self.entry_chave.pack(fill="x", pady=(6, 0))

        # Chave da instalacao (lida automaticamente)
        self.lbl_instalacao = ctk.CTkLabel(
            campo, text="Chave da instalacao: (aguardando...)",
            font=ctk.CTkFont(size=11), text_color=COR_MUTED
        )
        self.lbl_instalacao.pack(anchor="w", pady=(4, 0))

        # Botao Instalar
        self.btn_instalar = ctk.CTkButton(
            self,
            text="Instalar chave",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=46,
            fg_color=COR_ACCENT,
            hover_color="#0096b8",
            text_color="#000000",
            command=self._iniciar_instalacao,
        )
        self.btn_instalar.pack(fill="x", padx=20, pady=(18, 0))

        # Log
        log_frame = ctk.CTkFrame(self, fg_color=COR_PAINEL, corner_radius=8)
        log_frame.pack(fill="both", expand=True, padx=20, pady=14)
        self.log_box = ctk.CTkTextbox(
            log_frame, font=ctk.CTkFont(size=11, family="Consolas"),
            fg_color="transparent", text_color=COR_TEXTO,
            wrap="word", state="disabled",
        )
        self.log_box.pack(fill="both", expand=True, padx=8, pady=8)

        # Inicia leitura da chave de instalacao em background
        threading.Thread(target=self._ler_chave_instalacao, daemon=True).start()

    # ── Log ────────────────────────────────────────────────────────────────
    def log(self, msg, cor=None):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    # ── Leitura da chave da instalacao ────────────────────────────────────
    def _ler_chave_instalacao(self):
        """Tenta ler a chave de instalacao do Sitrad na tela de Licencas."""
        if not PYWINAUTO_OK:
            return
        for tentativa in range(10):
            time.sleep(2)
            try:
                app = Application(backend='uia').connect(title="SITRAD - 1.8.32")
                main = app.top_window()
                lbl = main.child_window(auto_id="lblInstallationKey", control_type="Text")
                texto = lbl.window_text().strip()
                # Texto e "Chave da Instalacao: XXXX-XXXX-..."
                if ":" in texto:
                    chave = texto.split(":", 1)[1].strip()
                    self.lbl_instalacao.configure(
                        text=f"Chave da instalacao: {chave}",
                        text_color=COR_VERDE
                    )
                    return
            except Exception:
                pass
        self.lbl_instalacao.configure(
            text="Chave da instalacao: (abra Licencas no Sitrad para exibir)",
            text_color=COR_AMARELO
        )

    # ── Instalacao ─────────────────────────────────────────────────────────
    def _iniciar_instalacao(self):
        chave = self.entry_chave.get().strip()
        if not chave:
            self.log("  Digite a chave de licenca antes de instalar.")
            return
        if not PYWINAUTO_OK:
            self.log("X  pywinauto nao disponivel.")
            return
        self.btn_instalar.configure(state="disabled", text="Instalando...")
        threading.Thread(target=self._instalar_thread, args=(chave,), daemon=True).start()

    def _instalar_thread(self, chave):
        try:
            self._instalar_chave(chave)
        except Exception as ex:
            self.log(f"X  Erro inesperado: {ex}")
            self.btn_instalar.configure(state="normal", text="Instalar chave")

    def _instalar_chave(self, chave):
        self.log("-" * 50)
        self.log("[1/5] Localizando o Sitrad Pro...")

        # Conecta ao Sitrad
        try:
            app = Application(backend='uia').connect(title="SITRAD - 1.8.32")
            main = app.top_window()
        except Exception as e:
            self.log(f"X  Sitrad Pro nao encontrado.")
            self.log(f"   Abra o Sitrad Pro e tente novamente.")
            self.btn_instalar.configure(state="normal", text="Instalar chave")
            return

        self.log("    OK Sitrad Pro localizado.")

        # Verifica se a tela de Licencas esta aberta
        self.log("[2/5] Verificando tela de Licencas...")
        licencas_abertas = False
        try:
            lbl = main.child_window(auto_id="lblInstallationKey", control_type="Text")
            lbl.wait("exists", timeout=3)
            licencas_abertas = True
            self.log("    OK Tela de Licencas ja esta aberta.")
        except Exception:
            pass

        if not licencas_abertas:
            self.log("    Abrindo Configuracoes dos servidores...")
            try:
                main.set_focus()
                time.sleep(0.3)
                menu_cfg = main.child_window(auto_id="mnuiConfiguration", control_type="Custom")
                menu_cfg.click_input()
                time.sleep(0.8)
                item = main.child_window(
                    title="Configuracoes dos servidores", control_type="MenuItem"
                )
                item.click_input()
                time.sleep(1.0)
                # Expande arvore
                try:
                    srv = main.child_window(title="Servidor Local", control_type="TreeItem")
                    srv.click_input()
                    srv.expand()
                    time.sleep(0.5)
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
                self.log("    OK Tela de Licencas aberta.")
            except Exception as e:
                self.log("X  Nao foi possivel abrir Licencas automaticamente.")
                self.log("   Navegue manualmente ate Licencas e tente novamente.")
                self.btn_instalar.configure(state="normal", text="Instalar chave")
                return

        # Clica no botao + (btnAddLicense)
        self.log("[3/5] Abrindo wizard de nova licenca...")
        try:
            main.set_focus()
            time.sleep(0.3)
            btn_add = main.child_window(auto_id="btnAddLicense", control_type="Button")
            btn_add.click_input()
            time.sleep(1.5)
        except Exception as e:
            self.log(f"X  Botao '+' nao encontrado: {e}")
            self.btn_instalar.configure(state="normal", text="Instalar chave")
            return

        # Preenche o campo de chave
        self.log("[4/5] Inserindo chave de licenca...")
        try:
            campo = main.child_window(auto_id="txtLicenseKey", control_type="Edit")
            campo.wait("exists visible", timeout=5)
            campo.click_input()
            time.sleep(0.3)
            campo.triple_click_input()
            campo.type_keys(chave, with_spaces=True)
            time.sleep(0.5)
        except Exception as e:
            self.log(f"X  Campo de chave nao encontrado: {e}")
            try:
                main.child_window(title="Cancelar", control_type="Button").click_input()
            except Exception:
                pass
            self.btn_instalar.configure(state="normal", text="Instalar chave")
            return

        # Verifica mensagem de validacao
        time.sleep(0.5)
        try:
            val_lbl = main.child_window(
                auto_id="lblLicenseKeyValidation", control_type="Text"
            )
            msg_val = val_lbl.window_text().strip()
            if msg_val:
                self.log(f"    Validacao: {msg_val}")
        except Exception:
            pass

        # Clica em Proximo
        self.log("[5/5] Confirmando (Proximo)...")
        try:
            btn_prox = main.child_window(title_re=".*Proximo.*|.*ximo.*", control_type="Button")
            btn_prox.click_input()
            time.sleep(2.0)
        except Exception as e:
            self.log(f"X  Botao Proximo nao encontrado: {e}")
            self.btn_instalar.configure(state="normal", text="Instalar chave")
            return

        # Verifica resultado
        time.sleep(1.0)
        try:
            tabela = main.child_window(auto_id="gdvLicenses", control_type="Table")
            rows = tabela.descendants(control_type="Custom")
            total_rows = len([r for r in rows if "Row" in r.window_text()])
            if total_rows > 0:
                self.log(f"\nSUCESSO! Licenca instalada com exito.")
                self.log(f"  Licencas ativas: {total_rows}")
            else:
                self.log("\nWizard concluido. Verifique a tabela no Sitrad.")
        except Exception:
            self.log("\nWizard concluido. Verifique a tabela no Sitrad.")

        self.log("-" * 50)
        self.btn_instalar.configure(state="normal", text="Instalar chave")


if __name__ == "__main__":
    app = IceNexusApp()
    app.mainloop()
