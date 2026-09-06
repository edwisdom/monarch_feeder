"""Platform integration configurations."""

import os

from monarch_feeder.integration_types import (
    DataStream,
    Integration,
    Platform,
    StreamType,
)
from monarch_feeder.platforms.human_interest import (
    HumanInterestData,
    get_human_interest_data,
)
from monarch_feeder.platforms.hsa_bank import HSABankData, get_hsa_bank_data
from monarch_feeder.platforms.rippling import RipplingData, get_rippling_data

EMPLOYER_NAME = os.getenv("EMPLOYER_NAME")

# Platform integrations mapping
INTEGRATIONS: dict[Platform, Integration] = {
    Platform.HUMAN_INTEREST: Integration[HumanInterestData](
        name="Human Interest",
        data_fetcher=lambda: get_human_interest_data(
            account_name=f"Human Interest - {EMPLOYER_NAME} 401k"
        ),
        data_streams=[
            DataStream(
                name="Human Interest Transactions",
                stream_type=StreamType.TRANSACTIONS,
                account_id=os.getenv("MONARCH_HUMAN_INTEREST_ACCOUNT_ID"),
                account_name=f"Human Interest - {EMPLOYER_NAME} 401k",
                extractor=lambda data: data.transactions,
                category_id=os.getenv("MONARCH_HUMAN_INTEREST_CATEGORY_ID"),
            ),
            DataStream(
                name="Human Interest Portfolio",
                stream_type=StreamType.PORTFOLIO,
                account_id=os.getenv("MONARCH_HUMAN_INTEREST_ACCOUNT_ID"),
                account_name=f"Human Interest - {EMPLOYER_NAME} 401k",
                extractor=lambda data: data.portfolio,
            ),
        ],
    ),
    Platform.RIPPLING: Integration[RipplingData](
        name="Rippling",
        data_fetcher=lambda: get_rippling_data(
            hsa_account_name=f"Rippling - {EMPLOYER_NAME} HSA",
            commuter_account_name=f"Rippling - {EMPLOYER_NAME} Commuter Benefits",
        ),
        data_streams=[
            DataStream(
                name="Rippling HSA Transactions",
                stream_type=StreamType.TRANSACTIONS,
                account_id=os.getenv("MONARCH_ELEVATE_UMB_ACCOUNT_ID"),
                account_name=f"Rippling - {EMPLOYER_NAME} HSA",
                extractor=lambda data: data.hsa_transactions,
                category_id=os.getenv("MONARCH_ELEVATE_UMB_CATEGORY_ID"),
            ),
            DataStream(
                name="Rippling HSA Portfolio",
                stream_type=StreamType.PORTFOLIO,
                account_id=os.getenv("MONARCH_ELEVATE_UMB_ACCOUNT_ID"),
                account_name=f"Rippling - {EMPLOYER_NAME} HSA",
                extractor=lambda data: data.hsa_portfolio,
            ),
            DataStream(
                name="Rippling Commuter Benefits",
                stream_type=StreamType.TRANSACTIONS,
                account_id=os.getenv("MONARCH_RIPPLING_COMMUTER_ACCOUNT_ID"),
                account_name=f"Rippling - {EMPLOYER_NAME} Commuter Benefits",
                extractor=lambda data: data.commuter_benefits_transactions,
                category_id=os.getenv("MONARCH_RIPPLING_COMMUTER_CATEGORY_ID"),
                update_balance=True,
            ),
        ],
    ),
    Platform.HSA_BANK: Integration[HSABankData](
        name="HSA Bank",
        data_fetcher=lambda: get_hsa_bank_data(
            account_name=f"HSA Bank - {EMPLOYER_NAME} HSA"
        ),
        data_streams=[
            DataStream(
                name="HSA Bank Transactions",
                stream_type=StreamType.TRANSACTIONS,
                account_id=os.getenv("MONARCH_HSA_BANK_ACCOUNT_ID"),
                account_name=f"HSA Bank - {EMPLOYER_NAME} HSA",
                extractor=lambda data: data.transactions,
                category_id=os.getenv("MONARCH_HSA_BANK_CATEGORY_ID"),
            ),
            DataStream(
                name="HSA Bank Portfolio",
                stream_type=StreamType.PORTFOLIO,
                account_id=os.getenv("MONARCH_HSA_BANK_ACCOUNT_ID"),
                account_name=f"HSA Bank - {EMPLOYER_NAME} HSA",
                extractor=lambda data: data.portfolio,
            ),
        ],
    ),
}
