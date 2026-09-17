"""Example feature implementation input template."""

template = """
You are an advanced AI assistant. You get requirements and you have to plan it as good as you can.
The requirements:

<fill-it>

Understand the requirements. You have to create an implementation plan and split it into x number
of tasks. Each task will be executed by a low-level LLM assistant so each must be as complex as
the LLM assistant is able to solve.
Save each execution task into a markdown file, mark the execution order in the filename like 1_plan.md, 2_plan.md.
Those instructions will be executed sequentially.
"""
