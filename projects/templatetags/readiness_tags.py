from django import template

from projects import readiness

register = template.Library()


@register.simple_tag
def project_readiness(project):
    """{% project_readiness project as r %} -- r.ok, r.problems (each with .code, .message, .detail)."""
    return readiness.check(project)
