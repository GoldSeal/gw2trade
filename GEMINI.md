# Project: Guild Wars 2 Crafting Calculator

## General Project Instructions
- This project uses Python.
- When you geenrate new Python code, follow the existing coding style.
- Prefer functional programming paradigms where appropriate.
- Document architectual descisions

## Implementation rules

- Prefer the smallest change that solves the requested problem.
- Reuse existing components and design tokens before adding new ones.
- Do not introduce a dependency without explaining why it is needed.
- Preserve loading, empty, error, disabled, and success states.
- Never open, print, or modify `.env` files or credentials.
- Ask before changing authentication, database rules, or deployment settings.

## Coding Style
- Use PEP 8.

## Project structure
The project uses PyQt6 for UI, sqlalchemy for ORM, and alembic for DB schema changes.
The sources are in src/gw2trade.
Main file is trade_tracker.py
models.py contains the DB models
db.py contains sqlalchemy and alembic glue

I started refactoring the PI code in api.py
