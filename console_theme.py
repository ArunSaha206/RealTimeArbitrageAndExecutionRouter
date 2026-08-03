from rich.console import Console
from rich.theme import Theme

# Minimalist theme: plain text, with targeted number highlighting
minimal_theme = Theme({
    "header": "bold white",
    "gain": "green",
    "loss": "red",
    "muted": "dim white",
})

console = Console(theme=minimal_theme)