"""Checks run in code on an AI-drafted blog post, against the source text the model read.

The model writes; these checks decide what counts as backed by a source. They are advice for the reviewing admin,
who must still confirm the review before the post can be published (see posts.update_post)."""
import re
import unicodedata

from .models import utcnow

MIN_CLAIMS = 3
# Share of the body's 8-word sequences also found in the sources above which the draft reads as copied.
OVERLAP_LIMIT = 0.15
SHINGLE = 8

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})

def normalise(text: str) -> str:
    """Lower case, straight quotes, single spaces, no punctuation at the ends, so a quote survives formatting changes."""
    text = unicodedata.normalize("NFKC", text or "").translate(_QUOTES).lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,;:'\"()[]-…")

def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9₹]+", normalise(text))

def quote_found(quote: str, text: str) -> bool:
    q = normalise(quote)
    if len(q) < 8:
        return False
    if q in normalise(text):
        return True
    # Same words in the same order, ignoring punctuation (PDF text loses commas and hyphens across lines).
    words = _words(quote)
    return len(words) >= 3 and " ".join(words) in " ".join(_words(text))

# Figures a reader would rely on: dates, rupee amounts, section numbers and case numbers.
_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
_MONTH_NUMBER = {m: i % 12 + 1 for i, m in enumerate("january february march april may june july august september october november december".split())}
_DAY_MONTH_YEAR = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+day\s+of)?\s+({_MONTHS})[a-z]*\.?,?\s+(\d{{4}})\b", re.IGNORECASE)
_MONTH_DAY_YEAR = re.compile(rf"\b({_MONTHS})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.IGNORECASE)
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")
_OTHER_FIGURES = re.compile("|".join(f"(?:{p})" for p in [
    r"(?:₹|\brs\.?|\binr)\s?[\d,]+(?:\.\d+)?(?:\s?(?:lakh|lakhs|crore|crores|cr))?",
    r"\bsections?\s+\d+[a-z]?(?:\s?\(\d+\))?",
    r"\b(?:w\.?p\.?|c\.?a\.?|s\.?l\.?p\.?|r\.?f\.?a\.?|m\.?f\.?a\.?|o\.?s\.?|c\.?c\.?|c\.?r\.?p\.?)\s?(?:\(c\)\s?)?no\.?\s?[\d/ -]+\d",
]), re.IGNORECASE)

def _month(name: str) -> int:
    name = name.lower()
    return next(n for full, n in _MONTH_NUMBER.items() if full.startswith(name[:3]))

def _dates(text: str) -> list[tuple[str, tuple[int, int, int]]]:
    """(as written, (year, month, day)) for every date in the text, whatever the format (Indian dd.mm.yyyy for numbers)."""
    found = []
    for m in _DAY_MONTH_YEAR.finditer(text):
        found.append((m.group(0), (int(m.group(3)), _month(m.group(2)), int(m.group(1)))))
    for m in _MONTH_DAY_YEAR.finditer(text):
        found.append((m.group(0), (int(m.group(3)), _month(m.group(1)), int(m.group(2)))))
    for m in _NUMERIC_DATE.finditer(text):
        found.append((m.group(0), (int(m.group(3)), int(m.group(2)), int(m.group(1)))))
    return found

def _figure_variants(figure: str) -> list[str]:
    f = normalise(figure)
    variants = {f, f.replace(",", "")}
    if re.match(r"^(₹|rs\.?|inr)", f):
        amount = re.sub(r"^(₹|rs\.?|inr)\s?", "", f)
        variants |= {amount, amount.replace(",", "")}
    return [v for v in variants if v]

def unverified_figures(body: str, sources: list[str]) -> list[str]:
    haystack = " ".join(normalise(s) for s in sources)
    flat = haystack.replace(",", "")
    source_dates = {value for text in sources for _, value in _dates(text)}
    missing: list[str] = []
    for written, value in _dates(body):
        if value not in source_dates and written not in missing:
            missing.append(written)
    for match in _OTHER_FIGURES.finditer(body):
        figure = match.group(0).strip()
        if not any(v in haystack or v in flat for v in _figure_variants(figure)) and figure not in missing:
            missing.append(figure)
    return missing

def _shingles(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}

def overlap(body: str, sources: list[str]) -> float:
    # Quoted passages are allowed to match the source, so leave them out.
    unquoted = re.sub(r"(?m)^>.*$", " ", body)
    unquoted = re.sub(r"[\"“][^\"”]{0,400}[\"”]", " ", unquoted)
    mine = _shingles(_words(unquoted))
    if not mine:
        return 0.0
    theirs: set[tuple[str, ...]] = set()
    for text in sources:
        theirs |= _shingles(_words(text))
    return round(len(mine & theirs) / len(mine), 3)

def run_checks(body: str, claims: list[dict], sources: list[dict], court: str = "") -> tuple[list[dict], dict]:
    """Mark each claim supported or not and summarise the checks. sources: [{"url", "text"}]."""
    by_url = {s["url"]: s.get("text", "") for s in sources}
    texts = [s.get("text", "") for s in sources if s.get("text")]
    checked = []
    for claim in claims:
        cited = by_url.get(claim.get("source_url", ""))
        supported = bool(cited and quote_found(claim.get("quote", ""), cited))
        if not supported and claim.get("quote"):
            # Right quote, wrong link: accept it but point at the source that has it.
            for url, text in by_url.items():
                if quote_found(claim["quote"], text):
                    claim = {**claim, "source_url": url}
                    supported = True
                    break
        checked.append({**claim, "supported": supported})

    figures = unverified_figures(body, texts)
    copied = overlap(body, texts)
    unsupported = sum(1 for c in checked if not c["supported"])
    warnings = []
    if not texts:
        warnings.append("No source text was stored, so nothing could be checked.")
    if unsupported:
        warnings.append(f"{unsupported} claim{'s are' if unsupported > 1 else ' is'} not backed by a quote in the sources.")
    if len(checked) < MIN_CLAIMS:
        warnings.append(f"Only {len(checked)} claim{'s' if len(checked) != 1 else ''} listed; expected at least {MIN_CLAIMS}.")
    if court and not any(normalise(court) in normalise(c.get("claim", "") + " " + c.get("quote", "")) for c in checked if c["supported"]):
        warnings.append(f"No supported claim names the court ({court}).")
    if figures:
        warnings.append(f"{len(figures)} date, amount or section number in the body is not in the sources.")
    if copied > OVERLAP_LIMIT:
        warnings.append(f"{round(copied * 100)}% of the wording matches the sources; rewrite in your own words.")
    return checked, {
        "claims": len(checked), "unsupported": unsupported, "unverified_figures": figures, "overlap": copied,
        "warnings": warnings, "checked_at": utcnow().isoformat(),
    }
