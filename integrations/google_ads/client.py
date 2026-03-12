"""
Google Ads API integration.

Hierarchy: Customer (account) -> Campaign (per instance) -> Ad Group (per clinic)
"""


def create_customer(customer_name: str) -> str:
    """
    Create a new Google Ads customer account for an instance.

    Args:
        customer_name: Name for the account (typically instance_name)

    Returns:
        google_ads_customer_id: The created customer/account ID
    """
    # TODO: Implement Google Ads API call
    # Uses CustomerService to create a new customer under your MCC
    raise NotImplementedError("Google Ads create_customer not implemented")


def create_campaign(customer_id: str, campaign_name: str) -> str:
    """
    Create a Google Ads campaign for an instance.

    Args:
        customer_id: The instance's Google Ads customer ID
        campaign_name: Name for the campaign (typically instance_name)

    Returns:
        google_ads_campaign_id: The created campaign's ID
    """
    # TODO: Implement Google Ads API call
    # Uses CampaignService to create campaign
    raise NotImplementedError("Google Ads create_campaign not implemented")


def create_ad_group(customer_id: str, campaign_id: str, ad_group_name: str) -> str:
    """
    Create a Google Ads ad group for a clinic.

    Args:
        customer_id: The instance's Google Ads customer ID
        campaign_id: The instance's campaign ID
        ad_group_name: Name for the ad group (typically clinic_name)

    Returns:
        google_ads_ad_group_id: The created ad group's ID
    """
    # TODO: Implement Google Ads API call
    # Uses AdGroupService to create ad group under campaign
    raise NotImplementedError("Google Ads create_ad_group not implemented")


def delete_customer(customer_id: str) -> bool:
    """Delete/cancel a Google Ads customer account."""
    # TODO: Implement for cleanup/rollback
    # Note: Google Ads accounts can't be deleted, only cancelled
    raise NotImplementedError("Google Ads delete_customer not implemented")


def delete_campaign(customer_id: str, campaign_id: str) -> bool:
    """Delete a Google Ads campaign."""
    # TODO: Implement for cleanup/rollback
    raise NotImplementedError("Google Ads delete_campaign not implemented")


def delete_ad_group(customer_id: str, ad_group_id: str) -> bool:
    """Delete a Google Ads ad group."""
    # TODO: Implement for cleanup/rollback
    raise NotImplementedError("Google Ads delete_ad_group not implemented")
