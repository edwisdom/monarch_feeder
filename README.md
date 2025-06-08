# Monarch Feeder

## Background

When I started a new job, none of my new financial accounts natively synced to Monarch Money. So 
I decided to build the integrations myself.

Monarch Feeder is an automated financial data synchronization tool that extracts transaction and portfolio data from various financial accounts (Human Interest 401k, Rippling HSA/Commuter Benefits) and syncs it to Monarch Money using AI-powered browser automation.

## 🎯 What It Does

This tool automates the tedious process of manually importing financial data from accounts that don't have direct API access or integrations with personal finance tools. It uses computer vision and AI to:

1. **Extract Data**: Automatically log into your financial accounts and scrapes transaction/portfolio data
2. **Process Data**: Convert extracted data into structured JSON format
3. **Sync to Monarch**: Upload the data to your Monarch Money account with proper categorization

### Supported Platforms

- **Human Interest** (401k): Transactions and portfolio holdings
- **Rippling HSA**: HSA transactions, portfolio holdings, and commuter benefits
- **Monarch Money**: Target platform for data synchronization

## 🚀 Quick Start

### Prerequisites

- Docker (for automated browser interactions, download [here](https://www.docker.com/))
- uv (Python package manager, download [here](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer))

### 1. Clone and Setup

```bash
git clone <repository-url>
cd monarch_feeder
```

### 2. Install Dependencies

Using uv:
```bash
uv sync
```

### 3. Environment Configuration

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your actual credentials (see [Environment Variables](#environment-variables) section for details).

### 4. Setup MFA (Multi-Factor Authentication)

For accounts that require MFA, you'll need to get your QR codes. This repository then handles
extracting the secret embedded in those QR codes.

1. Save MFA QR codes as images in the `.auth/` directory:
   - `monarch_mfa_auth_qr.png` - Monarch Money MFA QR code (export from Google Authenticator)
   - `rippling_mfa_auth_qr.png` - Rippling MFA QR code (from Twilio Authy)
       - They won't let you export, but you can go to Rippling for a new one and screenshot it.

2. Run this to automatically update your `.env` file with the extracted MFA secrets:
```bash
python -m monarch_feeder.scripts.save_totp_secret
```

### 5. Get Monarch Account and Category IDs

Make sure that you've made Monarch manual accounts (e.g. for Human Interest, Rippling, etc.) using their UI. 
Then, run this script to create two files:

1. `monarch_accounts.json`: All your Monarch accounts -- look for the ID field for the relevant accounts.
2. `monarch_categories.json`: All your Monarch transaction categories -- look for the IDs for categories you want to default to.

```bash
python -m monarch_feeder.scripts.get_monarch_accounts
```

Find the relevant account IDs and category IDs and update your `.env` file.

### 6. Run the Complete Workflow

```bash
# Build, run all automations, and sync to Monarch
inv build-run-and-sync

# Or run individual steps:
inv build                    # Build Docker container
inv run --automations human_interest,rippling  # Run automations
inv sync-data               # Sync to Monarch
```

## 📋 Environment Variables

Your `.env` file needs the following variables to be changed from the example file:

### Monarch Money Configuration
```bash
MONARCH_EMAIL=your_email@example.com
MONARCH_PASSWORD=yourpassword

# Account IDs (get these from the generated monarch_accounts.json)
MONARCH_HUMAN_INTEREST_ACCOUNT_ID="123456789012345678"
MONARCH_ELEVATE_UMB_ACCOUNT_ID="123456789012345678"
MONARCH_RIPPLING_COMMUTER_ACCOUNT_ID="123456789012345678"

# Category IDs for transaction categorization (from monarch_categories.json)
MONARCH_HUMAN_INTEREST_CATEGORY_ID="123456789012345678"
MONARCH_ELEVATE_UMB_CATEGORY_ID="123456789012345678"
MONARCH_RIPPLING_COMMUTER_CATEGORY_ID="123456789012345678"
```

### Human Interest (401k) Configuration
```bash
HUMAN_INTEREST_EMAIL=your_email@example.com
HUMAN_INTEREST_PASSWORD=yourpassword
```

### Rippling Configuration
```bash
RIPPLING_EMAIL=your_email@example.com
RIPPLING_PASSWORD=yourpassword
```

### AI Configuration
```bash
ANTHROPIC_API_KEY=sk-ant-putyourkeyhere  # For Claude AI automation
```

### Other
```bash
EMPLOYER_NAME=your_employer_name # For prompting and account naming
```

## 🛠️ Available Commands

The project uses [Invoke](https://pyinvoke.org/) for task management.

### Core Automation Commands

```bash
# Build the Docker automation container
inv build

# List available automations
inv list-automations

# Run specific automations
inv run --automations human_interest
inv run --automations rippling
inv run --automations human_interest,rippling

# Sync extracted data to Monarch Money
inv sync-data
inv sync-data --dry-run  # Preview what would be synced

# Complete workflow (build + run + sync)
inv build-run-and-sync
```

### Debugging Utilities

```bash
# Test TOTP generation after extracting secret from your QR code
python -m monarch_feeder.scripts.test_otp
```

## 📁 Output Structure

Automation outputs are saved in structured directories:

```
automation_outputs/
├── human_interest/
│   ├── transactions/
│   │   └── human_interest_transactions_{yyyymmdd}_{hhmmss}.json
│   └── portfolio/
│       └── human_interest_portfolio_{yyyymmdd}_{hhmmss}.json
└── rippling/
    ├── hsa_transactions/
    │   └── rippling_hsa_transactions_{yyyymmdd}_{hhmmss}.json
    ├── hsa_portfolio/
    │   └── rippling_hsa_portfolio_{yyyymmdd}_{hhmmss}.json
    └── commuter_benefits/
        └── rippling_commuter_benefits_{yyyymmdd}_{hhmmss}.json

automation_logs/
├── automation_human_interest_{yyyymmdd}_{hhmmss}.log
├── automation_rippling_{yyyymmdd}_{hhmmss}.log
└── automation_human_interest-rippling_{yyyymmdd}_{hhmmss}.log
```

## 🔧 How It Works

### 1. Browser Automation
The system uses Docker containers with desktop environments to run automated browsers. Claude AI analyzes screenshots and performs actions like:
- Navigating web pages
- Logging into accounts
- Extracting transaction data
- Downloading portfolio information

### 2. Data Processing
Extracted data is structured into JSON format with standardized schemas for:
- **Transactions**: Date, amount, description, counterparty
- **Portfolio Holdings**: Stock ticker, shares, market value

### 3. Monarch Integration
Using the `monarchmoney` Python library, the system:
- Authenticates with your Monarch account
- Creates new transactions with proper categorization
- Updates portfolio holdings for investment accounts

## 🔐 Security Considerations

- **Credentials**: Store all sensitive credentials in `.env` file (never commit to version control)
- **MFA Secrets**: TOTP secrets are extracted locally and stored securely
- **Data Storage**: Financial data is stored locally in JSON format
- **Network**: Automation runs in isolated Docker containers

**IMPORTANT**: You are letting an LLM interact with your financial accounts, which has some inherent risk.

## 🐛 Troubleshooting

### Common Issues

1. **MFA Problems**: 
   - Ensure QR codes are clear and properly saved in `.auth/` directory
   - Test TOTP generation: `python -m monarch_feeder.scripts.test_otp`

2. **Docker Issues**:
   - Ensure Docker is running and you have permissions
   - Clean containers: `inv clean`

3. **Account ID Issues**:
   - Re-run: `python -m monarch_feeder.scripts.get_monarch_accounts`
   - Verify account IDs in your `.env` file match the JSON output

### Logs and Debugging

- Automation logs: Check Docker container output
- Data validation: Use `--dry-run` flag to preview changes before syncing

## 🤝 Contributing

This is a personal automation tool, but improvements are welcome:

1. Fork the repository
2. Create a feature branch
3. Test your changes thoroughly
4. Submit a pull request

## ⚠️ Disclaimer

This tool automates interactions with financial websites. Use at your own risk and ensure compliance with the terms of service of all platforms involved. Always verify data accuracy before making financial decisions.

