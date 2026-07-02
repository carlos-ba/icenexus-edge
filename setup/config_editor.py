"""
IceNexus Edge — Editor de Configuração de Cliente
Ferramenta de laboratório para preparar o client_config.json antes da visita de campo.
"""

import customtkinter as ctk
import json
import os
import subprocess
import threading
from pathlib import Path
from tkinter import messagebox, filedialog
import tkinter as tk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Paths ─────────────────────────────────────────────────────────────────────
EDITOR_DIR  = Path(__file__).parent
PROJECT_DIR = EDITOR_DIR.parent
CONFIG_DIR  = PROJECT_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "client_config.json"

# ── Cores ─────────────────────────────────────────────────────────────────────
COR_BG       = "#0d1117"
COR_SURFACE  = "#161b22"
COR_CARD     = "#1c2128"
COR_BORDER   = "#30363d"
COR_ACCENT   = "#00b4d8"
COR_GREEN    = "#06d6a0"
COR_YELLOW   = "#ffd166"
COR_RED      = "#ef476f"
COR_TEXT     = "#e6edf3"
COR_MUTED    = "#8b949e"

TIPOS_GRUPO = ["camara", "chiller", "freezer", "condicionador", "controlador"]
ICONES_TIPO = {
    "camara":        "❄",
    "chiller":       "🌡",
    "freezer":       "🧊",
    "condicionador": "💨",
    "controlador":   "📡",
}
SENSORES = ["t1", "t2", "t3", "t4"]


