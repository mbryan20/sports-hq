"""Team-name matching shared by the cards (CFBD names) and the line scanner (ESPN names). No numpy."""
import re, unicodedata

ALIASES = {"miami (fl)": "miami", "n. carolina": "north carolina", "sdsu": "san diego state",
           "connecticut": "uconn", "boston coll.": "boston college", "n. dak. st.": "north dakota state", "byu": "byu", "ole miss": "ole miss"}


def norm(name):
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()
    n = ALIASES.get(n, n)
    n = re.sub(r"\bst\.$", "state", n)
    return n.replace(".", "")
