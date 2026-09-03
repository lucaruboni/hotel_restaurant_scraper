"""UI da terminale (rich): banner, progress bar, tabella riepilogo."""

from collections import Counter

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich import box

console = Console()


def print_banner(location: str, categories: list, source: str, max_results: int):
    text = (
        f"[bold]Zona:[/bold] {location}\n"
        f"[bold]Categorie:[/bold] {', '.join(categories)}\n"
        f"[bold]Sorgente dati:[/bold] {source}\n"
        f"[bold]Max risultati per categoria:[/bold] {max_results}"
    )
    console.print(
        Panel(text, title="[bold cyan]🏨 Hotel & Restaurant Scraper 🍽️[/bold cyan]", border_style="cyan", box=box.ROUNDED)
    )


def make_progress() -> Progress:
    return Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
        TimeElapsedColumn(),
        console=console,
    )


def print_place_found(name: str, category: str, has_email: bool, has_social: bool):
    icon = "🏨" if category == "hotel" else "🍽️"
    extras = []
    if has_email:
        extras.append("[green]email[/green]")
    if has_social:
        extras.append("[magenta]social[/magenta]")
    extra_txt = f" [dim]({', '.join(extras)})[/dim]" if extras else ""
    console.print(f"  {icon} [white]{name}[/white]{extra_txt}")


def print_warning(message: str):
    console.print(f"  [yellow]⚠ {message}[/yellow]")


def print_error(message: str):
    console.print(f"[bold red]✖ {message}[/bold red]")


def print_summary(results: list, output_path: str, elapsed_seconds: float):
    counts = Counter(r.category for r in results)
    with_email = sum(1 for r in results if r.email)
    with_social = sum(1 for r in results if r.instagram or r.facebook or r.linkedin)
    with_website = sum(1 for r in results if r.website)
    with_phone = sum(1 for r in results if r.phone)

    table = Table(title="Riepilogo risultati", box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
    table.add_column("Metrica")
    table.add_column("Valore", justify="right")

    table.add_row("Totale risultati", str(len(results)))
    for cat, n in counts.items():
        table.add_row(f"  di cui {cat}", str(n))
    table.add_row("Con sito web", str(with_website))
    table.add_row("Con email", str(with_email))
    table.add_row("Con almeno un social", str(with_social))
    table.add_row("Con telefono", str(with_phone))
    table.add_row("Tempo impiegato", f"{elapsed_seconds:.1f}s")

    console.print()
    console.print(table)
    console.print(Panel(f"[bold green]✔ File salvato in:[/bold green] {output_path}", border_style="green", box=box.ROUNDED))
