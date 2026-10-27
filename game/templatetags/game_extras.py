"""模板中的字典索引和游戏时长格式化工具。"""

from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    return mapping.get(key)


@register.filter
def duration(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
