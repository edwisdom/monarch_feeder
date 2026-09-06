# Monarch Feeder

## Background

When I started a new job, none of my new financial accounts natively synced to Monarch Money. So 
I decided to build the integrations myself.

Monarch Feeder is an automated financial data synchronization tool that extracts transaction and portfolio data from various financial accounts (Human Interest 401k, Rippling HSA/Commuter Benefits, HSA Bank HSA) and syncs it to Monarch Money.

## 🎯 What It Does

This tool automates the tedious process of manually importing financial data from accounts that don't have direct API access or integrations with personal finance tools.

1. **Extract Data**: Automatically log into your financial accounts and scrapes transaction/portfolio data
2. **Process Data**: Convert extracted data into a structured format
3. **Sync to Monarch**: Upload the data to your Monarch Money account with proper categorization

### Supported Platforms

- **Human Interest** (401k): Transactions and portfolio holdings
- **Rippling HSA**: HSA transactions, portfolio holdings, and commuter benefits
- **HSA Bank** (HSA): Cash transactions, investment holdings, and uninvested cash
- **Monarch Money**: Target platform for data synchronization

## 🚀 Quick Start

### Prerequisites

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

**HSA Bank is different.** It only offers email, text, or phone-call second
factors, so there's no secret to extract. Instead, HSA Bank syncs run in a
dedicated browser profile (`profiles/hsa_bank`) with a pinned user agent. The
first sync opens a browser and pauses while you enter the emailed code; Okta
then issues a long-lived device token that persists in that profile, so later
syncs sign in without a challenge. Don't delete `profiles/` unless you want to
go through the code again.

### 5. Get Monarch Account and Category IDs

Make sure that you've made Monarch manual accounts (e.g. for Human Interest, Rippling, etc.) using their UI. 
Then, run this script to create two files:

1. `monarch_accounts.json`: All your Monarch accounts -- look for the ID field for the relevant accounts.
2. `monarch_categories.json`: All your Monarch transaction categories -- look for the IDs for categories you want to default to.

```bash
python -m monarch_feeder.scripts.get_monarch_info
```

Find the relevant account IDs and category IDs and update your `.env` file.

### 6. Run the Complete Workflow

```bash
# Run all integrations and sync to Monarch
inv sync

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
MONARCH_HSA_BANK_ACCOUNT_ID="123456789012345678"

# Category IDs for transaction categorization (from monarch_categories.json)
MONARCH_HUMAN_INTEREST_CATEGORY_ID="123456789012345678"
MONARCH_ELEVATE_UMB_CATEGORY_ID="123456789012345678"
MONARCH_RIPPLING_COMMUTER_CATEGORY_ID="123456789012345678"
MONARCH_HSA_BANK_CATEGORY_ID="123456789012345678"
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

### HSA Bank Configuration
```bash
HSA_BANK_USERNAME=yourusername
HSA_BANK_PASSWORD=yourpassword
```

### Other
```bash
EMPLOYER_NAME=your_employer_name # For account naming
```

## 🛠️ Available Commands

The project uses [Invoke](https://pyinvoke.org/) for task management.

### Core Automation Commands

```bash
# List available integrations
inv list-integrations

# Run specific platform integrations
inv sync --platforms=human_interest
inv sync --platforms=rippling
inv sync --platforms=hsa_bank
inv sync --platforms=human_interest,rippling

# Preview what would be synced
inv sync --dry-run
```

### Debugging Utilities

```bash
# Test TOTP generation after extracting secret from your QR code
python -m monarch_feeder.scripts.test_otp
```

## 🔧 How It Works

### 1. Authentication via Browser Automation
The system uses [Botasaurus](https://github.com/omkarcloud/botasaurus) to automate real browsers for authentication:
- Navigates to login pages
- Fills in credentials and handles MFA/OTP codes
- Extracts session tokens and cookies from the authenticated browser session

### 2. Direct API Scraping
Once authenticated, the system makes direct HTTP requests to the platforms' internal APIs:
- **Human Interest**: GraphQL API calls to fetch transaction history and portfolio allocations
- **Rippling**: REST API calls to retrieve HSA activities, holdings, and commuter benefit transactions
- **HSA Bank**: REST API calls to `api.bendhsa.com` (HSA Bank's portal is a white-labelled Bend deployment) for cash transactions and DriveWealth investment holdings

HSA Bank holds a cash floor (currently $1,000, plus at least $1 more before it
will invest), so most of the account can sit uninvested. The portfolio stream
syncs that cash alongside the ETFs, as a `USD-USD` holding whose share count is
the dollar balance - the same way Monarch itself represents cash inside an
investment account. Without it the account would read ~$1,000 light.
- All data is returned as structured JSON from the platforms' production APIs

### 3. Data Processing
Raw API responses are parsed into standardized data models:
- **Transactions**: Date, amount, description, counterparty account
- **Portfolio Holdings**: Stock ticker symbol, number of shares

### 4. Monarch Integration
Using the [`monarchmoney`](https://github.com/hammem/monarchmoney) Python library, the system:
- Authenticates with your Monarch Money account by driving the web app's sign-in
  form in a browser and reusing its session cookies (see below)
- Compares scraped transactions against existing Monarch data to avoid duplicates
- Creates new transactions with proper categorization and account assignment
- Updates portfolio holdings for investment accounts

## 🔐 Security Considerations

- **Credentials**: Store all sensitive credentials in `.env` file (never commit to version control)
- **MFA Secrets**: TOTP secrets are extracted locally and stored securely

## 🐛 Troubleshooting

### Common Issues

1. **MFA Problems**: 
   - Ensure QR codes are clear and properly saved in `.auth/` directory
   - Test TOTP generation: `python -m monarch_feeder.scripts.test_otp`

2. **Account ID Issues**:
   - Re-run: `python -m monarch_feeder.scripts.get_monarch_info`
   - Verify account IDs in your `.env` file match the JSON output

3. **Monarch login**: Monarch no longer supports the library's plain
   email/password API login. That endpoint is reCAPTCHA-gated and throttles
   scripted logins, and it no longer returns a reusable bearer token. So
   `monarch_feeder/monarch.py` signs in through the web app in a browser and
   keeps the resulting session in `.mm/mm_session.json`. Calls made with that
   session need a few things the library doesn't send on its own, all handled in
   `client_for_session`:
   - the `session_id` and `csrftoken` cookies, plus `X-CSRFToken`
   - an `Origin`/`Referer` from the web app, or Django's CSRF check rejects it
   - a browser `User-Agent`, since Cloudflare blocks the library's default one
   - `api.monarch.com` directly, because the library's `api.monarchmoney.com`
     301s and the redirected POST loses its body
   - an `operationName` on every GraphQL request

4. **HSA Bank asks for a code every run**: something cleared the browser
   profile. Delete `profiles/hsa_bank`, run a sync, and enter the emailed code
   once more to re-establish the device token.

### Logs and Debugging

- Data validation: Use `--dry-run` flag to preview changes before syncing

## 🤝 Contributing

This is a personal automation tool, but improvements are welcome:

1. Fork the repository
2. Create a feature branch
3. Test your changes thoroughly
4. Submit a pull request

## ⚠️ Disclaimer

This tool automates interactions with financial websites. Use at your own risk and ensure compliance with the terms of service of all platforms involved. Always verify data accuracy before making financial decisions.

