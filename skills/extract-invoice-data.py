#!/usr/bin/env python3
"""
Skill: Extract and verify a SINGLE invoice using Claude Agent SDK

This skill handles ONE invoice document (which may span multiple pages).
It performs WITHIN-DOCUMENT verification only.

Scope:
- Extract structured data from a single invoice (can be multi-page)
- Verify calculations WITHIN the invoice:
  * Sum of line items = subtotal
  * HST calculation (13% of subtotal)
  * Total calculation (subtotal + HST - holdback + misc)
- Return extraction results and verification status

Usage:
    python extract-invoice-data.py <image_path1> [image_path2...] --output-dir=/path/to/output

Output Files:

    1. invoice_data.json - Extracted invoice data:
    {
      "invoiceNumber": "INV-12345",
      "vendorName": "ABC Construction Ltd.",
      "invoiceDate": "2024-01-15",
      "totalPayableAmount": 11500.00,
      "subtotalAmount": 10000.00,
      "hstAmount": 1300.00,
      "holdbackAmount": 0.00,
      "miscellaneousAmount": 200.00,
      "lineItems": [
        {
          "description": "Labour - Week 1",
          "quantity": 40,
          "unit": "hours",
          "unitPrice": 125.00,
          "amount": 5000.00
        },
        {
          "description": "Materials - Lumber",
          "quantity": 1,
          "unit": "lot",
          "unitPrice": 5000.00,
          "amount": 5000.00
        }
      ]
    }

    2. verification_report.json - Verification results:
    {
      "passed": false,
      "checks": [
        {
          "name": "line_items_sum",
          "passed": true,
          "expected": 10000.00,
          "actual": 10000.00,
          "message": "Line items sum matches subtotal"
        },
        {
          "name": "hst_calculation",
          "passed": true,
          "expected": 1300.00,
          "actual": 1300.00,
          "tolerance": 0.01,
          "message": "HST calculation is correct (13% of subtotal)"
        },
        {
          "name": "total_calculation",
          "passed": false,
          "expected": 11300.00,
          "actual": 11500.00,
          "message": "Total does not match: subtotal + HST - holdback + misc"
        }
      ]
    }

    3. session_id.txt - Agent session ID for resumption

Returns:
    JSON with extraction status and session ID
"""

import sys
import os
import json
import argparse
from pathlib import Path
from pydantic import BaseModel
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage


# Define structured output schemas with Pydantic
class LineItem(BaseModel):
    description: str
    quantity: float
    unit: str
    unitPrice: float
    amount: float


class InvoiceData(BaseModel):
    invoiceNumber: str
    vendorName: str
    invoiceDate: str  # YYYY-MM-DD
    totalPayableAmount: float
    subtotalAmount: float
    hstAmount: float
    holdbackAmount: float
    miscellaneousAmount: float
    lineItems: list[LineItem]


class VerificationCheck(BaseModel):
    name: str
    passed: bool
    expected: float
    actual: float
    tolerance: float = 0.0
    message: str


class VerificationReport(BaseModel):
    passed: bool  # True only if ALL checks pass
    checks: list[VerificationCheck]


class InvoiceExtraction(BaseModel):
    """Combined schema for invoice extraction and verification"""
    invoice: InvoiceData
    verification: VerificationReport


