# Control Tower deterministic visual baseline

This tool captures the approved Control Tower states without changing application code.

Profiles:

- `desk-1680x896`
- `office-1920x1080`

States:

1. overview
2. Temuan expanded
3. Manufacturing Order hover
4. Cek Stock selected (unmapped evidence state)
5. Manufacturing Order selected (mapped evidence state)
6. Purchase Order selected (mapped procurement route)

## First approved baseline

Keep the dashboard running at `http://127.0.0.1:8000`, then run:

```powershell
.\tools\control_tower_visual\capture-baseline.ps1
```

Review every generated image in:

```text
tests/visual/control-tower/baseline/
```

Do not treat the baseline as approved until the owner has visually reviewed it.

## Later regression check

```powershell
.\tools\control_tower_visual\check-visual.ps1
```

Results are written outside the baseline folder:

```text
artifacts/control-tower-visual/
```

The comparison allows a maximum changed-pixel ratio of 0.5% after ignoring per-channel differences of 12 or less. Any detected difference still requires human review; a passing pixel comparison does not prove business correctness.

The script uses the repository dashboard credentials through `src.utils.settings`. Environment variables `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD` can override them.
