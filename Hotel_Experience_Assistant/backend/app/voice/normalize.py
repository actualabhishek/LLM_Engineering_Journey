import re

# Hindi numbers 0-99 are irregular (not compositional like English), so each
# needs its own word. Indian numbering groups above that: hundred, thousand,
# lakh (10^5), crore (10^7).
_ONES = [
    "शून्य", "एक", "दो", "तीन", "चार", "पांच", "छह", "सात", "आठ", "नौ",
    "दस", "ग्यारह", "बारह", "तेरह", "चौदह", "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस",
    "बीस", "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस", "सत्ताईस", "अट्ठाईस", "उनतीस",
    "तीस", "इकतीस", "बत्तीस", "तैंतीस", "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस", "अड़तीस", "उनतालीस",
    "चालीस", "इकतालीस", "बयालीस", "तैंतालीस", "चवालीस", "पैंतालीस", "छियालीस", "सैंतालीस", "अड़तालीस", "उनचास",
    "पचास", "इक्यावन", "बावन", "तिरेपन", "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन", "उनसठ",
    "साठ", "इकसठ", "बासठ", "तिरेसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ", "उनहत्तर",
    "सत्तर", "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर", "छिहत्तर", "सतहत्तर", "अठहत्तर", "उन्यासी",
    "अस्सी", "इक्यासी", "बयासी", "तिरासी", "चौरासी", "पचासी", "छियासी", "सत्तासी", "अट्ठासी", "नवासी",
    "नब्बे", "इक्यानबे", "बानबे", "तिरानबे", "चौरानबे", "पंचानबे", "छियानबे", "सत्तानबे", "अट्ठानबे", "निन्यानबे",
]

# Numeral run, optionally ₹-prefixed and comma-grouped, not glued to a letter
# (so alphanumeric booking references like "SVH2K9F" are left untouched).
_NUMBER_RE = re.compile(r"(?<![A-Za-zऀ-ॿ])(₹\s?)?(\d[\d,]*)(?![A-Za-zऀ-ॿ])")


def _number_to_words(n: int) -> str:
    if n == 0:
        return _ONES[0]
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, n = divmod(n, 1_000)
    hundred, rest = divmod(n, 100)
    parts = []
    if crore:
        parts.append(f"{_number_to_words(crore)} करोड़")
    if lakh:
        parts.append(f"{_ONES[lakh]} लाख")
    if thousand:
        parts.append(f"{_ONES[thousand]} हज़ार")
    if hundred:
        parts.append(f"{_ONES[hundred]} सौ")
    if rest:
        parts.append(_ONES[rest])
    return " ".join(parts)


def to_hindi_speech_text(text: str) -> str:
    def replace(match: re.Match) -> str:
        is_rupee = match.group(1) is not None
        words = _number_to_words(int(match.group(2).replace(",", "")))
        return f"{words} रुपये" if is_rupee else words

    return _NUMBER_RE.sub(replace, text)
