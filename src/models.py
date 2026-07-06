"""
models.py — Modelos ORM SQLAlchemy para o SitradColetor
Suporta: TC-900E (temperatura), PCT-122E (refrigeração c/ pressão),
         TC-970E (temp+umidade), VX-series (inversor), etc.
"""

from datetime import datetime, UTC
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Instrument(Base):
    """Instrumento monitorado — pode ser real (Sitrad) ou virtual (emulador)."""
    __tablename__ = "instruments"

    id:             Mapped[int]  = mapped_column(Integer, primary_key=True, autoincrement=True)
    sitrad_id:      Mapped[int]  = mapped_column(Integer, unique=True, nullable=False)
    name:           Mapped[str]  = mapped_column(String, nullable=False)
    address:        Mapped[int]  = mapped_column(Integer, nullable=False)
    converter_name: Mapped[str]  = mapped_column(String, nullable=True)
    model_id:       Mapped[int]  = mapped_column(Integer, nullable=True)
    model_name:     Mapped[str]  = mapped_column(String, nullable=True)   # "PCT-122E plus", "TC-900E Log", etc.
    source:         Mapped[str]  = mapped_column(String, default="sitrad") # "sitrad" | "emulator"
    status:         Mapped[str]  = mapped_column(String, default="Unknown")
    enabled:        Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen:     Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                      default=lambda: datetime.now(UTC))
    last_seen:      Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                      default=lambda: datetime.now(UTC),
                                                      onupdate=lambda: datetime.now(UTC))

    readings:     Mapped[list["Reading"]]    = relationship(back_populates="instrument", lazy="noload")
    alarm_events: Mapped[list["AlarmEvent"]] = relationship(back_populates="instrument", lazy="noload")


class Reading(Base):
    """
    Leitura de sensores e saídas — campos genéricos + específicos por modelo.
    Campos não aplicáveis ao modelo ficam NULL.
    """
    __tablename__ = "readings"

    id:            Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int]      = mapped_column(ForeignKey("instruments.id"), nullable=False, index=True)
    timestamp:     Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                     default=lambda: datetime.now(UTC), index=True)

    # ── Sensores de temperatura (todos os modelos) ──────────────
    t1: Mapped[float | None] = mapped_column(Float, nullable=True)  # Sonda 1 / Gás sucção
    t2: Mapped[float | None] = mapped_column(Float, nullable=True)  # Sonda 2 / Gás descarga
    t3: Mapped[float | None] = mapped_column(Float, nullable=True)  # Sonda 3 / Câmara
    t4: Mapped[float | None] = mapped_column(Float, nullable=True)  # Sonda 4 / Aletado (PCT)

    # ── Pressões (PCT-122E plus, PCT-120E, PCT-410, etc.) ───────
    p1: Mapped[float | None] = mapped_column(Float, nullable=True)  # Pressão sucção (PSIG)
    p2: Mapped[float | None] = mapped_column(Float, nullable=True)  # Pressão descarga (PSIG)

    # ── Temperaturas de saturação e cálculos termodinâmicos ─────
    t_sat_p1:   Mapped[float | None] = mapped_column(Float, nullable=True)  # Tsat evaporação (°C)
    t_sat_p2:   Mapped[float | None] = mapped_column(Float, nullable=True)  # Tsat condensação (°C)
    superheat:  Mapped[float | None] = mapped_column(Float, nullable=True)  # Superaquecimento (K)
    subcooling: Mapped[float | None] = mapped_column(Float, nullable=True)  # Subresfriamento (K)

    # ── Saídas analógicas (PCT series) ──────────────────────────
    an1_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # Saída analógica 1 (%)
    an2_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # Saída analógica 2 (%)

    # ── Umidade (TC-970E Log) ────────────────────────────────────
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)  # UR %

    # ── Controle operacional ────────────────────────────────────
    setpoint:       Mapped[float | None] = mapped_column(Float, nullable=True)
    differential:   Mapped[float | None] = mapped_column(Float, nullable=True)
    process_status: Mapped[int | None]   = mapped_column(Integer, nullable=True)
    process_text:   Mapped[str | None]   = mapped_column(String, nullable=True)

    # ── Saídas digitais ─────────────────────────────────────────
    out_refrigeration: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # Compressor / OUT1
    out_fan:           Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # Ventilador / OUT2
    out_defrost:       Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # Degelo / OUT3
    out_buzzer:        Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # ── Alarmes ─────────────────────────────────────────────────
    alm_high_t1:    Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    alm_low_t1:     Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    alm_door:       Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    alm_high_press: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    alm_low_press:  Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # ── Erros de sonda ───────────────────────────────────────────
    err_s1: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    err_s2: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    err_s3: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # ── Modos especiais ──────────────────────────────────────────
    fast_freezing: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    economic_mode: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    instrument: Mapped["Instrument"] = relationship(back_populates="readings", lazy="noload")


