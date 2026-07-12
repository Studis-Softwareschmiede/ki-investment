"""Secret-Hygiene-Helfer (Querschnitt, architecture.md §4 `app/core/`: „secrets").

Adapter dürfen Credentials (API-Keys/OAuth-Tokens) nie im Klartext loggen
(AC3, `docs/specs/dateneingang.md`; security-Floor `security/R01`).
`mask_secret` ist der gemeinsame Helfer dafür.

**Secret-Store-Auflösung mit strikter Paper/Live-Trennung (Story S-008,
`docs/specs/betriebssicherung.md` AC6):** `resolve_secret_store_zugang`
löst Zugangsdaten für einen Dienst (z. B. einen künftigen Broker-Adapter
aus `docs/specs/ausfuehrung-paper.md`) NIE hartkodiert, sondern
ausschließlich über Umgebungsvariablen auf — genau der Mechanismus, der
schon über `.env`/`.env.gpg` (`scripts/{encrypt,decrypt,load}-env.sh`)
committed/entschlüsselt wird (AC6: "niemals im Code oder in versionierten
Dateien"). Die eigentliche AC6-Anforderung dieser Story ist die **strikte
Trennung** zwischen `paper` und `live`: der Env-Var-Name trägt die Umgebung
als eigenes Namensraum-Segment (`{DIENST}_{UMGEBUNG}_...`, z. B.
`IBKR_PAPER_API_KEY` vs. `IBKR_LIVE_API_KEY`) — es gibt **keinen**
gemeinsamen Basisnamen mit einem Modus-Flag, das umgeschaltet werden
könnte, und **keinen** Fallback von `live` auf `paper` (oder umgekehrt).
Eine falsch konfigurierte/fehlende `live`-Variable liefert daher niemals
still den `paper`-Wert zurück, sondern schlägt hart mit
`SecretStoreFehler` fehl. Noch kein konkreter Dienst konsumiert diese
Funktion in dieser Story (kein Broker-Adapter existiert noch — Nicht-Ziel
dieses Board-Items); sie ist der Secret-Store-Baustein, an den künftige
Broker-/Handelsplattform-Adapter andocken.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from app.contracts.betriebssicherung import SecretStoreZugang, Umgebung


class SecretStoreFehler(RuntimeError):
    """Für den angeforderten Dienst/Umgebung liegt kein vollständiger
    Secret-Store-Eintrag vor (AC6) — fehlender/leerer Endpunkt oder
    API-Key. Es gibt bewusst KEINEN Fallback auf eine andere Umgebung."""


def resolve_secret_store_zugang(
    dienst: str,
    umgebung: Umgebung,
    *,
    env: Mapping[str, str] | None = None,
) -> SecretStoreZugang:
    """Löst die Zugangsdaten für `dienst` in genau `umgebung` auf (AC6).

    Env-Var-Namensschema (strikt getrennter Namensraum je Umgebung):
    `{DIENST}_{UMGEBUNG}_ENDPOINT`, `{DIENST}_{UMGEBUNG}_API_KEY`,
    optional `{DIENST}_{UMGEBUNG}_API_SECRET` (Gross-Umwandlung von
    `dienst`/`umgebung`). `env` ist injizierbar (Default `os.environ`),
    damit Tests ohne echte Prozess-Umgebungsvariablen laufen.

    Wirft `SecretStoreFehler`, wenn Endpunkt oder API-Key fehlen/leer sind
    — nie einen stillen Rückfall auf die jeweils andere Umgebung oder auf
    einen Platzhalterwert.
    """
    quelle = env if env is not None else os.environ
    praefix = f"{dienst.upper()}_{umgebung.upper()}"
    endpunkt = quelle.get(f"{praefix}_ENDPOINT")
    api_key = quelle.get(f"{praefix}_API_KEY")
    api_secret = quelle.get(f"{praefix}_API_SECRET") or None
    if not endpunkt or not api_key:
        raise SecretStoreFehler(
            f"Kein vollständiger Secret-Store-Eintrag für Dienst={dienst!r} "
            f"Umgebung={umgebung!r} — erwartet {praefix}_ENDPOINT + "
            f"{praefix}_API_KEY (getrennter Namensraum je Umgebung, AC6)."
        )
    return SecretStoreZugang(
        dienst=dienst,
        umgebung=umgebung,
        endpunkt=endpunkt,
        api_key=api_key,
        api_secret=api_secret,
    )


def mask_secret(value: str | None) -> str:
    """Maskiert ein Secret für Log-/Debug-Ausgaben — gibt NIE den Klartext zurück.

    Werte mit <= 4 Zeichen werden vollständig durch `*` ersetzt. Längere
    Werte behalten die ersten/letzten zwei Zeichen zur Wiedererkennbarkeit
    in Logs, der Rest wird maskiert. `None`/leer wird als `"<leer>"` markiert.
    """
    if not value:
        return "<leer>"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"
