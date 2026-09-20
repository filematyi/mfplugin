"""Registered input templates."""

from mfpy.templates.planner import template as planner_template
from mfpy.templates.plan_executor import template as plan_executor

templates = {
    "Planner": planner_template,
    "Plan Executor": plan_executor,
}
