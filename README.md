# Agent Workspace

This package contains the agent workspace for Claude Agent SDK, including:
- **Skills**: Reusable Python scripts that agents can execute
- **Prompts**: Prompt templates for different tasks
- **Tools**: Custom tools for Agent SDK

## Structure

```
agent-workspace/
├── skills/           # Python skills agents can execute
│   ├── extract-pdf-images.py      # Convert PDF to PNG images
│   └── extract-invoice-data.py    # Extract & verify invoice data
├── prompts/          # Prompt templates
├── tools/            # Custom Agent SDK tools
└── requirements.txt  # Python dependencies
```

## Usage in E2B Sandbox

This workspace is cloned into E2B sandboxes and used by agents:

```typescript
// Clone workspace into sandbox
await sandbox.commands.run(
  "git clone /path/to/monorepo /home/user/workspace"
);

// Install dependencies
await sandbox.commands.run(
  "cd /home/user/workspace/packages/agent-workspace && pip install -r requirements.txt"
);

// Run agent skill
await sandbox.process.start({
  cmd: "python /home/user/workspace/packages/agent-workspace/skills/extract-invoice-data.py ..."
});
```

## Skills

### extract-pdf-images.py

Converts PDF files to PNG images (one per page).

**Usage:**
```bash
python skills/extract-pdf-images.py <pdf_path> <output_dir> [--dpi=300]
```

**Output:**
- `page_001.png`, `page_002.png`, etc.
- JSON with image metadata

### extract-invoice-data.py

Extracts and verifies invoice data using Claude Agent SDK with **structured outputs** and Pydantic validation.

**Features:**
- Type-safe extraction using Pydantic models
- Automatic JSON Schema validation
- Within-document verification (line items, HST, totals)
- Session management for human-in-the-loop workflows

**Usage:**
```bash
python skills/extract-invoice-data.py image1.png image2.png --output-dir=/home/user/output
```

**Output:**
- `invoice_data.json`: Extracted invoice data (validated against schema)
- `verification_report.json`: Verification results (passed/failed checks)
- `session_id.txt`: Agent session ID for resumption

**Structured Output Schema:**
```python
class InvoiceExtraction(BaseModel):
    invoice: InvoiceData      # All extracted fields
    verification: VerificationReport  # Validation check results
```

The agent returns validated, type-safe data that matches the Pydantic schema. If validation fails, the skill returns an error with details about what went wrong.

## Dependencies

Install with:
```bash
pip install -r requirements.txt
```

System dependencies (for PDF processing):
```bash
apt-get install poppler-utils
```

## Development

Add new skills to `skills/` directory with:
1. Executable Python script (`#!/usr/bin/env python3`)
2. Docstring with usage instructions
3. JSON output for easy parsing
4. Command-line argument support

Add prompts to `prompts/` directory as text files.
