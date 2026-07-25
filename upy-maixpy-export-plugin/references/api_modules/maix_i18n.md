# maix.i18n

Official URL: https://wiki.sipeed.com/maixpy/api/maix/i18n.html

Status: seed_reference

Brief: internationalization module.

Stage A policy: OCR and display text workflows may mention i18n prerequisites, but should not generate locale-file management unless explicitly requested.

Officially indexed callable surface:

```python
from maix import i18n

i18n.get_locale()
i18n.get_language_name()
i18n.load_trans_yaml(locales_dir)

translator = i18n.Trans()
translator.load(locales_dir)
translator.update_dict(locales_dict)
translator.tr(key, locale="")
translator.set_locale(locale)
translator.get_locale()
```

Restrictions:

- OCR recognition output can be sent as UTF-8 JSONL text without using `maix.i18n`.
- Do not create translation YAML files in stage A.
