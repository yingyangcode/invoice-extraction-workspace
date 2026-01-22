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
from datetime import date
from pydantic import BaseModel, Field
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
)


# Define structured output schemas with Pydantic
class LineItem(BaseModel):
    description: str = Field(description="Description of the line item work or materials")
    quantity: float = Field(description="Quantity of the line item")
    unit: str = Field(description="Unit of measurement (e.g., hours, each, sq ft)")
    unitPrice: float = Field(description="Price per unit")
    amount: float = Field(description="Total amount for this line item (quantity × unitPrice)")


class InvoiceData(BaseModel):
    invoiceNumber: str = Field(description="Invoice number as shown on the document")
    vendorName: str = Field(description="Name of the vendor/contractor")
    invoiceDate: date = Field(description="Invoice date in YYYY-MM-DD format (convert from any format shown)")
    totalPayableAmount: float = Field(description="Total amount payable on the invoice")
    subtotalAmount: float = Field(description="Subtotal before taxes and other adjustments")
    hstAmount: float = Field(description="HST/tax amount (use 0.0 if not applicable)")
    holdbackAmount: float = Field(description="Holdback/retainage amount (use 0.0 if not applicable)")
    miscellaneousAmount: float = Field(description="Any miscellaneous charges or credits (use 0.0 if not applicable)")
    lineItems: list[LineItem] = Field(description="List of all line items from the invoice")


class VerificationCheck(BaseModel):
    name: str = Field(description="Name of the verification check (e.g., 'line_items_sum', 'hst_calculation', 'total_calculation')")
    passed: bool = Field(description="Whether this verification check passed")
    expected: float = Field(description="Expected value for this check")
    actual: float = Field(description="Actual calculated value")
    tolerance: float = Field(default=0.0, description="Tolerance allowed for this check (0.0 for exact match)")
    message: str = Field(default="", description="Human-readable message explaining the check result")


class VerificationReport(BaseModel):
    passed: bool = Field(description="True only if ALL verification checks passed")
    checks: list[VerificationCheck] = Field(description="List of all verification checks performed")


class InvoiceExtraction(BaseModel):
    """Combined schema for invoice extraction and verification"""
    invoice: InvoiceData = Field(description="Extracted invoice data including all line items and amounts")
    verification: VerificationReport = Field(description="Verification report with all calculation checks")


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

    # Create extraction and verification prompt - minimal and direct
    prompt = f"""Extract and verify invoice data from this image:

{files_context}

Extract the invoice information including vendor name, invoice number, date (in YYYY-MM-DD format), all line items, and amounts. Verify that line items sum to subtotal, HST is 13% of subtotal, and total equals subtotal + HST - holdback + miscellaneous. Use 0.0 for amounts not on the invoice.
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
                output_format={
                    "type": "json_schema",
                    "schema": InvoiceExtraction.model_json_schema()
                }
            )
        )

        # Stream agent messages
        async for message in response:
            # Capture session ID from SystemMessage with init subtype
            if isinstance(message, SystemMessage):
                if message.subtype == "init":
                    captured_session_id = message.data.get("session_id")
                    print(f"SESSION_ID:{captured_session_id}", flush=True)

            # Print text and tool use from AssistantMessage content blocks
            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(f"Agent: {block.text}", flush=True)
                    elif isinstance(block, ToolUseBlock):
                        print(f"Agent using tool: {block.name}", flush=True)

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
    parser.add_argument("--project-id", help="Project ID for linking invoice")
    parser.add_argument("--contract-id", help="Contract ID for linking invoice")
    parser.add_argument("--vendor-id", help="Vendor ID for linking invoice")
    parser.add_argument("--document-id", help="Document ID for linking invoice")

    args = parser.parse_args()

    result = asyncio.run(extract_invoice_data(args.images, args.output_dir))

    # Add context IDs to result if provided
    if args.project_id:
        result["projectId"] = args.project_id
    if args.contract_id:
        result["contractId"] = args.contract_id
    if args.vendor_id:
        result["vendorId"] = args.vendor_id
    if args.document_id:
        result["documentId"] = args.document_id

    print(json.dumps(result, indent=2))

    sys.exit(0 if result["success"] else 1)
