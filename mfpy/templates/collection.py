"""Registered input templates."""

from mfpy.templates.example import template as example_template
from mfpy.templates.planner import template as planner_template

templates = {
    "Feature implementation": example_template,
    "Planner": planner_template,
}
