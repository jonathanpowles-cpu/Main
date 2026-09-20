# MyFitnessPal nutrient connector

Turns a nutrition information panel (a HelloFresh recipe card, a packet label,
a meal-kit sheet) into a private custom food in your MyFitnessPal account.

It is an [MCP](https://modelcontextprotocol.io) server plus a small CLI.
Claude reads the nutrients off the photo; the connector maps them to
MyFitnessPal's units and food schema and creates the food.

## How it works

```
photo of label ──► Claude reads "per serving" column
                        │
                        ▼
              preview_food (shows payload, you confirm)
                        │
                        ▼
              create_food ──► POST api.myfitnesspal.com/v2/foods
```

- Energy in kJ is converted to kcal (÷ 4.184); labels that print both use the printed kcal.
- Sodium, potassium and cholesterol go in as mg; everything else in grams.
- If the label has a "per 100 g" column, the serving weight is derived from the
  ratio (2680 kJ / 620 kJ per 100 g → 432 g) and a "1 g" serving size is added
  so the food can be logged by weight too.
- Foods are created **private** (not shared to the public database).

## Setup

```bash
pip install -r connectors/myfitnesspal/requirements.txt
```

### Authentication

MyFitnessPal has no public API, so the connector reuses the cookies of a
browser session where you are logged in to myfitnesspal.com. Provide one of:

| Variable | Value |
|----------|-------|
| `MFP_COOKIE_HEADER` | The full `Cookie:` request header from a logged-in myfitnesspal.com page (DevTools → Network → any request → Request Headers → Cookie) |
| `MFP_COOKIES_FILE` | Path to a Netscape `cookies.txt` export (e.g. from the "Get cookies.txt" browser extension) |

Cookies expire; if you see `MFPAuthError`, log in again and re-export.

### Register as a Claude connector

The server runs locally on the machine where Claude Desktop or Claude Code
runs, so install it there:

```bash
git clone https://github.com/jonathanpowles-cpu/Main.git
cd Main
pip install -r connectors/myfitnesspal/requirements.txt
```

**Claude Desktop** — add to `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`),
using the absolute path of your clone for `PYTHONPATH`:

```json
{
  "mcpServers": {
    "myfitnesspal": {
      "command": "python",
      "args": ["-m", "connectors.myfitnesspal", "serve"],
      "env": {
        "PYTHONPATH": "/path/to/Main",
        "MFP_COOKIE_HEADER": "…"
      }
    }
  }
}
```

Restart Claude Desktop; the connector appears under the tools menu.

**Claude Code** — from any directory:

```bash
claude mcp add myfitnesspal \
    -e PYTHONPATH=/path/to/Main -e MFP_COOKIE_HEADER="…" \
    -- python -m connectors.myfitnesspal serve
```

Then, in a chat, attach a photo of the label and say
"add this to MyFitnessPal as *Beef & garlic rice bowl* by HelloFresh".
Claude will call `preview_food`, show you the values, and call `create_food`
once you confirm.

## Tools

| Tool | Purpose |
|------|---------|
| `parse_nutrition_label(label_text)` | Parse panel text (`Protein (g) 36.9g 8.5g` …) into per-serving and per-100 g nutrients |
| `preview_food(name, nutrition, brand?, serving_description?, per_100g?, country_code?)` | Show the exact request body and a manual-entry list. Sends nothing |
| `create_food(…same args…)` | Create the food in MyFitnessPal |
| `create_food_from_label(name, label_text, brand?, …)` | Parse and create in one step |

`nutrition` takes the per-serving values: `calories` or `energy_kj` (one is
required), `protein_g`, `fat_g`, `saturated_fat_g`, `trans_fat_g`,
`polyunsaturated_fat_g`, `monounsaturated_fat_g`, `cholesterol_mg`,
`sodium_mg`, `potassium_mg`, `carbohydrates_g`, `fibre_g`, `sugars_g`,
`serving_weight_g`.

## CLI

```bash
# Parse a label pasted into a text file
python -m connectors.myfitnesspal parse label.txt

# Preview without sending anything
python -m connectors.myfitnesspal create --name "Beef & garlic rice bowl" \
    --brand HelloFresh --label label.txt --dry-run

# Create from explicit values
python -m connectors.myfitnesspal create --name "Beef & garlic rice bowl" \
    --brand HelloFresh --kj 2680 --protein 36.9 --fat 22.2 --saturated 9.4 \
    --carbs 70.7 --sugars 9 --sodium 1580 --fibre 8.5
```

`--dry-run` also prints a `manual_entry` list in the order of MyFitnessPal's
"Create a Food" form, as a fallback if the private endpoint changes.

## Caveats

- The endpoints (`/user/auth_token`, `/v2/foods`) are the ones the
  MyFitnessPal website uses, not a supported API. They can change without
  notice; the request shapes live in `mfp_client.py` and are easy to adjust.
- Only the HTTP calls are unverified against the live service; the
  payload mapping, parsing and auth flow are covered by `tests/test_mfp_*.py`
  and `tests/test_nutrition.py` with mocked HTTP.
