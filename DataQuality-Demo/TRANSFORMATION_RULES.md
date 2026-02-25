# Transformation Rules Documentation

This document explains all the transformation rules defined in `config.yaml` that map source data fields to target data fields.

## Overview

The transformation rules are Python functions that take a source row and compute the corresponding value for the target system. Each rule is executed dynamically and can access any field from the source row using dictionary notation.

---

## ID Column Rules (Matching Keys)

These rules transform the identifying columns used to match records between source and target systems.

### 1. `newOrderId` - Order Identifier

**Purpose**: Generates a unique order identifier based on instrument type.

**Logic**:
- **SWAP instruments**: Appends leg ID to order ID
  - Format: `{orderId}_{legId}`
  - Example: `ORD1001_0`
  
- **BLOCK instruments**: Appends allocation and quote IDs
  - Format: `{orderId}_{allocationId}_{quoteId}`
  - Example: `ORD1001_ALLOC123_QUOTE456`
  
- **Other instruments**: Returns order ID as-is
  - Format: `{orderId}`
  - Example: `ORD1001`

**Source Fields**: `orderId`, `instType`, `l_id`, `allocationId`, `q_id`

---

### 2. `datetime_epoch` - Timestamp

**Purpose**: Converts timestamp to integer epoch format.

**Logic**:
- Converts float timestamp to integer string
- Handles conversion errors gracefully
- Returns empty string on failure

**Example**:
- Input: `1708857600.5`
- Output: `"1708857600"`

**Source Fields**: `datetime_epoch`

---

### 3. `executionType` - Transaction Type Mapping

**Purpose**: Maps source transaction types to target execution type codes.

**Mappings**:
| Source (`transactionType`) | Target (`executionType`) |
|----------------------------|--------------------------|
| NEW                        | NEWO                     |
| CONFIRMED                  | CONF                     |
| CANCELLED                  | CAMO                     |
| REJECTED                   | REMO                     |
| TRADE                      | FILL                     |
| TRADE_ACK                  | PARF                     |

**Example**:
- Input: `transactionType = "TRADE"`
- Output: `"FILL"`

**Source Fields**: `transactionType`

---

### 4. `transactionId` - Transaction Identifier

**Purpose**: Builds transaction ID from currency pair information.

**Logic**:
1. Checks if precious metals based on characters 2-3 of currency pair
   - Precious metals: AU (Gold), AG (Silver), PT (Platinum), PD (Palladium)
   
2. Determines prefix:
   - `PM` for precious metals
   - `FX` for foreign exchange
   
3. Adds 'X' prefix to currency pair for precious metals
   - `XAUUSD` for gold, `XAGUSD` for silver, etc.
   
4. Builds final ID: `{prefix}SPOT{currencyPair}`

**Examples**:
- FX: `tradeCurrencies = "EURUSD"` → `"FXSPOTEURUSD"`
- PM: `tradeCurrencies = "GAUUSD"` → `"PMSPOTXAUUSD"`

**Source Fields**: `tradeCurrencies`

---

### 5. `buySellIndicator` - Trade Direction

**Purpose**: Maps trade direction to standardized format.

**Mappings**:
| Source (`direction`) | Target (`buySellIndicator`) |
|---------------------|----------------------------|
| BUY                 | BUYI                       |
| SELL                | SELL                       |
| Other               | (empty)                    |

**Note**: The simplified version now does a straight mapping. The original complex version considered currency order and instrument type for potential flipping.

**Source Fields**: `direction`

---

### 6. `i_quantity` - Initial Quantity

**Purpose**: Returns quantity with potential negative sign based on direction matching.

**Logic**:
1. Gets allocation quantity from source
2. Returns as-is if empty or "NA"
3. Adds negative sign (`-`) if `directionMatchesRequest` is "false"
4. Returns positive value otherwise

**Examples**:
- `allocationQty = "1000"`, `directionMatchesRequest = "true"` → `"1000"`
- `allocationQty = "1000"`, `directionMatchesRequest = "false"` → `"-1000"`
- `allocationQty = "NA"` → `"NA"`

**Source Fields**: `allocationQty`, `directionMatchesRequest`

---

## Extra Column Rules (Additional Fields)

These rules transform additional fields that are not part of the matching key but are needed in the target system.

### 7. `location` - Market Code

**Purpose**: Cleans and standardizes market identifier code.

**Logic**:
1. Removes special characters and formatting artifacts:
   - Empty quotes: `''`
   - Braces: `{`, `}`
   - Labels: `MicCode=`
   - Empty parentheses: `()`
2. Returns `"XXXX"` as default if market code is empty
3. Otherwise returns cleaned code

**Examples**:
- Input: `"{MicCode=XLON}"`
- Output: `"XLON"`
- Input: `""`
- Output: `"XXXX"`

**Source Fields**: `mCode`

---

### 8. `multiplier` - Price Multiplier

**Purpose**: Returns fixed multiplier value.

**Logic**: Always returns `"1"`

**Use Case**: Used for price calculations where no scaling is needed.

---

### 9. `qCurrency` - Quote Currency

**Purpose**: Extracts quote currency from trading pair based on quote unit.

