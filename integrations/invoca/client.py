"""
Invoca API integration.

Hierarchy: Network -> Profile (per instance) -> Campaign (per clinic)
"""


def create_profile(network_id: str, profile_name: str) -> str:
    """
    Create an Invoca profile for a new instance.

    Args:
        network_id: Your Invoca network ID
        profile_name: Name for the profile (typically instance_name)

    Returns:
        invoca_profile_id: The created profile's ID
    """
    # TODO: Implement Invoca API call
    # POST to Invoca API to create profile
    raise NotImplementedError("Invoca create_profile not implemented")


def create_campaign(profile_id: str, campaign_name: str, destination_number: str) -> str:
    """
    Create an Invoca campaign for a clinic under an instance's profile.

    Args:
        profile_id: The instance's Invoca profile ID
        campaign_name: Name for the campaign (typically clinic_name)
        destination_number: The clinic's transfer/destination phone number

    Returns:
        invoca_campaign_id: The created campaign's ID
    """
    # TODO: Implement Invoca API call
    # POST to Invoca API to create campaign under profile
    raise NotImplementedError("Invoca create_campaign not implemented")


def delete_profile(profile_id: str) -> bool:
    """Delete an Invoca profile and its campaigns."""
    # TODO: Implement for cleanup/rollback
    raise NotImplementedError("Invoca delete_profile not implemented")


def delete_campaign(campaign_id: str) -> bool:
    """Delete an Invoca campaign."""
    # TODO: Implement for cleanup/rollback
    raise NotImplementedError("Invoca delete_campaign not implemented")
