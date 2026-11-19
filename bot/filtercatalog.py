"""What the panel offers for each filter of ``telemirror.messagefilters``:
its args (kind, default), which are asked for when it's added, where it goes
in the list — and how the panel names them (Russian)."""

# What the panel offers for each filter of telemirror/messagefilters: (arg, kind,
# default). Kinds: list-like — "set" (a !!set of strings), "list", "map"
# ("key => value"), "ids" (channel ids); scalars — "bool", "text", "number".
# An arg present in the file gets its kind from its value, so any hand-written
# arg of a known type is editable too; an arg of an unknown type is shown only.
LIST_KINDS = ("set", "list", "map", "ids")
SCALAR_KINDS = ("bool", "text", "number")
FILTER_ARGS: dict[str, tuple] = {
    "SkipWithKeywordsFilter": (("keywords", "set", None),),
    "AllowWithKeywordsFilter": (("keywords", "set", None),),
    "SkipWithUrlFilter": (("blacklist", "set", None),),
    "SkipUrlFilter": (("skip_mention", "bool", True),),
    "SkipAllFilter": (),
    "UrlMessageFilter": (("blacklist", "set", None), ("whitelist", "set", None), ("placeholder", "text", "***"),
                         ("filter_mention", "bool", False), ("filter_by_id_mention", "bool", False)),
    "KeywordReplaceFilter": (("keywords", "map", None),),
    "StripFooterFilter": (("max_lines", "number", 3),),
    "ForwardFormatFilter": (("format", "text", None),),
    "MappedNameForwardFormat": (("mapped", "map", None), ("format", "text", None)),
    "DocumentFilenameFilter": (("suffix", "text", ""), ("remove", "list", None)),
    # The rest of telemirror.watermark.processor.WatermarkConfig, with its defaults.
    "WatermarkRemovalFilter": (("remove_watermark", "bool", True), ("stamp_watermark", "bool", True),
                               ("template_path", "text", None), ("match_threshold", "number", 0.31),
                               ("channels", "ids", None),
                               ("scale_min", "number", 0.2), ("scale_max", "number", 1.0),
                               ("scale_steps", "number", 80), ("inpaint_dilate_px", "number", 6),
                               ("stamp_watermark_path", "text", None), ("stamp_opacity", "number", 0.55),
                               ("stamp_scale", "number", 0.35), ("stamp_video_max_duration_s", "number", 300.0),
                               ("stamp_video_preset", "text", "veryfast"), ("stamp_video_crf", "number", 18),
                               ("stamp_video_max_encode_s", "number", 180.0),
                               ("stamp_video_encode_realtime_ratio", "number", 0.73),
                               ("max_concurrent_video_encodes", "number", 1)),
    "RestrictSavingContentBypassFilter": (),
}
# Asked for when the filter is added: the filter can't be built without it.
REQUIRED_ARG = {"SkipWithKeywordsFilter": "keywords", "AllowWithKeywordsFilter": "keywords",
                "SkipWithUrlFilter": "blacklist", "KeywordReplaceFilter": "keywords"}
# Cheap filters that only drop messages: added before the transforming ones
# (the order rule of .configs/mirror.config.yml-example).
EARLY_FILTERS = frozenset({"SkipAllFilter", "SkipUrlFilter", "SkipWithUrlFilter", "SkipWithKeywordsFilter",
                           "AllowWithKeywordsFilter"})
# Goes right after them: it finds the source's tail by its links, which the
# transforming filters hide (UrlMessageFilter) or add (ForwardFormatFilter).
AFTER_EARLY_FILTERS = frozenset({"StripFooterFilter"})
# MappedNameForwardFormat needs both a mapping and a format to exist — hand-written only.
ADDABLE_FILTERS = tuple(n for n in FILTER_ARGS if n != "MappedNameForwardFormat")
_INT_KEY_MAPS = {("MappedNameForwardFormat", "mapped")}  # channel id → name
# A bool that may be a set of names instead (``filter_mention: [@a, @b]`` —
# only these): its first item replaces the bool, its last one going brings the default back.
BOOL_OR_SET = frozenset({("UrlMessageFilter", "filter_mention")})

