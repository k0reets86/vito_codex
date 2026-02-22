"""Test balance checker module."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.balance_checker import BalanceChecker, ServiceBalance


async def test_check_all():
    """Check all service balances (real API calls)."""
    checker = BalanceChecker()
    balances = await checker.check_all()

    print(f"\nChecked {len(balances)} services:\n")
    for b in balances:
        if b.error:
            print(f"  {b.name}: ERROR — {b.error}")
        elif b.balance is not None:
            status = "LOW" if b.is_low else "OK"
            print(f"  {b.name}: ${b.balance:.2f} [{status}]")
        else:
            print(f"  {b.name}: {b.details}")

    # Format report
    report = checker.format_report(balances, include_internal={
        "daily_spent": 0.05,
        "daily_earned": 0.0,
        "daily_limit": 3.0,
    })
    print(f"\nFormatted report:\n{report}")

    # Check alerts
    alerts = checker.get_low_balance_alerts(balances)
    if alerts:
        print(f"\nAlerts: {alerts}")
    else:
        print("\nNo low balance alerts.")

    return balances


def test_format_report():
    """Test report formatting."""
    checker = BalanceChecker()
    balances = [
        ServiceBalance(name="anti_captcha", balance=10.0, is_low=False),
        ServiceBalance(name="anthropic", details={"status": "active"}),
        ServiceBalance(name="openai", balance=0, is_low=True, details={"threshold": 5.0}),
        ServiceBalance(name="replicate", error="Invalid API key"),
    ]

    report = checker.format_report(balances)
    print(f"\nFormatted report:\n{report}")
    assert "LOW" in report
    assert "WARNING" in report
    assert "anti_captcha" in report
    print("Format test: OK")


if __name__ == "__main__":
    test_format_report()
    asyncio.run(test_check_all())
    print("\nAll balance checker tests passed.")
