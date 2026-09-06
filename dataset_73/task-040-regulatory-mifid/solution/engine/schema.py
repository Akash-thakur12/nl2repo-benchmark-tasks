from __future__ import annotations

# MiFID II RTS 22 required transaction-report fields (canonical upper-case keys).
MANDATORY_FIELDS = ["LEI", "ISIN", "VENUE", "CAPACITY", "PRICE", "QTY", "TS", "SIDE"]

SIDES = {"BUY", "SELL"}
CAPACITIES = {"DEAL", "MTCH", "AOTC"}

# A small ISO 10383 MIC allow-list for the exercise.
KNOWN_MICS = {
    "XNAS", "XNYS", "XLON", "XPAR", "XETR", "XAMS", "XBRU", "XLIS",
    "XMIL", "XMAD", "XSWX", "XTKS", "XHKG", "BATE", "CHIX", "TRQX",
}