class DiagnosisCase(Base):
    """
    Caso de diagnóstico confirmado pela equipe técnica.
    Alimenta a memória operacional da IA — RAG simplificado.
    """
    __tablename__ = "diagnosis_cases"

    id:              Mapped[int]  = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id:   Mapped[int]  = mapped_column(ForeignKey("instruments.id"), nullable=False, index=True)
    instrument_name: Mapped[str]  = mapped_column(String, nullable=False)

    # O que a IA diagnosticou
    ai_status:       Mapped[str]  = mapped_column(String, nullable=True)   # NORMAL/ATENÇÃO/CRÍTICO
    ai_diagnosis:    Mapped[str]  = mapped_column(String, nullable=True)   # texto do diagnóstico
    ai_cause:        Mapped[str]  = mapped_column(String, nullable=True)   # causa provável da IA

    # O que o técnico confirmou
    confirmed:       Mapped[bool] = mapped_column(Boolean, default=False)
    ai_was_correct:  Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # IA acertou?
    confirmed_cause: Mapped[str | None]  = mapped_column(String, nullable=True)   # causa real
    resolution:      Mapped[str | None]  = mapped_column(String, nullable=True)   # solução aplicada
    outcome:         Mapped[str | None]  = mapped_column(String, nullable=True)   # resultado
    confirmed_by:    Mapped[str | None]  = mapped_column(String, nullable=True)   # nome do técnico

    # Estado do sistema no momento
    symptom_summary: Mapped[str | None]  = mapped_column(String, nullable=True)   # resumo dos valores
    p1_at_fault:     Mapped[float | None] = mapped_column(Float, nullable=True)
    p2_at_fault:     Mapped[float | None] = mapped_column(Float, nullable=True)
    t3_at_fault:     Mapped[float | None] = mapped_column(Float, nullable=True)
    sh_at_fault:     Mapped[float | None] = mapped_column(Float, nullable=True)

    occurred_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                    default=lambda: datetime.now(UTC))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AlarmEvent(Base):
    """Evento de alarme — abertura e fechamento."""
    __tablename__ = "alarm_events"

    id:            Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int]      = mapped_column(ForeignKey("instruments.id"), nullable=False, index=True)
    code:          Mapped[str]      = mapped_column(String, nullable=False)
    description:   Mapped[str]      = mapped_column(String, nullable=False)
    severity:      Mapped[str]      = mapped_column(String, default="warning")
    started_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                     default=lambda: datetime.now(UTC))
    cleared_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active:     Mapped[bool]     = mapped_column(Boolean, default=True, index=True)

    # Aceite de atendimento
    assumed_by:  Mapped[str | None]      = mapped_column(String, nullable=True)
    assumed_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Validação do diagnóstico da IA pelo técnico responsável
    diagnostico_correto: Mapped[bool | None]     = mapped_column(Boolean, nullable=True)
    causa_real:          Mapped[str | None]      = mapped_column(String, nullable=True)
    avaliado_em:         Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    instrument: Mapped["Instrument"] = relationship(back_populates="alarm_events", lazy="noload")
