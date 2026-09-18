from django import template

register = template.Library()


@register.filter
def get_attr(obj, field_path):
    """
    Usage: {{ object|get_attr:"property.name" }}
    Supports dotted paths for FK lookups (e.g. rt.property.name).
    """
    value = obj
    for part in field_path.split('.'):
        value = getattr(value, part, '')
        if callable(value):
            value = value()
    return value