**Logic**:
1. Cleans currency codes:
   - `CNH` → `CNY` (Chinese Yuan offshore to onshore)
   - `SGX` → `SGD` (Singapore Exchange to Singapore Dollar)
   
2. Extracts currency:
   - If `q_unit = "BASE"`: Returns first 3 characters
   - If `q_unit = "COUNTER"`: Returns last 3 characters

**Examples**:
- `tradeCurrencies = "EURUSD"`, `q_unit = "BASE"` → `"EUR"`
- `tradeCurrencies = "EURUSD"`, `q_unit = "COUNTER"` → `"USD"`
- `tradeCurrencies = "GBPCNH"`, `q_unit = "COUNTER"` → `"CNY"` (after cleanup)

**Source Fields**: `tradeCurrencies`, `q_unit`

---

### 10. `pCurrency` - Price Currency

**Purpose**: Extracts price currency (always counter currency).

**Logic**:
1. Cleans currency codes (same as qCurrency)
2. Always returns last 3 characters of trading pair

**Examples**:
- `tradeCurrencies = "EURUSD"` → `"USD"`
- `tradeCurrencies = "GBPJPY"` → `"JPY"`
- `tradeCurrencies = "AUDCNH"` → `"CNY"` (after cleanup)

**Source Fields**: `tradeCurrencies`

---

### 11. `fCode` - Financial Instrument Code

**Purpose**: Generates financial code for forward (non-spot) instruments.

**Logic**:
1. Returns empty string for SPOT instruments:
   - `instType = "SPOT"`, OR
   - `tenor = "SPOT"` AND `instType` in ["BLOCK", "OUTRIGHT"]
   
2. For forward instruments:
   - Format: `FWD_{currencyPair}`
   - Example: `"FWD_EURUSD"`

**Examples**:
- SPOT: `instType = "SPOT"` → `""`
- Forward: `instType = "OUTRIGHT"`, `tenor = "1M"`, `tradeCurrencies = "EURUSD"` → `"FWD_EURUSD"`

**Source Fields**: `instType`, `tenor`, `tradeCurrencies`

---

### 12. `orderType` - Order Type Mapping

**Purpose**: Maps source order types to target codes.

**Mappings**:
| Source (`orderType`) | Target |
|---------------------|--------|
| QUOTED              | QOT    |
| MARKET              | MKT    |
| LIMIT               | LMT    |
| Other               | (empty)|

**Example**:
- Input: `orderType = "MARKET"`
- Output: `"MKT"`

**Source Fields**: `orderType`

---

### 13. `price` - Price Value

**Purpose**: Returns source price as-is (pass-through).

**Logic**:
- Simply returns the source price field stripped of whitespace
- All price scenario handling (missing, NA, negative) is controlled by the simulator script

**Example**:
- Input: `price = " 100.50 "`
- Output: `"100.50"`

**Source Fields**: `price`

**Note**: This is a simplified rule since the `simulate_price_scenarios.py` script handles all price-related data quality scenarios.

---

## Consistency Check Rules

These rules are used during consistency checking to compute expected values. They may differ slightly from transformation rules.

### `orderType` (Consistency Check)

**Purpose**: Same as transformation rule - maps order types to target codes.

**Logic**: Identical to the main `orderType` rule (no randomness).

**Mappings**: Same as transformation rule above.

**Note**: Previously, the transformation rule had randomness (QUOTED could be either QOT or RFS), but the consistency rule used regex `(QOT|RFS)` to accept both. Now both rules are simplified to always use QOT.

---

## Special Functions

### `additionalModifications`

**Purpose**: Handles special matching for BLOCK instruments using quote IDs.

**Logic**:
1. Checks if `target_quoteId` column exists
2. If exists, creates an alternative matching key using quote ID instead of order ID
3. Performs additional join on this alternative key
4. Returns combined results

**Use Case**: BLOCK trades may need to match on quote ID rather than order ID in some scenarios.

**Requirements**: Uses Polars DataFrame library (`pl.concat_str`, `pl.with_columns`)

---

## Configuration Structure

### ID Columns (Matching Keys)
These columns form the composite key for matching source and target records:
- `newOrderId`
- `buySellIndicator`
- `executionType`
- `datetime_epoch`
- `i_quantity`

### Timestamp Configuration
- **Source column**: `datetime_epoch`
- **Target column**: `datetime_epoch`
- **Delta tolerance**: 1 second

### Extra Columns to Fill
Additional fields populated in the augmented target:
- `orderType`
- `location`
- `multiplier`
- `pCurrency`
- `qCurrency`
- `fCode`
- `transactionId`
- `price`

### Consistency Check Columns
Fields validated for consistency between source and expected target values:
- `orderType`
- `location`
- `multiplier`
- `pCurrency`
- `qCurrency`
- `fCode`
- `transactionId`

**Note**: `price` is NOT in consistency check columns because price scenarios are controlled by the simulator.

---

## How Rules Are Used

### 1. Target Generation
When generating target records from source:
```python
for col in id_columns + extra_columns_to_fill:
    target_record[col] = transformation_rule[col](source_record)
```

