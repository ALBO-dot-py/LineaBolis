from enum import Enum

class Ruolo(str, Enum):
    """Ruoli disponibili per un utente"""
    admin = "A"
    nutrizionista = "N"
    paziente = "P"

class StatoUtente(str, Enum):
    """Stati disponibili per un utente"""
    attivo = "A"
    disattivo = "D"

class StatoAppuntamento(str, Enum):
    """Stati disponibili per un appuntamento"""
    proposta_paziente = "P"
    proposta_nutrizionista = "N"
    confermato = "C"
    rifiutato_nutrizionista = "R"
    rifiutato_paziente = "Q"
    rifiuto_automatico_nutrizionista = "D"
    rifiuto_automatico_paziente = "U"
    annullato_paziente = "A"
    annullato_nutrizionista = "X"
    disdetta_tardiva = "T"
    mancata_presenza = "M"
    eseguito = "E"

class AzioneAppuntamento(str, Enum):
    """Azioni consentite su un appuntamento"""
    accetta = "accetta"
    rifiuta = "rifiuta"
    annulla = "annulla"
    eseguito = "eseguito"
    mancata_presenza = "mancata-presenza"

class TipoDieta(str, Enum):
    """Tipologie disponibili per una dieta"""
    giornaliero = "G"
    settimanale = "S"

class StatoDieta(str, Enum):
    """Stati disponibili per una dieta"""
    attiva = "A"
    archiviata = "R"

class Sesso(str, Enum):
    """Valori disponibili per il sesso del paziente"""
    maschio = "M"
    femmina = "F"

class TipoDatoMedico(str, Enum):
    """Tipologie disponibili per un dato medico"""
    patologia = "P"
    allergia = "A"
    farmaco = "F"
    terapia = "T"