# ── how the panel names them ────────────────────────────────────────────────
NAMES = {
    "SkipWithKeywordsFilter": "Пропускать посты со словами",
    "AllowWithKeywordsFilter": "Только посты со словами",
    "SkipWithUrlFilter": "Пропускать посты со ссылками на каналы",
    "SkipUrlFilter": "Пропускать посты с любыми ссылками",
    "SkipAllFilter": "Пауза: не копировать ничего",
    "UrlMessageFilter": "Прятать ссылки",
    "KeywordReplaceFilter": "Замена слов",
    "StripFooterFilter": "Убрать подпись источника",
    "ForwardFormatFilter": "Подпись с источником",
    "MappedNameForwardFormat": "Подпись со своими именами каналов",
    "DocumentFilenameFilter": "Переименование файлов",
    "WatermarkRemovalFilter": "Водяной знак",
    "RestrictSavingContentBypassFilter": "Обход запрета копирования",
}
ABOUT = {
    "SkipWithKeywordsFilter": "не копировать посты, в которых есть эти слова",
    "AllowWithKeywordsFilter": "копировать только посты, в которых есть эти слова",
    "SkipWithUrlFilter": "не копировать посты со ссылками на эти каналы или сайты",
    "SkipUrlFilter": "не копировать посты, в которых есть любая ссылка",
    "SkipAllFilter": "временно не копировать ничего — например, пока настраиваете",
    "UrlMessageFilter": "заменять ссылки в тексте на «***» (только в режиме «копия»)",
    "KeywordReplaceFilter": "заменять одни слова на другие (только в режиме «копия»)",
    "StripFooterFilter": "срезать в конце поста строки со ссылками и @упоминаниями — «Подпишись на @канал» "
                         "(только в режиме «копия»)",
    "ForwardFormatFilter": "добавлять к посту подпись с названием источника и ссылкой на него",
    "MappedNameForwardFormat": "подпись с заданными вами именами каналов",
    "DocumentFilenameFilter": "менять имена присланных файлов (только в режиме «копия»)",
    "WatermarkRemovalFilter": "убирать водяной знак источника с фото и видео и/или ставить свой "
                              "(только в режиме «копия»)",
    "RestrictSavingContentBypassFilter": "копировать фото и видео из каналов, где запрещено сохранение "
                                         "(ставьте после фильтра «Водяной знак»)",
}
# Shown on a filter's card only after 🔬 Тонкая настройка (or when set in the file).
ADVANCED_ARGS = frozenset({
    "match_threshold", "scale_min", "scale_max", "scale_steps", "inpaint_dilate_px",
    "stamp_video_max_duration_s", "stamp_video_preset", "stamp_video_crf", "stamp_video_max_encode_s",
    "stamp_video_encode_realtime_ratio", "max_concurrent_video_encodes",
})


def display_name(name: str) -> str:
    """A filter's name for people; a hand-written unknown one as it is."""
    return NAMES.get(name, name)


ARG_LABELS = {
    "keywords": "слова", "blacklist": "запрещённые ссылки", "whitelist": "разрешённые ссылки",
    "placeholder": "чем заменять", "filter_mention": "убирать @упоминания",
    "filter_by_id_mention": "убирать упоминания людей без @имени", "skip_mention": "и с @упоминаниями",
    "max_lines": "срезать строк со ссылками, не больше", "format": "вид подписи", "mapped": "имена каналов", "suffix": "добавлять к имени", "remove": "убирать из имени",
    "remove_watermark": "убирать знак источника", "stamp_watermark": "ставить свой знак",
    "template_path": "образец знака источника (файл на сервере)", "match_threshold": "точность поиска знака",
    "channels": "только для источников",
    "scale_min": "поиск знака: мин. масштаб", "scale_max": "поиск знака: макс. масштаб",
    "scale_steps": "поиск знака: шагов масштаба", "inpaint_dilate_px": "расширение области знака, px",
    "stamp_watermark_path": "свой знак (файл на сервере)", "stamp_opacity": "свой знак: прозрачность",
    "stamp_scale": "свой знак: размер", "stamp_video_max_duration_s": "видео со знаком: макс. длина, с",
    "stamp_video_preset": "видео: пресет x264", "stamp_video_crf": "видео: качество (CRF)",
    "stamp_video_max_encode_s": "видео: макс. время кодирования, с",
    "stamp_video_encode_realtime_ratio": "видео: скорость кодирования к реальному времени",
    "max_concurrent_video_encodes": "видео: кодировать одновременно",
}