### 2. Matching
Records are matched using the transformed ID columns:
```python
id_key = '--'.join([rule(source) for rule in id_column_rules])
```

### 3. Consistency Checking
For matched records, check if target values match expected values:
```python
expected_value = consistency_rule[col](source_record)
actual_value = target_record[col]
if expected_value != actual_value:
    augmented_target[col] = expected_value  # Fill correct value
```

---

## Example Record Transformation

**Source Record**:
```python
{
    'orderId': 'ORD1001',
    'instType': 'SPOT',
    'transactionType': 'TRADE',
    'tradeCurrencies': 'EURUSD',
    'direction': 'BUY',
    'allocationQty': '10000',
    'directionMatchesRequest': 'true',
    'mCode': 'XLON',
    'q_unit': 'BASE',
    'orderType': 'MARKET',
    'datetime_epoch': '1708857600',
    'price': '100.50'
}
```

**Target Record (After Transformation)**:
```python
{
    'newOrderId': 'ORD1001',                    # SPOT, no suffix
    'executionType': 'FILL',                    # TRADE → FILL
    'buySellIndicator': 'BUYI',                 # BUY → BUYI
    'i_quantity': '10000',                      # Positive (match=true)
    'datetime_epoch': '1708857600',             # Converted to int string
    'transactionId': 'FXSPOTEURUSD',           # FX + SPOT + pair
    'location': 'XLON',                         # Cleaned
    'multiplier': '1',                          # Fixed value
    'qCurrency': 'EUR',                         # BASE unit, first 3 chars
    'pCurrency': 'USD',                         # Last 3 chars
    'fCode': '',                                # Empty for SPOT
    'orderType': 'MKT',                         # MARKET → MKT
    'price': '100.50'                           # Pass-through
}
```

---

## Simplifications Made

The rules have been simplified from their original complex versions:

1. **newOrderId**: Removed complex buy/sell direction logic for BLOCK trades
2. **buySellIndicator**: Simplified from complex currency order flipping logic to direct mapping
3. **fCode**: Simplified from complex precious metal and currency ordering logic to simple FWD prefix
4. **orderType**: Removed randomness (QUOTED now always maps to QOT, not random QOT/RFS)
5. **qCurrency/pCurrency**: Removed extensive currency code replacements, kept only common ones

These simplifications make the rules easier to understand and maintain while preserving core functionality for the data quality simulator.

---

## Field Name Mapping Reference

| Source System Field        | Target System Field    | Description                  |
|---------------------------|------------------------|------------------------------|
| orderId                   | newOrderId             | Order identifier             |
| transactionType           | executionType          | Transaction type code        |
| direction                 | buySellIndicator       | Buy/Sell direction           |
| allocationQty             | i_quantity             | Initial quantity             |
| datetime_epoch            | datetime_epoch         | Timestamp (epoch seconds)    |
| tradeCurrencies           | transactionId          | Transaction identifier       |
| mCode                     | location               | Market/venue code            |
| (constant)                | multiplier             | Price multiplier (always 1)  |
| tradeCurrencies + q_unit  | qCurrency              | Quote currency               |
| tradeCurrencies           | pCurrency              | Price currency               |
| instType + tenor + pair   | fCode                  | Financial instrument code    |
| orderType                 | orderType              | Order type code              |
| price                     | price                  | Price value                  |

---

## Troubleshooting

### Common Issues

1. **Empty values returned**:
   - Check if source field exists in the row
   - Verify field names match exactly (case-sensitive)
   - Check for None values vs empty strings

2. **Type errors**:
   - All values are strings - use `str()` for conversion
   - Use `.get()` with default values for safety

3. **Missing fields**:
   - Use `row.get('field', '')` instead of `row['field']`
   - Provides empty string default if field missing

4. **Consistency check failures**:
   - Ensure consistency rule matches transformation rule logic
   - Check for regex patterns in consistency rules

---

## Best Practices

1. **Always return strings**: All rule functions must return string values
2. **Use `.get()` for safety**: Use `row.get('field', '')` to handle missing fields
3. **Strip whitespace**: Use `.strip()` on string inputs to remove leading/trailing spaces
4. **Handle empty values**: Check for empty strings and "NA" values explicitly
5. **Document logic**: Add comments explaining complex transformations
6. **Test edge cases**: Consider empty values, None, special characters

---

## Testing Rules

To test a specific rule transformation:

```python
from data_quality_agent.config import get_config

config = get_config("./config.yaml")
mapping = list(config['mappings'].values())[0]

# Load rule
import re
rule_code = mapping['rules']['newOrderId']
rule_namespace = {}
exec(rule_code, rule_namespace)
newOrderIdRule = rule_namespace['newOrderIdRule']

# Test with sample data
test_row = {
    'orderId': 'ORD1001',
    'instType': 'SWAP',
    'l_id': '1'
}

result = newOrderIdRule(test_row)
print(result)  # Should print: ORD1001_1
```

---

## Version History

- **v2.0** (Feb 2026): Simplified rules for easier understanding and maintenance
- **v1.0** (Original): Complex rules with extensive currency handling and conditional logic
