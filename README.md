# OM Extractor

A Python-based tool for extracting structured information from real estate Offering Memorandums (OMs) using AWS Bedrock and Claude AI.

## Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure AWS Credentials
You need to set up AWS credentials with access to Bedrock. You can do this in several ways:

**Option A: AWS CLI Configuration**
```bash
aws configure
```

**Option B: Environment Variables**
Create a `.env` file in the project root:
```
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
```

**Option C: IAM Role (if running on EC2)**

### 3. Verify Bedrock Access
Make sure your AWS account has access to Amazon Bedrock and the Claude model.

## Usage

### Basic Usage
```python
from src.OMExtractor import OMExtractor

# Initialize the extractor
extractor = OMExtractor()

# Extract from a specific file
result = extractor.extract_from_file("your_om_file.pdf")

# Print results
print(result.tenant_name)
print(result.sales_price)
```

### Run the Test Script
```bash
python test_extractor.py
```

## Project Structure

```
RobbyGPT/
├── OM_Repo/              # Place your OM PDFs here
├── src/
│   ├── OMExtractor.py    # Main extraction class
│   └── models.py         # Data models
├── config/
│   └── config.py         # Configuration settings
├── tests/                # Test files
├── requirements.txt       # Python dependencies
├── test_extractor.py     # Test script
└── README.md            # This file
```

## Features

- ✅ PDF text extraction
- ✅ Claude AI integration via AWS Bedrock
- ✅ Chunking for large documents
- ✅ Structured data extraction
- ✅ JSON output with validation
- ✅ Error handling and logging
- ✅ Configurable settings

## Extracted Information

The tool extracts exactly 19 specific fields from OMs using a hybrid categorized approach:

### Group 1: Property & Location (5 fields)
- **Tenant Name** - Name of the tenant/lessee
- **Property Address** - Full property address
- **City** - City where property is located
- **State** - State where property is located
- **Submarket Name** - Submarket or area name

### Group 2: Financial Details (6 fields)
- **Sales Price** - Property sale price (decimal number)
- **Annual Rent** - Annual rental amount (decimal number)
- **Lease Type** - Type of lease (e.g., NNN, Gross, Modified Gross)
- **Increases** - Rent increase description (text)
- **Numerical Rent Increase** - Rent increase percentage (decimal number)
- **Frequency of Rent Increase** - Years between increases (decimal number)

### Group 3: Physical Property (4 fields)
- **Year Built/Renovated** - Year building was built or renovated (decimal number)
- **Building SF** - Building square footage (decimal number)
- **Land (Acres)** - Land size in acres (decimal number)
- **Landlord Expense Responsibilities** - What expenses landlord is responsible for

### Group 4: Lease Details (4 fields)
- **Sale Date** - Date of sale (ISO date format: YYYY-MM-DD)
- **Lease Expiration Date** - When lease expires (ISO date format: YYYY-MM-DD)
- **Guarantor (Operator)** - Guarantor or operator name
- **Rent Commencement Date** - When rent payments begin (ISO date format: YYYY-MM-DD)

## Data Formatting

- **Numerical fields**: Returned as decimal numbers (no $, commas, or text)
- **Date fields**: Returned in ISO format (YYYY-MM-DD) for easy Python datetime parsing
- **Text fields**: Returned as clean strings

## Configuration

Edit `config/config.py` to modify:
- AWS region
- Claude model version
- Token limits
- Temperature settings
- Chunk sizes
- Parallel processing settings

### Parallel Processing

The system always uses parallel processing for maximum speed:
- **4 concurrent workers** process all groups simultaneously
- **Always enabled** for optimal performance
- **Configurable** via `MAX_WORKERS` environment variable

## Troubleshooting

1. **AWS Credentials Error**: Make sure your AWS credentials are properly configured
2. **Bedrock Access Error**: Verify your AWS account has Bedrock access
3. **PDF Reading Error**: Ensure the PDF is not password-protected or corrupted
4. **Token Limit Error**: Large PDFs are automatically chunked

## Next Steps

- Add support for Word documents
- Implement batch processing
- Add confidence scoring
- Create web interface
- Add database storage 