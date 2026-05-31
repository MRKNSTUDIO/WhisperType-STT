# predownload_models.py
import questionary
from rich.console import Console
from rich.panel import Panel
from model_fetcher import fetch_available_whisper_models, is_installed, download_model, prettify
import tui

console = Console()

def main():
    console.print(Panel("[bold cyan]Model Download Wizard[/bold cyan]", expand=False, border_style="cyan"))
    console.print("\n[bold]Fetching available Whisper models from Hugging Face...[/bold]")

    models = fetch_available_whisper_models()
    if not models:
        tui.print_error("Could not fetch models from Hugging Face. Check your internet connection.")
        console.print("\nPress any key to continue...")
        input()
        return

    console.print(f"[green]Found {len(models)} available models.[/green]\n")

    choices = []
    for model in models:
        installed_marker = " [Installed]" if is_installed(model['id']) else ""
        choices.append(questionary.Choice(
            title=f"{model['name']}{installed_marker}",
            value=model['id']
        ))

    selected_models = questionary.checkbox(
        "Select models to download (use Space to select, Enter to confirm):",
        choices=choices
    ).ask()

    if not selected_models:
        console.print("\n[yellow]No models selected. Skipping download.[/yellow]")
        console.print("\nPress any key to continue...")
        input()
        return

    console.print(f"\n[bold]Downloading {len(selected_models)} model(s)...[/bold]\n")

    for model_id in selected_models:
        if is_installed(model_id):
            tui.print_info(f"Skipping {prettify(model_id)} (already installed)")
            continue

        tui.print_info(f"Downloading {prettify(model_id)}...")
        if download_model(model_id):
            tui.print_success(f"Downloaded {prettify(model_id)}")
        else:
            tui.print_error(f"Failed to download {prettify(model_id)}")

    console.print("\n[bold green]Download process complete![/bold green]")
    console.print("\nPress any key to continue...")
    input()

if __name__ == "__main__":
    main()
