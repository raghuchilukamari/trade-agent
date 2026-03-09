#!/usr/bin/env python3
"""
CLI runner for the Trading Analysis Agent pipeline.

Usage:
    python scripts/run_analysis.py --date 2026-03-06 --type weekday
    python scripts/run_analysis.py --date 2026-03-08 --type weekend
    python scripts/run_analysis.py  # defaults to today
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


async def main(target_date: date, analysis_type: str, data_dir: str | None):
    """Execute the daily analysis pipeline."""
    from app.core.database import db_manager
    from app.core.ollama_client import ollama_manager
    from app.core.polygon_client import polygon_manager
    from app.core.client import ServiceContainer
    from app.workers.daily_pipeline import DailyPipeline

    console.print(Panel(
        f"[bold blue]Trading Analysis Agent[/bold blue]\n"
        f"Date: {target_date.isoformat()}\n"
        f"Type: {analysis_type}\n"
        f"Data: {data_dir or 'default'}",
        title="🤖 Pipeline Starting",
    ))

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        # Initialize services
        task = progress.add_task("Initializing services...", total=None)
        await asyncio.gather(
            db_manager.initialize(),
            ollama_manager.initialize(),
            polygon_manager.initialize(),
        )
        progress.update(task, description="✅ Services initialized")

        # Create pipeline
        services = ServiceContainer(db=db_manager, llm=ollama_manager, polygon=polygon_manager)
        pipeline = DailyPipeline(services)

        # Execute
        progress.update(task, description="🔄 Running analysis pipeline...")
        result = await pipeline.execute(
            target_date=target_date,
            analysis_type=analysis_type,
            flow_data_dir=data_dir,
        )
        progress.update(task, description="✅ Pipeline complete")

    # Print results
    report = result.get("report", {})
    if report:
        console.print(Panel(
            report.get("executive_summary", "No summary"),
            title="📊 Executive Summary",
            border_style="green",
        ))

        if result.get("docx_path"):
            console.print(f"\n📄 Report saved to: [bold]{result['docx_path']}[/bold]")

    # Cleanup
    await db_manager.shutdown()
    await ollama_manager.shutdown()
    await polygon_manager.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trading Analysis Agent CLI")
    parser.add_argument("--date", type=str, default=None, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--type", type=str, default=None, choices=["weekday", "weekend"],
                        help="Analysis type (auto-detected if not set)")
    parser.add_argument("--data-dir", type=str, default=None, help="Override flow data directory")
    args = parser.parse_args()

    # Parse date
    if args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target = date.today()

    # Auto-detect type
    if args.type:
        atype = args.type
    else:
        atype = "weekend" if target.weekday() >= 5 else "weekday"

    asyncio.run(main(target, atype, args.data_dir))
