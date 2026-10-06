"""
Which labor classification (the unified trades list of the daily report) a day-labor worker's trade belongs to.

The roster's trade is free text written by whoever added the worker ("معلم طوبار", "Carpenter", "عامل عادي" ...), while
every worker-attendance row of a daily report must carry a classification from reports.master_data_models, so the
printed report can be grouped and subtotalled by trade. The mobile screen sets it from the worker's own trade with the
rules below; anything unknown falls back to "Unskilled Labor". It can still be corrected in the web report.
"""
import re

from reports.master_data_models import LaborClassification

FALLBACK = 'Unskilled Labor'

# (words found in the worker's trade, name of the classification) -- first match wins
KEYWORDS = [
    (('طوبار', 'نجار', 'carpent', 'formwork'), 'Carpenter'),
    (('كهرب', 'electric'), 'Electrician'),
    (('سباك', 'plumb'), 'Plumber 1st team'),
    (('دهان', 'paint'), 'Painter'),
    (('لحام', 'weld'), 'Welder'),
    (('قصار', 'plaster'), 'Plaster'),
    (('بلاط', 'tile'), 'Tile workers'),
    (('جبس', 'gypsum'), 'Gypsum Works'),
    (('حداد', 'iron', 'steel'), 'Iron sheet Workers'),
    (('الومنيوم', 'ألمنيوم', 'aluminium', 'aluminum'), 'Aluminium Workers'),
    (('حجر', 'masonry', 'stone'), 'Masonry'),
    (('بلوك', 'block'), 'Block Mason'),
    (('بناء', 'mason'), 'Masonry'),
    (('سائق', 'operator', 'حفار', 'جرافة'), 'Equipment Operator'),
    (('حارس', 'guard'), 'Guard'),
    (('مراقب', 'فني', 'معلم', 'skilled', 'foreman'), 'Skilled Labor'),
]


def classification_for(trade, cache=None):
    """The LaborClassification for a worker's trade text (never None unless the master data is empty)."""
    cache = cache if cache is not None else {}
    if not cache:
        cache.update({c.name.lower(): c for c in LaborClassification.objects.all()})
    text = re.sub(r'\s+', ' ', str(trade or '')).strip().lower()
    if text in cache:
        return cache[text]
    for words, name in KEYWORDS:
        if any(word in text for word in words) and name.lower() in cache:
            return cache[name.lower()]
    return cache.get(FALLBACK.lower()) or next(iter(cache.values()), None)
