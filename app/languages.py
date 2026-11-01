"""The Try page's languages: speak any of them, hear it in any of them.

Each one: (name told to Meta's ears and to the brain, its own name, ElevenLabs language code).
The code is the voice: eleven_v4_turbo speaks 94 languages (its own list, checked 1 Nov 2026).
Eight of India's 22 languages have no voice yet (None): Meta still hears and translates them,
and the visitor reads the translation."""

INDIAN = [
    ("Assamese", "অসমীয়া", "as"), ("Bengali", "বাংলা", "bn"), ("Bodo", "बड़ो", None), ("Dogri", "डोगरी", None),
    ("Gujarati", "ગુજરાતી", "gu"), ("Hindi", "हिन्दी", "hi"), ("Kannada", "ಕನ್ನಡ", "kn"), ("Kashmiri", "کٲشُر", None),
    ("Konkani", "कोंकणी", None), ("Maithili", "मैथिली", None), ("Malayalam", "മലയാളം", "ml"),
    ("Manipuri", "মৈতৈলোন্", None), ("Marathi", "मराठी", "mr"), ("Nepali", "नेपाली", "ne"), ("Odia", "ଓଡ଼ିଆ", "or"),
    ("Punjabi", "ਪੰਜਾਬੀ", "pa"), ("Sanskrit", "संस्कृतम्", None), ("Santali", "ᱥᱟᱱᱛᱟᱲᱤ", None), ("Sindhi", "سنڌي", "sd"),
    ("Tamil", "தமிழ்", "ta"), ("Telugu", "తెలుగు", "te"), ("Urdu", "اردو", "ur"),
]

WORLD = [
    ("English", "English", "en"),
    ("Afrikaans", "Afrikaans", "af"), ("Amharic", "አማርኛ", "am"), ("Arabic", "العربية", "ar"), ("Armenian", "Հայերեն", "hy"),
    ("Asturian", "Asturianu", "ast"), ("Azerbaijani", "Azərbaycanca", "az"), ("Belarusian", "Беларуская", "be"),
    ("Bosnian", "Bosanski", "bs"), ("Bulgarian", "Български", "bg"), ("Burmese", "မြန်မာ", "my"),
    ("Cantonese", "粵語", "yue"), ("Catalan", "Català", "ca"), ("Cebuano", "Cebuano", "ceb"), ("Chichewa", "Chichewa", "ny"),
    ("Chinese", "中文", "zh"), ("Croatian", "Hrvatski", "hr"), ("Czech", "Čeština", "cs"), ("Danish", "Dansk", "da"),
    ("Dutch", "Nederlands", "nl"), ("Estonian", "Eesti", "et"), ("Filipino", "Filipino", "fil"), ("Finnish", "Suomi", "fi"),
    ("French", "Français", "fr"), ("Fula", "Pulaar", "ff"), ("Galician", "Galego", "gl"), ("Georgian", "ქართული", "ka"),
    ("German", "Deutsch", "de"), ("Greek", "Ελληνικά", "el"), ("Hausa", "Hausa", "ha"), ("Hebrew", "עברית", "he"),
    ("Hungarian", "Magyar", "hu"), ("Icelandic", "Íslenska", "is"), ("Indonesian", "Bahasa Indonesia", "id"),
    ("Irish", "Gaeilge", "ga"), ("Italian", "Italiano", "it"), ("Japanese", "日本語", "ja"), ("Javanese", "Basa Jawa", "jv"),
    ("Kamba", "Kikamba", "kam"), ("Kazakh", "Қазақша", "kk"), ("Korean", "한국어", "ko"),
    ("Kurdish (Sorani)", "کوردی", "ckb"), ("Kyrgyz", "Кыргызча", "ky"), ("Lao", "ລາວ", "lo"), ("Latvian", "Latviešu", "lv"),
    ("Lingala", "Lingála", "ln"), ("Lithuanian", "Lietuvių", "lt"), ("Luganda", "Luganda", "lg"),
    ("Luxembourgish", "Lëtzebuergesch", "lb"), ("Macedonian", "Македонски", "mk"), ("Malay", "Bahasa Melayu", "ms"),
    ("Maltese", "Malti", "mt"), ("Maori", "Te Reo Māori", "mi"), ("Mongolian", "Монгол", "mn"), ("Norwegian", "Norsk", "no"),
    ("Occitan", "Occitan", "oc"), ("Pashto", "پښتو", "ps"), ("Persian", "فارسی", "fa"), ("Polish", "Polski", "pl"),
    ("Portuguese", "Português", "pt"), ("Romanian", "Română", "ro"), ("Russian", "Русский", "ru"), ("Serbian", "Српски", "sr"),
    ("Shona", "chiShona", "sn"), ("Slovak", "Slovenčina", "sk"), ("Slovenian", "Slovenščina", "sl"),
    ("Somali", "Soomaali", "so"), ("Spanish", "Español", "es"), ("Swahili", "Kiswahili", "sw"), ("Swedish", "Svenska", "sv"),
    ("Tajik", "Тоҷикӣ", "tg"), ("Thai", "ไทย", "th"), ("Turkish", "Türkçe", "tr"), ("Ukrainian", "Українська", "uk"),
    ("Uzbek", "Oʻzbekcha", "uz"), ("Vietnamese", "Tiếng Việt", "vi"), ("Welsh", "Cymraeg", "cy"), ("Wolof", "Wolof", "wo"),
    ("Yoruba", "Yorùbá", "yo"), ("Zulu", "isiZulu", "zu"),
]

VOICE_CODE = {name: code for name, _, code in INDIAN + WORLD}   # name → ElevenLabs code (None: read only)


def for_the_page() -> dict:
    """What the Try page shows in its two lists: India's languages first, then the world's."""
    shown = lambda group: [{"name": n, "native": native, "code": code} for n, native, code in group]
    return {"india": shown(INDIAN), "world": shown(WORLD)}