# ══════════════════════════════════════════════════════════════════════════════
class ConfigEditor(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("IceNexus Edge — Editor de Configuração")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(fg_color=COR_BG)

        self.config_data  = self._config_vazio()
        self.grupo_atual  = None   # índice do grupo selecionado
        self.inst_atual   = None   # índice do instrumento selecionado
        self.modificado   = False

        self._build_header()
        self._build_body()
        self._build_statusbar()

        self._carregar_config()
        self._atualizar_lista_grupos()

    # ── Config vazio ──────────────────────────────────────────────────────────

    def _config_vazio(self):
        return {
            "_modo":               "personalizado",
            "cliente":             "",
            "unidade":             "",
            "instalacao":          "",
            "responsavel_tecnico": "",
            "grupos":              [],
        }

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        h = ctk.CTkFrame(self, fg_color=COR_SURFACE, corner_radius=0, height=64)
        h.pack(fill="x")
        h.pack_propagate(False)

        ctk.CTkLabel(h, text="❄ IceNexus Edge",
                     font=ctk.CTkFont("Arial", 20, "bold"),
                     text_color=COR_ACCENT).place(x=20, y=10)
        ctk.CTkLabel(h, text="Editor de Configuração de Cliente",
                     font=ctk.CTkFont("Arial", 11),
                     text_color=COR_MUTED).place(x=22, y=38)

        # Botões direita
        btn_frame = ctk.CTkFrame(h, fg_color="transparent")
        btn_frame.place(relx=1.0, x=-16, rely=0.5, anchor="e")

        ctk.CTkButton(btn_frame, text="📂 Abrir",    width=90, height=32,
                      fg_color=COR_CARD, border_color=COR_BORDER, border_width=1,
                      hover_color="#252d38",
                      command=self._abrir_config).pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="💾 Salvar",   width=90, height=32,
                      fg_color=COR_ACCENT, hover_color="#009ab8",
                      command=self._salvar_config).pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="🚀 Testar",   width=90, height=32,
                      fg_color=COR_GREEN, text_color="#000", hover_color="#04b888",
                      command=self._testar_dashboard).pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="🆕 Novo",     width=80, height=32,
                      fg_color=COR_CARD, border_color=COR_BORDER, border_width=1,
                      hover_color="#252d38",
                      command=self._novo_config).pack(side="left", padx=4)

    # ── Body ──────────────────────────────────────────────────────────────────

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=0, pady=0)

        # Coluna esquerda — dados do cliente + lista de grupos
        self.col_esq = ctk.CTkFrame(body, fg_color=COR_SURFACE,
                                     corner_radius=0, width=320)
        self.col_esq.pack(side="left", fill="y")
        self.col_esq.pack_propagate(False)

        # Coluna direita — edição do grupo/instrumento selecionado
        self.col_dir = ctk.CTkFrame(body, fg_color=COR_BG, corner_radius=0)
        self.col_dir.pack(side="left", fill="both", expand=True)

        self._build_col_esquerda()
        self._build_col_direita()

    def _build_col_esquerda(self):
        pad = {"padx": 16}

        ctk.CTkLabel(self.col_esq, text="DADOS DO CLIENTE",
                     font=ctk.CTkFont("Arial", 10, "bold"),
                     text_color=COR_MUTED).pack(pady=(16, 6), **pad, anchor="w")

        campos = [
            ("Cliente",              "cliente"),
            ("Unidade / Filial",     "unidade"),
            ("Data de instalação",   "instalacao"),
            ("Responsável técnico",  "responsavel_tecnico"),
        ]
        self._entries = {}
        for label, key in campos:
            ctk.CTkLabel(self.col_esq, text=label,
                         font=ctk.CTkFont("Arial", 11),
                         text_color=COR_MUTED).pack(**pad, anchor="w")
            e = ctk.CTkEntry(self.col_esq, height=32,
                              fg_color=COR_CARD, border_color=COR_BORDER,
                              font=ctk.CTkFont("Arial", 12))
            e.pack(fill="x", **pad, pady=(2, 8))
            e.bind("<KeyRelease>", lambda ev, k=key: self._on_field_change(k))
            self._entries[key] = e

        # Modo
        ctk.CTkLabel(self.col_esq, text="Modo",
                     font=ctk.CTkFont("Arial", 11),
                     text_color=COR_MUTED).pack(**pad, anchor="w")
        self.modo_var = ctk.StringVar(value="personalizado")
        seg = ctk.CTkSegmentedButton(self.col_esq,
                                      values=["personalizado", "automatico"],
                                      variable=self.modo_var,
                                      command=self._on_modo_change)
        seg.pack(fill="x", **pad, pady=(2, 16))

        # Separator
        ctk.CTkFrame(self.col_esq, fg_color=COR_BORDER, height=1).pack(fill="x")

        # Grupos
        header_frame = ctk.CTkFrame(self.col_esq, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(12, 6))
        ctk.CTkLabel(header_frame, text="GRUPOS",
                     font=ctk.CTkFont("Arial", 10, "bold"),
                     text_color=COR_MUTED).pack(side="left")
        ctk.CTkButton(header_frame, text="+ Grupo", width=72, height=26,
                      fg_color=COR_ACCENT, hover_color="#009ab8",
                      font=ctk.CTkFont("Arial", 11),
                      command=self._novo_grupo).pack(side="right")

        self.lista_grupos = ctk.CTkScrollableFrame(self.col_esq,
                                                    fg_color="transparent",
                                                    height=240)
        self.lista_grupos.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_col_direita(self):
        self.frame_vazio = ctk.CTkFrame(self.col_dir, fg_color="transparent")
        self.frame_vazio.place(relx=.5, rely=.45, anchor="center")
        ctk.CTkLabel(self.frame_vazio, text="Selecione um grupo →",
                     font=ctk.CTkFont("Arial", 14),
                     text_color=COR_MUTED).pack()
        ctk.CTkLabel(self.frame_vazio,
                     text="Clique em um grupo na lista à esquerda\npara editar seus instrumentos.",
                     font=ctk.CTkFont("Arial", 11),
                     text_color=COR_BORDER, justify="center").pack(pady=6)

        self.frame_grupo_editor = ctk.CTkFrame(self.col_dir, fg_color="transparent")

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_statusbar(self):
        sb = ctk.CTkFrame(self, fg_color=COR_SURFACE,
                          corner_radius=0, height=30)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self.lbl_status = ctk.CTkLabel(sb, text=f"Config: {CONFIG_FILE}",
                                        font=ctk.CTkFont("Arial", 10),
                                        text_color=COR_MUTED)
        self.lbl_status.place(x=12, rely=.5, anchor="w")
        self.lbl_modif = ctk.CTkLabel(sb, text="",
                                       font=ctk.CTkFont("Arial", 10),
                                       text_color=COR_YELLOW)
        self.lbl_modif.place(relx=1.0, x=-12, rely=.5, anchor="e")

    def _set_status(self, msg, modificado=None):
        self.lbl_status.configure(text=msg)
        if modificado is not None:
            self.modificado = modificado
            self.lbl_modif.configure(text="● não salvo" if modificado else "✓ salvo")

    # ══════════════════════════════════════════════════════════════════════════
    # Dados do cliente
    # ══════════════════════════════════════════════════════════════════════════

    def _on_field_change(self, key):
        self.config_data[key] = self._entries[key].get().strip()
        self._set_status(f"Config: {CONFIG_FILE}", modificado=True)

    def _on_modo_change(self, val):
        self.config_data["_modo"] = val
        self._set_status(f"Config: {CONFIG_FILE}", modificado=True)

    def _preencher_campos(self):
        for key, entry in self._entries.items():
            entry.delete(0, "end")
            entry.insert(0, self.config_data.get(key, ""))
        self.modo_var.set(self.config_data.get("_modo", "personalizado"))

    # ══════════════════════════════════════════════════════════════════════════
    # Lista de grupos
    # ══════════════════════════════════════════════════════════════════════════

    def _atualizar_lista_grupos(self):
        for w in self.lista_grupos.winfo_children():
            w.destroy()

        grupos = self.config_data.get("grupos", [])
        if not grupos:
            ctk.CTkLabel(self.lista_grupos,
                         text="Nenhum grupo.\nClique em '+ Grupo'.",
                         font=ctk.CTkFont("Arial", 11),
                         text_color=COR_MUTED, justify="center").pack(pady=20)
            return

        for i, grupo in enumerate(grupos):
            icone = ICONES_TIPO.get(grupo.get("tipo", ""), "📡")
            n_inst = len(grupo.get("instrumentos", []))
            selecionado = (i == self.grupo_atual)

            row = ctk.CTkFrame(self.lista_grupos,
                               fg_color=COR_ACCENT if selecionado else COR_CARD,
                               corner_radius=8, height=52)
            row.pack(fill="x", pady=3)
            row.pack_propagate(False)

            ctk.CTkLabel(row, text=icone, font=ctk.CTkFont("Arial", 16),
                         text_color="white" if selecionado else COR_TEXT
                         ).place(x=10, y=14)
            ctk.CTkLabel(row, text=grupo.get("nome", f"Grupo {i+1}"),
                         font=ctk.CTkFont("Arial", 12, "bold"),
                         text_color="white" if selecionado else COR_TEXT
                         ).place(x=38, y=8)
            ctk.CTkLabel(row, text=f"{n_inst} instrumento{'s' if n_inst != 1 else ''}",
                         font=ctk.CTkFont("Arial", 10),
                         text_color="rgba(255,255,255,.7)" if selecionado else COR_MUTED
                         ).place(x=38, y=28)

            ctk.CTkButton(row, text="✕", width=24, height=24,
                          fg_color="transparent", hover_color=COR_RED,
                          text_color=COR_MUTED,
                          command=lambda idx=i: self._remover_grupo(idx)
                          ).place(relx=1.0, x=-6, y=14, anchor="ne")

            row.bind("<Button-1>", lambda e, idx=i: self._selecionar_grupo(idx))
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda e, idx=i: self._selecionar_grupo(idx))

    def _novo_grupo(self):
        grupo = {
            "id":           f"grupo_{len(self.config_data['grupos'])+1}",
            "nome":         "Novo Grupo",
            "tipo":         "controlador",
            "icone":        "📡",
            "instrumentos": [],
        }
        self.config_data["grupos"].append(grupo)
        self.grupo_atual = len(self.config_data["grupos"]) - 1
        self._atualizar_lista_grupos()
        self._abrir_editor_grupo(self.grupo_atual)
        self._set_status(f"Config: {CONFIG_FILE}", modificado=True)

    def _remover_grupo(self, idx):
        nome = self.config_data["grupos"][idx].get("nome", f"Grupo {idx+1}")
        if not messagebox.askyesno("Remover grupo",
                                    f"Remover '{nome}' e todos os seus instrumentos?"):
            return
        self.config_data["grupos"].pop(idx)
        if self.grupo_atual == idx:
            self.grupo_atual = None
            self._mostrar_vazio()
        elif self.grupo_atual and self.grupo_atual > idx:
            self.grupo_atual -= 1
        self._atualizar_lista_grupos()
        self._set_status(f"Config: {CONFIG_FILE}", modificado=True)

    def _selecionar_grupo(self, idx):
        self.grupo_atual = idx
        self.inst_atual  = None
        self._atualizar_lista_grupos()
        self._abrir_editor_grupo(idx)

    def _mostrar_vazio(self):
        self.frame_grupo_editor.place_forget()
        self.frame_vazio.place(relx=.5, rely=.45, anchor="center")

    # ══════════════════════════════════════════════════════════════════════════
    # Editor de grupo
    # ══════════════════════════════════════════════════════════════════════════

    def _abrir_editor_grupo(self, idx):
        self.frame_vazio.place_forget()
        for w in self.frame_grupo_editor.winfo_children():
            w.destroy()
        self.frame_grupo_editor.place(x=0, y=0, relwidth=1, relheight=1)

        grupo = self.config_data["grupos"][idx]

        # ── Cabeçalho do grupo ───────────────────────────────────────────────
        top = ctk.CTkFrame(self.frame_grupo_editor, fg_color=COR_SURFACE,
                           corner_radius=0, height=58)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="Editar Grupo",
                     font=ctk.CTkFont("Arial", 10, "bold"),
                     text_color=COR_MUTED).place(x=20, y=8)

        nome_var = ctk.StringVar(value=grupo.get("nome", ""))
        nome_entry = ctk.CTkEntry(top, textvariable=nome_var, width=220, height=30,
                                   fg_color=COR_CARD, border_color=COR_BORDER,
                                   font=ctk.CTkFont("Arial", 13, "bold"))
        nome_entry.place(x=20, y=26)

        tipo_var = ctk.StringVar(value=grupo.get("tipo", "controlador"))
        tipo_menu = ctk.CTkOptionMenu(top, values=TIPOS_GRUPO,
                                       variable=tipo_var, width=140, height=30,
                                       fg_color=COR_CARD,
                                       button_color=COR_BORDER,
                                       dropdown_fg_color=COR_CARD)
        tipo_menu.place(x=252, y=26)

        def on_grupo_change(*_):
            grupo["nome"]  = nome_var.get().strip()
            grupo["tipo"]  = tipo_var.get()
            grupo["icone"] = ICONES_TIPO.get(tipo_var.get(), "📡")
            self._atualizar_lista_grupos()
            self._set_status(f"Config: {CONFIG_FILE}", modificado=True)

        nome_var.trace_add("write", on_grupo_change)
        tipo_var.trace_add("write", on_grupo_change)

        # ── Área principal: lista instrumentos + painel edição ───────────────
        area = ctk.CTkFrame(self.frame_grupo_editor, fg_color="transparent")
        area.pack(fill="both", expand=True, padx=20, pady=16)

        # Lista de instrumentos (esquerda)
        col_lista = ctk.CTkFrame(area, fg_color=COR_SURFACE, corner_radius=10, width=280)
        col_lista.pack(side="left", fill="y", padx=(0, 12))
        col_lista.pack_propagate(False)

        hdr = ctk.CTkFrame(col_lista, fg_color="transparent", height=40)
        hdr.pack(fill="x", padx=12, pady=(12, 6))
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="INSTRUMENTOS",
                     font=ctk.CTkFont("Arial", 10, "bold"),
                     text_color=COR_MUTED).place(x=0, rely=.5, anchor="w")
        ctk.CTkButton(hdr, text="+ Add", width=60, height=26,
                      fg_color=COR_ACCENT, hover_color="#009ab8",
                      font=ctk.CTkFont("Arial", 11),
                      command=lambda: self._novo_instrumento(idx, lista_frame, col_form)
                      ).place(relx=1.0, rely=.5, anchor="e")

        lista_frame = ctk.CTkScrollableFrame(col_lista, fg_color="transparent")
        lista_frame.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        # Formulário de instrumento (direita)
        col_form = ctk.CTkFrame(area, fg_color="transparent")
        col_form.pack(side="left", fill="both", expand=True)

        self._renderizar_lista_instrumentos(idx, lista_frame, col_form)

    def _renderizar_lista_instrumentos(self, grupo_idx, lista_frame, col_form):
        for w in lista_frame.winfo_children():
            w.destroy()

        grupo = self.config_data["grupos"][grupo_idx]
        insts = grupo.get("instrumentos", [])

        if not insts:
            ctk.CTkLabel(lista_frame, text="Sem instrumentos.\nClique em '+ Add'.",
                         font=ctk.CTkFont("Arial", 11),
                         text_color=COR_MUTED, justify="center").pack(pady=20)
            return

        for i, inst in enumerate(insts):
            selecionado = (i == self.inst_atual)
            row = ctk.CTkFrame(lista_frame,
                               fg_color=COR_ACCENT if selecionado else COR_CARD,
                               corner_radius=8, height=48)
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)

            nome = inst.get("nome_exibicao", f"Instrumento {i+1}")
            sid  = inst.get("sitrad_id", "?")
            ctk.CTkLabel(row, text=nome[:28] + ("…" if len(nome) > 28 else ""),
                         font=ctk.CTkFont("Arial", 11, "bold"),
                         text_color="white" if selecionado else COR_TEXT
                         ).place(x=10, y=6)
            ctk.CTkLabel(row, text=f"ID: {sid}",
                         font=ctk.CTkFont("Arial", 10),
                         text_color="rgba(255,255,255,.6)" if selecionado else COR_MUTED
                         ).place(x=10, y=26)

            ctk.CTkButton(row, text="✕", width=22, height=22,
                          fg_color="transparent", hover_color=COR_RED,
                          text_color=COR_MUTED,
                          command=lambda gi=grupo_idx, ii=i: self._remover_instrumento(gi, ii, lista_frame, col_form)
                          ).place(relx=1.0, x=-4, y=13, anchor="ne")

            row.bind("<Button-1>", lambda e, ii=i: self._selecionar_instrumento(grupo_idx, ii, lista_frame, col_form))
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda e, ii=i: self._selecionar_instrumento(grupo_idx, ii, lista_frame, col_form))

    def _novo_instrumento(self, grupo_idx, lista_frame, col_form):
        grupo = self.config_data["grupos"][grupo_idx]
        inst  = {
            "sitrad_id":       len(grupo.get("instrumentos", [])) + 1,
            "nome_exibicao":   "Novo Instrumento",
            "setpoint_ref":    None,
            "alarme_min":      None,
            "alarme_max":      None,
            "sensor_principal": "t1",
            "notas":           "",
        }
        grupo.setdefault("instrumentos", []).append(inst)
        self.inst_atual = len(grupo["instrumentos"]) - 1
        self._renderizar_lista_instrumentos(grupo_idx, lista_frame, col_form)
        self._abrir_form_instrumento(grupo_idx, self.inst_atual, lista_frame, col_form)
        self._set_status(f"Config: {CONFIG_FILE}", modificado=True)

    def _remover_instrumento(self, grupo_idx, inst_idx, lista_frame, col_form):
        grupo = self.config_data["grupos"][grupo_idx]
        nome  = grupo["instrumentos"][inst_idx].get("nome_exibicao", "instrumento")
        if not messagebox.askyesno("Remover", f"Remover '{nome}'?"):
            return
        grupo["instrumentos"].pop(inst_idx)
        if self.inst_atual == inst_idx:
            self.inst_atual = None
            for w in col_form.winfo_children():
                w.destroy()
        self._renderizar_lista_instrumentos(grupo_idx, lista_frame, col_form)
        self._atualizar_lista_grupos()
        self._set_status(f"Config: {CONFIG_FILE}", modificado=True)

    def _selecionar_instrumento(self, grupo_idx, inst_idx, lista_frame, col_form):
        self.inst_atual = inst_idx
        self._renderizar_lista_instrumentos(grupo_idx, lista_frame, col_form)
        self._abrir_form_instrumento(grupo_idx, inst_idx, lista_frame, col_form)

    # ══════════════════════════════════════════════════════════════════════════
    # Formulário de instrumento
    # ══════════════════════════════════════════════════════════════════════════

    def _abrir_form_instrumento(self, grupo_idx, inst_idx, lista_frame, col_form):
        for w in col_form.winfo_children():
            w.destroy()

        grupo = self.config_data["grupos"][grupo_idx]
        inst  = grupo["instrumentos"][inst_idx]

        def field(parent, label, key, largura=220, converter=None):
            ctk.CTkLabel(parent, text=label,
                         font=ctk.CTkFont("Arial", 11),
                         text_color=COR_MUTED).pack(anchor="w")
            v = ctk.StringVar(value=str(inst.get(key, "") or ""))
            e = ctk.CTkEntry(parent, textvariable=v, width=largura, height=32,
                              fg_color=COR_CARD, border_color=COR_BORDER,
                              font=ctk.CTkFont("Arial", 12))
            e.pack(anchor="w", pady=(2, 10))

            def on_change(*_):
                raw = v.get().strip()
                if converter:
                    try:    inst[key] = converter(raw) if raw else None
                    except: pass
                else:
                    inst[key] = raw
                self._set_status(f"Config: {CONFIG_FILE}", modificado=True)
                if key == "nome_exibicao":
                    self._renderizar_lista_instrumentos(grupo_idx, lista_frame, col_form)

            v.trace_add("write", on_change)
            return v

        ctk.CTkLabel(col_form, text="INSTRUMENTO",
                     font=ctk.CTkFont("Arial", 10, "bold"),
                     text_color=COR_MUTED).pack(anchor="w", pady=(0, 8))

        grid = ctk.CTkFrame(col_form, fg_color="transparent")
        grid.pack(fill="x")

        col1 = ctk.CTkFrame(grid, fg_color="transparent")
        col1.pack(side="left", fill="x", expand=True, padx=(0, 12))
        col2 = ctk.CTkFrame(grid, fg_color="transparent")
        col2.pack(side="left", fill="x", expand=True)

        # Coluna 1
        field(col1, "Nome de exibição",  "nome_exibicao")
        field(col1, "ID Sitrad (sitrad_id)", "sitrad_id", converter=int)
        field(col1, "Setpoint referência (°C)", "setpoint_ref", converter=float)

        # Coluna 2
        field(col2, "Alarme mínimo (°C)", "alarme_min", converter=float)
        field(col2, "Alarme máximo (°C)", "alarme_max", converter=float)

        # Sensor principal
        ctk.CTkLabel(col2, text="Sensor principal",
                     font=ctk.CTkFont("Arial", 11),
                     text_color=COR_MUTED).pack(anchor="w")
        sensor_var = ctk.StringVar(value=inst.get("sensor_principal", "t1"))
        seg = ctk.CTkSegmentedButton(col2, values=SENSORES,
                                      variable=sensor_var, width=220, height=30)
        seg.pack(anchor="w", pady=(2, 10))
        sensor_var.trace_add("write", lambda *_: inst.update(
            sensor_principal=sensor_var.get()) or self._set_status(
            f"Config: {CONFIG_FILE}", modificado=True))

        # Notas
        ctk.CTkLabel(col_form, text="Notas / observações",
                     font=ctk.CTkFont("Arial", 11),
                     text_color=COR_MUTED).pack(anchor="w", pady=(4, 2))
        txt_notas = ctk.CTkTextbox(col_form, height=70, fg_color=COR_CARD,
                                    border_color=COR_BORDER, border_width=1,
                                    font=ctk.CTkFont("Arial", 11))
        txt_notas.pack(fill="x")
        txt_notas.insert("1.0", inst.get("notas", ""))
        txt_notas.bind("<KeyRelease>", lambda e: inst.update(
            notas=txt_notas.get("1.0", "end").strip()) or self._set_status(
            f"Config: {CONFIG_FILE}", modificado=True))

        # Dica sobre o sitrad_id
        ctk.CTkLabel(col_form,
                     text="ℹ  O 'ID Sitrad' é o ID numérico do instrumento retornado pela API do Sitrad\n"
                          "   (visível no banco após a primeira sincronização).",
                     font=ctk.CTkFont("Arial", 10),
                     text_color=COR_MUTED, justify="left").pack(anchor="w", pady=(12, 0))

    # ══════════════════════════════════════════════════════════════════════════
    # Arquivo
    # ══════════════════════════════════════════════════════════════════════════

    def _carregar_config(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    self.config_data = json.load(f)
                self._preencher_campos()
                self._set_status(f"Carregado: {CONFIG_FILE}", modificado=False)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível ler o config:\n{e}")
        else:
            self._set_status(f"Novo: {CONFIG_FILE}", modificado=False)

    def _salvar_config(self):
        # Limpa campos de instrução antes de salvar
        data = {k: v for k, v in self.config_data.items()
                if not k.startswith("_instrucoes")}
        data["_modo"] = self.modo_var.get()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._set_status(f"Salvo: {CONFIG_FILE}", modificado=False)
            messagebox.showinfo("Salvo", f"Configuração salva em:\n{CONFIG_FILE}")
        except Exception as e:
            messagebox.showerror("Erro ao salvar", str(e))

    def _abrir_config(self):
        if self.modificado:
            if not messagebox.askyesno("Alterações não salvas",
                                        "Há alterações não salvas. Deseja descartar?"):
                return
        path = filedialog.askopenfilename(
            title="Abrir configuração",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
            initialdir=str(CONFIG_DIR),
        )
        if path:
            global CONFIG_FILE
            CONFIG_FILE = Path(path)
            self.grupo_atual = None
            self.inst_atual  = None
            self._mostrar_vazio()
            self._carregar_config()
            self._atualizar_lista_grupos()

    def _novo_config(self):
        if self.modificado:
            if not messagebox.askyesno("Alterações não salvas",
                                        "Descartar alterações e criar novo config?"):
                return
        self.config_data  = self._config_vazio()
        self.grupo_atual  = None
        self.inst_atual   = None
        self._preencher_campos()
        self._atualizar_lista_grupos()
        self._mostrar_vazio()
        self._set_status("Novo config (não salvo)", modificado=True)

    def _testar_dashboard(self):
        self._salvar_config()
        # Abre o dashboard no navegador
        import webbrowser
        try:
            webbrowser.open("http://localhost:8100")
            self._set_status("Dashboard aberto em http://localhost:8100", modificado=False)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir o navegador:\n{e}")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ConfigEditor()
    app.mainloop()
