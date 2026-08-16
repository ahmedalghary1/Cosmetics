"""Small, dependency-free SVG icon tags backed by vetted local assets."""

from functools import lru_cache
from pathlib import Path
import re

from django import template
from django.template import TemplateSyntaxError
from django.utils.html import format_html
from django.utils.safestring import mark_safe


register = template.Library()
ICON_DIR = Path(__file__).resolve().parent.parent / "icon_assets"
ICON_NAME = re.compile(r"^[a-z0-9-]+$")
SVG_BODY = re.compile(r"<svg\b[^>]*>(.*)</svg>\s*$", re.DOTALL)


@lru_cache(maxsize=128)
def _icon_body(name):
    if not ICON_NAME.fullmatch(name):
        raise TemplateSyntaxError(f"Invalid icon name: {name}")
    path = ICON_DIR / f"{name}.svg"
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise TemplateSyntaxError(f"Unknown local icon: {name}") from exc
    match = SVG_BODY.search(source)
    if not match:
        raise TemplateSyntaxError(f"Invalid SVG source for icon: {name}")
    return mark_safe(match.group(1).strip())


@register.simple_tag
def icon(name, css_class=""):
    """Render a decorative Lucide icon; the surrounding control owns its label."""
    return format_html(
        '<svg class="ui-icon {}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true" focusable="false">{}</svg>',
        css_class,
        _icon_body(name),
    )


@register.simple_tag
def brand_icon(name, css_class=""):
    """Render a decorative Simple Icons brand mark."""
    return format_html(
        '<svg class="ui-icon brand-icon {}" viewBox="0 0 24 24" fill="currentColor" '
        'aria-hidden="true" focusable="false">{}</svg>',
        css_class,
        _icon_body(f"brand-{name}"),
    )