async def extract_invoice_data(image_paths: list[str], output_dir: str):
    """
    Extract and verify invoice data from images using Agent SDK with structured outputs

    Args:
        image_paths: List of paths to invoice image files
        output_dir: Directory to save output files

    Returns:
        dict: Status and session information with typed invoice/verification data
    """
    # Validate inputs
    for img_path in image_paths:
        if not os.path.exists(img_path):
            return {
                "success": False,
                "error": f"Image file not found: {img_path}"
            }

    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Build file context for the agent
    files_context = "\n".join([f"- {path}" for path in image_paths])

    # Create extraction and verification prompt
    prompt = f"""You are an invoice data extraction and verification specialist.

**Available invoice image files:**
{files_context}

**Your task:**

1. **Read and analyze** the invoice images at the paths listed above using your Read tool

2. **Extract** all invoice information and perform verification checks.

The response will be structured output containing:
- **invoice**: All extracted invoice data (number, vendor, date, amounts, line items)
- **verification**: Results of validation checks on the extracted data

**Verification checks to perform:**
- **line_items_sum**: Sum all line item amounts and compare to subtotalAmount (must match exactly)
- **hst_calculation**: Calculate 13% of subtotal and compare to hstAmount (allow ±1% tolerance)
- **total_calculation**: Verify totalPayableAmount = subtotalAmount + hstAmount - holdbackAmount + miscellaneousAmount

Each check should include:
- whether it passed (bool)
- expected value (float)
- actual value (float)
- tolerance if applicable (float, default 0)
- descriptive message explaining the result

The overall verification.passed field should be true ONLY if ALL checks pass.
"""

    # Track session ID and structured output
    captured_session_id = None
    extraction_result = None

    try:
        # Call Agent SDK with structured output
        response = query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                model="claude-sonnet-4-5",
                allowed_tools=["Read"],
                permission_mode="acceptEdits",
                max_tokens=8192,
                output_format={
                    "type": "json_schema",
                    "schema": InvoiceExtraction.model_json_schema()
                }
            )
        )

        # Stream agent messages
        async for message in response:
            # Capture session ID from init message
            if message.type == "system" and message.subtype == "init":
                captured_session_id = message.session_id
                print(f"SESSION_ID:{message.session_id}", flush=True)

            # Print text messages
            elif message.type == "text":
                print(f"Agent: {message.content}", flush=True)

            # Print tool use
            elif message.type == "tool_use":
                tool_name = getattr(message, 'tool_name', 'unknown')
                print(f"Agent using tool: {tool_name}", flush=True)

            # Capture structured output from result message
            elif isinstance(message, ResultMessage):
                if message.subtype == "success" and message.structured_output:
                    # Validate with Pydantic
                    extraction_result = InvoiceExtraction.model_validate(message.structured_output)
                    print("\nExtraction complete!", flush=True)
                elif message.subtype == "error_max_structured_output_retries":
                    return {
                        "success": False,
                        "error": "Agent could not produce valid structured output after multiple attempts",
                        "session_id": captured_session_id
                    }

        if not extraction_result:
            return {
                "success": False,
                "error": "No structured output received from agent",
                "session_id": captured_session_id
            }

        # Save outputs to files for compatibility
        invoice_file = os.path.join(output_dir, "invoice_data.json")
        verification_file = os.path.join(output_dir, "verification_report.json")
        session_file = os.path.join(output_dir, "session_id.txt")

        with open(invoice_file, 'w') as f:
            json.dump(extraction_result.invoice.model_dump(), f, indent=2)

        with open(verification_file, 'w') as f:
            json.dump(extraction_result.verification.model_dump(), f, indent=2)

        if captured_session_id:
            with open(session_file, 'w') as f:
                f.write(captured_session_id)

        return {
            "success": True,
            "session_id": captured_session_id,
            "output_dir": output_dir,
            "verification_passed": extraction_result.verification.passed,
            "invoice": extraction_result.invoice.model_dump(),
            "verification": extraction_result.verification.model_dump(),
            "files": {
                "invoice_data": invoice_file,
                "verification_report": verification_file,
                "session_id": session_file if captured_session_id else None
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "session_id": captured_session_id
        }


if __name__ == "__main__":
    import asyncio

    parser = argparse.ArgumentParser(description="Extract and verify invoice data using Agent SDK")
    parser.add_argument("images", nargs="+", help="Invoice image file paths")
    parser.add_argument("--output-dir", required=True, help="Directory to save output files")

    args = parser.parse_args()

    result = asyncio.run(extract_invoice_data(args.images, args.output_dir))
    print(json.dumps(result, indent=2))

    sys.exit(0 if result["success"] else 1)
