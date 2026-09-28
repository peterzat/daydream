"""The systemd units under ops/ (installed by ops/install-prod.sh)."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

UNITS = Path(__file__).resolve().parent.parent / "ops" / "systemd"


@pytest.mark.parametrize("name", ["daydream-keepsakes.service", "daydream-offsite.service"])
def test_operator_jobs_that_drop_to_the_service_user_can_use_sudo(name):
    """`bin/game prod keepsakes|offsite` runs its export as the daydream user
    through sudo; NoNewPrivileges would make that sudo fail, so the timer
    would fail every run while a hand run works (SECURITY WARN 2026-09-28)."""
    text = (UNITS / name).read_text()
    assert "bin/game prod" in text
    assert not any(line.strip().startswith("NoNewPrivileges=") for line in text.splitlines())


def test_the_prod_service_itself_keeps_no_new_privileges():
    text = (UNITS / "daydream-prod.service").read_text()
    assert "NoNewPrivileges=yes" in text
