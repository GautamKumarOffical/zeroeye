# JSON Schemas

This directory contains JSON Schema definitions for data structures used in the Tent of Trials platform.

## Schemas

### order.schema.json

Describes the **Order** data structure used by the market engine (`market/types/types.go`). An Order represents a request to buy or sell a trading instrument with specific parameters including price, quantity, order type, and time-in-force policy.

**Validated against:**
- `examples/valid_limit_order.json` — A standard limit buy order
- `examples/valid_iceberg_order.json` — A partially-filled iceberg sell order
- `examples/invalid_missing_required.json` — Invalid order with bad side value and missing fields

## Validation

Validate schemas using any JSON Schema validator:

```bash
# Using jsonschema (Python)
pip install jsonschema
python -c "
import json, jsonschema
schema = json.load(open('schemas/order.schema.json'))
instance = json.load(open('schemas/examples/valid_limit_order.json'))
jsonschema.validate(instance, schema)
print('Valid!')
"

# Using ajx (Node.js)
npx ajx validate -s schemas/order.schema.json schemas/examples/valid_limit_order.json
```
